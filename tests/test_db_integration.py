"""
Testes de integração contra PostgreSQL real.

Rodam apenas com QUIZ_DB_INTEGRATION=1 e DATABASE_URL apontando para
localhost/127.0.0.1 (CI ou banco descartável): os testes apagam dados.
Valida:
1. Migrations idempotentes (rodar duas vezes não falha).
2. Rate limit persistente em uma ida ao banco: permite até o limite, bloqueia
   depois, e o bloqueio vale para outra instância (memória vazia, ex: serverless).
3. Limpeza global de registros antigos de rate limit.
4. find_with_questions respeita visibilidade (público/privado/dono).
5. scripts/reset_database.py: simulação não apaga; 'all' preserva o admin.
6. Seed do admin não regrava a senha quando já está sincronizada.
"""
import os
import time
import unittest
from unittest.mock import patch
from urllib.parse import urlparse

from api.utils.config import DATABASE_URL, ADMIN_USERNAME


def _local_db_enabled() -> bool:
    if os.getenv("QUIZ_DB_INTEGRATION") != "1":
        return False
    host = urlparse(DATABASE_URL or "").hostname or ""
    return host in ("localhost", "127.0.0.1")


@unittest.skipUnless(_local_db_enabled(), "QUIZ_DB_INTEGRATION=1 com banco local não configurado")
class TestDatabaseIntegration(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from api.database.migrations import run_migrations
        run_migrations()
        run_migrations()  # idempotente

    def setUp(self):
        from scripts.reset_database import run
        run("all", dry_run=False)

    # ─── Rate limit ──────────────────────────────────────────────────────────

    def _db_rows(self, key):
        from api.database.connection import get_cursor
        with get_cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM rate_limits WHERE key = %s", (key,))
            return int(cur.fetchone()["n"])

    def test_rate_limit_allows_until_limit_then_blocks(self):
        from api.repositories.rate_limit_repository import RateLimitRepository
        repo = RateLimitRepository()
        key = "it:limit"
        results = [repo.check_and_record(key, limit=3, window_seconds=60) for _ in range(4)]
        self.assertEqual([r[0] for r in results], [True, True, True, False])
        self.assertGreaterEqual(results[-1][1], 1)
        self.assertEqual(self._db_rows(key), 3)

    def test_rate_limit_is_shared_across_instances_via_db(self):
        from api.repositories.rate_limit_repository import RateLimitRepository
        key = "it:shared"
        first = RateLimitRepository()
        for _ in range(2):
            self.assertTrue(first.check_and_record(key, limit=2, window_seconds=60)[0])
        other = RateLimitRepository()  # memória vazia, como outra função serverless
        allowed, retry_after = other.check_and_record(key, limit=2, window_seconds=60)
        self.assertFalse(allowed)
        self.assertGreaterEqual(retry_after, 1)
        self.assertEqual(self._db_rows(key), 2)

    def test_rate_limit_cleanup_removes_rows_older_than_retention(self):
        from api.database.connection import get_cursor
        from api.repositories import rate_limit_repository as rl
        with get_cursor() as cur:
            cur.execute(
                "INSERT INTO rate_limits (key, timestamp, tokens) VALUES (%s, %s, 1)",
                ("it:stale-ip", time.time() - rl._RETENTION_SECONDS - 60),
            )
        with patch.object(rl, "_CLEANUP_PROBABILITY", 1.0):
            rl.RateLimitRepository().check_and_record("it:fresh", limit=5, window_seconds=60)
        self.assertEqual(self._db_rows("it:stale-ip"), 0)
        self.assertEqual(self._db_rows("it:fresh"), 1)

    # ─── Carregamento de quiz ────────────────────────────────────────────────

    def _make_user(self, username):
        from api.repositories.user_repository import UserRepository
        return UserRepository().create_user(username, f"{username}@quiz.study", "h", "s")

    def test_find_with_questions_respects_visibility(self):
        from api.repositories.quiz_repository import QuizRepository
        from api.exceptions.quiz_exceptions import QuizNotFound
        repo = QuizRepository()
        owner = self._make_user("it_owner")
        questions = [
            {"question_number": 2, "question": "Q2?", "options": ["a", "b"], "answer": 1},
            {"question_number": 1, "question": "Q1?", "options": ["a", "b"], "answer": 0},
        ]
        repo.save_quiz("it-public", "Público", questions, is_public=True)
        repo.save_quiz("it-private", "Privado", questions, created_by=owner["id"], is_public=False)

        quiz, qs = repo.find_with_questions("it-public")
        self.assertEqual(quiz["name"], "it-public")
        self.assertEqual([q["question_number"] for q in qs], [1, 2])
        self.assertEqual(qs[0]["options"], ["a", "b"])

        with self.assertRaises(QuizNotFound):
            repo.find_with_questions("it-private")
        quiz, _ = repo.find_with_questions("it-private", owner["id"])
        self.assertEqual(quiz["name"], "it-private")

        default_quiz, _ = repo.find_with_questions(None)
        self.assertEqual(default_quiz["name"], "it-public")

    # ─── Limpeza do banco ────────────────────────────────────────────────────

    def test_reset_dry_run_counts_without_deleting(self):
        from api.repositories.quiz_repository import QuizRepository
        from scripts.reset_database import run
        QuizRepository().save_quiz("it-dry", "Dry", [{"question": "Q?", "options": ["a"], "answer": 0}])

        counts = run("content", dry_run=True)
        self.assertEqual(counts["quizzes"], 1)
        self.assertEqual(counts["questions"], 1)
        self.assertEqual(run("content", dry_run=True)["quizzes"], 1)

    def test_reset_all_keeps_admin_and_removes_other_users(self):
        from api.repositories.user_repository import UserRepository
        from scripts.reset_database import run
        users = UserRepository()
        self._make_user("it_student")
        self.assertIsNotNone(users.find_by_username(ADMIN_USERNAME))

        deleted = run("all", dry_run=False)
        self.assertEqual(deleted["users (exceto admin)"], 1)
        self.assertIsNone(users.find_by_username("it_student"))
        self.assertIsNotNone(users.find_by_username(ADMIN_USERNAME))

    # ─── Seed do admin ───────────────────────────────────────────────────────

    def test_seed_admin_does_not_rewrite_synced_password(self):
        from api.repositories.user_repository import UserRepository
        from api.services.auth_service import AuthService
        before = UserRepository().find_by_username(ADMIN_USERNAME)
        AuthService().seed_admin_if_needed()
        after = UserRepository().find_by_username(ADMIN_USERNAME)
        self.assertEqual(before["salt"], after["salt"])
        self.assertEqual(before["password_hash"], after["password_hash"])


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(_local_db_enabled(), "QUIZ_DB_INTEGRATION=1 com banco local não configurado")
class TestAIJobsIntegration(unittest.TestCase):
    """ai_jobs e ai_cache no PostgreSQL de verdade (docs/PLANO_ACELY.md, Fase 1)."""

    @classmethod
    def setUpClass(cls):
        from api.database.migrations import run_migrations
        run_migrations()

    def setUp(self):
        from api.database.connection import get_cursor
        from api.repositories.ai_job_repository import AIJobRepository
        with get_cursor() as cur:
            cur.execute("DELETE FROM ai_jobs")
            cur.execute("DELETE FROM ai_cache")
        self.repo = AIJobRepository()

    def _id(self):
        import uuid
        return str(uuid.uuid4())

    def test_job_lifecycle_survives_another_instance(self):
        from api.repositories.ai_job_repository import AIJobRepository
        job_id = self._id()
        created, _ = self.repo.start(job_id, "guest", "g1", "generate", "h")
        self.assertTrue(created)
        other = AIJobRepository()  # outra instância (memória vazia)
        created, job = other.start(job_id, "guest", "g1", "generate", "h")
        self.assertFalse(created)
        self.assertEqual(job["status"], "running")
        self.repo.finish(job_id, {"http_status": 201, "data": {"name": "quiz-x"}})
        job = other.get(job_id)
        self.assertEqual(job["status"], "done")
        self.assertEqual(job["result"]["data"]["name"], "quiz-x")
        self.assertEqual(other._jobs, {})  # veio do banco, não da memória

    def test_conflict_failed_restart_and_abandoned(self):
        from api.database.connection import get_cursor
        from api.repositories.ai_job_repository import JobConflict
        job_id = self._id()
        self.repo.start(job_id, "user", "1", "generate", "h")
        with self.assertRaises(JobConflict):
            self.repo.start(job_id, "user", "2", "generate", "h")
        self.repo.fail(job_id, "fora", "QUIZ_ERROR", 422)
        created, _ = self.repo.start(job_id, "user", "1", "generate", "h")
        self.assertTrue(created)
        with get_cursor() as cur:
            cur.execute("UPDATE ai_jobs SET updated_at = NOW() - INTERVAL '7 minutes' WHERE id = %s", (job_id,))
        self.assertEqual(self.repo.get(job_id)["status"], "failed")
        created, _ = self.repo.start(job_id, "user", "1", "generate", "h")
        self.assertTrue(created)

    def test_parallel_starts_create_only_one(self):
        import threading
        job_id = self._id()
        results = []
        def start():
            results.append(self.repo.start(job_id, "guest", "g", "generate", "h")[0])
        threads = [threading.Thread(target=start) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(sorted(results), [False, False, False, False, True])

    def test_cache_roundtrip_and_expiry(self):
        from api.database.connection import get_cursor
        self.repo.cache_set("k1", {"questions": [{"q": "ç"}]})
        self.repo.cache_set("k1", {"questions": [{"q": "novo"}]})
        self.assertEqual(self.repo.cache_get("k1"), {"questions": [{"q": "novo"}]})
        with get_cursor() as cur:
            cur.execute("UPDATE ai_cache SET created_at = NOW() - INTERVAL '8 days'")
        self.assertIsNone(self.repo.cache_get("k1"))
