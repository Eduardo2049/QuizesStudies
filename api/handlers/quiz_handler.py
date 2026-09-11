"""
Handler HTTP Principal — Suporte a multipart/form-data para upload de arquivos
"""
import io
import json
import re
import time
from collections import defaultdict, deque
from threading import Lock
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from api.utils.config import WEB_DIR, DEBUG, COOKIE_SECURE
from api.controllers.quiz_controller import QuizController, UploadController
from api.controllers.auth_controller import AuthController
from api.exceptions.quiz_exceptions import QuizAPIException
from api.middleware.http_middleware import HTTPMiddleware, ResponseFormatter
from api.utils.validators import AnswerValidator

# Extensões permitidas para upload
ALLOWED_EXTENSIONS = {"txt", "pdf", "docx"}
MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB
MAX_JSON_BYTES = 256 * 1024
AUTH_RATE_WINDOW_SECONDS = 15 * 60
AUTH_RATE_LIMIT = 10
_auth_requests = defaultdict(deque)
_auth_requests_lock = Lock()


def _allow_auth_request(handler, limit: int = AUTH_RATE_LIMIT) -> bool:
    """Applies a small per-process limit to login and registration attempts."""
    client_ip = getattr(handler, "client_address", ("unknown",))[0]
    now = time.monotonic()
    cutoff = now - AUTH_RATE_WINDOW_SECONDS
    with _auth_requests_lock:
        requests = _auth_requests[(handler.path, client_ip)]
        while requests and requests[0] <= cutoff:
            requests.popleft()
        if len(requests) >= limit:
            return False
        requests.append(now)
        return True


def _parse_multipart(body: bytes, boundary: str) -> tuple[str | None, bytes | None]:
    """
    Parser manual de multipart/form-data.
    Compatível com Python 3.13+ (módulo cgi foi removido).

    Procura pelo campo 'file' e retorna (filename, content).
    Retorna (None, None) se o campo não for encontrado.
    """
    boundary_bytes = boundary.encode()

    # Dividir body nos delimitadores de boundary
    parts = body.split(b"--" + boundary_bytes)

    for part in parts:
        if b"\r\n\r\n" not in part:
            continue

        headers_raw, _, file_content = part.partition(b"\r\n\r\n")
        headers_text = headers_raw.decode("utf-8", errors="replace")

        # Verificar se é o campo 'file'
        if 'name="file"' not in headers_text:
            continue

        # Extrair filename do Content-Disposition
        filename_match = re.search(r'filename="([^"]+)"', headers_text)
        if not filename_match:
            continue

        filename = filename_match.group(1).strip()

        # Remover o \r\n final que o multipart adiciona
        if file_content.endswith(b"\r\n"):
            file_content = file_content[:-2]

        return filename, file_content

    return None, None


_migrations_initialized = False


def _ensure_migrations():
    """Garante que as tabelas do banco foram criadas, útil no ambiente Serverless da Vercel."""
    global _migrations_initialized
    if not _migrations_initialized:
        try:
            from api.database.migrations import run_migrations
            run_migrations()
            _migrations_initialized = True
        except Exception as e:
            if DEBUG:
                print(f"[db] Erro ao garantir migrations no handler: {e}")


class QuizHandler(BaseHTTPRequestHandler):
    """Handler HTTP principal com padrão Controller + Middleware"""

    def __init__(self, *args, **kwargs):
        self.quiz_controller = QuizController()
        self.upload_controller = UploadController()
        self.auth_controller = AuthController()
        super().__init__(*args, **kwargs)

    def do_OPTIONS(self):
        """Handle CORS preflight requests"""
        HTTPMiddleware.handle_preflight(self)

    def _get_request_url(self):
        """Obtém o path da requisição, compatível com rewrites e proxies da Vercel."""
        raw_path = (
            self.headers.get("x-invoke-path")
            or self.headers.get("x-forwarded-uri")
            or self.headers.get("x-matched-path")
            or self.headers.get("x-original-url")
            or self.headers.get("x-rewrite-url")
            or self.path
        )
        if raw_path in ("/api/index.py", "/api/index", "/api/index.py/", "/api/"):
            raw_path = "/"
        return urlparse(raw_path)

    def do_GET(self):
        """Handle GET requests"""
        request = self._get_request_url()
        query = parse_qs(request.query)

        if request.path.startswith("/api/"):
            _ensure_migrations()

        try:
            # 0. API: Dados do usuário autenticado
            if request.path == "/api/auth/me":
                token = HTTPMiddleware.get_auth_token(self)
                response = self.auth_controller.get_me(token)
                status, data = ResponseFormatter.success(response["data"])
                HTTPMiddleware.send_json_response(self, status, data)
                return

            # 1. API: Listar quizzes
            if request.path == "/api/quizzes":
                response = self.quiz_controller.get_quizzes()
                status, data = ResponseFormatter.success(response["data"])
                HTTPMiddleware.send_json_response(self, status, data)
                return

            # 2. API: Carregar um quiz
            if request.path == "/api/quiz":
                source_name = query.get("source", [None])[0]
                response = self.quiz_controller.get_quiz(source_name)
                status, data = ResponseFormatter.success(response["data"])
                HTTPMiddleware.send_json_response(self, status, data)
                return

            # 3. Servir HTML principal
            if request.path in ("/", "/index.html", "/api/index.py", "/api/index"):
                if not HTTPMiddleware.get_auth_token(self):
                    self.send_response(302)
                    self.send_header("Location", "/login")
                    HTTPMiddleware.add_cache_headers(self, cache=False)
                    self.end_headers()
                    return

                index_file = WEB_DIR / "index.html"
                if index_file.is_file():
                    content = index_file.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(content)))
                    HTTPMiddleware.add_cors_headers(self)
                    HTTPMiddleware.add_security_headers(self)
                    HTTPMiddleware.add_cache_headers(self, cache=False)
                    self.end_headers()
                    self.wfile.write(content)
                else:
                    status, data = ResponseFormatter.not_found("index.html não encontrado")
                    HTTPMiddleware.send_json_response(self, status, data)
                return

            # 3.1 Servir HTML de Login
            if request.path in ("/login", "/login.html"):
                login_file = WEB_DIR / "login.html"
                if login_file.is_file():
                    content = login_file.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(content)))
                    HTTPMiddleware.add_cors_headers(self)
                    HTTPMiddleware.add_security_headers(self)
                    HTTPMiddleware.add_cache_headers(self, cache=False)
                    self.end_headers()
                    self.wfile.write(content)
                else:
                    status, data = ResponseFormatter.not_found("login.html não encontrado")
                    HTTPMiddleware.send_json_response(self, status, data)
                return

            # 3.2 Servir HTML de Cadastro
            if request.path in ("/register", "/register.html"):
                register_file = WEB_DIR / "register.html"
                if register_file.is_file():
                    content = register_file.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(content)))
                    HTTPMiddleware.add_cors_headers(self)
                    HTTPMiddleware.add_security_headers(self)
                    HTTPMiddleware.add_cache_headers(self, cache=False)
                    self.end_headers()
                    self.wfile.write(content)
                else:
                    status, data = ResponseFormatter.not_found("register.html não encontrado")
                    HTTPMiddleware.send_json_response(self, status, data)
                return

            # 4. Servir arquivos estáticos /web/*
            if request.path.startswith("/web/"):
                relative_path = request.path.removeprefix("/web/").split("?", 1)[0]
                static_file = (WEB_DIR / relative_path).resolve()
                web_root = WEB_DIR.resolve()

                if web_root in static_file.parents and static_file.is_file():
                    content_type = (
                        "text/css; charset=utf-8" if static_file.suffix == ".css" else
                        "application/javascript; charset=utf-8" if static_file.suffix == ".js" else
                        "text/html; charset=utf-8" if static_file.suffix == ".html" else
                        "image/svg+xml" if static_file.suffix == ".svg" else
                        "image/png" if static_file.suffix == ".png" else
                        "application/octet-stream"
                    )
                    try:
                        content = static_file.read_bytes()
                        self.send_response(200)
                        self.send_header("Content-Type", content_type)
                        self.send_header("Content-Length", str(len(content)))
                        HTTPMiddleware.add_cors_headers(self)
                        HTTPMiddleware.add_security_headers(self)
                        HTTPMiddleware.add_cache_headers(self, cache=False)
                        self.end_headers()
                        self.wfile.write(content)
                    except Exception as e:
                        status, data = ResponseFormatter.error(f"Erro ao ler arquivo: {e}", "FILE_ERROR", 500)
                        HTTPMiddleware.send_json_response(self, status, data)
                    return
                else:
                    status, data = ResponseFormatter.not_found("Arquivo estático não encontrado")
                    HTTPMiddleware.send_json_response(self, status, data)
                    return

            # 5. Rota não encontrada
            status, data = ResponseFormatter.not_found(f"Rota {request.path} não encontrada")
            HTTPMiddleware.send_json_response(self, status, data)

        except QuizAPIException as e:
            status, data = ResponseFormatter.error(e.message, "QUIZ_ERROR", e.status_code)
            HTTPMiddleware.send_json_response(self, status, data)
        except Exception as e:
            if DEBUG:
                import traceback
                traceback.print_exc()
            status, data = ResponseFormatter.error("Erro interno do servidor", "INTERNAL_ERROR", 500)
            HTTPMiddleware.send_json_response(self, status, data)

    def do_POST(self):
        """Handle POST requests"""
        request = self._get_request_url()

        if request.path.startswith("/api/"):
            _ensure_migrations()

        try:
            # ── 0. Rotas de Autenticação ───────────────────────────────────────
            if request.path == "/api/auth/login":
                if not _allow_auth_request(self):
                    status, data = ResponseFormatter.error(
                        "Muitas tentativas. Tente novamente mais tarde.",
                        "RATE_LIMITED",
                        429,
                    )
                    HTTPMiddleware.send_json_response(self, status, data)
                    return
                length = int(self.headers.get("Content-Length", 0))
                if length > MAX_JSON_BYTES:
                    status, data = ResponseFormatter.bad_request("Corpo da requisição muito grande")
                    HTTPMiddleware.send_json_response(self, 413, data)
                    return
                try:
                    payload = json.loads(self.rfile.read(length)) if length > 0 else {}
                except json.JSONDecodeError:
                    status, data = ResponseFormatter.bad_request("JSON inválido")
                    HTTPMiddleware.send_json_response(self, status, data)
                    return
                response = self.auth_controller.login(payload)
                token = response["data"].get("token")
                status, data = ResponseFormatter.success(response["data"], response["message"])
                cookie = HTTPMiddleware.session_cookie(token, COOKIE_SECURE, 7 * 24 * 60 * 60)
                HTTPMiddleware.send_json_response(self, status, data, set_cookie=cookie)
                return

            if request.path == "/api/auth/register":
                if not _allow_auth_request(self):
                    status, data = ResponseFormatter.error(
                        "Muitas tentativas. Tente novamente mais tarde.",
                        "RATE_LIMITED",
                        429,
                    )
                    HTTPMiddleware.send_json_response(self, status, data)
                    return
                length = int(self.headers.get("Content-Length", 0))
                if length > MAX_JSON_BYTES:
                    status, data = ResponseFormatter.bad_request("Corpo da requisição muito grande")
                    HTTPMiddleware.send_json_response(self, 413, data)
                    return
                try:
                    payload = json.loads(self.rfile.read(length)) if length > 0 else {}
                except json.JSONDecodeError:
                    status, data = ResponseFormatter.bad_request("JSON inválido")
                    HTTPMiddleware.send_json_response(self, status, data)
                    return
                response = self.auth_controller.register(payload)
                status, data = ResponseFormatter.created(response["data"], response["message"])
                HTTPMiddleware.send_json_response(self, status, data)
                return

            if request.path == "/api/auth/logout":
                token = HTTPMiddleware.get_auth_token(self)
                response = self.auth_controller.logout(token)
                status, data = ResponseFormatter.success(response["data"], response["message"])
                clear_cookie = HTTPMiddleware.session_cookie(None, COOKIE_SECURE, 0)
                HTTPMiddleware.send_json_response(self, status, data, set_cookie=clear_cookie)
                return

            # ── 1. Upload de arquivo (multipart/form-data) ────────────────────
            if request.path == "/api/upload":
                self._handle_upload()
                return

            # ── 2. Submissão de respostas (application/json) ──────────────────
            if request.path == "/api/quiz/submit":
                token = HTTPMiddleware.get_auth_token(self)
                if not token or not self.auth_controller.service.validate_token(token):
                    status, data = ResponseFormatter.unauthorized("Autenticação necessária para enviar respostas")
                    HTTPMiddleware.send_json_response(self, status, data)
                    return
                if not _allow_auth_request(self, limit=30):
                    status, data = ResponseFormatter.error(
                        "Muitas submissões. Tente novamente mais tarde.",
                        "RATE_LIMITED",
                        429,
                    )
                    HTTPMiddleware.send_json_response(self, status, data)
                    return
                length = int(self.headers.get("Content-Length", 0))
                if length > MAX_JSON_BYTES:
                    status, data = ResponseFormatter.bad_request("Corpo da requisição muito grande")
                    HTTPMiddleware.send_json_response(self, 413, data)
                    return
                if length == 0:
                    status, data = ResponseFormatter.bad_request("Corpo da requisição vazio")
                    HTTPMiddleware.send_json_response(self, status, data)
                    return

                try:
                    payload = json.loads(self.rfile.read(length))
                except json.JSONDecodeError:
                    status, data = ResponseFormatter.bad_request("JSON inválido")
                    HTTPMiddleware.send_json_response(self, status, data)
                    return

                is_valid, error_msg = AnswerValidator.validate_submit_payload(payload)
                if not is_valid:
                    status, data = ResponseFormatter.bad_request(error_msg)
                    HTTPMiddleware.send_json_response(self, status, data)
                    return

                response = self.quiz_controller.submit_answers(payload)
                status, data = ResponseFormatter.success(response["data"])
                HTTPMiddleware.send_json_response(self, status, data)
                return

            # ── 3. Rota não encontrada ─────────────────────────────────────────
            status, data = ResponseFormatter.not_found(f"Rota {request.path} não encontrada")
            HTTPMiddleware.send_json_response(self, status, data)

        except QuizAPIException as e:
            status, data = ResponseFormatter.error(e.message, "QUIZ_ERROR", e.status_code)
            HTTPMiddleware.send_json_response(self, status, data)
        except Exception as e:
            if DEBUG:
                import traceback
                traceback.print_exc()
            status, data = ResponseFormatter.error("Erro interno do servidor", "INTERNAL_ERROR", 500)
            HTTPMiddleware.send_json_response(self, status, data)

    # ─── Helpers ──────────────────────────────────────────────────────────────

    def _handle_upload(self):
        """Processa upload multipart/form-data de arquivo TXT/PDF/DOCX."""
        # 0. Validação de Autenticação (Apenas Admin)
        token = HTTPMiddleware.get_auth_token(self)
        if not token:
            status, data = ResponseFormatter.unauthorized("Autenticação necessária para enviar simulados")
            HTTPMiddleware.send_json_response(self, status, data)
            return

        user = self.auth_controller.service.validate_token(token)
        if not user:
            status, data = ResponseFormatter.unauthorized("Sessão expirada ou inválida. Faça login novamente")
            HTTPMiddleware.send_json_response(self, status, data)
            return

        if user.get("role") != "admin":
            status, data = ResponseFormatter.forbidden("Apenas administradores podem fazer upload de novos simulados")
            HTTPMiddleware.send_json_response(self, status, data)
            return

        content_type = self.headers.get("Content-Type", "")
        content_length = int(self.headers.get("Content-Length", 0))

        if content_length > MAX_UPLOAD_BYTES:
            status, data = ResponseFormatter.bad_request(
                f"Arquivo muito grande. Limite: {MAX_UPLOAD_BYTES // (1024*1024)} MB"
            )
            HTTPMiddleware.send_json_response(self, status, data)
            return

        if "multipart/form-data" not in content_type:
            status, data = ResponseFormatter.bad_request(
                "Content-Type deve ser multipart/form-data"
            )
            HTTPMiddleware.send_json_response(self, status, data)
            return

        body = self.rfile.read(content_length)

        # Extrair boundary do Content-Type
        boundary_match = re.search(r"boundary=([^;\s]+)", content_type)
        if not boundary_match:
            status, data = ResponseFormatter.bad_request("multipart boundary não encontrado")
            HTTPMiddleware.send_json_response(self, status, data)
            return

        filename, file_content = _parse_multipart(body, boundary_match.group(1))

        if filename is None or file_content is None:
            status, data = ResponseFormatter.bad_request("Campo 'file' não encontrado no formulário")
            HTTPMiddleware.send_json_response(self, status, data)
            return

        if not file_content:
            status, data = ResponseFormatter.bad_request("Arquivo vazio")
            HTTPMiddleware.send_json_response(self, status, data)
            return

        # Validar extensão
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext not in ALLOWED_EXTENSIONS:
            status, data = ResponseFormatter.bad_request(
                f"Extensão '.{ext}' não suportada. Use: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
            )
            HTTPMiddleware.send_json_response(self, status, data)
            return

        # Delegar ao controller
        response = self.upload_controller.upload_file(filename, file_content, ext)
        status, data = ResponseFormatter.created(
            response["data"],
            response["data"].get("message")
        )
        HTTPMiddleware.send_json_response(self, status, data)

    def log_message(self, format, *args):
        """Custom logging para modo debug"""
        if DEBUG:
            print(f"📡 {self.command} {self.path}")
