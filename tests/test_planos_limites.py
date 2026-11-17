"""
Planos e limites decididos no servidor (docs/PLANO_SAAS.md, Fase S1).

Cobre:
1. Período mensal no horário de Brasília e data de renovação.
2. EntitlementsService: cota mensal por métrica, devolução, reserva preguiçosa,
   admin sem cota, troca de plano, máximo de questões e de upload.
3. Rotas: GET /api/me/plan; geração e variações de quem tem conta gastam a cota do plano,
   cache e falha da IA devolvem o uso, passar da cota dá PLAN_LIMIT_REACHED.
4. Migration: tabelas novas idempotentes e planos semeados sem sobrescrever ajustes.

Roda sem PostgreSQL: o repositório de planos fica só em memória e a IA é simulada.
"""

import json
import os
import threading
import unittest
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from urllib.parse import urlparse

from api.database import migrations
from api.exceptions.quiz_exceptions import PlanLimitReached, PlanQuestionLimit
from api.repositories.plan_repository import PlanRepository
from api.services.entitlements_service import EntitlementsService
from api.utils.plans import (
    DEFAULT_PLANS,
    HARD_MAX_QUESTIONS,
    METRIC_LIMIT_KEYS,
    current_period,
    effective_limits,
    period_renews_on,
)

STUDENT = {"id": 7, "username": "aluna", "email": "aluna@exemplo.com", "role": "student"}
ADMIN = {"id": 1, "username": "admin", "email": "admin@acely.com.br", "role": "admin"}


def _service(**plan_overrides):
    repo = PlanRepository(use_db=False)
    if plan_overrides:
        repo._plans["free"]["limits"].update(plan_overrides)
    return EntitlementsService(repo=repo)


class TestPeriods(unittest.TestCase):
    def test_period_uses_brasilia_time(self):
        # 02:00 UTC de 1º de dezembro ainda é 30 de novembro em Brasília
        self.assertEqual(current_period(datetime(2026, 12, 1, 2, 0, tzinfo=timezone.utc)), "2026-11")  # noqa: UP017
        self.assertEqual(current_period(datetime(2026, 12, 1, 3, 0, tzinfo=timezone.utc)), "2026-12")  # noqa: UP017

    def test_renewal_date(self):
        self.assertEqual(period_renews_on("2026-11"), date(2026, 12, 1))
        self.assertEqual(period_renews_on("2026-12"), date(2027, 1, 1))

    def test_effective_limits_fill_defaults_and_apply_hard_caps(self):
        limits = effective_limits({"max_questions": 50, "max_upload_mb": None, "chave_estranha": 1})
        self.assertEqual(limits["max_questions"], HARD_MAX_QUESTIONS)
        self.assertEqual(limits["max_upload_mb"], 20)
        self.assertNotIn("chave_estranha", limits)
        self.assertEqual(
            limits["ai_generations_per_month"], DEFAULT_PLANS["free"]["limits"]["ai_generations_per_month"]
        )

    def test_every_plan_defines_every_monthly_limit(self):
        for plan_id, plan in DEFAULT_PLANS.items():
            for key in METRIC_LIMIT_KEYS.values():
                with self.subTest(plan=plan_id, key=key):
                    self.assertIn(key, plan["limits"])


class TestEntitlementsService(unittest.TestCase):
    def test_new_account_starts_on_free_with_personal_workspace(self):
        status = _service().status(STUDENT)
        self.assertEqual(status["plan"]["id"], "free")
        self.assertEqual(status["workspace"]["kind"], "personal")
        self.assertEqual(status["usage"]["ai_generation"]["used"], 0)
        self.assertEqual(status["usage"]["ai_generation"]["limit"], 30)
        self.assertEqual(status["renews_on"], period_renews_on(status["period"]).isoformat())

    def test_monthly_quota_blocks_with_clear_message(self):
        service = _service(ai_generations_per_month=2)
        for _ in range(2):
            service.reservation(STUDENT, "ai_generation").acquire()
        with self.assertRaises(PlanLimitReached) as ctx:
            service.reservation(STUDENT, "ai_generation").acquire()
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertEqual(ctx.exception.error_code, "PLAN_LIMIT_REACHED")
        self.assertIn("1º de", ctx.exception.message)
        self.assertIn("gabarito continua liberado", ctx.exception.message)
        self.assertEqual(service.status(STUDENT)["usage"]["ai_generation"]["remaining"], 0)

    def test_metrics_are_counted_separately(self):
        service = _service(ai_generations_per_month=1, ai_remixes_per_month=1)
        service.reservation(STUDENT, "ai_generation").acquire()
        service.reservation(STUDENT, "ai_remix").acquire()  # não esbarra na cota de geração
        with self.assertRaises(PlanLimitReached):
            service.reservation(STUDENT, "ai_remix").acquire()

    def test_refund_and_lazy_reservation(self):
        service = _service()
        reservation = service.reservation(STUDENT, "ai_generation")
        self.assertFalse(reservation.acquired)
        self.assertEqual(service.status(STUDENT)["usage"]["ai_generation"]["used"], 0)
        reservation.acquire()
        reservation.acquire()  # idempotente
        self.assertEqual(service.status(STUDENT)["usage"]["ai_generation"]["used"], 1)
        reservation.refund()
        reservation.refund()  # segunda devolução não faz nada
        self.assertEqual(service.status(STUDENT)["usage"]["ai_generation"]["used"], 0)

    def test_quota_is_per_person(self):
        service = _service(ai_generations_per_month=1)
        service.reservation(STUDENT, "ai_generation").acquire()
        other = {**STUDENT, "id": 8}
        service.reservation(other, "ai_generation").acquire()

    def test_zero_limit_blocks_immediately(self):
        service = _service(ai_remixes_per_month=0)
        with self.assertRaises(PlanLimitReached):
            service.reservation(STUDENT, "ai_remix").acquire()

    def test_admin_has_no_quota(self):
        service = _service(ai_generations_per_month=0, max_questions=5)
        for _ in range(3):
            service.reservation(ADMIN, "ai_generation").acquire()
        service.check_questions(ADMIN, 30)
        status = service.status(ADMIN)
        self.assertTrue(status["unlimited"])
        self.assertIsNone(status["usage"]["ai_generation"]["limit"])

    def test_changing_plan_changes_limits(self):
        service = _service(ai_generations_per_month=1)
        service.reservation(STUDENT, "ai_generation").acquire()
        workspace_id = service.status(STUDENT)["workspace"]["id"]
        service.repo.set_workspace_plan(workspace_id, "pro")
        status = service.status(STUDENT)
        self.assertEqual(status["plan"]["id"], "pro")
        self.assertEqual(status["usage"]["ai_generation"]["remaining"], 299)
        service.reservation(STUDENT, "ai_generation").acquire()

    def test_unknown_plan_falls_back_to_free(self):
        service = _service()
        workspace_id = service.status(STUDENT)["workspace"]["id"]
        service.repo.set_workspace_plan(workspace_id, "plano-que-nao-existe")
        self.assertEqual(service.status(STUDENT)["plan"]["id"], "free")

    def test_question_limit(self):
        service = _service(max_questions=10)
        service.check_questions(STUDENT, 10)
        service.check_questions(STUDENT, "auto")
        service.check_questions(STUDENT, None)
        with self.assertRaises(PlanQuestionLimit) as ctx:
            service.check_questions(STUDENT, "15")
        self.assertEqual(ctx.exception.error_code, "PLAN_QUESTION_LIMIT")
        self.assertIn("até 10 questões", ctx.exception.message)

    def test_upload_limit_in_bytes(self):
        self.assertEqual(_service(max_upload_mb=5).max_upload_bytes(STUDENT), 5 * 1024 * 1024)
        self.assertEqual(_service(max_upload_mb=500).max_upload_bytes(STUDENT), 20 * 1024 * 1024)

    def test_unknown_metric_is_rejected(self):
        with self.assertRaises(ValueError):
            _service().reservation(STUDENT, "qualquer")


def _fake_generated_quiz(**_kwargs):
    return {
        "title": "Juros compostos",
        "questions": [
            {
                "id": 1,
                "section": "Geral",
                "question": "Quanto é 2+2?",
                "options": ["3", "4"],
                "answer": 1,
                "context": "",
                "explanation": "Soma simples.",
            }
        ],
        "usage": {},
        "model": "fake",
        "provider": "fake",
    }


class TestPlanRoutes(unittest.TestCase):
    """Handler real em processo, sem banco: a conta é simulada e o simulado não é salvo."""

    @classmethod
    def setUpClass(cls):
        import api.handlers.quiz_handler as qh

        cls.qh = qh
        cls.user = None
        cls.patches = [
            patch.object(qh, "_ensure_migrations", lambda: None),
            patch.object(qh.QuizHandler, "_get_current_user_or_none", lambda self: cls.user),
            patch.object(qh.QuizHandler, "_require_authenticated_user", lambda self: cls._require()),
        ]
        for p in cls.patches:
            p.start()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), qh.QuizHandler)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def _require(cls):
        from api.exceptions.quiz_exceptions import QuizAPIException

        if not cls.user:
            raise QuizAPIException("Autenticação necessária", 401)
        return cls.user

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        for p in cls.patches:
            p.stop()

    def setUp(self):
        type(self).user = dict(STUDENT)
        self.service = _service(ai_generations_per_month=2, ai_remixes_per_month=1, max_questions=10)
        self.svc_patch = patch.object(self.qh, "entitlements_service", self.service)
        self.svc_patch.start()
        # Simulado de quem tem conta não vai para o banco neste teste
        self.persist_patch = patch.object(
            self.qh.QuizController, "generate_quiz_by_topic", self._fake_controller_generate
        )
        self.persist_patch.start()
        self.limiters = (self.qh._rl_generate, self.qh._rl_remix, self.qh._rl_read)
        self.saved_repos = [limiter.repo for limiter in self.limiters]
        for limiter in self.limiters:
            limiter._requests.clear()
            limiter.repo = None
        self.cached = False

    def tearDown(self):
        self.svc_patch.stop()
        self.persist_patch.stop()
        for limiter, repo in zip(self.limiters, self.saved_repos, strict=True):
            limiter.repo = repo

    def _fake_controller_generate(self_controller, **kwargs):
        from api.services import ai_service

        generated = ai_service.generate_quiz_by_topic(**{k: kwargs[k] for k in ("topic", "num_questions")})
        test = TestPlanRoutes._current
        return {
            "status": "success",
            "data": {
                "quiz_id": 1,
                "label": generated["title"],
                "cached": test.cached,
                "questions": generated["questions"],
                "message": "ok",
            },
        }

    def run(self, result=None):
        TestPlanRoutes._current = self
        return super().run(result)

    def _request(self, path, method="GET", data=None):
        body = json.dumps(data).encode("utf-8") if data is not None else None
        headers = {"Content-Type": "application/json"} if data is not None else {}
        req = urllib.request.Request(self.base + path, data=body, headers=headers, method=method)  # noqa: S310
        try:
            with urllib.request.urlopen(req) as resp:  # noqa: S310
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8"))

    def test_me_plan_requires_account(self):
        type(self).user = None
        status, _ = self._request("/api/me/plan")
        self.assertEqual(status, 401)

    def test_me_plan_returns_plan_and_usage(self):
        status, body = self._request("/api/me/plan")
        self.assertEqual(status, 200)
        data = body["data"]
        self.assertEqual(data["plan"]["id"], "free")
        self.assertEqual(data["usage"]["ai_generation"], {"used": 0, "limit": 2, "remaining": 2})
        self.assertEqual(data["limits"]["max_questions"], 10)

    @patch("api.services.ai_service.generate_quiz_by_topic", side_effect=_fake_generated_quiz)
    def test_account_generation_uses_plan_quota_until_limit(self, _mock_ai):
        for expected_remaining in (1, 0):
            status, body = self._request("/api/quiz/generate", "POST", {"topic": "Juros", "num_questions": 5})
            self.assertEqual(status, 201)
            self.assertEqual(body["data"]["plan"]["usage"]["ai_generation"]["remaining"], expected_remaining)
        status, body = self._request("/api/quiz/generate", "POST", {"topic": "Juros", "num_questions": 5})
        self.assertEqual(status, 403)
        self.assertEqual(body["error"], "PLAN_LIMIT_REACHED")

    @patch("api.services.ai_service.generate_quiz_by_topic", side_effect=_fake_generated_quiz)
    def test_cached_result_gives_the_use_back(self, _mock_ai):
        self.cached = True
        status, body = self._request("/api/quiz/generate", "POST", {"topic": "Juros", "num_questions": 5})
        self.assertEqual(status, 201)
        self.assertEqual(body["data"]["plan"]["usage"]["ai_generation"]["used"], 0)

    def test_ai_failure_gives_the_use_back(self):
        from api.services.ai_service import AIServiceError

        with patch("api.services.ai_service.generate_quiz_by_topic", side_effect=AIServiceError("fora")):
            status, _ = self._request("/api/quiz/generate", "POST", {"topic": "Juros", "num_questions": 5})
        self.assertGreaterEqual(status, 400)
        _, body = self._request("/api/me/plan")
        self.assertEqual(body["data"]["usage"]["ai_generation"]["used"], 0)

    def test_too_many_questions_is_rejected_before_calling_ai(self):
        with patch("api.services.ai_service.generate_quiz_by_topic") as mock_ai:
            status, body = self._request("/api/quiz/generate", "POST", {"topic": "Juros", "num_questions": 20})
        self.assertEqual(status, 400)
        self.assertEqual(body["error"], "PLAN_QUESTION_LIMIT")
        mock_ai.assert_not_called()
        _, body = self._request("/api/me/plan")
        self.assertEqual(body["data"]["usage"]["ai_generation"]["used"], 0)

    @patch(
        "api.services.ai_service.remix_questions_by_ai",
        return_value=[{"id": 1, "question": "Nova", "options": ["a", "b"], "answer": 0}],
    )
    def test_account_remix_uses_its_own_quota(self, _mock_remix):
        payload = {"questions": [{"question": "Quanto é 2+2?", "options": ["3", "4"], "answer": 1}]}
        status, body = self._request("/api/quiz/remix-mistakes", "POST", payload)
        self.assertEqual(status, 200)
        self.assertEqual(body["data"]["plan"]["usage"]["ai_remix"]["remaining"], 0)
        status, body = self._request("/api/quiz/remix-mistakes", "POST", payload)
        self.assertEqual(status, 403)
        self.assertEqual(body["error"], "PLAN_LIMIT_REACHED")


class TestPlanMigrations(unittest.TestCase):
    def test_new_tables_are_idempotent(self):
        sql = migrations.SCHEMA_SQL
        for table in ("plans", "workspaces", "workspace_members", "usage_counters"):
            with self.subTest(table=table):
                self.assertIn(f"CREATE TABLE IF NOT EXISTS {table} (", sql)
        self.assertIn("CREATE UNIQUE INDEX IF NOT EXISTS uq_workspaces_personal_owner", sql)
        self.assertNotRegex(sql.upper(), r"\bDROP\b|\bTRUNCATE\b")

    def test_seed_keeps_manual_changes(self):
        self.assertIn("ON CONFLICT (id) DO NOTHING", migrations.PLANS_SEED_SQL)
        self.assertIn("ON CONFLICT DO NOTHING", migrations.PERSONAL_WORKSPACES_SQL)

    def test_run_migrations_seeds_every_plan(self):
        executed = []

        class FakeCursor:
            def execute(self, sql, params=None):
                executed.append((sql, params))

        class FakeCtx:
            def __enter__(self):
                return FakeCursor()

            def __exit__(self, *exc):
                return False

        with (
            patch.object(migrations, "get_direct_cursor", lambda: FakeCtx()),
            patch("api.services.auth_service.AuthService.seed_admin_if_needed", lambda self: None),
        ):
            migrations.run_migrations()
        seeded = {params[0]: json.loads(params[2]) for sql, params in executed if sql == migrations.PLANS_SEED_SQL}
        self.assertEqual(set(seeded), set(DEFAULT_PLANS))
        self.assertEqual(seeded["free"], DEFAULT_PLANS["free"]["limits"])
        self.assertEqual(executed[-1][0], migrations.PERSONAL_WORKSPACES_SQL)


def _local_db_enabled() -> bool:
    from api.utils.config import DATABASE_URL

    host = urlparse(DATABASE_URL or "").hostname or ""
    return os.getenv("QUIZ_DB_INTEGRATION") == "1" and host in ("localhost", "127.0.0.1")


@unittest.skipUnless(_local_db_enabled(), "QUIZ_DB_INTEGRATION=1 com banco local não configurado")
class TestPlanRepositoryIntegration(unittest.TestCase):
    """Contra PostgreSQL real: UPSERT atômico, cascata ao excluir a conta e exportação."""

    @classmethod
    def setUpClass(cls):
        migrations.run_migrations()
        migrations.run_migrations()  # idempotente

    def setUp(self):
        from api.database.connection import get_cursor

        with get_cursor() as cur:
            cur.execute("DELETE FROM users WHERE username LIKE 'plano_%%'")
            cur.execute(
                "INSERT INTO users (username, email, password_hash, salt) VALUES (%s, %s, 'x', 'y') RETURNING id",
                ("plano_teste", "plano_teste@exemplo.com"),
            )
            self.user_id = cur.fetchone()["id"]
        self.repo = PlanRepository()
        self.user = {"id": self.user_id, "role": "student"}

    def tearDown(self):
        from api.database.connection import get_cursor

        with get_cursor() as cur:
            cur.execute("DELETE FROM users WHERE username LIKE 'plano_%%'")

    def test_personal_workspace_is_created_once(self):
        first = self.repo.get_personal_workspace(self.user_id)
        second = self.repo.get_personal_workspace(self.user_id)
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(first["plan_id"], "free")

    def test_concurrent_consumption_never_passes_the_limit(self):
        workspace_id = self.repo.get_personal_workspace(self.user_id)["id"]
        results = []
        lock = threading.Lock()

        def consume():
            ok = PlanRepository().try_consume(workspace_id, self.user_id, "ai_generation", "2026-11", 5)
            with lock:
                results.append(ok)

        threads = [threading.Thread(target=consume) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(results.count(True), 5)
        self.assertEqual(self.repo.get_usage(workspace_id, self.user_id, "2026-11"), {"ai_generation": 5})
        self.repo.release(workspace_id, self.user_id, "ai_generation", "2026-11")
        self.assertEqual(self.repo.get_usage(workspace_id, self.user_id, "2026-11"), {"ai_generation": 4})

    def test_plan_change_and_service_status(self):
        service = EntitlementsService(repo=self.repo)
        service.reservation(self.user, "ai_generation").acquire()
        workspace_id = service.status(self.user)["workspace"]["id"]
        self.repo.set_workspace_plan(workspace_id, "pro")
        status = service.status(self.user)
        self.assertEqual(status["plan"]["id"], "pro")
        self.assertEqual(status["usage"]["ai_generation"]["remaining"], 299)

    def test_export_and_account_deletion_cascade(self):
        from api.database.connection import get_cursor
        from api.repositories.user_repository import UserRepository

        EntitlementsService(repo=self.repo).reservation(self.user, "ai_remix").acquire()
        exported = self.repo.export_for_user(self.user_id)
        self.assertEqual(exported["workspaces"][0]["role"], "owner")
        self.assertEqual(exported["usage"][0]["metric"], "ai_remix")

        UserRepository().delete_user_and_data(self.user_id)
        with get_cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM workspaces WHERE owner_user_id = %s", (self.user_id,))
            self.assertEqual(cur.fetchone()["n"], 0)
            cur.execute("SELECT COUNT(*) AS n FROM usage_counters WHERE user_id = %s", (self.user_id,))
            self.assertEqual(cur.fetchone()["n"], 0)


if __name__ == "__main__":
    unittest.main()
