"""Middleware HTTP: CORS, cache, formatação de respostas e decorators utilitários"""
import json
import time
from http.cookies import SimpleCookie
from functools import wraps
from api.utils.config import DEBUG, ALLOWED_ORIGINS, COOKIE_SECURE


def timing_decorator(func):
    """Mede e loga o tempo de execução de um método (apenas em modo DEBUG)."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        if DEBUG:
            print(f"[timing] {func.__name__}: {time.time() - start:.3f}s")
        return result
    return wrapper


def error_handler_decorator(func):
    """Captura e reloga exceções (apenas em modo DEBUG) antes de relançá-las."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if DEBUG:
                print(f"[error] {func.__name__}: {e}")
            raise
    return wrapper


class HTTPMiddleware:
    """Helpers para headers, autenticação e envio de respostas HTTP."""

    @staticmethod
    def add_cors_headers(handler) -> None:
        origin = handler.headers.get("Origin", "")
        if origin and origin in ALLOWED_ORIGINS:
            handler.send_header("Access-Control-Allow-Origin", origin)
            handler.send_header("Access-Control-Allow-Credentials", "true")
            handler.send_header("Vary", "Origin")
            handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, DELETE")
            handler.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With")

    @staticmethod
    def add_security_headers(handler) -> None:
        handler.send_header("X-Content-Type-Options", "nosniff")
        handler.send_header("X-Frame-Options", "DENY")
        handler.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        handler.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        handler.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' https://va.vercel-scripts.com; style-src 'self'; img-src 'self' data:; connect-src 'self' https://vitals.vercel-insights.com; object-src 'none'; base-uri 'self'; frame-ancestors 'none'")
        handler.send_header("Strict-Transport-Security", "max-age=63072000; includeSubDomains; preload")

    @staticmethod
    def add_cache_headers(handler, cache: bool = False) -> None:
        value = "public, max-age=3600" if cache else "no-store, no-cache, must-revalidate"
        handler.send_header("Cache-Control", value)

    @staticmethod
    def get_bearer_token(handler) -> str | None:
        """Extrai o Bearer token do header Authorization."""
        auth_header = handler.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return str(auth_header[7:].strip())
        return None

    @staticmethod
    def get_auth_token(handler) -> str | None:
        """Reads the legacy Bearer token or the HttpOnly session cookie."""
        bearer_token = HTTPMiddleware.get_bearer_token(handler)
        if bearer_token:
            return bearer_token
        cookies = SimpleCookie()
        cookies.load(handler.headers.get("Cookie", ""))
        session_cookie = cookies.get("ifuture_session")
        return session_cookie.value if session_cookie else None

    @staticmethod
    def _cookie(name: str, value: str | None, secure: bool, max_age: int) -> str:
        attributes = ["Path=/", "HttpOnly", "SameSite=Lax", f"Max-Age={max_age}"]
        if secure:
            attributes.append("Secure")
        return f"{name}={value or ''}; " + "; ".join(attributes)

    @staticmethod
    def session_cookie(token: str | None, secure: bool, max_age: int) -> str:
        return HTTPMiddleware._cookie("ifuture_session", token, secure, max_age)

    @staticmethod
    def guest_cookie(guest_id: str | None, secure: bool, max_age: int) -> str:
        """Cookie HttpOnly do modo convidado (identificador aleatório, sem dados pessoais)."""
        from api.services.guest_service import GUEST_COOKIE_NAME
        return HTTPMiddleware._cookie(GUEST_COOKIE_NAME, guest_id, secure, max_age)

    @staticmethod
    def get_guest_id(handler) -> str | None:
        """Lê o identificador de convidado do cookie; valores fora do formato são ignorados."""
        from api.services.guest_service import GUEST_COOKIE_NAME, GuestService
        cookies = SimpleCookie()
        try:
            cookies.load(handler.headers.get("Cookie", ""))
        except Exception:
            return None
        morsel = cookies.get(GUEST_COOKIE_NAME)
        value = morsel.value if morsel else None
        return value if GuestService.is_valid_guest_id(value) else None

    @staticmethod
    def is_cross_site_request(handler) -> bool:
        """True quando um POST vem de outro site (defesa extra além do SameSite=Lax).

        Navegadores enviam `Origin` em POSTs e `Sec-Fetch-Site`; clientes sem navegador
        (curl, testes) não enviam nenhum dos dois e continuam funcionando. Origens de
        ALLOWED_ORIGINS (CORS configurado) são aceitas.
        """
        from urllib.parse import urlparse
        from api.utils.config import TRUST_PROXY

        fetch_site = (handler.headers.get("Sec-Fetch-Site") or "").lower()
        if fetch_site == "cross-site":
            origin = handler.headers.get("Origin", "")
            return origin not in ALLOWED_ORIGINS

        origin = handler.headers.get("Origin")
        if not origin or origin == "null":
            return bool(origin)  # "null" (iframe sandbox, file://) é tratado como outro site
        if origin in ALLOWED_ORIGINS:
            return False

        host = handler.headers.get("Host", "")
        if TRUST_PROXY:
            host = handler.headers.get("X-Forwarded-Host", host) or host
        origin_host = urlparse(origin).netloc
        return bool(host) and origin_host.lower() != host.split(",")[0].strip().lower()

    @staticmethod
    def get_client_ip(handler) -> str:
        """
        Obtém o IP real do cliente.
        Se TRUST_PROXY estiver ativo (ou em ambiente Vercel), confia em CF-Connecting-IP
        e X-Forwarded-For. Caso contrário, utiliza estritamente o endereço de socket direto
        para impedir spoofing de cabeçalhos por clientes não autenticados.
        """
        import os
        from api.utils.config import TRUST_PROXY
        socket_ip = getattr(handler, "client_address", ("unknown",))[0]
        if not TRUST_PROXY:
            return socket_ip

        # Na Vercel, o X-Forwarded-For é reescrito pela plataforma (não aceita IP externo),
        # mas um CF-Connecting-IP enviado pelo cliente passa direto: confiar nele deixaria
        # qualquer pessoa trocar de "IP" a cada requisição e furar rate limits e o teto
        # por IP do convidado. Lá, só os cabeçalhos da própria Vercel valem.
        if os.getenv("VERCEL") == "1":
            for header in ("x-vercel-forwarded-for", "x-real-ip", "X-Forwarded-For"):
                value = handler.headers.get(header)
                if value:
                    return str(value.split(",")[0].strip())
            return socket_ip

        cf_ip = handler.headers.get("CF-Connecting-IP")
        if cf_ip:
            return str(cf_ip.strip())

        x_forwarded = handler.headers.get("X-Forwarded-For")
        if x_forwarded:
            return str(x_forwarded.split(",")[0].strip())

        return socket_ip

    @staticmethod
    def send_json_response(
        handler,
        status: int,
        data: dict,
        set_cookie: str | list[str] | None = None,
        clear_cookie: bool = False
    ) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")

        handler.send_response(status)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Content-Length", str(len(body)))

        if set_cookie:
            for cookie in ([set_cookie] if isinstance(set_cookie, str) else set_cookie):
                handler.send_header("Set-Cookie", cookie)
        elif clear_cookie:
            handler.send_header(
                "Set-Cookie",
                HTTPMiddleware.session_cookie(None, COOKIE_SECURE, 0)
            )

        HTTPMiddleware.add_cors_headers(handler)
        HTTPMiddleware.add_security_headers(handler)
        HTTPMiddleware.add_cache_headers(handler, cache=False)
        handler.end_headers()

        try:
            handler.wfile.write(body)
        except (BrokenPipeError, ConnectionAbortedError):
            return

    @staticmethod
    def send_cached_json_response(
        handler,
        status: int,
        data: dict,
        max_age: int = 60,
    ) -> None:
        """
        Envia resposta JSON com suporte a ETag e validação condicional If-None-Match.
        Se o cliente já possuir a versão mais recente em cache, responde com HTTP 304 Not Modified.
        """
        import hashlib
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        etag = f'"{hashlib.sha256(body).hexdigest()[:16]}"'

        client_etag = handler.headers.get("If-None-Match")
        if client_etag and client_etag.strip() == etag:
            handler.send_response(304)
            handler.send_header("ETag", etag)
            handler.send_header("Cache-Control", f"private, max-age={max_age}, must-revalidate")
            HTTPMiddleware.add_cors_headers(handler)
            HTTPMiddleware.add_security_headers(handler)
            handler.end_headers()
            return

        handler.send_response(status)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Content-Length", str(len(body)))
        handler.send_header("ETag", etag)
        handler.send_header("Cache-Control", f"private, max-age={max_age}, must-revalidate")

        HTTPMiddleware.add_cors_headers(handler)
        HTTPMiddleware.add_security_headers(handler)
        handler.end_headers()

        try:
            handler.wfile.write(body)
        except (BrokenPipeError, ConnectionAbortedError):
            return

    @staticmethod
    def handle_preflight(handler) -> None:
        handler.send_response(204)
        HTTPMiddleware.add_cors_headers(handler)
        HTTPMiddleware.add_security_headers(handler)
        handler.end_headers()


class ResponseFormatter:
    """Formata respostas JSON consistentes para todos os endpoints."""

    @staticmethod
    def success(data=None, message: str = "OK", status_code: int = 200):
        payload = {
            "status": "success",
            "message": message,
            "data": data if data is not None else {},
        }
        # Expõe as chaves do data no nível raiz para compatibilidade com o cliente
        if isinstance(data, dict):
            for key, val in data.items():
                if key not in payload:
                    payload[key] = val
        return status_code, payload

    @staticmethod
    def error(message: str, error_code: str = "ERROR", status_code: int = 400):
        return status_code, {"status": "error", "error": error_code, "message": message}

    @staticmethod
    def created(data, message: str = "Criado com sucesso"):
        return ResponseFormatter.success(data, message, 201)

    @staticmethod
    def not_found(message: str = "Recurso não encontrado"):
        return ResponseFormatter.error(message, "NOT_FOUND", 404)

    @staticmethod
    def bad_request(message: str = "Requisição inválida"):
        return ResponseFormatter.error(message, "BAD_REQUEST", 400)

    @staticmethod
    def unauthorized(message: str = "Autenticação necessária"):
        return ResponseFormatter.error(message, "UNAUTHORIZED", 401)

    @staticmethod
    def forbidden(message: str = "Acesso negado: privilégios insuficientes"):
        return ResponseFormatter.error(message, "FORBIDDEN", 403)

