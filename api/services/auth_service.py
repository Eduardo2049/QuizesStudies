"""
Serviço de Autenticação e Gestão de Sessões
Usa PBKDF2-HMAC-SHA256 com salt seguro (nativo do Python).
"""
import hashlib
import hmac
import math
import re
import secrets
from api.repositories.user_repository import UserRepository
from api.services.email_service import EmailService
from api.exceptions.quiz_exceptions import QuizAPIException
from api.utils.config import (
    ADMIN_USERNAME,
    ADMIN_PASSWORD,
    DEBUG,
    AUTH_CODE_SECRET,
    LOGIN_CODE_TTL_MINUTES,
    LOGIN_CODE_MAX_ATTEMPTS,
    LOGIN_CODE_RESEND_SECONDS,
    LOGIN_CODE_MAX_PER_HOUR,
)

# Salt e hash fixos usados como dummy para equalizar o tempo de resposta
# quando o usuário não existe (prevenção de enumeração por timing).
# O custo vem do PBKDF2 da senha recebida em verify_password, não deste valor:
# por isso ele é uma constante, e não um hash calculado no import (≈0,4 s a
# menos em cada cold start da Vercel).
_DUMMY_SALT = "0000000000000000000000000000000000000000000000000000000000000000"
_DUMMY_HASH = "f" * 64

ADMIN_EMAIL = "admin@acely.com.br"
_LEGACY_ADMIN_EMAIL = "admin@quiz.study"
_USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{3,30}$")
_EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
MAX_PASSWORD_CHARS = 256
EMAIL_VERIFICATION_HOURS = 24

_RESET_REQUEST_MESSAGE = (
    "Se os dados informados estiverem cadastrados, você receberá as instruções para redefinir sua senha."
)

# ─── Códigos de 6 dígitos por e-mail ─────────────────────────────────────────
EMAIL_CODE_PURPOSES = ("login", "delete_account")
_CODE_PATTERN = re.compile(r"^\d{6}$")
_CODE_SENT_MESSAGE = "Enviamos um código de 6 dígitos para o seu e-mail."
_INVALID_EMAIL_MESSAGE = "Informe um e-mail válido, como nome@exemplo.com."
_CODE_EXPIRED_MESSAGE = "Este código venceu ou já foi usado. Peça um novo código."


class EmailCodeWait(QuizAPIException):
    """Pedido de código cedo demais para o mesmo e-mail (reenvio ou limite por hora)."""

    def __init__(self, retry_after: int, message: str):
        self.retry_after = max(1, int(retry_after))
        super().__init__(message, 429, "CODE_RESEND_WAIT")


def normalize_email(email) -> str:
    return str(email or "").strip().lower()


def is_valid_email(email: str) -> bool:
    return 0 < len(email) <= 254 and bool(_EMAIL_PATTERN.match(email))


def _email_code_key() -> bytes:
    """Chave do HMAC dos códigos. Fica fora do banco (variável de ambiente)."""
    secret = AUTH_CODE_SECRET or f"acely-email-code:{ADMIN_PASSWORD}"
    return hashlib.sha256(secret.encode("utf-8")).digest()


def hash_email_code(email: str, purpose: str, code: str) -> str:
    """HMAC-SHA256 do código ligado ao e-mail e à finalidade: o código de um e-mail
    não serve para outro, e o de login não serve para excluir a conta."""
    message = f"{purpose}:{normalize_email(email)}:{code}".encode("utf-8")
    return hmac.new(_email_code_key(), message, hashlib.sha256).hexdigest()


def new_email_code() -> str:
    """Seis dígitos de um gerador criptográfico (inclui zeros à esquerda)."""
    return f"{secrets.randbelow(1_000_000):06d}"


def username_from_email(email: str, exists) -> str:
    """Nome de usuário a partir da parte antes do @, com número se já existir."""
    base = re.sub(r"[^a-z0-9_]", "", email.split("@", 1)[0].lower())[:26] or "aluno"
    if len(base) < 3:
        base = f"{base}aluno"
    name, n = base, 1
    while exists(name):
        n += 1
        name = f"{base}{n}"
    return name


def hash_password(password: str, salt: str = None) -> tuple[str, str]:
    """
    Gera hash seguro da senha usando PBKDF2-HMAC-SHA256 (600.000 iterações recomendadas pela OWASP).
    Retorna (hash_hex, salt_hex).
    """
    if salt is None:
        salt = secrets.token_hex(16)
    
    key = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations=600_000,
    )
    return key.hex(), salt


def _hash_token(token: str) -> str:
    """Gera hash SHA-256 do token de sessão para armazenamento seguro no banco."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_password(password: str, salt: str, password_hash: str) -> bool:
    """Verifica se a senha em texto plano bate com o hash armazenado."""
    calculated_hash, _ = hash_password(password, salt)
    return hmac.compare_digest(calculated_hash, password_hash)


class AuthService:
    """Regras de negócio para autenticação de usuários e controle de sessões"""

    def __init__(self, repository: UserRepository = None, email_service: EmailService = None):
        self.repo = repository or UserRepository()
        self.email_service = email_service or EmailService()

    def seed_admin_if_needed(self):
        """Garante a existência do usuário administrador e sincroniza sua senha com ADMIN_PASSWORD."""
        try:
            admin_pwd = ADMIN_PASSWORD
            if not admin_pwd or len(admin_pwd) < 8:
                raise RuntimeError(
                    "ADMIN_PASSWORD não definido ou com menos de 8 caracteres. "
                    "Configure uma senha forte no ambiente/Vercel antes de iniciar."
                )
            admin = self.repo.find_by_username(ADMIN_USERNAME)
            # O primeiro admin foi criado com um e-mail de um domínio que não é do projeto:
            # quem controlasse esse domínio poderia receber e-mails destinados ao admin.
            if admin and (admin.get("email") or "").lower() == _LEGACY_ADMIN_EMAIL:
                self.repo.update_email(admin["id"], ADMIN_EMAIL)
            # Já sincronizado: evita novo PBKDF2 + UPDATE a cada cold start.
            if (
                admin
                and admin.get("role") == "admin"
                and verify_password(admin_pwd, admin["salt"], admin["password_hash"])
            ):
                return

            pwd_hash, salt = hash_password(admin_pwd)
            if not admin:
                admin = self.repo.create_user(
                    username=ADMIN_USERNAME,
                    email=ADMIN_EMAIL,
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
        """
        Autentica o usuário e retorna o token de sessão.
        Executa PBKDF2 mesmo quando o usuário não existe para equalizar o
        tempo de resposta e impedir enumeração de contas por timing.
        """
        if not username or not password:
            raise QuizAPIException("Usuário e senha são obrigatórios", 400)

        user = self.repo.find_by_username(username)

        if not user:
            # Hash falso: garante que o ramo «não encontrado» leva o mesmo
            # tempo que o ramo «encontrado» (≈175 ms de PBKDF2).
            verify_password(password, _DUMMY_SALT, _DUMMY_HASH)
            raise QuizAPIException("Credenciais inválidas", 401)

        if not verify_password(password, user["salt"], user["password_hash"]):
            raise QuizAPIException("Credenciais inválidas", 401)

        self.repo.cleanup_expired_sessions()

        # Gerar token seguro de sessão (48 bytes URL-safe = 64 caracteres)
        token = secrets.token_urlsafe(48)
        token_hash = _hash_token(token)
        session = self.repo.create_session(token_hash, user["id"], duration_days=7)

        return {
            "token": token,
            "expires_at": session["expires_at"].isoformat(),
            "user": {
                "id": user["id"],
                "username": user["username"],
                "email": user["email"],
                "role": user["role"],
            }
        }

    def register(self, username: str, email: str, password: str, app_url: str = "") -> dict:
        """Registra um novo estudante e envia o link de confirmação do e-mail."""
        username = username.strip()
        email = email.strip().lower()

        # Só letras, números e . _ - : nada de espaços, controles ou sósias de outros nomes
        if not _USERNAME_PATTERN.match(username):
            raise QuizAPIException(
                "O nome de usuário deve ter de 3 a 30 caracteres: letras, números, ponto, hífen ou sublinhado.", 400
            )
        if len(email) > 254 or not _EMAIL_PATTERN.match(email):
            raise QuizAPIException("E-mail inválido", 400)
        if len(password) < 8:
            raise QuizAPIException("Senha deve ter pelo menos 8 caracteres", 400)
        if len(password) > MAX_PASSWORD_CHARS:
            raise QuizAPIException(f"A senha deve ter no máximo {MAX_PASSWORD_CHARS} caracteres.", 400)

        # Mensagem uniforme contra enumeração de contas
        if self.repo.find_by_username(username) or self.repo.find_by_email(email):
            raise QuizAPIException("Nome de usuário ou e-mail já cadastrado", 409)

        pwd_hash, salt = hash_password(password)
        user = self.repo.create_user(username, email, pwd_hash, salt, role="student")

        # O cadastro vale mesmo se o e-mail não sair agora: o link pode ser reenviado em Minha conta
        try:
            self.send_email_verification(user, app_url)
        except Exception as e:
            print(f"[auth] Falha ao enviar a confirmação de e-mail: {type(e).__name__}")

        return {
            "id": user["id"],
            "username": user["username"],
            "email": user["email"],
            "role": user["role"],
            "email_verified": bool(user.get("email_verified")),
        }

    # ─── Confirmação de e-mail ───────────────────────────────────────────────

    def send_email_verification(self, user: dict, app_url: str = "") -> bool:
        """Gera um link de confirmação (24 h, uso único) e envia para o e-mail da conta."""
        base_url = (app_url or "").rstrip("/")
        if not base_url:
            print("[auth] APP_URL não configurado: e-mail de confirmação não enviado")
            return False
        token = secrets.token_urlsafe(32)
        self.repo.create_email_verification(_hash_token(token), user["id"], expires_hours=EMAIL_VERIFICATION_HOURS)
        verify_url = f"{base_url}/api/auth/verify-email?token={token}"
        success, mode = self.email_service.send_email_verification(user["email"], user["username"], verify_url)
        return success and mode != "simulated"

    def resend_email_verification(self, user: dict, app_url: str = "") -> dict:
        """Reenvia o link para a própria conta logada."""
        if user.get("email_verified"):
            return {"already_verified": True, "message": "Seu e-mail já está confirmado."}
        if not self.send_email_verification(user, app_url):
            raise QuizAPIException("Não foi possível enviar o link agora. Tente novamente mais tarde.", 503)
        return {"already_verified": False, "message": "Enviamos um novo link de confirmação para o seu e-mail."}

    def verify_email(self, token: str) -> bool:
        """Confirma o e-mail pelo link recebido. Devolve False para link inválido, usado ou vencido."""
        token = (token or "").strip()
        if not token or len(token) > 128:
            return False
        return self.repo.consume_email_verification(_hash_token(token)) is not None

    # ─── Entrar com código por e-mail ────────────────────────────────────────
    # Fluxo: a pessoa digita o e-mail, recebe 6 dígitos válidos por LOGIN_CODE_TTL_MINUTES
    # e entra com eles. Sem conta com esse e-mail, a conta é criada no código certo (nunca
    # antes: e-mail digitado errado não deixa conta solta). O código certo prova que a
    # pessoa lê aquele e-mail, então o e-mail já fica confirmado.

    def request_email_code(self, email: str, purpose: str = "login", language: str = "pt-BR") -> dict:
        """Gera e envia um código. A resposta é a mesma exista ou não conta com o e-mail."""
        email = normalize_email(email)
        if purpose not in EMAIL_CODE_PURPOSES:
            raise QuizAPIException("Finalidade do código inválida.", 400)
        if not is_valid_email(email):
            raise QuizAPIException(_INVALID_EMAIL_MESSAGE, 400, "INVALID_EMAIL")
        if not self.email_service.is_configured() and not DEBUG:
            # Sem SMTP o código nunca chegaria: melhor avisar do que deixar a pessoa esperando
            print("[auth] SMTP não configurado: login por código indisponível (defina SMTP_HOST)")
            raise QuizAPIException(
                "O envio de códigos por e-mail está indisponível agora. Entre com o Google ou continue como convidado.",
                503,
                "EMAIL_CODE_UNAVAILABLE",
            )

        stats = self.repo.email_code_send_stats(email, purpose)
        since = stats.get("seconds_since_last")
        if since is not None and since < LOGIN_CODE_RESEND_SECONDS:
            wait = math.ceil(LOGIN_CODE_RESEND_SECONDS - since)
            raise EmailCodeWait(wait, f"Aguarde {wait} segundos para pedir outro código.")
        if stats.get("sent_last_hour", 0) >= LOGIN_CODE_MAX_PER_HOUR:
            raise EmailCodeWait(
                15 * 60, "Muitos códigos pedidos para este e-mail. Tente de novo em 15 minutos."
            )

        response = {
            "message": _CODE_SENT_MESSAGE,
            "expires_in": LOGIN_CODE_TTL_MINUTES * 60,
            "resend_in": LOGIN_CODE_RESEND_SECONDS,
        }

        # O admin entra só com usuário e senha (ADMIN_PASSWORD), como na recuperação de senha e
        # no Google: um código por e-mail abriria uma porta extra para a conta mais poderosa.
        # A resposta é igual à de qualquer e-mail para não revelar qual endereço é o do admin.
        user = self.repo.find_by_email(email)
        if user and user.get("role") == "admin":
            print("[auth] código por e-mail recusado para o administrador (use usuário e senha)")
            return response

        code = new_email_code()
        self.repo.create_email_code(email, purpose, hash_email_code(email, purpose, code), LOGIN_CODE_TTL_MINUTES)
        success, mode = self.email_service.send_email_code(
            email, code, LOGIN_CODE_TTL_MINUTES, purpose=purpose, language=language
        )
        if not success:
            raise QuizAPIException(
                "Não foi possível enviar o código agora. Tente de novo em alguns minutos.", 503, "EMAIL_SEND_FAILED"
            )
        # Só em desenvolvimento, sem SMTP: o código volta na resposta para testar sem caixa de e-mail
        if mode == "simulated" and DEBUG:
            response["dev_code"] = code
        return response

    def _check_email_code(self, email: str, purpose: str, code: str) -> None:
        """Confere o código e o queima. Cada palpite conta, certo ou errado."""
        code = re.sub(r"\s+", "", str(code or ""))
        if not _CODE_PATTERN.match(code):
            raise QuizAPIException("Digite os 6 números do código.", 400, "INVALID_CODE")

        row = self.repo.take_email_code_attempt(email, purpose, LOGIN_CODE_MAX_ATTEMPTS)
        if not row:
            raise QuizAPIException(_CODE_EXPIRED_MESSAGE, 400, "CODE_EXPIRED")

        if not hmac.compare_digest(row["code_hash"], hash_email_code(email, purpose, code)):
            remaining = max(0, LOGIN_CODE_MAX_ATTEMPTS - int(row.get("attempts") or 0))
            if remaining == 0:
                raise QuizAPIException(_CODE_EXPIRED_MESSAGE, 400, "CODE_EXPIRED")
            raise QuizAPIException(
                f"Código incorreto. Você ainda tem {remaining} tentativa(s) com este código.", 400, "INVALID_CODE"
            )

        if not self.repo.consume_email_code(row["id"]):
            raise QuizAPIException(_CODE_EXPIRED_MESSAGE, 400, "CODE_EXPIRED")

    def login_with_email_code(self, email: str, code: str) -> dict:
        """Confere o código e devolve uma sessão no mesmo formato de login(). Cria a conta se preciso."""
        email = normalize_email(email)
        if not is_valid_email(email):
            raise QuizAPIException(_INVALID_EMAIL_MESSAGE, 400, "INVALID_EMAIL")
        self._check_email_code(email, "login", code)

        repo = self.repo
        user = repo.find_by_email(email)
        created = False
        if not user:
            username = username_from_email(email, lambda n: bool(repo.find_by_username(n)))
            # Senha aleatória que ninguém conhece: a conta entra por código (ou pelo Google)
            pwd_hash, salt = hash_password(secrets.token_urlsafe(32))
            try:
                user = repo.create_user(username, email, pwd_hash, salt, role="student", email_verified=True)
                created = True
            except Exception:
                # Outra requisição criou a conta no mesmo instante: usa a que ficou no banco
                user = repo.find_by_email(email)
                if not user:
                    raise
        elif user.get("role") == "admin":
            raise QuizAPIException("A conta de administrador entra só com usuário e senha.", 403, "CODE_ADMIN_BLOCKED")
        elif not user.get("email_verified"):
            # Conta criada com este e-mail sem confirmação (cadastro antigo por senha): quem a criou
            # pode não ser o dono do e-mail. O código acabou de provar quem é o dono: a senha vira
            # aleatória, as outras sessões caem e o e-mail passa a contar como confirmado.
            pwd_hash, salt = hash_password(secrets.token_urlsafe(32))
            repo.update_password_and_role(user["id"], pwd_hash, salt)
            repo.delete_user_sessions(user["id"])
            repo.mark_email_verified(user["id"])

        repo.cleanup_expired_sessions()
        token = secrets.token_urlsafe(48)
        session = repo.create_session(_hash_token(token), user["id"], duration_days=7)
        return {
            "token": token,
            "expires_at": session["expires_at"].isoformat(),
            "created": created,
            "user": {
                "id": user["id"],
                "username": user["username"],
                "email": user["email"],
                "role": user["role"],
                "email_verified": True,
            },
        }

    def request_account_deletion_code(self, user: dict, language: str = "pt-BR") -> dict:
        """Envia para o e-mail da conta o código que confirma a exclusão (substitui a senha)."""
        if not user:
            raise QuizAPIException("Autenticação necessária", 401)
        if user.get("role") == "admin":
            raise QuizAPIException(
                "A conta de administrador não pode ser excluída por aqui. Use os scripts de manutenção.", 403
            )
        result = self.request_email_code(user.get("email", ""), purpose="delete_account", language=language)
        result["message"] = "Enviamos um código para o seu e-mail. Digite-o abaixo para confirmar."
        return result

    def export_account(self, user_id: int) -> dict:
        """LGPD art. 18 (acesso e portabilidade): cópia dos dados da conta."""
        data = self.repo.export_user_data(user_id)
        if not data:
            raise QuizAPIException("Conta não encontrada", 404)
        # Workspaces e uso mensal (Fase S1 do PLANO_SAAS.md)
        from api.repositories.plan_repository import plan_repo

        data.update(plan_repo.export_for_user(user_id))
        return data

    def delete_account(self, user: dict, password: str = "", code: str = "") -> None:
        """LGPD art. 18 (eliminação): apaga a conta depois de confirmar com o código do e-mail.

        A tela usa o código (contas que entram por código ou pelo Google não têm senha
        conhecida). A confirmação por senha continua aceita para clientes antigos da API.
        """
        if not user:
            raise QuizAPIException("Autenticação necessária", 401)
        if user.get("role") == "admin":
            raise QuizAPIException(
                "A conta de administrador não pode ser excluída por aqui. Use os scripts de manutenção.", 403
            )
        if code:
            try:
                self._check_email_code(normalize_email(user.get("email")), "delete_account", code)
            except QuizAPIException as e:
                # 403 e não 400/401: a sessão continua válida, só a confirmação falhou
                raise QuizAPIException(f"{e.message} A conta não foi excluída.", 403, "WRONG_CODE")
        elif password:
            # ── Confirmação por senha (formulário comentado na tela; mantida na API) ──
            record = self.repo.find_by_username(user["username"])
            if not record or not verify_password(password, record["salt"], record["password_hash"]):
                raise QuizAPIException("Senha incorreta. A conta não foi excluída.", 403, "WRONG_PASSWORD")
        else:
            raise QuizAPIException("Confirme com o código enviado para o seu e-mail.", 400)
        self.repo.delete_user_and_data(user["id"])

    def validate_token(self, token: str) -> dict | None:
        """Valida se o token de sessão é válido e retorna o usuário consultando pelo hash."""
        if not token:
            return None
        token_hash = _hash_token(token)
        return self.repo.find_session_user(token_hash)

    def logout(self, token: str) -> bool:
        """Encerra a sessão removendo o token correspondente por hash."""
        if not token:
            return False
        token_hash = _hash_token(token)
        return self.repo.delete_session(token_hash)

    # ─── Recuperação de Senha ────────────────────────────────────────────────

    def request_password_reset(self, identifier: str, app_url: str = "") -> dict:
        """
        Gera solicitação de recuperação de senha.
        Anti-enumeração: executa hash dummy e devolve a mesma resposta genérica
        mesmo se o usuário não existir, prevenindo enumeração por timing ou payload.
        """
        identifier = (identifier or "").strip()
        if not identifier:
            raise QuizAPIException("Informe seu e-mail ou nome de usuário", 400)

        # Localiza por e-mail ou por username
        user = self.repo.find_by_email(identifier) if "@" in identifier else self.repo.find_by_username(identifier)
        if not user and "@" not in identifier:
            user = self.repo.find_by_email(identifier)
        if not user and "@" in identifier:
            user = self.repo.find_by_username(identifier)

        not_sent = {
            "message": _RESET_REQUEST_MESSAGE,
            "email_sent": False,
            "dev_reset_url": None,
            "dev_token": None,
        }
        if not user:
            # Hash falso para mitigar timing attacks
            verify_password("dummy_password", _DUMMY_SALT, _DUMMY_HASH)
            return not_sent

        # A senha do admin vem de ADMIN_PASSWORD (sincronizada a cada inicialização): um link
        # por e-mail só abriria uma porta extra para a conta mais poderosa.
        if user.get("role") == "admin":
            print("[auth] recuperação por e-mail desativada para o administrador (use ADMIN_PASSWORD)")
            return not_sent

        # Sem endereço público confiável (APP_URL), nenhum link sai: montá-lo a partir do
        # Host da requisição deixaria um atacante apontar o link da vítima para outro site.
        base_url = (app_url or "").rstrip("/")
        if not base_url:
            print("[auth] APP_URL não configurado: e-mail de recuperação não enviado")
            return not_sent

        # Usuário válido: gerar token com alta entropia (32 bytes = 43+ chars)
        token = secrets.token_urlsafe(32)
        token_hash = _hash_token(token)

        self.repo.create_password_reset(token_hash, user["id"], expires_minutes=30)

        reset_url = f"{base_url}/reset-password?token={token}"

        success, mode = self.email_service.send_password_reset_email(
            to_email=user["email"],
            username=user["username"],
            reset_url=reset_url,
            token=token,
        )

        # Token só volta no corpo em DEBUG: sem SMTP em produção, devolvê-lo
        # permitiria a qualquer um redefinir a senha de qualquer conta.
        is_simulated = (mode == "simulated")
        expose_token = is_simulated and DEBUG
        return {
            "message": _RESET_REQUEST_MESSAGE,
            "email_sent": success and not is_simulated,
            "dev_reset_url": reset_url if expose_token else None,
            "dev_token": token if expose_token else None,
        }

    def verify_reset_token(self, token: str) -> dict:
        """Valida o token de redefinição e retorna dados mascarados para confirmação visual."""
        token = (token or "").strip()
        if not token:
            raise QuizAPIException("Token de recuperação não fornecido", 400)

        # Sem PBKDF2 falso aqui: o token tem 256 bits e é buscado pelo hash, então o tempo
        # da consulta não revela nada, e o hash falso só daria CPU de graça a quem abusa.
        token_hash = _hash_token(token)
        reset = self.repo.find_password_reset(token_hash)
        if not reset:
            raise QuizAPIException("Link de recuperação inválido ou expirado", 400)

        email = reset.get("email", "")
        parts = email.split("@")
        masked_email = (
            f"{parts[0][:2]}***@{parts[1]}"
            if len(parts) == 2 and len(parts[0]) >= 2
            else email
        )

        return {
            "valid": True,
            "username": reset.get("username", ""),
            "masked_email": masked_email,
        }

    def reset_password(self, token: str, new_password: str) -> dict:
        """Aplica a nova senha com validação de complexidade, invalidação de sessões e queima do token."""
        token = (token or "").strip()
        if not token:
            raise QuizAPIException("Token de recuperação não fornecido", 400)

        if not new_password or len(new_password) < 8:
            raise QuizAPIException("A nova senha deve ter pelo menos 8 caracteres", 400)
        if len(new_password) > MAX_PASSWORD_CHARS:
            raise QuizAPIException(f"A senha deve ter no máximo {MAX_PASSWORD_CHARS} caracteres.", 400)

        token_hash = _hash_token(token)
        reset = self.repo.find_password_reset(token_hash)
        if not reset:
            raise QuizAPIException("Link de recuperação inválido ou expirado", 400)

        # Queima o token antes de trocar a senha: o UPDATE ... WHERE used = FALSE é atômico,
        # então dois pedidos simultâneos com o mesmo link não trocam a senha duas vezes.
        if not self.repo.mark_password_reset_used(token_hash):
            raise QuizAPIException("Link de recuperação inválido ou expirado", 400)

        user_id = reset["user_id"]
        pwd_hash, salt = hash_password(new_password)

        self.repo.update_password_and_role(user_id, pwd_hash, salt)
        self.repo.delete_user_sessions(user_id)
        # O link chegou pelo e-mail da conta: isso também confirma o e-mail
        self.repo.mark_email_verified(user_id)

        return {
            "message": "Senha redefinida com sucesso! Você já pode entrar com sua nova senha.",
        }
