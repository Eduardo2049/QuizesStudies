"""
Testes End-to-End de autenticação e controle de acesso.

Sobe o servidor em setUpClass, aguarda a porta responder e derruba em tearDownClass.
Compatível com 'python -m unittest discover tests'.

Requisitos de ambiente:
    ADMIN_PASSWORD  -- senha do admin (obrigatória)
    E2E_PORT        -- porta do servidor (padrão: 8005)
"""

import json
import os
import socket
import subprocess
import sys
import time
import unittest
import urllib.error
import urllib.request

_BASE_URL = ""
_PROC = None

E2E_PORT = int(os.environ.get("E2E_PORT", "8005"))
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
STARTUP_TIMEOUT = 10  # segundos máximos para o servidor subir


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _wait_for_port(host, port, timeout):
    """Aguarda a porta TCP aceitar conexões (polling sem sleep fixo)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def _request(path, data=None, headers=None, method=None):
    """Executa uma requisição HTTP e devolve (status_code, body_dict)."""
    h = dict(headers or {})
    body = None
    if data is not None:
        if isinstance(data, dict):
            body = json.dumps(data).encode("utf-8")
            h.setdefault("Content-Type", "application/json")
        else:
            body = data
    req = urllib.request.Request(
        f"{_BASE_URL}{path}", data=body, headers=h, method=method
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


# ---------------------------------------------------------------------------
# Fixture de classe
# ---------------------------------------------------------------------------

class AuthE2ETestCase(unittest.TestCase):
    """Testes de autenticação e controle de acesso contra o servidor real."""

    admin_token = ""
    student_token = ""

    _BOUNDARY = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    _UPLOAD_BODY = (
        "----WebKitFormBoundary7MA4YWxkTrZu0gW\r\n"
        'Content-Disposition: form-data; name="file"; filename="teste_prova.txt"\r\n'
        "Content-Type: text/plain\r\n\r\n"
        "**1.** Questao teste de raciocínio?\n"
        "a) Opcao A\n"
        "b) Opcao B\n\n"
        "# Gabarito\n"
        "1. a) Opcao A\r\n"
        "----WebKitFormBoundary7MA4YWxkTrZu0gW--\r\n"
    ).encode("utf-8")
    _UPLOAD_HEADERS = {
        "Content-Type": "multipart/form-data; boundary=----WebKitFormBoundary7MA4YWxkTrZu0gW"
    }

    @classmethod
    def setUpClass(cls):
        global _BASE_URL, _PROC

        if not ADMIN_PASSWORD:
            raise unittest.SkipTest(
                "ADMIN_PASSWORD nao configurada -- pulando testes e2e."
            )

        env = os.environ.copy()
        env["PORT"] = str(E2E_PORT)

        _PROC = subprocess.Popen(
            [sys.executable, "-u", "quiz_api.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
        )

        _BASE_URL = f"http://localhost:{E2E_PORT}"

        if not _wait_for_port("localhost", E2E_PORT, STARTUP_TIMEOUT):
            _PROC.terminate()
            raise RuntimeError(
                f"Servidor nao respondeu em {STARTUP_TIMEOUT}s na porta {E2E_PORT}."
            )

    @classmethod
    def tearDownClass(cls):
        global _PROC
        if _PROC is not None:
            _PROC.terminate()
            try:
                _PROC.wait(timeout=5)
            except subprocess.TimeoutExpired:
                _PROC.kill()
            _PROC = None

    def test_01_login_wrong_password(self):
        """Login com senha errada deve retornar 401."""
        st, _ = _request(
            "/api/auth/login", {"username": "admin", "password": "wrongpassword"}
        )
        self.assertEqual(st, 401, "Esperado 401 para senha incorreta")

    def test_02_admin_login_success(self):
        """Login com credenciais corretas deve retornar 200 e um token."""
        st, data = _request(
            "/api/auth/login", {"username": "admin", "password": ADMIN_PASSWORD}
        )
        self.assertEqual(st, 200, f"Esperado 200, obtido {st}")
        token = data.get("data", {}).get("token", "")
        self.assertTrue(token, "Token nao retornado no payload")
        AuthE2ETestCase.admin_token = token

    def test_03_me_endpoint(self):
        """GET /api/auth/me com token valido deve confirmar a sessao."""
        self.assertTrue(self.admin_token, "Prereq: admin_token ausente (test_02 falhou?)")
        st, data = _request(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(st, 200)
        self.assertEqual(data["data"]["user"]["username"], "admin")

    def test_04_upload_without_token_is_401(self):
        """Upload sem token deve retornar 401 Unauthorized."""
        st, _ = _request(
            "/api/upload", data=self._UPLOAD_BODY, headers=self._UPLOAD_HEADERS
        )
        self.assertEqual(st, 401, f"Esperado 401 sem token, obtido {st}")

    def test_05_student_auth(self):
        """Registro ou login de estudante deve funcionar."""
        st, data = _request(
            "/api/auth/register",
            {
                "username": "aluno_e2e",
                "email": "aluno_e2e@escola.com",
                "password": "senha_estudante_123",
            },
        )
        self.assertIn(st, (201, 409), f"Esperado 201 ou 409, obtido {st}: {data}")

        st, data = _request(
            "/api/auth/login",
            {"username": "aluno_e2e", "password": "senha_estudante_123"},
        )
        self.assertEqual(st, 200, f"Login do estudante falhou: {st}")
        AuthE2ETestCase.student_token = data["data"]["token"]

    def test_06_student_upload_is_403(self):
        """Upload com token de estudante deve retornar 403 Forbidden."""
        self.assertTrue(self.student_token, "Prereq: student_token ausente (test_05 falhou?)")
        headers = {
            **self._UPLOAD_HEADERS,
            "Authorization": f"Bearer {self.student_token}",
        }
        st, _ = _request("/api/upload", data=self._UPLOAD_BODY, headers=headers)
        self.assertEqual(st, 403, f"Esperado 403 para estudante, obtido {st}")

    def test_07_admin_upload_is_201(self):
        """Upload com token de admin deve retornar 201 Created."""
        self.assertTrue(self.admin_token, "Prereq: admin_token ausente (test_02 falhou?)")
        headers = {
            **self._UPLOAD_HEADERS,
            "Authorization": f"Bearer {self.admin_token}",
        }
        st, data = _request("/api/upload", data=self._UPLOAD_BODY, headers=headers)
        self.assertEqual(st, 201, f"Esperado 201 para admin, obtido {st}: {data}")

    def test_08_logout_invalidates_token(self):
        """Apos logout, o token nao deve mais ser aceito pelo /api/auth/me."""
        self.assertTrue(self.admin_token, "Prereq: admin_token ausente (test_02 falhou?)")
        auth_header = {"Authorization": f"Bearer {self.admin_token}"}

        st, _ = _request("/api/auth/logout", headers=auth_header, method="POST")
        self.assertEqual(st, 200, f"Logout esperava 200, obtido {st}")

        st, _ = _request("/api/auth/me", headers=auth_header)
        self.assertEqual(st, 401, f"Token deveria ser invalido apos logout, obtido {st}")
        AuthE2ETestCase.admin_token = ""


if __name__ == "__main__":
    unittest.main()