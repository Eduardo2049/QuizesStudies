"""
Testes da rota HTTP POST /api/auth/forgot-password contra o QuizHandler real
(servidor em processo, sem banco: serviço de autenticação e rate limit isolados).
Valida:
1. A rota responde 200 (regressão: NameError em PORT derrubava a rota com 500).
2. O link de redefinição usa APP_URL quando definido, ou o Host da requisição.
3. Em produção (DEBUG=false) o token nunca é devolvido no corpo da resposta.
"""
import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from api.handlers import quiz_handler
from api.handlers.quiz_handler import QuizHandler, RateLimiter
from api.services.auth_service import AuthService


class TestForgotPasswordRoute(unittest.TestCase):

    def setUp(self):
        self.captured = {}

        def fake_reset(service_self, identifier, app_url=""):
            self.captured["identifier"] = identifier
            self.captured["app_url"] = app_url
            return {
                "message": "Se os dados informados estiverem cadastrados, você receberá as instruções.",
                "email_sent": True,
                "dev_reset_url": None,
                "dev_token": None,
            }

        patches = [
            patch.object(quiz_handler, "_ensure_migrations", lambda: None),
            patch.object(quiz_handler, "_rl_forgot_password", RateLimiter(limit=100, window_seconds=60)),
            patch.object(AuthService, "request_password_reset", fake_reset),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), QuizHandler)
        self.port = self.server.server_address[1]
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def _post(self, payload, headers=None):
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/auth/forgot-password",
            data=body,
            headers={"Content-Type": "application/json", **(headers or {})},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8"))

    def test_forgot_password_route_returns_200(self):
        status, data = self._post({"email": "aluno@quiz.study"})
        self.assertEqual(status, 200, data)
        self.assertEqual(self.captured["identifier"], "aluno@quiz.study")

    def test_reset_link_uses_app_url_env_when_set(self):
        with patch.dict("os.environ", {"APP_URL": "https://meu-quiz.vercel.app/"}):
            status, _ = self._post({"email": "aluno@quiz.study"})
        self.assertEqual(status, 200)
        self.assertEqual(self.captured["app_url"], "https://meu-quiz.vercel.app")

    def test_reset_link_falls_back_to_request_host(self):
        with patch.dict("os.environ", {}, clear=False) as env:
            env.pop("APP_URL", None)
            status, _ = self._post(
                {"email": "aluno@quiz.study"},
                headers={"X-Forwarded-Proto": "https"},
            )
        self.assertEqual(status, 200)
        self.assertEqual(self.captured["app_url"], f"https://127.0.0.1:{self.port}")


class TestForgotPasswordNoTokenLeak(unittest.TestCase):
    """Sem SMTP em produção, a API não pode devolver o token (permitiria sequestro de conta)."""

    def _service(self):
        from unittest.mock import MagicMock
        repo = MagicMock()
        repo.find_by_email.return_value = {"id": 7, "username": "ana", "email": "ana@quiz.study"}
        email = MagicMock()
        email.send_password_reset_email.return_value = (True, "simulated")
        return AuthService(repository=repo, email_service=email)

    def test_simulated_mode_hides_token_when_not_debug(self):
        with patch("api.services.auth_service.DEBUG", False):
            res = self._service().request_password_reset("ana@quiz.study", app_url="https://x.app")
        self.assertIsNone(res["dev_token"])
        self.assertIsNone(res["dev_reset_url"])
        self.assertFalse(res["email_sent"])

    def test_simulated_mode_exposes_token_only_in_debug(self):
        with patch("api.services.auth_service.DEBUG", True):
            res = self._service().request_password_reset("ana@quiz.study", app_url="http://localhost:8000")
        self.assertIsNotNone(res["dev_token"])
        self.assertIn("/reset-password?token=", res["dev_reset_url"])


if __name__ == "__main__":
    unittest.main()
