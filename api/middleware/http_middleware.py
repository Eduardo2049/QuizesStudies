"""
Middleware e Decorators - Padrão Spring Interceptor
Centraliza lógica transversal (logging, CORS, autenticação)
"""
import json
import time
from functools import wraps
from api.utils.config import DEBUG


def timing_decorator(func):
    """Decorator que mede tempo de execução"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        elapsed = time.time() - start
        if DEBUG:
            print(f"⏱️  {func.__name__} levou {elapsed:.3f}s")
        return result
    return wrapper


def error_handler_decorator(func):
    """Decorator que captura e loga erros"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if DEBUG:
                print(f"❌ Erro em {func.__name__}: {str(e)}")
            raise
    return wrapper


class HTTPMiddleware:
    """Middleware para requisições HTTP"""

    @staticmethod
    def add_cors_headers(handler):
        """
        Adiciona headers CORS a uma resposta.
        
        Args:
            handler: BaseHTTPRequestHandler
        """
        handler.send_header("Access-Control-Allow-Origin", "*")
        handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        handler.send_header("Access-Control-Allow-Headers", "Content-Type")

    @staticmethod
    def add_cache_headers(handler, cache=False):
        """
        Adiciona headers de cache.
        
        Args:
            handler: BaseHTTPRequestHandler
            cache: Se deve cachear (padrão False para API)
        """
        if cache:
            handler.send_header("Cache-Control", "max-age=3600")
        else:
            handler.send_header("Cache-Control", "no-store, no-cache, must-revalidate")

    @staticmethod
    def send_json_response(handler, status: int, data: dict):
        """
        Envia resposta JSON com headers padrão.
        
        Args:
            handler: BaseHTTPRequestHandler
            status: HTTP status code
            data: Dados a serializar
        """
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Content-Length", str(len(body)))
        
        HTTPMiddleware.add_cors_headers(handler)
        HTTPMiddleware.add_cache_headers(handler, cache=False)
        
        handler.end_headers()
        handler.wfile.write(body)

    @staticmethod
    def handle_preflight(handler):
        """Handle CORS preflight request"""
        handler.send_response(204)
        HTTPMiddleware.add_cors_headers(handler)
        handler.end_headers()


class ResponseFormatter:
    """Formata respostas consistentes"""

    @staticmethod
    def success(data=None, message="OK", status_code=200):
        """Formata resposta de sucesso"""
        return status_code, {
            "status": "success",
            "message": message,
            "data": data or {}
        }

    @staticmethod
    def error(message: str, error_code: str = "ERROR", status_code=400):
        """Formata resposta de erro"""
        return status_code, {
            "status": "error",
            "error": error_code,
            "message": message
        }

    @staticmethod
    def created(data, message="Criado com sucesso"):
        """Formata resposta 201 Created"""
        return ResponseFormatter.success(data, message, 201)

    @staticmethod
    def not_found(message="Recurso não encontrado"):
        """Formata resposta 404"""
        return ResponseFormatter.error(message, "NOT_FOUND", 404)

    @staticmethod
    def bad_request(message="Requisição inválida"):
        """Formata resposta 400"""
        return ResponseFormatter.error(message, "BAD_REQUEST", 400)

    @staticmethod
    def unauthorized(message="Não autorizado"):
        """Formata resposta 401"""
        return ResponseFormatter.error(message, "UNAUTHORIZED", 401)
