"""
Serviço de Autenticação e Gestão de Sessões
Usa PBKDF2-HMAC-SHA256 com salt seguro (nativo do Python).
"""
import hashlib
import hmac
import secrets
from api.repositories.user_repository import UserRepository
from api.exceptions.quiz_exceptions import QuizAPIException
from api.utils.config import ADMIN_USERNAME, ADMIN_PASSWORD, DEBUG


def hash_password(password: str, salt: str = None) -> tuple[str, str]:
    """
    Gera hash seguro da senha usando PBKDF2-HMAC-SHA256.
    Retorna (hash_hex, salt_hex).
    """
    if salt is None:
        salt = secrets.token_hex(16)
    
    key = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations=100_000,
    )
    return key.hex(), salt


def verify_password(password: str, salt: str, password_hash: str) -> bool:
    """Verifica se a senha em texto plano bate com o hash armazenado."""
    calculated_hash, _ = hash_password(password, salt)
    return hmac.compare_digest(calculated_hash, password_hash)


class AuthService:
    """Regras de negócio para autenticação de usuários e controle de sessões"""

    def __init__(self, repository: UserRepository = None):
        self.repo = repository or UserRepository()

    def seed_admin_if_needed(self):
        """Garante a existência do usuário administrador e sincroniza sua senha com ADMIN_PASSWORD."""
        try:
            admin_pwd = ADMIN_PASSWORD
            if not admin_pwd:
                raise RuntimeError(
                    "ADMIN_PASSWORD não definido no ambiente. "
                    "Adicione ao .env antes de iniciar o servidor."
                )
            pwd_hash, salt = hash_password(admin_pwd)

            admin = self.repo.find_by_username(ADMIN_USERNAME)
            if not admin:
                admin = self.repo.create_user(
                    username=ADMIN_USERNAME,
                    email="admin@quiz.study",
                    password_hash=pwd_hash,
                    salt=salt,
                    role="admin",
                )
                if DEBUG:
                    print(f"🔐 Usuário admin inicial criado: {admin['username']} (role: admin)")
            else:
                self.repo.update_password_and_role(admin["id"], pwd_hash, salt, role="admin")
                if DEBUG:
                    print(f"🔐 Senha e permissões do admin '{ADMIN_USERNAME}' sincronizadas com sucesso")
        except Exception as e:
            if DEBUG:
                print(f"⚠️ Erro ao verificar/criar admin inicial: {e}")

    def login(self, username: str, password: str) -> dict:
        """Autentica o usuário e retorna o token de sessão."""
        if not username or not password:
            raise QuizAPIException("Usuário e senha são obrigatórios", 400)

        user = self.repo.find_by_username(username)
        if not user:
            raise QuizAPIException("Credenciais inválidas", 401)

        if not verify_password(password, user["salt"], user["password_hash"]):
            raise QuizAPIException("Credenciais inválidas", 401)

        self.repo.cleanup_expired_sessions()

        # Gerar token seguro de sessão (48 bytes URL-safe = 64 caracteres)
        token = secrets.token_urlsafe(48)
        session = self.repo.create_session(token, user["id"], duration_days=7)

        return {
            "token": session["token"],
            "expires_at": session["expires_at"].isoformat(),
            "user": {
                "id": user["id"],
                "username": user["username"],
                "email": user["email"],
                "role": user["role"],
            }
        }

    def register(self, username: str, email: str, password: str) -> dict:
        """Registra um novo estudante."""
        username = username.strip()
        email = email.strip().lower()

        if len(username) < 3:
            raise QuizAPIException("Nome de usuário deve ter pelo menos 3 caracteres", 400)
        if "@" not in email:
            raise QuizAPIException("E-mail inválido", 400)
        if len(password) < 6:
            raise QuizAPIException("Senha deve ter pelo menos 6 caracteres", 400)

        if self.repo.find_by_username(username):
            raise QuizAPIException("Nome de usuário já está em uso", 409)
        if self.repo.find_by_email(email):
            raise QuizAPIException("E-mail já está em uso", 409)

        pwd_hash, salt = hash_password(password)
        user = self.repo.create_user(username, email, pwd_hash, salt, role="student")

        return {
            "id": user["id"],
            "username": user["username"],
            "email": user["email"],
            "role": user["role"],
        }

    def validate_token(self, token: str) -> dict | None:
        """Valida se o token de sessão é válido e retorna o usuário."""
        if not token:
            return None
        return self.repo.find_session_user(token)

    def logout(self, token: str) -> bool:
        """Encerra a sessão removendo o token."""
        if not token:
            return False
        return self.repo.delete_session(token)
