"""
Controller para endpoints de autenticação
"""
from api.services.auth_service import AuthService
from api.exceptions.quiz_exceptions import QuizAPIException
from api.middleware.http_middleware import timing_decorator, error_handler_decorator


class AuthController:
    """Controller para autenticação, login e sessões"""

    def __init__(self, auth_service: AuthService = None):
        self.service = auth_service or AuthService()

    @timing_decorator
    @error_handler_decorator
    def login(self, payload: dict) -> dict:
        """POST /api/auth/login - Autentica usuário e retorna token"""
        if not isinstance(payload, dict):
            raise QuizAPIException("Payload inválido", 400)

        username = payload.get("username", "").strip()
        password = payload.get("password", "")

        result = self.service.login(username, password)
        return {
            "status": "success",
            "message": "Login realizado com sucesso",
            "data": result,
        }

    @timing_decorator
    @error_handler_decorator
    def register(self, payload: dict) -> dict:
        """POST /api/auth/register - Registra novo estudante"""
        if not isinstance(payload, dict):
            raise QuizAPIException("Payload inválido", 400)

        username = payload.get("username", "").strip()
        email = payload.get("email", "").strip()
        password = payload.get("password", "")

        user = self.service.register(username, email, password)
        return {
            "status": "success",
            "message": "Usuário registrado com sucesso",
            "data": {"user": user},
        }

    @timing_decorator
    @error_handler_decorator
    def get_me(self, token: str) -> dict:
        """GET /api/auth/me - Retorna os dados do usuário autenticado"""
        if not token:
            raise QuizAPIException("Token não fornecido", 401)

        user = self.service.validate_token(token)
        if not user:
            raise QuizAPIException("Sessão expirada ou inválida", 401)

        return {
            "status": "success",
            "data": {
                "user": {
                    "id": user["id"],
                    "username": user["username"],
                    "email": user["email"],
                    "role": user["role"],
                }
            }
        }

    @timing_decorator
    @error_handler_decorator
    def logout(self, token: str) -> dict:
        """POST /api/auth/logout - Invalida o token de sessão"""
        if token:
            self.service.logout(token)
        return {
            "status": "success",
            "message": "Logout realizado com sucesso",
            "data": {},
        }
