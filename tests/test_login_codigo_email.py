"""
Entrar com código de 6 dígitos enviado por e-mail.

Valida:
1. O código é gerado com 6 dígitos, guardado só como HMAC e enviado para o e-mail pedido.
2. Reenvio só depois de LOGIN_CODE_RESEND_SECONDS e no máximo LOGIN_CODE_MAX_PER_HOUR por hora.
3. O código certo cria a conta (e-mail confirmado) ou entra na existente; vale uma vez só.
4. Palpites errados contam e, no limite, o código morre (até o certo é recusado).
5. O código é ligado ao e-mail e à finalidade (login não exclui conta e vice-versa).
6. O admin não recebe código (mesma resposta de qualquer e-mail) nem entra por código.
7. Conta antiga sem e-mail confirmado: o código troca a senha por uma aleatória e derruba sessões.
8. Excluir a conta com o código do e-mail (403 com código errado, sem derrubar a sessão).
9. As rotas HTTP: cookie HttpOnly no sucesso, token fora do JSON, 429 com retry_after.
10. SQL real (só com QUIZ_DB_INTEGRATION=1): tentativas atômicas, uso único e validade.
"""
import json
import os
import threading
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from urllib.parse import urlparse

from api.exceptions.quiz_exceptions import QuizAPIException
from api.services import auth_service as auth_module
from api.services.auth_service import (
    AuthService,
    EmailCodeWait,
    hash_email_code,
    new_email_code,
    username_from_email,
)
from api.utils.config import DATABASE_URL


class _FakeEmail:
    def __init__(self, configured=True, success=True):
        self.configured = configured
        self.success = success
        self.sent = []

    def is_configured(self):
        return self.configured

    def send_email_code(self, to_email, code, minutes, purpose="login", language="pt-BR"):
        self.sent.append({"to": to_email, "code": code, "minutes": minutes, "purpose": purpose, "language": language})
        return (self.success, "sent" if self.configured else "simulated")


class _FakeRepo:
    """Repositório em memória com a mesma semântica do SQL de user_repository."""

    def __init__(self):
        self.now = datetime(2026, 11, 17, 12, 0, 0)
        self.codes = []
        self.users = {}
        self.sessions = {}
        self.deleted_sessions_for = []
        self.deleted_users = []
        self._next_id = 1

    # códigos
    def create_email_code(self, email, purpose, code_hash, ttl_minutes):
        for row in self.codes:
            if row["email"] == email and row["purpose"] == purpose and not row["used"]:
                row["used"] = True
        row = {
            "id": len(self.codes) + 1, "email": email, "purpose": purpose, "code_hash": code_hash,
            "expires_at": self.now + timedelta(minutes=ttl_minutes), "attempts": 0, "used": False,
            "created_at": self.now,
        }
        self.codes.append(row)
        return dict(row)

    def email_code_send_stats(self, email, purpose):
        recent = [
            r for r in self.codes
            if r["email"] == email and r["purpose"] == purpose and r["created_at"] > self.now - timedelta(hours=1)
        ]
        last = max((r["created_at"] for r in recent), default=None)
        return {
            "sent_last_hour": len(recent),
            "seconds_since_last": (self.now - last).total_seconds() if last else None,
        }

    def take_email_code_attempt(self, email, purpose, max_attempts):
        valid = [
            r for r in self.codes
            if r["email"] == email and r["purpose"] == purpose and not r["used"] and r["expires_at"] > self.now
        ]
        if not valid:
            return None
        row = max(valid, key=lambda r: (r["created_at"], r["id"]))
        if row["attempts"] >= max_attempts:
            return None
        row["attempts"] += 1
        return {"id": row["id"], "code_hash": row["code_hash"], "attempts": row["attempts"]}

    def consume_email_code(self, code_id):
        for row in self.codes:
            if row["id"] == code_id and not row["used"]:
                row["used"] = True
                return True
        return False

    # usuários e sessões
    def find_by_email(self, email):
        return next((dict(u) for u in self.users.values() if u["email"].lower() == email.lower()), None)

    def find_by_username(self, username):
        return next((dict(u) for u in self.users.values() if u["username"].lower() == username.lower()), None)

    def create_user(self, username, email, password_hash, salt, role="student", email_verified=False):
        user = {
            "id": self._next_id, "username": username, "email": email, "password_hash": password_hash,
            "salt": salt, "role": role, "email_verified": email_verified,
        }
        self.users[self._next_id] = user
        self._next_id += 1
        return dict(user)

    def update_password_and_role(self, user_id, password_hash, salt, role=None):
        self.users[user_id].update(password_hash=password_hash, salt=salt)

    def delete_user_sessions(self, user_id):
        self.deleted_sessions_for.append(user_id)

    def mark_email_verified(self, user_id):
        self.users[user_id]["email_verified"] = True

    def cleanup_expired_sessions(self):
        return 0

    def create_session(self, token_hash, user_id, duration_days=7):
        self.sessions[token_hash] = user_id
        return {"expires_at": self.now + timedelta(days=duration_days)}

    def delete_user_and_data(self, user_id):
        self.deleted_users.append(user_id)


def _service(configured=True, success=True):
    repo, email = _FakeRepo(), _FakeEmail(configured, success)
    return AuthService(repository=repo, email_service=email), repo, email


class TestCodeHelpers(unittest.TestCase):

    def test_code_has_six_digits_with_leading_zeros(self):
        with patch.object(auth_module.secrets, "randbelow", return_value=42):
            self.assertEqual(new_email_code(), "000042")
        for _ in range(200):
            code = new_email_code()
            self.assertRegex(code, r"^\d{6}$")

    def test_hash_is_bound_to_email_and_purpose(self):
        base = hash_email_code("a@x.com", "login", "123456")
        self.assertEqual(base, hash_email_code(" A@X.com ", "login", "123456"))
        self.assertNotEqual(base, hash_email_code("b@x.com", "login", "123456"))
        self.assertNotEqual(base, hash_email_code("a@x.com", "delete_account", "123456"))
        self.assertNotIn("123456", base)

    def test_hash_depends_on_server_secret(self):
        with patch.object(auth_module, "AUTH_CODE_SECRET", "segredo-1"):
            first = hash_email_code("a@x.com", "login", "123456")
        with patch.object(auth_module, "AUTH_CODE_SECRET", "segredo-2"):
            second = hash_email_code("a@x.com", "login", "123456")
        self.assertNotEqual(first, second)

    def test_username_from_email(self):
        taken = {"maria", "maria2"}
        self.assertEqual(username_from_email("Maria@x.com", lambda n: n in taken), "maria3")
        self.assertEqual(username_from_email("jo@x.com", lambda n: False), "joaluno")
        long_name = username_from_email(("a" * 60) + "@x.com", lambda n: False)
        self.assertLessEqual(len(long_name), 30)
        self.assertRegex(long_name, r"^[A-Za-z0-9_.-]{3,30}$")


class TestRequestCode(unittest.TestCase):

    def test_sends_code_and_stores_only_the_hash(self):
        service, repo, email = _service()
        result = service.request_email_code("  Ana@Exemplo.com ", language="en")
        self.assertEqual(result["expires_in"], auth_module.LOGIN_CODE_TTL_MINUTES * 60)
        self.assertEqual(result["resend_in"], auth_module.LOGIN_CODE_RESEND_SECONDS)
        self.assertNotIn("dev_code", result)
        self.assertEqual(len(email.sent), 1)
        sent = email.sent[0]
        self.assertEqual(sent["to"], "ana@exemplo.com")
        self.assertEqual(sent["language"], "en")
        self.assertRegex(sent["code"], r"^\d{6}$")
        stored = repo.codes[0]
        self.assertEqual(stored["email"], "ana@exemplo.com")
        self.assertNotEqual(stored["code_hash"], sent["code"])
        self.assertEqual(stored["code_hash"], hash_email_code("ana@exemplo.com", "login", sent["code"]))
        self.assertEqual(stored["expires_at"] - repo.now, timedelta(minutes=auth_module.LOGIN_CODE_TTL_MINUTES))

    def test_invalid_email_is_rejected(self):
        service, _, email = _service()
        for bad in ("", "sem-arroba", "a@b", "a b@c.com", ("x" * 250) + "@c.com"):
            with self.subTest(email=bad), self.assertRaises(QuizAPIException) as ctx:
                service.request_email_code(bad)
            self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(email.sent, [])

    def test_resend_waits_and_hourly_cap(self):
        service, repo, email = _service()
        service.request_email_code("ana@exemplo.com")
        repo.now += timedelta(seconds=20)
        with self.assertRaises(EmailCodeWait) as ctx:
            service.request_email_code("ana@exemplo.com")
        self.assertEqual(ctx.exception.status_code, 429)
        self.assertEqual(ctx.exception.retry_after, auth_module.LOGIN_CODE_RESEND_SECONDS - 20)

        for _ in range(auth_module.LOGIN_CODE_MAX_PER_HOUR - 1):
            repo.now += timedelta(seconds=auth_module.LOGIN_CODE_RESEND_SECONDS)
            service.request_email_code("ana@exemplo.com")
        repo.now += timedelta(seconds=auth_module.LOGIN_CODE_RESEND_SECONDS)
        with self.assertRaises(EmailCodeWait):
            service.request_email_code("ana@exemplo.com")
        self.assertEqual(len(email.sent), auth_module.LOGIN_CODE_MAX_PER_HOUR)
        # Outro e-mail não é afetado
        service.request_email_code("bia@exemplo.com")

    def test_admin_gets_same_answer_but_no_code(self):
        service, repo, email = _service()
        repo.create_user("admin", "admin@acely.com.br", "h", "s", role="admin", email_verified=True)
        admin_answer = service.request_email_code("admin@acely.com.br")
        other_answer = service.request_email_code("ninguem@exemplo.com")
        self.assertEqual(admin_answer, other_answer)
        self.assertEqual([m["to"] for m in email.sent], ["ninguem@exemplo.com"])

    def test_without_smtp_in_production_is_unavailable(self):
        service, _, email = _service(configured=False)
        with patch.object(auth_module, "DEBUG", False), self.assertRaises(QuizAPIException) as ctx:
            service.request_email_code("ana@exemplo.com")
        self.assertEqual(ctx.exception.status_code, 503)
        self.assertEqual(email.sent, [])

    def test_debug_without_smtp_returns_dev_code(self):
        service, _, email = _service(configured=False)
        with patch.object(auth_module, "DEBUG", True):
            result = service.request_email_code("ana@exemplo.com")
        self.assertEqual(result["dev_code"], email.sent[0]["code"])

    def test_send_failure_is_reported(self):
        service, _, _ = _service(success=False)
        with self.assertRaises(QuizAPIException) as ctx:
            service.request_email_code("ana@exemplo.com")
        self.assertEqual(ctx.exception.status_code, 503)


class TestLoginWithCode(unittest.TestCase):

    def _code(self, service, email_service, address="ana@exemplo.com"):
        service.request_email_code(address)
        return email_service.sent[-1]["code"]

    def test_right_code_creates_verified_account_once(self):
        service, repo, email = _service()
        code = self._code(service, email)
        result = service.login_with_email_code("ANA@exemplo.com", code)
        self.assertTrue(result["created"])
        self.assertTrue(result["token"])
        user = repo.find_by_email("ana@exemplo.com")
        self.assertTrue(user["email_verified"])
        self.assertEqual(user["role"], "student")
        self.assertEqual(user["username"], "ana")
        # Mesmo código de novo: já foi usado
        with self.assertRaises(QuizAPIException) as ctx:
            service.login_with_email_code("ana@exemplo.com", code)
        self.assertEqual(ctx.exception.error_code, "CODE_EXPIRED")

        # Segundo acesso entra na mesma conta
        repo.now += timedelta(minutes=2)
        code2 = self._code(service, email)
        result2 = service.login_with_email_code("ana@exemplo.com", f" {code2[:3]} {code2[3:]} ")
        self.assertFalse(result2["created"])
        self.assertEqual(result2["user"]["id"], result["user"]["id"])
        self.assertEqual(len(repo.users), 1)

    def test_wrong_guesses_burn_the_code(self):
        service, repo, email = _service()
        code = self._code(service, email)
        wrong = "000000" if code != "000000" else "111111"
        for i in range(auth_module.LOGIN_CODE_MAX_ATTEMPTS):
            with self.assertRaises(QuizAPIException) as ctx:
                service.login_with_email_code("ana@exemplo.com", wrong)
            remaining = auth_module.LOGIN_CODE_MAX_ATTEMPTS - (i + 1)
            if remaining:
                self.assertIn(f"{remaining} tentativa", ctx.exception.message)
        with self.assertRaises(QuizAPIException) as ctx:
            service.login_with_email_code("ana@exemplo.com", code)
        self.assertEqual(ctx.exception.error_code, "CODE_EXPIRED")
        self.assertEqual(repo.users, {})

    def test_expired_code_is_refused(self):
        service, repo, email = _service()
        code = self._code(service, email)
        repo.now += timedelta(minutes=auth_module.LOGIN_CODE_TTL_MINUTES, seconds=1)
        with self.assertRaises(QuizAPIException) as ctx:
            service.login_with_email_code("ana@exemplo.com", code)
        self.assertEqual(ctx.exception.error_code, "CODE_EXPIRED")

    def test_new_code_replaces_the_old_one(self):
        service, repo, email = _service()
        old = self._code(service, email)
        repo.now += timedelta(seconds=auth_module.LOGIN_CODE_RESEND_SECONDS)
        new = self._code(service, email)
        if old != new:
            with self.assertRaises(QuizAPIException):
                service.login_with_email_code("ana@exemplo.com", old)
        self.assertTrue(service.login_with_email_code("ana@exemplo.com", new)["token"])

    def test_code_is_bound_to_email(self):
        service, _, email = _service()
        code = self._code(service, email, "ana@exemplo.com")
        with self.assertRaises(QuizAPIException):
            service.login_with_email_code("bia@exemplo.com", code)

    def test_malformed_code(self):
        service, _, _ = _service()
        for bad in ("", "12345", "1234567", "abcdef", "12 34 5"):
            with self.subTest(code=bad), self.assertRaises(QuizAPIException) as ctx:
                service.login_with_email_code("ana@exemplo.com", bad)
            self.assertEqual(ctx.exception.status_code, 400)

    def test_admin_cannot_enter_with_code(self):
        service, repo, email = _service()
        repo.create_user("admin", "admin@acely.com.br", "h", "s", role="admin", email_verified=True)
        # Mesmo que alguém grave um código para o e-mail do admin, ele não abre a conta
        repo.create_email_code("admin@acely.com.br", "login", hash_email_code("admin@acely.com.br", "login", "123456"), 10)
        with self.assertRaises(QuizAPIException) as ctx:
            service.login_with_email_code("admin@acely.com.br", "123456")
        self.assertEqual(ctx.exception.status_code, 403)

    def test_unverified_legacy_account_is_secured(self):
        service, repo, email = _service()
        legacy = repo.create_user("antigo", "ana@exemplo.com", "hash-antigo", "salt-antigo", email_verified=False)
        code = self._code(service, email)
        result = service.login_with_email_code("ana@exemplo.com", code)
        self.assertFalse(result["created"])
        stored = repo.users[legacy["id"]]
        self.assertTrue(stored["email_verified"])
        self.assertNotEqual(stored["password_hash"], "hash-antigo")
        self.assertEqual(repo.deleted_sessions_for, [legacy["id"]])


class TestDeleteAccountWithCode(unittest.TestCase):

    def test_delete_with_email_code(self):
        service, repo, email = _service()
        user = repo.create_user("ana", "ana@exemplo.com", "h", "s", email_verified=True)
        service.request_account_deletion_code(user)
        self.assertEqual(email.sent[-1]["purpose"], "delete_account")
        code = email.sent[-1]["code"]
        wrong = "000000" if code != "000000" else "111111"
        with self.assertRaises(QuizAPIException) as ctx:
            service.delete_account(user, code=wrong)
        self.assertEqual(ctx.exception.status_code, 403)  # 401 derrubaria a sessão
        self.assertEqual(repo.deleted_users, [])
        service.delete_account(user, code=code)
        self.assertEqual(repo.deleted_users, [user["id"]])

    def test_login_code_does_not_delete_and_vice_versa(self):
        service, repo, email = _service()
        user = repo.create_user("ana", "ana@exemplo.com", "h", "s", email_verified=True)
        service.request_email_code("ana@exemplo.com")
        login_code = email.sent[-1]["code"]
        with self.assertRaises(QuizAPIException):
            service.delete_account(user, code=login_code)
        repo.now += timedelta(minutes=2)
        service.request_account_deletion_code(user)
        delete_code = email.sent[-1]["code"]
        with self.assertRaises(QuizAPIException):
            service.login_with_email_code("ana@exemplo.com", delete_code)
        self.assertEqual(repo.deleted_users, [])

    def test_delete_requires_confirmation(self):
        service, repo, _ = _service()
        user = repo.create_user("ana", "ana@exemplo.com", "h", "s", email_verified=True)
        with self.assertRaises(QuizAPIException) as ctx:
            service.delete_account(user)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_admin_cannot_request_delete_code(self):
        service, _, email = _service()
        with self.assertRaises(QuizAPIException) as ctx:
            service.request_account_deletion_code({"id": 1, "email": "admin@acely.com.br", "role": "admin"})
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertEqual(email.sent, [])


class TestCodeRoutes(unittest.TestCase):
    """Rotas HTTP com o serviço trocado por um falso (sem banco nem SMTP)."""

    @classmethod
    def setUpClass(cls):
        from api.handlers import quiz_handler
        from api.handlers.quiz_handler import QuizHandler

        cls.patches = [patch.object(quiz_handler, "_ensure_migrations", lambda: None)]
        for limiter in (quiz_handler._rl_email_code_send, quiz_handler._rl_email_code_fail_ip):
            cls.patches.append(patch.object(limiter, "repo", None))
        for p in cls.patches:
            p.start()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), QuizHandler)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        for p in cls.patches:
            p.stop()

    def _post(self, path, body):
        req = urllib.request.Request(
            f"{self.base}{path}", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read()), resp.headers.get_all("Set-Cookie") or []
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read()), e.headers.get_all("Set-Cookie") or []

    def test_request_code_route(self):
        with patch.object(AuthService, "request_email_code", return_value={"message": "ok", "expires_in": 600, "resend_in": 60}) as m:
            status, body, _ = self._post("/api/auth/email-code", {"email": "ana@exemplo.com", "language": "en"})
        self.assertEqual(status, 200)
        self.assertEqual(body["data"]["expires_in"], 600)
        m.assert_called_once_with("ana@exemplo.com", purpose="login", language="en")

    def test_request_code_wait_is_429_with_seconds(self):
        with patch.object(AuthService, "request_email_code", side_effect=EmailCodeWait(42, "Aguarde 42 segundos para pedir outro código.")):
            status, body, _ = self._post("/api/auth/email-code", {"email": "ana@exemplo.com"})
        self.assertEqual(status, 429)
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"], "CODE_RESEND_WAIT")
        self.assertEqual(body["retry_after"], 42)

    def test_verify_sets_httponly_cookie_and_hides_token(self):
        fake = {
            "token": "tok-secreto", "expires_at": "2026-11-24T12:00:00", "created": True,
            "user": {"id": 9, "username": "ana", "email": "ana@exemplo.com", "role": "student", "email_verified": True},
        }
        with patch.object(AuthService, "login_with_email_code", return_value=fake):
            status, body, cookies = self._post("/api/auth/email-code/verify", {"email": "ana@exemplo.com", "code": "123456"})
        self.assertEqual(status, 200)
        self.assertNotIn("token", body["data"])
        self.assertNotIn("tok-secreto", json.dumps(body))
        session = [c for c in cookies if "tok-secreto" in c]
        self.assertTrue(session, "cookie de sessão ausente")
        self.assertTrue(all("HttpOnly" in c for c in session))

    def test_verify_wrong_code_is_400(self):
        error = QuizAPIException("Código incorreto. Você ainda tem 4 tentativa(s) com este código.", 400, "INVALID_CODE")
        with patch.object(AuthService, "login_with_email_code", side_effect=error):
            status, body, cookies = self._post("/api/auth/email-code/verify", {"email": "ana@exemplo.com", "code": "000000"})
        self.assertEqual(status, 400)
        self.assertEqual(body["error"], "INVALID_CODE")

    def test_providers_reports_email_code(self):
        with urllib.request.urlopen(f"{self.base}/api/auth/providers", timeout=5) as resp:
            data = json.loads(resp.read())["data"]
        self.assertIn("email_code", data)
        self.assertIn("google", data)

    def test_delete_code_requires_account(self):
        status, body, _ = self._post("/api/account/delete-code", {"language": "pt-BR"})
        self.assertEqual(status, 401)


def _local_db_enabled() -> bool:
    if os.getenv("QUIZ_DB_INTEGRATION") != "1":
        return False
    return (urlparse(DATABASE_URL or "").hostname or "") in ("localhost", "127.0.0.1")


@unittest.skipUnless(_local_db_enabled(), "QUIZ_DB_INTEGRATION=1 com banco local não configurado")
class TestEmailCodeRepositorySQL(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from api.database.migrations import run_migrations
        run_migrations()
        run_migrations()  # idempotente com a tabela nova

    def setUp(self):
        from api.database.connection import get_cursor
        from api.repositories.user_repository import UserRepository

        self.repo = UserRepository()
        self.email = "sql-codigo@exemplo.com"
        with get_cursor() as cur:
            cur.execute("DELETE FROM email_codes WHERE email = %s", (self.email,))
            cur.execute("DELETE FROM users WHERE email = %s", (self.email,))

    def test_attempts_single_use_and_replacement(self):
        h1 = hash_email_code(self.email, "login", "111111")
        self.repo.create_email_code(self.email, "login", h1, 10)
        stats = self.repo.email_code_send_stats(self.email, "login")
        self.assertEqual(stats["sent_last_hour"], 1)
        self.assertLess(stats["seconds_since_last"], 5)

        for attempt in range(1, 4):
            row = self.repo.take_email_code_attempt(self.email, "login", 3)
            self.assertEqual(row["attempts"], attempt)
            self.assertEqual(row["code_hash"], h1)
        self.assertIsNone(self.repo.take_email_code_attempt(self.email, "login", 3))

        # Código novo invalida o anterior; usar queima uma vez só
        h2 = hash_email_code(self.email, "login", "222222")
        self.repo.create_email_code(self.email, "login", h2, 10)
        row = self.repo.take_email_code_attempt(self.email, "login", 5)
        self.assertEqual(row["code_hash"], h2)
        self.assertTrue(self.repo.consume_email_code(row["id"]))
        self.assertFalse(self.repo.consume_email_code(row["id"]))
        self.assertIsNone(self.repo.take_email_code_attempt(self.email, "login", 5))
        # Outra finalidade não enxerga o código de login
        self.assertIsNone(self.repo.take_email_code_attempt(self.email, "delete_account", 5))

    def test_expired_code_is_not_offered(self):
        from api.database.connection import get_cursor

        self.repo.create_email_code(self.email, "login", hash_email_code(self.email, "login", "333333"), 10)
        with get_cursor() as cur:
            cur.execute("UPDATE email_codes SET expires_at = NOW() - INTERVAL '1 second' WHERE email = %s", (self.email,))
        self.assertIsNone(self.repo.take_email_code_attempt(self.email, "login", 5))

    def test_full_login_against_database(self):
        email_service = _FakeEmail()
        service = AuthService(email_service=email_service)
        service.request_email_code(self.email)
        result = service.login_with_email_code(self.email, email_service.sent[-1]["code"])
        self.assertTrue(result["created"])
        self.assertTrue(service.validate_token(result["token"]))
        user = self.repo.find_by_email(self.email)
        self.assertTrue(user["email_verified"])
        # Excluir a conta leva junto os códigos do e-mail
        self.repo.delete_user_and_data(user["id"])
        self.assertEqual(self.repo.email_code_send_stats(self.email, "login")["sent_last_hour"], 0)


if __name__ == "__main__":
    unittest.main()
