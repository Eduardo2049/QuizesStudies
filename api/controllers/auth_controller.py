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
    def register(self, payload: dict, app_url: str = "") -> dict:
        """POST /api/auth/register - Registra novo estudante"""
        if not isinstance(payload, dict):
            raise QuizAPIException("Payload inválido", 400)

        username = str(payload.get("username") or "").strip()
        email = str(payload.get("email") or "").strip()
        password = str(payload.get("password") or "")

        user = self.service.register(username, email, password, app_url=app_url)
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
                    "email_verified": bool(user.get("email_verified")),
                }
            }
        }

    @timing_decorator
    @error_handler_decorator
    def resend_email_verification(self, user: dict, app_url: str = "") -> dict:
        """POST /api/auth/resend-verification - Reenvia o link de confirmação do e-mail"""
        result = self.service.resend_email_verification(user, app_url=app_url)
        return {
            "status": "success",
            "message": result["message"],
            "data": result,
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

    @timing_decorator
    @error_handler_decorator
    def forgot_password(self, payload: dict, app_url: str = "") -> dict:
        """POST /api/auth/forgot-password - Solicita link de redefinição de senha"""
        if not isinstance(payload, dict):
            raise QuizAPIException("Payload inválido", 400)

        identifier = payload.get("email") or payload.get("username", "")
        identifier = str(identifier).strip()
        if not identifier:
            raise QuizAPIException("Informe seu e-mail ou nome de usuário", 400)

        result = self.service.request_password_reset(identifier, app_url=app_url)
        # Resposta idêntica exista a conta ou não (anti-enumeração): `email_sent` fica só
        # no servidor. O link de teste só sai em DEBUG, quando o serviço o devolve.
        data = {"message": result["message"]}
        if result.get("dev_token"):
            data["dev_reset_url"] = result.get("dev_reset_url")
            data["dev_token"] = result["dev_token"]
        return {
            "status": "success",
            "message": result["message"],
            "data": data,
        }

    @timing_decorator
    @error_handler_decorator
    def verify_reset_token(self, token: str) -> dict:
        """GET /api/auth/verify-reset-token - Valida se o token de recuperação é válido"""
        result = self.service.verify_reset_token(token)
        return {
            "status": "success",
            "data": result,
        }

    @timing_decorator
    @error_handler_decorator
    def reset_password(self, payload: dict) -> dict:
        """POST /api/auth/reset-password - Redefine a senha com o token fornecido"""
        if not isinstance(payload, dict):
            raise QuizAPIException("Payload inválido", 400)

        token = str(payload.get("token", "")).strip()
        new_password = str(payload.get("new_password", ""))

        result = self.service.reset_password(token, new_password)
        return {
            "status": "success",
            "message": result["message"],
            "data": {},
        }

