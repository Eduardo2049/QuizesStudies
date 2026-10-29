"""
Correções de segurança da recuperação de senha, redirecionamentos e entradas da IA.

Cobre:
1. A resposta de "Esqueci minha senha" é idêntica exista a conta ou não (sem `email_sent`).
2. Sem APP_URL, um Host forjado não vira o endereço do link enviado por e-mail.
3. Sem SMTP em produção, o link de redefinição não vai para o log.
4. Um link de redefinição não troca a senha duas vezes (pedidos simultâneos).
5. O `next` do login com Google recusa tab, quebra de linha e barra invertida.
6. A validação do token de redefinição tem limite de tentativas.
7. As questões enviadas para o remix são revalidadas e limitadas.
8. CSP com form-action e COOP iguais no servidor e na Vercel.
9. Confirmação de e-mail: cadastro envia o link, o link confirma uma vez só, a troca de
   senha por e-mail também confirma.
10. Login com Google: conta não confirmada perde a senha e as sessões de quem a criou;
    o admin não entra pelo Google.
11. O admin não recebe link de recuperação e deixa o e-mail antigo de outro domínio.
12. "Esqueci minha senha" tem tempo mínimo de resposta.
13. Cookie de sessão com prefixo __Host- sem desconectar quem usa o nome antigo.
14. Nome de usuário só com letras, números, ponto, hífen e sublinhado.
"""

import io
import json
import os
import threading
import unittest
import urllib.error
import urllib.request
from contextlib import redirect_stdout
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import MagicMock, patch

from api.controllers.auth_controller import AuthController
from api.controllers.quiz_controller import MAX_REMIX_QUESTIONS, _sanitize_remix_questions
from api.exceptions.quiz_exceptions import QuizAPIException
from api.handlers import quiz_handler
from api.handlers.quiz_handler import QuizHandler, RateLimiter
from api.middleware.http_middleware import HTTPMiddleware
from api.services import google_auth_service
from api.services.auth_service import AuthService
from api.services.email_service import EmailService
from api.services.google_auth_service import GoogleAuthService, safe_next

ROOT = Path(__file__).resolve().parent.parent
USER = {"id": 7, "username": "ana", "email": "ana@exemplo.com", "salt": "s", "role": "student"}


def _service(user):
    repo = MagicMock()
    repo.find_by_email.return_value = user
    repo.find_by_username.return_value = user
    email = MagicMock()
    email.send_password_reset_email.return_value = (True, "sent")
    return AuthService(repository=repo, email_service=email), repo, email


class TestForgotPasswordDoesNotRevealAccounts(unittest.TestCase):
    def test_response_is_identical_for_existing_and_missing_account(self):
        existing, _, email = _service(USER)
        missing, _, _ = _service(None)
        with patch("api.services.auth_service.DEBUG", False):
            a = AuthController(auth_service=existing).forgot_password(
                {"email": "ana@exemplo.com"}, "https://acely.com.br"
            )
            b = AuthController(auth_service=missing).forgot_password({"email": "x@exemplo.com"}, "https://acely.com.br")
        email.send_password_reset_email.assert_called_once()
        self.assertEqual(a, b)
        self.assertNotIn("email_sent", a["data"])
        self.assertNotIn("dev_token", a["data"])

    def test_debug_still_returns_test_link(self):
        service, _, email = _service(USER)
        email.send_password_reset_email.return_value = (True, "simulated")
        with patch("api.services.auth_service.DEBUG", True):
            res = AuthController(auth_service=service).forgot_password(
                {"email": "ana@exemplo.com"}, "http://localhost:8000"
            )
        self.assertIn("/reset-password?token=", res["data"]["dev_reset_url"])


class TestResetLinkNeedsTrustedBaseUrl(unittest.TestCase):
    def test_service_sends_nothing_without_base_url(self):
        service, repo, email = _service(USER)
        with redirect_stdout(io.StringIO()):
            res = service.request_password_reset("ana@exemplo.com", app_url="")
        self.assertFalse(res["email_sent"])
        repo.create_password_reset.assert_not_called()
        email.send_password_reset_email.assert_not_called()


class TestForgotPasswordRouteHost(unittest.TestCase):
    """Rota real: o app_url que chega ao serviço depende do Host só quando ele é confiável."""

    def setUp(self):
        self.captured = {}

        def fake_reset(service_self, identifier, app_url=""):
            self.captured["app_url"] = app_url
            return {"message": "ok", "email_sent": True, "dev_reset_url": None, "dev_token": None}

        for p in (
            patch.object(quiz_handler, "_ensure_migrations", lambda: None),
            patch.object(quiz_handler, "_rl_forgot_password", RateLimiter(limit=100, window_seconds=60)),
            patch.object(quiz_handler, "FORGOT_PASSWORD_MIN_SECONDS", 0),
            patch.object(quiz_handler, "DEBUG", False),
            patch.object(AuthService, "request_password_reset", fake_reset),
        ):
            p.start()
            self.addCleanup(p.stop)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), QuizHandler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def _post(self, host):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/auth/forgot-password",
            data=json.dumps({"email": "ana@exemplo.com"}).encode(),
            headers={"Content-Type": "application/json", "Host": host},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = json.loads(resp.read())
        return body

    def _env(self, **values):
        """Ambiente só com as variáveis pedidas entre APP_URL e VERCEL (restaurado no fim)."""
        p = patch.dict("os.environ", values)
        p.start()
        self.addCleanup(p.stop)
        for key in ("APP_URL", "VERCEL"):
            if key not in values:
                os.environ.pop(key, None)

    def test_forged_host_is_ignored_without_app_url(self):
        self._env()
        body = self._post("site-do-atacante.com")
        self.assertEqual(self.captured["app_url"], "")
        self.assertNotIn("email_sent", body)

    def test_localhost_still_works_for_development(self):
        self._env()
        self._post(f"localhost:{self.port}")
        self.assertTrue(self.captured["app_url"].endswith(f"://localhost:{self.port}"))

    def test_vercel_host_is_trusted(self):
        self._env(VERCEL="1")
        self._post("acely.com.br")
        self.assertTrue(self.captured["app_url"].endswith("://acely.com.br"))

    def test_app_url_wins_over_host(self):
        self._env(APP_URL="https://acely.com.br/")
        self._post("site-do-atacante.com")
        self.assertEqual(self.captured["app_url"], "https://acely.com.br")


class TestSimulatedEmailKeepsTokenOutOfLogs(unittest.TestCase):
    def _log(self, debug):
        out = io.StringIO()
        with patch("api.services.email_service.DEBUG", debug), redirect_stdout(out):
            EmailService(host="").send_password_reset_email(
                "ana@exemplo.com", "ana", "https://acely.com.br/reset-password?token=SEGREDO123", "SEGREDO123"
            )
        return out.getvalue()

    def test_production_log_has_no_token(self):
        log = self._log(debug=False)
        self.assertNotIn("SEGREDO123", log)
        self.assertNotIn("ana@exemplo.com", log)
        self.assertIn("SMTP não configurado", log)

    def test_debug_log_keeps_link_for_development(self):
        self.assertIn("SEGREDO123", self._log(debug=True))


class TestResetTokenIsSingleUse(unittest.TestCase):
    def test_token_already_burned_does_not_change_password(self):
        repo = MagicMock()
        repo.find_password_reset.return_value = {"user_id": 7, "email": "ana@exemplo.com", "username": "ana"}
        repo.mark_password_reset_used.return_value = False  # outro pedido queimou antes
        service = AuthService(repository=repo, email_service=MagicMock())
        with self.assertRaises(QuizAPIException) as ctx:
            service.reset_password("tok", "NovaSenhaForte1")
        self.assertEqual(ctx.exception.status_code, 400)
        repo.update_password_and_role.assert_not_called()
        repo.delete_user_sessions.assert_not_called()


class TestSafeNextRejectsControlCharacters(unittest.TestCase):
    def test_tab_newline_and_backslash_fall_back_to_home(self):
        for raw in ("/\t/evil.com", "/\n/evil.com", "/\r/evil.com", "/a\\b", "/%09ok\x7f"):
            with self.subTest(raw=repr(raw)):
                self.assertEqual(safe_next(raw), "/")

    def test_normal_paths_still_work(self):
        self.assertEqual(safe_next("/?abrir=criar"), "/?abrir=criar")
        self.assertEqual(safe_next("/termos"), "/termos")


class TestVerifyResetTokenRateLimit(unittest.TestCase):
    def setUp(self):
        for p in (
            patch.object(quiz_handler, "_ensure_migrations", lambda: None),
            patch.object(quiz_handler, "_rl_reset_password", RateLimiter(limit=1, window_seconds=60)),
            patch.object(AuthService, "verify_reset_token", lambda self, token: {"valid": True}),
        ):
            p.start()
            self.addCleanup(p.stop)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), QuizHandler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def _status(self):
        url = f"http://127.0.0.1:{self.port}/api/auth/verify-reset-token?token=abc"
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                return resp.status
        except urllib.error.HTTPError as e:
            e.close()
            return e.code

    def test_second_attempt_is_limited(self):
        self.assertEqual(self._status(), 200)
        self.assertEqual(self._status(), 429)


class TestRemixInputIsSanitized(unittest.TestCase):
    def test_drops_invalid_items_and_limits_sizes(self):
        raw = [
            "texto solto",
            {"question": 123},
            {"question": "  ", "options": ["a"]},
            {"question": "Q" * 5000, "options": ["x" * 900, 7, "", "b"] + ["c"] * 10, "section": {"x": 1}},
        ] + [{"question": f"q{i}"} for i in range(20)]
        cleaned = _sanitize_remix_questions(raw)
        first = cleaned[0]
        self.assertEqual(len(first["question"]), 2000)
        self.assertEqual(first["section"], "Geral")
        self.assertTrue(all(isinstance(o, str) and 0 < len(o) <= 500 for o in first["options"]))
        self.assertLessEqual(len(first["options"]), 6)
        self.assertLessEqual(len(cleaned), MAX_REMIX_QUESTIONS)

    def test_non_list_is_empty(self):
        self.assertEqual(_sanitize_remix_questions({"question": "x"}), [])


class TestSecurityHeadersMatchVercel(unittest.TestCase):
    def test_csp_and_coop_are_the_same_in_both_places(self):
        sent = {}
        handler = MagicMock()
        handler.send_header.side_effect = lambda k, v: sent.__setitem__(k, v)
        from api.middleware.http_middleware import HTTPMiddleware

        HTTPMiddleware.add_security_headers(handler)
        vercel = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
        headers = {h["key"]: h["value"] for h in vercel["headers"][0]["headers"]}
        for key in ("Content-Security-Policy", "Cross-Origin-Opener-Policy"):
            with self.subTest(header=key):
                self.assertEqual(sent[key], headers[key])
        self.assertIn("form-action 'self'", sent["Content-Security-Policy"])
        self.assertEqual(sent["Cross-Origin-Opener-Policy"], "same-origin")


def _auth(user=None):
    repo = MagicMock()
    repo.find_by_email.return_value = user
    repo.find_by_username.return_value = user
    repo.create_user.side_effect = lambda username, email, *a, **k: {
        "id": 9,
        "username": username,
        "email": email,
        "role": k.get("role", "student"),
        "email_verified": k.get("email_verified", False),
    }
    email = MagicMock()
    email.send_email_verification.return_value = (True, "sent")
    email.send_password_reset_email.return_value = (True, "sent")
    return AuthService(repository=repo, email_service=email), repo, email


class TestEmailVerification(unittest.TestCase):
    def test_register_sends_single_use_link(self):
        service, repo, email = _auth()
        user = service.register("nova_conta", "Nova@Exemplo.com", "SenhaForte123", app_url="https://acely.com.br")
        self.assertFalse(user["email_verified"])
        token_hash, user_id = repo.create_email_verification.call_args[0][:2]
        self.assertEqual(user_id, 9)
        to, username, url = email.send_email_verification.call_args[0]
        self.assertEqual((to, username), ("nova@exemplo.com", "nova_conta"))
        self.assertTrue(url.startswith("https://acely.com.br/api/auth/verify-email?token="))
        self.assertNotIn(token_hash, url)  # no banco só o hash, no e-mail só o token

    def test_register_without_base_url_still_creates_account(self):
        service, repo, email = _auth()
        with redirect_stdout(io.StringIO()):
            service.register("nova_conta", "nova@exemplo.com", "SenhaForte123", app_url="")
        repo.create_user.assert_called_once()
        repo.create_email_verification.assert_not_called()
        email.send_email_verification.assert_not_called()

    def test_verify_email_accepts_only_valid_tokens(self):
        service, repo, _ = _auth()
        repo.consume_email_verification.return_value = 9
        self.assertTrue(service.verify_email("token-bom"))
        repo.consume_email_verification.return_value = None
        self.assertFalse(service.verify_email("token-usado"))
        repo.consume_email_verification.reset_mock()
        self.assertFalse(service.verify_email("x" * 500))
        self.assertFalse(service.verify_email(""))
        repo.consume_email_verification.assert_not_called()

    def test_password_reset_by_email_also_confirms_email(self):
        service, repo, _ = _auth()
        repo.find_password_reset.return_value = {"user_id": 9, "email": "a@b.com", "username": "a"}
        repo.mark_password_reset_used.return_value = True
        service.reset_password("tok", "NovaSenhaForte1")
        repo.mark_email_verified.assert_called_once_with(9)

    def test_resend_for_already_confirmed_account_sends_nothing(self):
        service, _, email = _auth()
        res = service.resend_email_verification({"id": 9, "email_verified": True}, app_url="https://acely.com.br")
        self.assertTrue(res["already_verified"])
        email.send_email_verification.assert_not_called()

    def test_resend_fails_clearly_without_base_url(self):
        service, _, _ = _auth()
        user = {"id": 9, "username": "a", "email": "a@b.com", "email_verified": False}
        with self.assertRaises(QuizAPIException) as ctx, redirect_stdout(io.StringIO()):
            service.resend_email_verification(user, app_url="")
        self.assertEqual(ctx.exception.status_code, 503)


class TestUsernameRules(unittest.TestCase):
    def test_rejects_spaces_symbols_and_long_names(self):
        service, repo, _ = _auth()
        for name in ("a b", "<b>x</b>", "ab", "x" * 31, "nome​com"):
            with self.subTest(name=name), self.assertRaises(QuizAPIException) as ctx:
                service.register(name, "a@b.com", "SenhaForte123")
            self.assertEqual(ctx.exception.status_code, 400)
        repo.create_user.assert_not_called()

    def test_rejects_oversized_password(self):
        service, _, _ = _auth()
        with self.assertRaises(QuizAPIException):
            service.register("aluno_ok", "a@b.com", "x" * 257)


class TestGoogleLoginTakeoverProtection(unittest.TestCase):
    def setUp(self):
        for p in (
            patch.object(google_auth_service, "GOOGLE_CLIENT_ID", "id"),
            patch.object(google_auth_service, "GOOGLE_CLIENT_SECRET", "segredo"),
        ):
            p.start()
            self.addCleanup(p.stop)

    def _login(self, existing):
        service, repo, _ = _auth(existing)
        repo.find_by_username.return_value = None
        repo.create_session.return_value = {"expires_at": MagicMock(isoformat=lambda: "x")}
        google = GoogleAuthService(service)
        profile = {"email": "dono@gmail.com", "email_verified": True}
        with patch.object(GoogleAuthService, "_fetch_profile", return_value=profile):
            result = google.login_with_code("code", "https://acely.com.br/api/auth/google/callback")
        return result, repo

    def test_unconfirmed_account_is_taken_back_from_its_creator(self):
        existing = {"id": 3, "username": "x", "email": "dono@gmail.com", "role": "student", "email_verified": False}
        _, repo = self._login(existing)
        repo.update_password_and_role.assert_called_once()
        repo.delete_user_sessions.assert_called_once_with(3)
        repo.mark_email_verified.assert_called_once_with(3)

    def test_confirmed_account_keeps_password_and_sessions(self):
        existing = {"id": 3, "username": "x", "email": "dono@gmail.com", "role": "student", "email_verified": True}
        _, repo = self._login(existing)
        repo.update_password_and_role.assert_not_called()
        repo.delete_user_sessions.assert_not_called()

    def test_new_account_from_google_is_already_confirmed(self):
        _, repo = self._login(None)
        self.assertTrue(repo.create_user.call_args.kwargs["email_verified"])

    def test_admin_cannot_sign_in_with_google(self):
        admin = {"id": 1, "username": "admin", "email": "dono@gmail.com", "role": "admin", "email_verified": True}
        with self.assertRaises(QuizAPIException) as ctx:
            self._login(admin)
        self.assertEqual(ctx.exception.error_code, "GOOGLE_ADMIN_BLOCKED")


class TestAdminAccountHardening(unittest.TestCase):
    def test_admin_gets_no_reset_link(self):
        admin = {"id": 1, "username": "admin", "email": "admin@acely.com.br", "role": "admin"}
        service, repo, email = _auth(admin)
        with redirect_stdout(io.StringIO()):
            res = service.request_password_reset("admin", app_url="https://acely.com.br")
        self.assertFalse(res["email_sent"])
        repo.create_password_reset.assert_not_called()
        email.send_password_reset_email.assert_not_called()

    def test_seed_moves_admin_off_the_old_domain(self):
        from api.services.auth_service import ADMIN_EMAIL

        admin = {"id": 1, "username": "admin", "email": "admin@quiz.study", "role": "admin", "salt": "s"}
        service, repo, _ = _auth(admin)
        with (
            patch("api.services.auth_service.ADMIN_PASSWORD", "SenhaForte123"),
            patch("api.services.auth_service.verify_password", return_value=True),
        ):
            service.seed_admin_if_needed()
        repo.update_email.assert_called_once_with(1, ADMIN_EMAIL)


class _LiveServer(unittest.TestCase):
    """Servidor real em processo, sem banco; cada classe acrescenta os patches dela."""

    def setUp(self):
        for p in (patch.object(quiz_handler, "_ensure_migrations", lambda: None), *self.patches_for_test()):
            p.start()
            self.addCleanup(p.stop)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), QuizHandler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def patches_for_test(self):
        return ()

    def _raw(self, method, path, body=None):
        import http.client

        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        headers = {"Content-Type": "application/json"} if body is not None else {}
        conn.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers)
        resp = conn.getresponse()
        resp.read()
        conn.close()
        return resp


class TestVerifyEmailRoute(_LiveServer):
    def patches_for_test(self):
        return (patch.object(quiz_handler, "_rl_reset_password", RateLimiter(limit=100, window_seconds=60)),)

    def test_redirects_with_result(self):
        with patch.object(AuthService, "verify_email", return_value=True):
            resp = self._raw("GET", "/api/auth/verify-email?token=bom")
        self.assertEqual((resp.status, resp.getheader("Location")), (302, "/?email=confirmado"))
        with patch.object(AuthService, "verify_email", return_value=False):
            resp = self._raw("GET", "/api/auth/verify-email?token=ruim")
        self.assertEqual(resp.getheader("Location"), "/?email=link_invalido")


class TestForgotPasswordMinimumTime(_LiveServer):
    def patches_for_test(self):
        fake = {"message": "ok", "email_sent": False, "dev_reset_url": None, "dev_token": None}
        return (
            patch.object(quiz_handler, "_rl_forgot_password", RateLimiter(limit=100, window_seconds=60)),
            patch.object(quiz_handler, "FORGOT_PASSWORD_MIN_SECONDS", 0.4),
            patch.object(AuthService, "request_password_reset", lambda self, identifier, app_url="": fake),
        )

    def test_fast_answers_wait_for_the_floor(self):
        import time

        started = time.monotonic()
        resp = self._raw("POST", "/api/auth/forgot-password", {"email": "x@exemplo.com"})
        self.assertEqual(resp.status, 200)
        self.assertGreaterEqual(time.monotonic() - started, 0.4)


class TestSessionCookieName(unittest.TestCase):
    def test_https_uses_host_prefix_and_dev_does_not(self):
        secure = HTTPMiddleware.session_cookie("abc", secure=True, max_age=60)
        self.assertTrue(secure.startswith("__Host-acely_session=abc;"))
        self.assertIn("Secure", secure)
        self.assertIn("Path=/", secure)
        self.assertNotIn("Domain", secure)
        plain = HTTPMiddleware.session_cookie("abc", secure=False, max_age=60)
        self.assertTrue(plain.startswith("acely_session=abc;"))

    def test_old_cookie_still_signs_in_and_new_one_wins(self):
        def token(cookie):
            return HTTPMiddleware.get_auth_token(MagicMock(headers={"Cookie": cookie}))

        self.assertEqual(token("ifuture_session=antigo"), "antigo")
        self.assertEqual(token("ifuture_session=antigo; __Host-acely_session=novo"), "novo")
        self.assertIsNone(token(""))

    def test_writing_the_session_always_clears_the_old_name(self):
        cookies = HTTPMiddleware.session_cookies("abc", secure=True, max_age=60)
        self.assertTrue(cookies[0].startswith("__Host-acely_session=abc;"))
        self.assertTrue(cookies[1].startswith("ifuture_session=;"))
        self.assertIn("Max-Age=0", cookies[1])


if __name__ == "__main__":
    unittest.main()
