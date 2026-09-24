"""
Handler HTTP Principal — Suporte a multipart/form-data para upload de arquivos
"""
import io
import json
import os
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


class RateLimiter:
    """
    Rate-limiter genérico com janela deslizante por chave (rota, IP, conta).
    Remove chaves expiradas automaticamente para prevenir vazamento de memória.
    """

    def __init__(self, limit: int, window_seconds: int):
        self.limit = limit
        self.window = window_seconds
        self._requests: dict = defaultdict(deque)
        self._lock = Lock()
        self._counter = 0

    def is_allowed(self, key: str) -> tuple[bool, int]:
        """
        Retorna (permitido, retry_after_segundos).
        retry_after é 0 quando a requisição é permitida.
        """
        now = time.monotonic()
        cutoff = now - self.window
        with self._lock:
            self._counter += 1
            reqs = self._requests[key]
            while reqs and reqs[0] <= cutoff:
                reqs.popleft()
            if len(reqs) >= self.limit:
                retry_after = max(1, int(reqs[0] - cutoff + 1))
                return False, retry_after
            reqs.append(now)

            # Limpeza periódica a cada 100 checagens para evitar vazamento de memória
            if self._counter % 100 == 0:
                expired = [k for k, v in self._requests.items() if not v or v[-1] <= cutoff]
                for k in expired:
                    del self._requests[k]

            return True, 0

    def check_handler(self, handler, route_key: str) -> tuple[bool, int]:
        """Extrai o IP real do handler e verifica o rate-limit."""
        client_ip = HTTPMiddleware.get_client_ip(handler)
        return self.is_allowed(f"{route_key}:{client_ip}")


# ─── Instâncias de rate-limiters por rota ────────────────────────────────────
_rl_auth = RateLimiter(limit=10, window_seconds=15 * 60)    # login/register: 10/15min
_rl_submit = RateLimiter(limit=30, window_seconds=15 * 60)  # submit: 30/15min
_rl_upload = RateLimiter(limit=5, window_seconds=60)         # upload: 5/min
_rl_generate = RateLimiter(limit=10, window_seconds=60)      # generate IA: 10/min
_rl_remix = RateLimiter(limit=10, window_seconds=60)         # remix IA: 10/min
_rl_read = RateLimiter(limit=120, window_seconds=60)         # leitura geral: 120/min


def _rate_limited_response(handler, retry_after: int) -> None:
    """Envia resposta 429 com header Retry-After."""
    from api.middleware.http_middleware import ResponseFormatter
    status, data = ResponseFormatter.error(
        f"Muitas requisições. Tente novamente em {retry_after} segundo(s).",
        "RATE_LIMITED",
        429,
    )
    handler.send_response(429)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Retry-After", str(retry_after))
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    handler.send_header("Content-Length", str(len(body)))
    HTTPMiddleware.add_cors_headers(handler)
    HTTPMiddleware.add_security_headers(handler)
    HTTPMiddleware.add_cache_headers(handler, cache=False)
    handler.end_headers()
    try:
        handler.wfile.write(body)
    except (BrokenPipeError, ConnectionAbortedError):
        pass


def _parse_multipart(body: bytes, boundary: str) -> tuple[str | None, bytes | None, dict[str, str]]:
    """
    Parser manual de multipart/form-data.
    Compatível com Python 3.13+ (módulo cgi foi removido).

    Procura pelo campo 'file' e retorna (filename, content, fields).
    """
    boundary_bytes = boundary.encode()
    fields = {}
    filename = None
    file_content = None

    # Dividir body nos delimitadores de boundary
    parts = body.split(b"--" + boundary_bytes)

    for part in parts:
        if b"\r\n\r\n" not in part:
            continue

        headers_raw, _, part_content = part.partition(b"\r\n\r\n")
        headers_text = headers_raw.decode("utf-8", errors="replace")

        field_match = re.search(r'name="([^"]+)"', headers_text)
        if not field_match:
            continue
        field_name = field_match.group(1)

        if field_name != "file":
            fields[field_name] = part_content.rstrip(b"\r\n").decode("utf-8", errors="replace")
            continue

        filename_match = re.search(r'filename="([^"]+)"', headers_text)
        if not filename_match:
            continue

        filename = filename_match.group(1).strip()

        # Remover o \r\n final que o multipart adiciona
        if part_content.endswith(b"\r\n"):
            part_content = part_content[:-2]
        file_content = part_content

    return filename, file_content, fields


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

    def setup(self):
        super().setup()
        if hasattr(self, "connection") and self.connection:
            try:
                self.connection.settimeout(30.0)
            except Exception:
                pass

    def do_OPTIONS(self):
        """Handle CORS preflight requests"""
        HTTPMiddleware.handle_preflight(self)

    def _read_body_bytes(self, max_bytes: int) -> bytes | None:
        """Lê o corpo da requisição com validação estrita de Content-Length."""
        raw_len = self.headers.get("Content-Length")
        if raw_len is None:
            status, data = ResponseFormatter.bad_request("Cabeçalho Content-Length é obrigatório")
            HTTPMiddleware.send_json_response(self, 411, data)
            return None

        try:
            length = int(raw_len.strip())
        except (ValueError, TypeError):
            status, data = ResponseFormatter.bad_request("Content-Length inválido")
            HTTPMiddleware.send_json_response(self, 400, data)
            return None

        if length <= 0:
            status, data = ResponseFormatter.bad_request("Corpo da requisição vazio ou tamanho inválido")
            HTTPMiddleware.send_json_response(self, 400, data)
            return None

        if length > max_bytes:
            status, data = ResponseFormatter.bad_request("Corpo da requisição muito grande")
            HTTPMiddleware.send_json_response(self, 413, data)
            return None

        try:
            return self.rfile.read(length)
        except Exception:
            status, data = ResponseFormatter.bad_request("Falha ao ler dados da conexão")
            HTTPMiddleware.send_json_response(self, 400, data)
            return None

    def _read_json_body(self, max_bytes: int = MAX_JSON_BYTES) -> dict | None:
        """Lê e faz parse de JSON do corpo da requisição com validação rigorosa."""
        body = self._read_body_bytes(max_bytes)
        if body is None:
            return None
        try:
            return json.loads(body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            status, data = ResponseFormatter.bad_request("JSON inválido")
            HTTPMiddleware.send_json_response(self, 400, data)
            return None

    def _get_request_url(self):
        """Obtém o path da requisição de forma segura, compatível com rewrites da Vercel."""
        raw_path = self.path or "/"

        # Só confia em headers de reescrita se explicitamente configurado no ambiente Vercel
        if os.getenv("VERCEL") == "1":
            for h in ("x-matched-path", "x-forwarded-uri"):
                val = self.headers.get(h)
                if val and val.startswith("/"):
                    raw_path = val
                    break

        parsed_path = urlparse(raw_path)
        forwarded_path = parse_qs(parsed_path.query).get("__path", [None])[0]
        if forwarded_path:
            raw_path = forwarded_path
            if parsed_path.query:
                remaining_query = parse_qs(parsed_path.query)
                remaining_query.pop("__path", None)
                query_string = "&".join(
                    f"{key}={value}"
                    for key, values in remaining_query.items()
                    for value in values
                )
                if query_string:
                    raw_path = f"{raw_path}?{query_string}"
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
                allowed, retry_after = _rl_read.check_handler(self, "GET:/api/quizzes")
                if not allowed:
                    _rate_limited_response(self, retry_after)
                    return
                user = self._get_current_user_or_none()
                user_id = user["id"] if user else None
                response = self.quiz_controller.get_quizzes(user_id)
                status, data = ResponseFormatter.success(response["data"])
                HTTPMiddleware.send_json_response(self, status, data)
                return

            # 2. API: Carregar um quiz
            if request.path == "/api/quiz":
                allowed, retry_after = _rl_read.check_handler(self, "GET:/api/quiz")
                if not allowed:
                    _rate_limited_response(self, retry_after)
                    return
                user = self._get_current_user_or_none()
                user_id = user["id"] if user else None
                source_name = query.get("source", [None])[0]
                response = self.quiz_controller.get_quiz(source_name, user_id)
                status, data = ResponseFormatter.success(response["data"])
                HTTPMiddleware.send_json_response(self, status, data)
                return

            # 2.1 API: Histórico de tentativas do usuário (Caderno de Erros)
            if request.path == "/api/user/attempts":
                user = self._get_current_user_or_none()
                if not user:
                    status, data = ResponseFormatter.success({"attempts": []})
                    HTTPMiddleware.send_json_response(self, status, data)
                    return
                allowed, retry_after = _rl_read.check_handler(self, "GET:/api/user/attempts")
                if not allowed:
                    _rate_limited_response(self, retry_after)
                    return
                response = self.quiz_controller.get_user_attempts(user["id"])
                status, data = ResponseFormatter.success(response["data"])
                HTTPMiddleware.send_json_response(self, status, data)
                return

            # 3. Servir HTML principal
            if request.path in ("/", "/guest", "/index.html", "/api/index.py", "/api/index"):
                if request.path != "/guest":
                    user = self._get_current_user_or_none()
                    if not user:
                        self.send_response(302)
                        self.send_header("Location", "/login")
                        token = HTTPMiddleware.get_auth_token(self)
                        if token:
                            clear_cookie = HTTPMiddleware.session_cookie(None, COOKIE_SECURE, 0)
                            self.send_header("Set-Cookie", clear_cookie)
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
            HTTPMiddleware.send_json_response(self, status, data, clear_cookie=(e.status_code == 401))
        except Exception as e:
            if DEBUG:
                import traceback
                traceback.print_exc()
            status, data = ResponseFormatter.error("Erro interno do servidor", "INTERNAL_ERROR", 500)
            HTTPMiddleware.send_json_response(self, status, data)

    def do_POST(self):
        """Handle POST requests"""
        request = self._get_request_url()
        query = parse_qs(request.query)

        if request.path.startswith("/api/"):
            _ensure_migrations()

        try:
            # ── 0. Rotas de Autenticação ───────────────────────────────────────
            if request.path == "/api/auth/login":
                allowed, retry_after = _rl_auth.check_handler(self, "POST:/api/auth/login")
                if not allowed:
                    _rate_limited_response(self, retry_after)
                    return

                payload = self._read_json_body()
                if payload is None:
                    return

                # Rate-limit adicional por nome de usuário para mitigar força bruta mesmo com IP dinâmico
                username = str(payload.get("username", "")).strip().lower()
                if username:
                    user_allowed, user_retry = _rl_auth.is_allowed(f"POST:/api/auth/login:user:{username}")
                    if not user_allowed:
                        _rate_limited_response(self, user_retry)
                        return

                response = self.auth_controller.login(payload)
                token = response["data"].get("token")
                status, data = ResponseFormatter.success(response["data"], response["message"])
                cookie = HTTPMiddleware.session_cookie(token, COOKIE_SECURE, 7 * 24 * 60 * 60)
                HTTPMiddleware.send_json_response(self, status, data, set_cookie=cookie)
                return

            if request.path == "/api/auth/register":
                allowed, retry_after = _rl_auth.check_handler(self, "POST:/api/auth/register")
                if not allowed:
                    _rate_limited_response(self, retry_after)
                    return

                payload = self._read_json_body()
                if payload is None:
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
                allowed, retry_after = _rl_upload.check_handler(self, "POST:/api/upload")
                if not allowed:
                    _rate_limited_response(self, retry_after)
                    return
                self._handle_upload(query.get("guest", ["0"])[0] == "1")
                return

            # ── 1.1 Gerar quiz por tema via IA (application/json) ────────────
            if request.path == "/api/quiz/generate":
                allowed, retry_after = _rl_generate.check_handler(self, "POST:/api/quiz/generate")
                if not allowed:
                    _rate_limited_response(self, retry_after)
                    return

                # Recurso de IA exige login obrigatório para proteger cotas
                user = self._require_authenticated_user()

                payload = self._read_json_body()
                if payload is None:
                    return

                topic = payload.get("topic", "").strip()
                if not topic:
                    status, data = ResponseFormatter.bad_request("O campo 'topic' (tema) é obrigatório")
                    HTTPMiddleware.send_json_response(self, status, data)
                    return

                num_questions = payload.get("num_questions", 5)
                difficulty = payload.get("difficulty", "Médio")
                context = payload.get("context", "")
                requested_public = payload.get("is_public", False) is True
                is_public = requested_public and user and user.get("role") == "admin"

                client_ip = HTTPMiddleware.get_client_ip(self)
                response = self.quiz_controller.generate_quiz_by_topic(
                    topic=topic,
                    num_questions=num_questions,
                    difficulty=difficulty,
                    context=context,
                    user_id=user["id"],
                    is_public=bool(is_public),
                    persist=True,
                    client_ip=client_ip,
                )
                status, data = ResponseFormatter.created(
                    response["data"],
                    response["data"].get("message")
                )
                HTTPMiddleware.send_json_response(self, status, data)
                return

            # ── 2. Submissão de respostas (application/json) ──────────────────
            if request.path == "/api/quiz/submit":
                allowed, retry_after = _rl_submit.check_handler(self, "POST:/api/quiz/submit")
                if not allowed:
                    _rate_limited_response(self, retry_after)
                    return
                user = self._get_current_user_or_none()
                user_id = user["id"] if user else None

                payload = self._read_json_body()
                if payload is None:
                    return

                is_valid, error_msg = AnswerValidator.validate_submit_payload(payload)
                if not is_valid:
                    status, data = ResponseFormatter.bad_request(error_msg)
                    HTTPMiddleware.send_json_response(self, status, data)
                    return

                response = self.quiz_controller.submit_answers(payload, user_id)
                status, data = ResponseFormatter.success(response["data"])
                HTTPMiddleware.send_json_response(self, status, data)
                return

            # ── 2.1 Mutação/Remix de questões erradas via IA (application/json) ──────────
            if request.path == "/api/quiz/remix-mistakes":
                allowed, retry_after = _rl_remix.check_handler(self, "POST:/api/quiz/remix-mistakes")
                if not allowed:
                    _rate_limited_response(self, retry_after)
                    return

                # Remix via IA exige usuário autenticado para proteger cota
                self._require_authenticated_user()

                payload = self._read_json_body()
                if payload is None:
                    return

                questions = payload.get("questions", [])
                if not isinstance(questions, list) or not questions:
                    status, data = ResponseFormatter.bad_request("Lista de questões 'questions' é obrigatória")
                    HTTPMiddleware.send_json_response(self, status, data)
                    return

                client_ip = HTTPMiddleware.get_client_ip(self)
                response = self.quiz_controller.remix_mistakes(questions, client_ip=client_ip)
                status, data = ResponseFormatter.success(response["data"])
                HTTPMiddleware.send_json_response(self, status, data)
                return

            # ── 3. Rota não encontrada ─────────────────────────────────────────
            status, data = ResponseFormatter.not_found(f"Rota {request.path} não encontrada")
            HTTPMiddleware.send_json_response(self, status, data)

        except QuizAPIException as e:
            status, data = ResponseFormatter.error(e.message, "QUIZ_ERROR", e.status_code)
            HTTPMiddleware.send_json_response(self, status, data, clear_cookie=(e.status_code == 401))
        except Exception as e:
            if DEBUG:
                import traceback
                traceback.print_exc()
            status, data = ResponseFormatter.error("Erro interno do servidor", "INTERNAL_ERROR", 500)
            HTTPMiddleware.send_json_response(self, status, data)

    # ─── Helpers ──────────────────────────────────────────────────────────────

    def _handle_upload(self, guest: bool = False):
        """Processa upload multipart/form-data de arquivo TXT/PDF/DOCX."""
        user = None if guest else self._require_authenticated_user()

        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            status, data = ResponseFormatter.bad_request(
                "Content-Type deve ser multipart/form-data"
            )
            HTTPMiddleware.send_json_response(self, status, data)
            return

        body = self._read_body_bytes(MAX_UPLOAD_BYTES)
        if body is None:
            return

        # Extrair boundary do Content-Type
        boundary_match = re.search(r"boundary=([^;\s]+)", content_type)
        if not boundary_match:
            status, data = ResponseFormatter.bad_request("multipart boundary não encontrado")
            HTTPMiddleware.send_json_response(self, status, data)
            return

        filename, file_content, fields = _parse_multipart(body, boundary_match.group(1))

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
        requested_public = fields.get("is_public", "false").lower() == "true"
        is_public = requested_public and user and user.get("role") == "admin"
        client_ip = HTTPMiddleware.get_client_ip(self)
        response = self.upload_controller.upload_file(
            filename,
            file_content,
            ext,
            user["id"] if user else None,
            bool(is_public),
            persist=not guest,
            client_ip=client_ip,
        )
        status, data = ResponseFormatter.created(
            response["data"],
            response["data"].get("message")
        )
        HTTPMiddleware.send_json_response(self, status, data)

    def _get_current_user_or_none(self):
        """Retorna o usuário autenticado ou None se não houver token válido (convidado)."""
        token = HTTPMiddleware.get_auth_token(self)
        if not token:
            return None
        return self.auth_controller.service.validate_token(token)

    def _require_authenticated_user(self):
        token = HTTPMiddleware.get_auth_token(self)
        user = self.auth_controller.service.validate_token(token)
        if not user:
            raise QuizAPIException("Autenticação necessária", 401)
        return user

    def log_message(self, format, *args):
        """Custom logging para modo debug"""
        if DEBUG:
            print(f"📡 {self.command} {self.path}")
