"""Middleware HTTP: CORS, cache, formatação de respostas e decorators utilitários"""
import json
import time
from functools import wraps
from api.utils.config import DEBUG, ALLOWED_ORIGINS


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
        if "*" in ALLOWED_ORIGINS or not ALLOWED_ORIGINS:
            allow_origin = "*"
        elif origin in ALLOWED_ORIGINS:
            allow_origin = origin
        else:
            allow_origin = ALLOWED_ORIGINS[0] if ALLOWED_ORIGINS else "*"

        handler.send_header("Access-Control-Allow-Origin", allow_origin)
        handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, DELETE")
        handler.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With")

    @staticmethod
    def add_cache_headers(handler, cache: bool = False) -> None:
        value = "public, max-age=3600" if cache else "no-store, no-cache, must-revalidate"
        handler.send_header("Cache-Control", value)

    @staticmethod
    def get_bearer_token(handler) -> str | None:
        """Extrai o Bearer token do header Authorization."""
        auth_header = handler.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return auth_header[7:].strip()
        return None

    @staticmethod
    def get_client_ip(handler) -> str:
        """
        Obtém o IP real do cliente, priorizando o cabeçalho Cloudflare (CF-Connecting-IP),
        seguido de X-Forwarded-For e por fim o socket local.
        """
        cf_ip = handler.headers.get("CF-Connecting-IP")
        if cf_ip:
            return cf_ip.strip()

        x_forwarded = handler.headers.get("X-Forwarded-For")
        if x_forwarded:
            return x_forwarded.split(",")[0].strip()

        return getattr(handler, "client_address", ("unknown",))[0]

    @staticmethod
    def send_json_response(handler, status: int, data: dict) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Content-Length", str(len(body)))
        HTTPMiddleware.add_cors_headers(handler)
        HTTPMiddleware.add_cache_headers(handler, cache=False)
        handler.end_headers()
        handler.wfile.write(body)

    @staticmethod
    def handle_preflight(handler) -> None:
        handler.send_response(204)
        HTTPMiddleware.add_cors_headers(handler)
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

