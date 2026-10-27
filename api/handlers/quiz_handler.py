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

from api.utils.config import WEB_DIR, DEBUG, COOKIE_SECURE, AUTO_MIGRATE, PORT
from api.controllers.quiz_controller import QuizController, UploadController
from api.controllers.auth_controller import AuthController
from api.exceptions.quiz_exceptions import QuizAPIException, AuthOrGuestRequired
from api.services.guest_service import guest_service, GUEST_COOKIE_MAX_AGE
from api.middleware.http_middleware import HTTPMiddleware, ResponseFormatter
from api.utils.validators import AnswerValidator
from api.repositories.rate_limit_repository import rate_limit_repo, RateLimitRepository

# Extensões permitidas para upload
ALLOWED_EXTENSIONS = {"txt", "pdf", "docx"}
MAX_UPLOAD_BYTES = 20 * 1024 * 1024        # 20 MB (autenticado)
MAX_GUEST_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB (convidado)
MAX_JSON_BYTES = 256 * 1024


class RateLimiter:
    """
    Rate-limiter genérico com janela deslizante por chave (rota, IP, conta).
    Suporta persistência via RateLimitRepository para cross-process/serverless
    e mantém execução rápida e isolada em memória quando repo=None (ex: testes).
    """

    def __init__(self, limit: int, window_seconds: int, repo: RateLimitRepository | None = None):
        self.limit = limit
        self.window = window_seconds
        self.repo = repo
        self._requests: dict = defaultdict(deque)
        self._lock = Lock()
        self._counter = 0

    def is_allowed(self, key: str) -> tuple[bool, int]:
        """
        Retorna (permitido, retry_after_segundos).
        retry_after é 0 quando a requisição é permitida.
        """
        now = time.time()
        cutoff = now - self.window
        with self._lock:
            self._counter += 1
            reqs = self._requests[key]
            while reqs and reqs[0] <= cutoff:
                reqs.popleft()
            if len(reqs) >= self.limit:
                retry_after = max(1, int(reqs[0] - cutoff + 1))
                return False, retry_after

        if self.repo is not None:
            allowed, retry_after = self.repo.check_and_record(key, self.limit, self.window, cost=1)
            if not allowed:
                return False, retry_after

        with self._lock:
            reqs.append(now)
            if self._counter % 100 == 0:
                expired = [k for k, v in self._requests.items() if not v or v[-1] <= cutoff]
                for k in expired:
                    del self._requests[k]

        return True, 0

    def is_blocked(self, key: str) -> tuple[bool, int]:
        """
        Retorna (bloqueado, retry_after_segundos) sem registrar consumo.
        """
        now = time.time()
        cutoff = now - self.window
        with self._lock:
            reqs = self._requests[key]
            while reqs and reqs[0] <= cutoff:
                reqs.popleft()
            if len(reqs) >= self.limit:
                retry_after = max(1, int(reqs[0] - cutoff + 1))
                return True, retry_after

        if self.repo is not None:
            return self.repo.is_blocked(key, self.limit, self.window)

        return False, 0

    def record(self, key: str, cost: int = 1) -> None:
        """Registra uma ocorrência/falha para a chave."""
        now = time.time()
        with self._lock:
            self._requests[key].append(now)
        if self.repo is not None:
            self.repo.record(key, cost)

    def reset(self, key: str) -> None:
        """Reseta registros da chave (ex: após login bem-sucedido)."""
        with self._lock:
            self._requests.pop(key, None)
        if self.repo is not None:
            self.repo.reset(key)

    def check_handler(self, handler, route_key: str) -> tuple[bool, int]:
        """Extrai o IP real do handler e verifica o rate-limit."""
        client_ip = HTTPMiddleware.get_client_ip(handler)
        return self.is_allowed(f"{route_key}:{client_ip}")


# ─── Instâncias de rate-limiters por rota com persistência compartilhada ─────
_rl_auth = RateLimiter(limit=10, window_seconds=15 * 60, repo=rate_limit_repo)    # cadastro/geral: 10/15min
_rl_forgot_password = RateLimiter(limit=5, window_seconds=15 * 60, repo=rate_limit_repo) # esqueci senha: 5/15min
_rl_reset_password = RateLimiter(limit=10, window_seconds=15 * 60, repo=rate_limit_repo) # redefinir senha: 10/15min
_rl_login_fail_user_ip = RateLimiter(limit=10, window_seconds=15 * 60, repo=rate_limit_repo)  # falhas por (IP + User): 10/15min
_rl_login_fail_ip = RateLimiter(limit=30, window_seconds=15 * 60, repo=rate_limit_repo)       # falhas por IP (anti-varredura): 30/15min
_rl_submit = RateLimiter(limit=30, window_seconds=15 * 60, repo=rate_limit_repo)  # submit: 30/15min
_rl_upload = RateLimiter(limit=5, window_seconds=60, repo=rate_limit_repo)         # upload: 5/min
_rl_generate = RateLimiter(limit=10, window_seconds=60, repo=rate_limit_repo)      # generate IA: 10/min
_rl_remix = RateLimiter(limit=10, window_seconds=60, repo=rate_limit_repo)         # remix IA: 10/min
_rl_read = RateLimiter(limit=120, window_seconds=60, repo=rate_limit_repo)         # leitura geral: 120/min
# novas sessões de convidado: 60/15min por IP. Folgado para uma sala de aula atrás do mesmo IP;
# quem renova o cookie para ganhar cota esbarra no teto por IP do GuestService (GUEST_AI_IP_LIMIT).
_rl_guest_start = RateLimiter(limit=60, window_seconds=15 * 60, repo=rate_limit_repo)


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
    if not AUTO_MIGRATE:
        return
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
            parsed = json.loads(body.decode("utf-8"))
            if isinstance(parsed, dict):
                return parsed
            status, data = ResponseFormatter.bad_request("JSON deve ser um objeto")
            HTTPMiddleware.send_json_response(self, 400, data)
            return None
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

            # 0.1 API: Validar token de recuperação de senha
            if request.path == "/api/auth/verify-reset-token":
                token = query.get("token", [None])[0]
                response = self.auth_controller.verify_reset_token(token)
                status, data = ResponseFormatter.success(response["data"])
                HTTPMiddleware.send_json_response(self, status, data)
                return

            # 0.2 API: Situação do modo convidado e cota gratuita de IA
            if request.path == "/api/guest/status":
                allowed, retry_after = _rl_read.check_handler(self, "GET:/api/guest/status")
                if not allowed:
                    _rate_limited_response(self, retry_after)
                    return
                guest_id = HTTPMiddleware.get_guest_id(self)
                client_ip = HTTPMiddleware.get_client_ip(self)
                status, data = ResponseFormatter.success({
                    "active": bool(guest_id),
                    "ai": guest_service.status(guest_id, client_ip),
                })
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
                HTTPMiddleware.send_cached_json_response(self, status, data, max_age=60)
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
                HTTPMiddleware.send_cached_json_response(self, status, data, max_age=120)
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

            # 3. Servir HTML principal — aberto a todos (sem muro de login).
            # O login só é pedido quando a pessoa tenta uma ação que precisa de conta
            # ou de sessão de convidado (ex.: usar a IA); isso é decidido no cliente
            # e garantido no servidor pelos endpoints de cada ação.
            if request.path in ("/", "/guest", "/index.html", "/api/index.py", "/api/index"):
                index_file = WEB_DIR / "index.html"
                if index_file.is_file():
                    content = index_file.read_bytes()
                    # Cookie de sessão expirado/inválido: limpa para o cliente começar como visitante.
                    # Se o banco estiver fora, mantém o cookie (pode ser uma sessão válida).
                    clear_session = False
                    token = HTTPMiddleware.get_auth_token(self)
                    if token:
                        try:
                            clear_session = not self.auth_controller.service.validate_token(token)
                        except Exception:
                            clear_session = False
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(content)))
                    if clear_session:
                        self.send_header("Set-Cookie", HTTPMiddleware.session_cookie(None, COOKIE_SECURE, 0))
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

            # 3.2.1 Servir HTML de Recuperação de Senha
            if request.path in ("/reset-password", "/reset-password.html", "/recuperar-senha", "/recuperar-senha.html"):
                reset_file = WEB_DIR / "reset-password.html"
                if reset_file.is_file():
                    content = reset_file.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(content)))
                    HTTPMiddleware.add_cors_headers(self)
                    HTTPMiddleware.add_security_headers(self)
                    HTTPMiddleware.add_cache_headers(self, cache=False)
                    self.end_headers()
                    self.wfile.write(content)
                else:
                    status, data = ResponseFormatter.not_found("reset-password.html não encontrado")
                    HTTPMiddleware.send_json_response(self, status, data)
                return

            # 3.3 Servir Favicon na raiz (/favicon.ico, /favicon.svg, /favicon.png, /apple-touch-icon.png)
            if request.path in ("/favicon.ico", "/favicon.svg", "/favicon.png", "/apple-touch-icon.png"):
                fav_name = request.path.lstrip("/").split("?", 1)[0]
                fav_file = (WEB_DIR / "icons" / fav_name).resolve()
                if fav_file.is_file():
                    content = fav_file.read_bytes()
                    mime = (
                        "image/svg+xml" if fav_file.suffix == ".svg" else
                        "image/png" if fav_file.suffix == ".png" else
                        "image/x-icon" if fav_file.suffix == ".ico" else
                        "application/octet-stream"
                    )
                    self.send_response(200)
                    self.send_header("Content-Type", mime)
                    self.send_header("Content-Length", str(len(content)))
                    HTTPMiddleware.add_cors_headers(self)
                    HTTPMiddleware.add_security_headers(self)
                    HTTPMiddleware.add_cache_headers(self, cache=True)
                    self.end_headers()
                    self.wfile.write(content)
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
                        "image/x-icon" if static_file.suffix == ".ico" else
                        "font/woff2" if static_file.suffix == ".woff2" else
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
            status, data = ResponseFormatter.error(e.message, e.error_code, e.status_code)
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
                payload = self._read_json_body()
                if payload is None:
                    return

                client_ip = HTTPMiddleware.get_client_ip(self)
                username = str(payload.get("username", "")).strip().lower()

                fail_user_ip_key = f"POST:/api/auth/login:fail:{client_ip}:{username}" if username else None
                fail_ip_key = f"POST:/api/auth/login:fail_ip:{client_ip}"

                # 1. Verifica se o par (IP + Usuário) ou o IP excedeu a cota de falhas consecutivas
                if fail_user_ip_key:
                    blocked, retry_after = _rl_login_fail_user_ip.is_blocked(fail_user_ip_key)
                    if blocked:
                        _rate_limited_response(self, retry_after)
                        return

                blocked_ip, retry_after_ip = _rl_login_fail_ip.is_blocked(fail_ip_key)
                if blocked_ip:
                    _rate_limited_response(self, retry_after_ip)
                    return

                # 2. Executa a autenticação e contabiliza tentativas apenas em caso de falha
                try:
                    response = self.auth_controller.login(payload)
                except QuizAPIException as e:
                    if e.status_code == 401:
                        if fail_user_ip_key:
                            _rl_login_fail_user_ip.record(fail_user_ip_key)
                        _rl_login_fail_ip.record(fail_ip_key)
                    raise

                # 3. Em caso de sucesso, logins válidos não gastam cota (mitiga problemas em NAT/escolas)
                # e resetam o histórico de falhas daquele IP para o usuário legítimo.
                if fail_user_ip_key:
                    _rl_login_fail_user_ip.reset(fail_user_ip_key)

                token = response["data"].get("token")
                status, data = ResponseFormatter.success(response["data"], response["message"])
                cookies = [
                    HTTPMiddleware.session_cookie(token, COOKIE_SECURE, 7 * 24 * 60 * 60),
                    # Ao entrar na conta, a sessão de convidado deixa de valer
                    HTTPMiddleware.guest_cookie(None, COOKIE_SECURE, 0),
                ]
                HTTPMiddleware.send_json_response(self, status, data, set_cookie=cookies)
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
                cookies = [
                    HTTPMiddleware.session_cookie(None, COOKIE_SECURE, 0),
                    HTTPMiddleware.guest_cookie(None, COOKIE_SECURE, 0),
                ]
                HTTPMiddleware.send_json_response(self, status, data, set_cookie=cookies)
                return

            # ── 0.1 Modo convidado ─────────────────────────────────────────────
            if request.path == "/api/guest/start":
                if self._get_current_user_or_none():
                    status, data = ResponseFormatter.error(
                        "Você já está conectado à sua conta.", "ALREADY_AUTHENTICATED", 409
                    )
                    HTTPMiddleware.send_json_response(self, status, data)
                    return

                client_ip = HTTPMiddleware.get_client_ip(self)
                guest_id = HTTPMiddleware.get_guest_id(self)
                if not guest_id:
                    # Só novas sessões gastam o limite: reabrir a mesma sessão é livre
                    allowed, retry_after = _rl_guest_start.check_handler(self, "POST:/api/guest/start")
                    if not allowed:
                        _rate_limited_response(self, retry_after)
                        return
                    guest_id = guest_service.new_guest_id()

                status, data = ResponseFormatter.success(
                    {"active": True, "ai": guest_service.status(guest_id, client_ip)},
                    "Modo convidado ativado",
                )
                cookie = HTTPMiddleware.guest_cookie(guest_id, COOKIE_SECURE, GUEST_COOKIE_MAX_AGE)
                HTTPMiddleware.send_json_response(self, status, data, set_cookie=cookie)
                return

            if request.path == "/api/guest/end":
                status, data = ResponseFormatter.success({"active": False}, "Modo convidado encerrado")
                cookie = HTTPMiddleware.guest_cookie(None, COOKIE_SECURE, 0)
                HTTPMiddleware.send_json_response(self, status, data, set_cookie=cookie)
                return

            if request.path == "/api/auth/forgot-password":
                allowed, retry_after = _rl_forgot_password.check_handler(self, "POST:/api/auth/forgot-password")
                if not allowed:
                    _rate_limited_response(self, retry_after)
                    return

                payload = self._read_json_body()
                if payload is None:
                    return

                host = self.headers.get("Host", f"localhost:{PORT}")
                proto = "https" if (self.headers.get("X-Forwarded-Proto") == "https" or COOKIE_SECURE) else "http"
                app_url = os.getenv("APP_URL", f"{proto}://{host}").rstrip("/")

                response = self.auth_controller.forgot_password(payload, app_url=app_url)
                status, data = ResponseFormatter.success(response["data"], response["message"])
                HTTPMiddleware.send_json_response(self, status, data)
                return

            if request.path == "/api/auth/reset-password":
                allowed, retry_after = _rl_reset_password.check_handler(self, "POST:/api/auth/reset-password")
                if not allowed:
                    _rate_limited_response(self, retry_after)
                    return

                payload = self._read_json_body()
                if payload is None:
                    return

                response = self.auth_controller.reset_password(payload)
                status, data = ResponseFormatter.success(response["data"], response["message"])
                HTTPMiddleware.send_json_response(self, status, data)
                return

            # ── 1. Upload de arquivo (multipart/form-data) ────────────────────
            if request.path == "/api/upload":
                allowed, retry_after = _rl_upload.check_handler(self, "POST:/api/upload")
                if not allowed:
                    _rate_limited_response(self, retry_after)
                    return
                # O parâmetro legado ?guest=1 é ignorado: quem decide é a sessão
                self._handle_upload()
                return

            # ── 1.1 Gerar quiz por tema via IA (application/json) ────────────
            if request.path == "/api/quiz/generate":
                allowed, retry_after = _rl_generate.check_handler(self, "POST:/api/quiz/generate")
                if not allowed:
                    _rate_limited_response(self, retry_after)
                    return

                # IA exige conta ou sessão de convidado (com cota gratuita)
                user, guest_id = self._require_user_or_guest()

                payload = self._read_json_body()
                if payload is None:
                    return

                topic = str(payload.get("topic", "")).strip()
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
                reservation = self._reserve_guest_ai(guest_id, client_ip)
                try:
                    response = self.quiz_controller.generate_quiz_by_topic(
                        topic=topic,
                        num_questions=num_questions,
                        difficulty=difficulty,
                        context=context,
                        user_id=user["id"] if user else None,
                        is_public=bool(is_public),
                        persist=bool(user),
                        client_ip=client_ip,
                    )
                except Exception:
                    if reservation:
                        reservation.refund()
                    raise
                if guest_id:
                    response["data"]["guest_ai"] = guest_service.status(guest_id, client_ip)
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

                # Remix via IA exige conta ou sessão de convidado (com cota gratuita)
                _user, guest_id = self._require_user_or_guest()

                payload = self._read_json_body()
                if payload is None:
                    return

                questions = payload.get("questions", [])
                if not isinstance(questions, list) or not questions:
                    status, data = ResponseFormatter.bad_request("Lista de questões 'questions' é obrigatória")
                    HTTPMiddleware.send_json_response(self, status, data)
                    return

                client_ip = HTTPMiddleware.get_client_ip(self)
                reservation = self._reserve_guest_ai(guest_id, client_ip)
                try:
                    response = self.quiz_controller.remix_mistakes(questions, client_ip=client_ip)
                except Exception:
                    if reservation:
                        reservation.refund()
                    raise
                if guest_id:
                    response["data"]["guest_ai"] = guest_service.status(guest_id, client_ip)
                status, data = ResponseFormatter.success(response["data"])
                HTTPMiddleware.send_json_response(self, status, data)
                return

            # ── 3. Rota não encontrada ─────────────────────────────────────────
            status, data = ResponseFormatter.not_found(f"Rota {request.path} não encontrada")
            HTTPMiddleware.send_json_response(self, status, data)

        except QuizAPIException as e:
            status, data = ResponseFormatter.error(e.message, e.error_code, e.status_code)
            HTTPMiddleware.send_json_response(self, status, data, clear_cookie=(e.status_code == 401))
        except Exception as e:
            if DEBUG:
                import traceback
                traceback.print_exc()
            status, data = ResponseFormatter.error("Erro interno do servidor", "INTERNAL_ERROR", 500)
            HTTPMiddleware.send_json_response(self, status, data)

    # ─── Helpers ──────────────────────────────────────────────────────────────

    def _handle_upload(self):
        """Processa upload multipart/form-data de arquivo TXT/PDF/DOCX.

        Com conta: salva no banco. Sem conta: o quiz volta só para o navegador
        (limite de 5 MB) e, se o arquivo precisar de IA, usa a cota do convidado.
        """
        user = self._get_current_user_or_none()
        guest = user is None

        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            status, data = ResponseFormatter.bad_request(
                "Content-Type deve ser multipart/form-data"
            )
            HTTPMiddleware.send_json_response(self, status, data)
            return

        limit_bytes = MAX_GUEST_UPLOAD_BYTES if guest else MAX_UPLOAD_BYTES
        raw_len = self.headers.get("Content-Length")
        if raw_len:
            try:
                if int(raw_len.strip()) > limit_bytes:
                    mb = limit_bytes // (1024 * 1024)
                    status, data = ResponseFormatter.bad_request(
                        f"Arquivo excede o limite máximo permitido de {mb} MB"
                        + (" para convidados. Faça login para enviar até 20 MB." if guest else "")
                    )
                    HTTPMiddleware.send_json_response(self, 413, data)
                    return
            except (ValueError, TypeError):
                pass

        body = self._read_body_bytes(limit_bytes)
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
        num_questions = fields.get("num_questions", "auto")
        context = fields.get("context", "")
        client_ip = HTTPMiddleware.get_client_ip(self)
        guest_id = HTTPMiddleware.get_guest_id(self) if guest else None
        reservation = guest_service.reservation(guest_id, client_ip) if guest_id else None
        try:
            response = self.upload_controller.upload_file(
                filename,
                file_content,
                ext,
                user["id"] if user else None,
                bool(is_public),
                persist=not guest,
                client_ip=client_ip,
                num_questions=num_questions,
                context=context,
                ai_gate=reservation.acquire if reservation else None,
            )
        except Exception:
            if reservation:
                reservation.refund()
            raise
        if guest_id:
            response["data"]["guest_ai"] = guest_service.status(guest_id, client_ip)
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

    def _require_user_or_guest(self):
        """Retorna (usuário, None) com conta ou (None, guest_id) com sessão de convidado."""
        user = self._get_current_user_or_none()
        if user:
            return user, None
        guest_id = HTTPMiddleware.get_guest_id(self)
        if not guest_id:
            raise AuthOrGuestRequired()
        return None, guest_id

    @staticmethod
    def _reserve_guest_ai(guest_id: str | None, client_ip: str):
        """Reserva um uso de IA da cota do convidado (nada a fazer para quem tem conta)."""
        if not guest_id:
            return None
        reservation = guest_service.reservation(guest_id, client_ip)
        reservation.acquire()
        return reservation

    def _require_authenticated_user(self):
        token = HTTPMiddleware.get_auth_token(self)
        if not token:
            raise QuizAPIException("Autenticação necessária", 401)
        user = self.auth_controller.service.validate_token(token)
        if not user:
            raise QuizAPIException("Autenticação necessária", 401)
        return user

    def log_message(self, format, *args):
        """Custom logging para modo debug"""
        if DEBUG:
            print(f"📡 {self.command} {self.path}")
