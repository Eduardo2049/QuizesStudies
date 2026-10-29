"""
Entrar com Google (OAuth 2.0 / OpenID Connect, fluxo de código no servidor).

Fica desligado até GOOGLE_CLIENT_ID e GOOGLE_CLIENT_SECRET estarem configurados.
Fluxo:
1. /api/auth/google/start gera um `state` aleatório, guarda num cookie HttpOnly
   junto com o destino (?next=) e redireciona para a tela de consentimento do Google.
2. O Google volta em /api/auth/google/callback com `code` e `state`. O servidor
   confere o `state` contra o cookie (CSRF), troca o `code` por um token direto com
   o Google (TLS, segredo do cliente) e lê o perfil em /userinfo.
3. Só e-mails verificados pelo Google entram. Se já existe conta com o e-mail, ela é
   usada; senão, uma conta de estudante é criada com senha aleatória (a pessoa pode
   definir uma senha depois por "Esqueci minha senha").
"""
from __future__ import annotations

import re
import secrets
from urllib.parse import urlencode, urlparse

import requests

from api.exceptions.quiz_exceptions import QuizAPIException
from api.services.auth_service import AuthService, hash_password, _hash_token
from api.utils.config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
STATE_COOKIE = "qs_oauth"
STATE_MAX_AGE = 10 * 60  # 10 minutos para concluir o login


def google_enabled() -> bool:
    return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)


def safe_next(raw: str | None) -> str:
    """Mesmo critério do login: só caminhos internos (sem redirecionamento aberto)."""
    raw = (raw or "/").strip()
    if not raw.startswith("/") or raw.startswith("//") or raw.startswith("/\\"):
        return "/"
    # O navegador descarta tab/quebra de linha e trata "\" como "/" ao ler o Location:
    # "/\t/site.com" viraria "//site.com" (outro site). Qualquer caractere assim é recusado.
    if "\\" in raw or any(ord(ch) < 0x21 or ord(ch) == 0x7F for ch in raw):
        return "/"
    parsed = urlparse(raw)
    if parsed.scheme or parsed.netloc:
        return "/"
    if parsed.path in ("/login", "/register", "/reset-password"):
        return "/"
    return raw[:300]


def build_state_cookie_value(next_path: str) -> tuple[str, str]:
    """Devolve (state, valor do cookie). O destino vai no cookie, não na URL do Google."""
    state = secrets.token_urlsafe(32)
    nxt = safe_next(next_path).replace(";", "").replace(",", "").replace(" ", "")
    return state, f"{state}|{nxt}"


def parse_state_cookie(value: str | None) -> tuple[str | None, str]:
    if not value or "|" not in value:
        return None, "/"
    state, nxt = value.split("|", 1)
    return state, safe_next(nxt)


def authorization_url(state: str, redirect_uri: str) -> str:
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "prompt": "select_account",
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def _username_from_email(email: str, exists) -> str:
    base = re.sub(r"[^a-z0-9_]", "", email.split("@", 1)[0].lower())[:40] or "aluno"
    if len(base) < 3:
        base = f"{base}aluno"
    name, n = base, 1
    while exists(name):
        n += 1
        name = f"{base}{n}"
    return name


class GoogleAuthService:
    def __init__(self, auth_service: AuthService | None = None, http=None):
        self.auth = auth_service or AuthService()
        self.http = http or requests

    def _fetch_profile(self, code: str, redirect_uri: str) -> dict:
        try:
            token_resp = self.http.post(TOKEN_URL, data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            }, timeout=10)
            if token_resp.status_code != 200:
                raise QuizAPIException("O Google não confirmou o login. Tente novamente.", 400, "GOOGLE_LOGIN_FAILED")
            access_token = token_resp.json().get("access_token")
            info_resp = self.http.get(USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"}, timeout=10)
            if info_resp.status_code != 200:
                raise QuizAPIException("Não foi possível ler seu perfil do Google.", 400, "GOOGLE_LOGIN_FAILED")
            return info_resp.json()
        except requests.RequestException:
            raise QuizAPIException("Falha na conexão com o Google. Tente novamente.", 502, "GOOGLE_LOGIN_FAILED")

    def login_with_code(self, code: str, redirect_uri: str) -> dict:
        """Troca o código por uma sessão do Acely. Devolve o mesmo formato de AuthService.login."""
        if not google_enabled():
            raise QuizAPIException("Login com Google não está disponível.", 404, "GOOGLE_DISABLED")
        if not code:
            raise QuizAPIException("Login com Google cancelado.", 400, "GOOGLE_LOGIN_FAILED")

        profile = self._fetch_profile(code, redirect_uri)
        email = str(profile.get("email") or "").strip().lower()
        if not email or profile.get("email_verified") is not True:
            raise QuizAPIException("Use uma conta Google com e-mail verificado.", 400, "GOOGLE_EMAIL_UNVERIFIED")

        repo = self.auth.repo
        user = repo.find_by_email(email)
        if not user:
            username = _username_from_email(email, lambda n: bool(repo.find_by_username(n)))
            pwd_hash, salt = hash_password(secrets.token_urlsafe(32))
            user = repo.create_user(username, email, pwd_hash, salt, role="student", email_verified=True)
        elif user.get("role") == "admin":
            # O admin entra só com usuário e senha (ADMIN_PASSWORD): o login com Google não
            # pode virar um caminho alternativo para a conta mais poderosa.
            raise QuizAPIException("A conta de administrador entra só com usuário e senha.", 403, "GOOGLE_ADMIN_BLOCKED")
        elif not user.get("email_verified"):
            # Conta criada com este e-mail sem confirmação: quem a criou pode não ser o dono
            # do e-mail (e conhece a senha). O Google acabou de provar quem é o dono: a senha
            # vira aleatória e as outras sessões caem, e o e-mail passa a contar como confirmado.
            pwd_hash, salt = hash_password(secrets.token_urlsafe(32))
            repo.update_password_and_role(user["id"], pwd_hash, salt)
            repo.delete_user_sessions(user["id"])
            repo.mark_email_verified(user["id"])

        token = secrets.token_urlsafe(48)
        session = repo.create_session(_hash_token(token), user["id"], duration_days=7)
        return {
            "token": token,
            "expires_at": session["expires_at"].isoformat(),
            "user": {"id": user["id"], "username": user["username"], "email": user["email"], "role": user["role"]},
        }
