"""
Serviço de envio de e-mails para recuperação de senha e notificações
Utiliza a biblioteca padrão do Python (smtplib e email.mime).
Quando o SMTP não está configurado, opera em modo simulado para desenvolvimento e testes.
"""
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, parseaddr
from html import escape
from urllib.parse import urlparse
from api.utils.config import (
    SMTP_HOST,
    SMTP_PORT,
    SMTP_USER,
    SMTP_PASSWORD,
    SMTP_FROM,
    SMTP_USE_TLS,
    SMTP_USE_SSL,
    DEBUG,
    APP_URL,
)


class EmailService:
    """Gerencia montagem e envio de e-mails transacionais."""

    def __init__(
        self,
        host: str = SMTP_HOST,
        port: int = SMTP_PORT,
        user: str = SMTP_USER,
        password: str = SMTP_PASSWORD,
        from_email: str = SMTP_FROM,
        use_tls: bool = SMTP_USE_TLS,
        use_ssl: bool = SMTP_USE_SSL,
    ):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.from_email = from_email or "noreply@acely.com.br"
        self.use_tls = use_tls
        self.use_ssl = use_ssl

    def is_configured(self) -> bool:
        """Indica se as credenciais de SMTP foram fornecidas no ambiente."""
        return bool(self.host and self.host.strip())

    def sender_header(self) -> str:
        """Remetente do cabeçalho From. Sem nome no SMTP_FROM (ex.: só o Gmail), aparece como "Acely"."""
        name, address = parseaddr(self.from_email)
        return formataddr((name or "Acely", address or self.from_email))

    def _log_unsent(self, kind: str, to_email: str, username: str, url: str) -> None:
        # Sem emoji: consoles Windows (cp1252) lançam UnicodeEncodeError no print.
        # O link só vai para o log em DEBUG: em produção, quem lê os logs poderia usá-lo
        # (trocar a senha ou confirmar o e-mail de outra conta).
        if DEBUG:
            print(f"[auth:simulated] Link de {kind} para '{username}' <{to_email}>: {url}")
        else:
            print(f"[auth] SMTP não configurado: e-mail de {kind} para '{username}' não enviado (defina SMTP_HOST)")

    def send_password_reset_email(
        self,
        to_email: str,
        username: str,
        reset_url: str,
        token: str,
    ) -> tuple[bool, str]:
        """
        Envia e-mail com link para redefinição de senha.
        Retorna (sucesso: bool, motivo: str).
        """
        if not self.is_configured():
            self._log_unsent("recuperação", to_email, username, reset_url)
            return True, "simulated"

        text_content = (
            f"Olá, {username}!\n\n"
            f"Recebemos uma solicitação para redefinir a senha da sua conta no Acely.\n"
            f"Para definir sua nova senha, acesse o link abaixo:\n\n"
            f"{reset_url}\n\n"
            f"Este link é válido por 30 minutos.\n"
            f"Se você não solicitou a recuperação, pode ignorar este e-mail com segurança.\n\n"
            f"— Equipe Acely"
        )
        html_content = _render_email(
            username=username,
            url=reset_url,
            intro="Recebemos uma solicitação para redefinir a senha da sua conta no <strong>Acely</strong>. "
            "Clique no botão abaixo para prosseguir:",
            button="Redefinir Minha Senha",
            expiry="Este link expira em <strong>30 minutos</strong> e só pode ser utilizado uma vez.",
            closing="Se você não fez essa solicitação, nenhuma ação é necessária — sua conta continua segura.",
        )
        return self._deliver("Recuperação de Senha — Acely", to_email, text_content, html_content, "redefinição")

    def send_email_verification(self, to_email: str, username: str, verify_url: str) -> tuple[bool, str]:
        """Envia o link de confirmação do e-mail informado no cadastro."""
        if not self.is_configured():
            self._log_unsent("confirmação de e-mail", to_email, username, verify_url)
            return True, "simulated"

        text_content = (
            f"Olá, {username}!\n\n"
            f"Confirme o e-mail da sua conta no Acely pelo link abaixo:\n\n"
            f"{verify_url}\n\n"
            f"Este link é válido por 24 horas.\n"
            f"Se você não criou uma conta no Acely, pode ignorar este e-mail.\n\n"
            f"— Equipe Acely"
        )
        html_content = _render_email(
            username=username,
            url=verify_url,
            intro="Confirme o e-mail da sua conta no <strong>Acely</strong>. A confirmação protege a conta "
            "e garante que a recuperação de senha chegue até você.",
            button="Confirmar meu e-mail",
            expiry="Este link expira em <strong>24 horas</strong> e só pode ser utilizado uma vez.",
            closing="Se você não criou uma conta no Acely, pode ignorar este e-mail.",
        )
        return self._deliver("Confirme seu e-mail — Acely", to_email, text_content, html_content, "confirmação")

    def send_email_code(
        self,
        to_email: str,
        code: str,
        minutes: int,
        purpose: str = "login",
        language: str = "pt-BR",
    ) -> tuple[bool, str]:
        """Envia o código de 6 dígitos (entrar sem senha ou confirmar a exclusão da conta)."""
        if not self.is_configured():
            # O código só vai para o log em DEBUG, pelo mesmo motivo dos links (ver _log_unsent)
            if DEBUG:
                print(f"[auth:simulated] Código de {purpose} para <{to_email}>: {code}")
            else:
                print(f"[auth] SMTP não configurado: código de {purpose} não enviado (defina SMTP_HOST)")
            return True, "simulated"

        copy = _CODE_EMAIL_COPY["en" if str(language).lower().startswith("en") else "pt"][
            "delete_account" if purpose == "delete_account" else "login"
        ]
        subject = copy["subject"].format(code=code)
        text_content = copy["text"].format(code=code, minutes=minutes)
        html_content = _render_code_email(code=code, minutes=minutes, copy=copy)
        return self._deliver(subject, to_email, text_content, html_content, f"código ({purpose})")

    def _deliver(self, subject: str, to_email: str, text_content: str, html_content: str, kind: str) -> tuple[bool, str]:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.sender_header()
        msg["To"] = to_email

        msg.attach(MIMEText(text_content, "plain", "utf-8"))
        msg.attach(MIMEText(html_content, "html", "utf-8"))

        try:
            smtp_cls = smtplib.SMTP_SSL if self.use_ssl else smtplib.SMTP
            with smtp_cls(self.host, self.port, timeout=10) as server:
                if self.use_tls and not self.use_ssl:
                    server.starttls()
                if self.user and self.password:
                    server.login(self.user, self.password)
                server.sendmail(self.from_email, [to_email], msg.as_string())

            if DEBUG:
                print(f"[email] E-mail de {kind} enviado com sucesso para {to_email}")
            return True, "sent"
        except Exception as e:
            print(f"[email] Erro ao enviar e-mail via SMTP ({self.host}:{self.port}): {e}")
            return False, str(e)


def _render_email(username: str, url: str, intro: str, button: str, expiry: str, closing: str) -> str:
    """Modelo HTML dos e-mails. `intro`, `expiry` e `closing` são texto fixo do código;
    o nome de usuário e o link vêm de fora e são escapados."""
    # Logo em PNG (clientes de e-mail bloqueiam SVG) no mesmo domínio do link enviado
    parsed = urlparse(url)
    site_url = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else "https://acely.com.br"
    logo_url = f"{site_url}/web/icons/favicon-192.png"
    site_label = parsed.netloc or "acely.com.br"
    safe_user = escape(username)
    safe_url = escape(url, quote=True)
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <style>
    body {{
      margin: 0; padding: 0; background-color: #f4f0e8;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
      color: #182326;
    }}
    .container {{
      max-width: 560px; margin: 30px auto; background-color: #ffffff;
      border: 1px solid #d8d0c3; border-radius: 12px; overflow: hidden;
      box-shadow: 0 4px 16px rgba(24,35,38,0.08);
    }}
    .header {{
      padding: 28px 32px; background-color: #0d3f3d;
      border-bottom: 1px solid #0d3f3d; text-align: center;
    }}
    .header img {{
      display: block; margin: 0 auto 12px; border: 0;
    }}
    .header h1 {{
      margin: 0; font-size: 22px; color: #f4f0e8; letter-spacing: -0.3px;
    }}
    .header p {{
      margin: 6px 0 0; font-size: 13px; color: #c9ddd9;
    }}
    .content {{
      padding: 32px; font-size: 15px; line-height: 1.6; color: #182326;
    }}
    .btn-wrapper {{
      text-align: center; margin: 28px 0;
    }}
    .btn {{
      display: inline-block; background-color: #c9462a; color: #ffffff !important;
      text-decoration: none; padding: 13px 28px; border-radius: 6px;
      font-weight: 700; font-size: 14px; letter-spacing: 0.3px;
    }}
    .fallback-link {{
      background: #f4f0e8; padding: 12px; border-radius: 8px;
      font-family: monospace; font-size: 12px; word-break: break-all;
      color: #176b67; margin-top: 14px;
    }}
    .footer {{
      padding: 20px 32px; background-color: #f4f0e8;
      border-top: 1px solid #d8d0c3; font-size: 12px; color: #5b635e; text-align: center;
    }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <img src="{logo_url}" alt="" width="48" height="48">
      <h1>Acely</h1>
      <p>Acesso à Plataforma de Simulados</p>
    </div>
    <div class="content">
      <p>Olá, <strong>{safe_user}</strong>,</p>
      <p>{intro}</p>
      <div class="btn-wrapper">
        <a href="{safe_url}" class="btn" target="_blank" rel="noopener">{button}</a>
      </div>
      <p style="font-size: 13px; color: #5b635e;">
        {expiry} Se o botão não funcionar, copie e cole o endereço abaixo no seu navegador:
      </p>
      <div class="fallback-link">{safe_url}</div>
      <p style="font-size: 12px; color: #5b635e; margin-top: 24px;">
        {closing}
      </p>
    </div>
    <div class="footer">
      Acely · Treinamento e simulados com IA ·
      <a href="{site_url}" style="color: #176b67;" target="_blank" rel="noopener">{site_label}</a>
    </div>
  </div>
</body>
</html>
"""


# Textos do e-mail com código. Ficam aqui (e não no dicionário do navegador) porque o
# e-mail é montado no servidor; o idioma vem do campo `language` do pedido.
_CODE_EMAIL_COPY = {
    "pt": {
        "login": {
            "subject": "Seu código do Acely: {code}",
            "title": "Seu código de acesso",
            "intro": "Use o código abaixo para entrar no Acely. Se ainda não tem conta, ela é criada agora, de graça.",
            "expiry": "O código vale por <strong>{minutes} minutos</strong> e só pode ser usado uma vez.",
            "closing": "Se você não pediu este código, pode ignorar este e-mail. Ninguém entra na sua conta sem ele.",
            "text": (
                "Seu código de acesso ao Acely: {code}\n\n"
                "Ele vale por {minutes} minutos e só pode ser usado uma vez.\n"
                "Se você não pediu este código, pode ignorar este e-mail.\n\n"
                "Equipe Acely"
            ),
            "footer": "Acely · Simulados com IA",
            "lang": "pt-BR",
        },
        "delete_account": {
            "subject": "Código para excluir sua conta no Acely",
            "title": "Confirme a exclusão da conta",
            "intro": "Recebemos um pedido para excluir sua conta no Acely com os simulados privados e o histórico. "
            "Digite o código abaixo em Minha conta para confirmar.",
            "expiry": "O código vale por <strong>{minutes} minutos</strong>. A exclusão não pode ser desfeita.",
            "closing": "Se não foi você, ignore este e-mail: sem o código a conta continua como está.",
            "text": (
                "Código para confirmar a exclusão da sua conta no Acely: {code}\n\n"
                "Ele vale por {minutes} minutos. A exclusão não pode ser desfeita.\n"
                "Se não foi você, ignore este e-mail.\n\n"
                "Equipe Acely"
            ),
            "footer": "Acely · Simulados com IA",
            "lang": "pt-BR",
        },
    },
    "en": {
        "login": {
            "subject": "Your Acely code: {code}",
            "title": "Your sign in code",
            "intro": "Use the code below to sign in to Acely. If you do not have an account yet, a free one is created now.",
            "expiry": "The code is valid for <strong>{minutes} minutes</strong> and works only once.",
            "closing": "If you did not ask for this code, you can ignore this email. No one gets into your account without it.",
            "text": (
                "Your Acely sign in code: {code}\n\n"
                "It is valid for {minutes} minutes and works only once.\n"
                "If you did not ask for this code, you can ignore this email.\n\n"
                "The Acely team"
            ),
            "footer": "Acely · AI practice tests",
            "lang": "en",
        },
        "delete_account": {
            "subject": "Code to delete your Acely account",
            "title": "Confirm account deletion",
            "intro": "We received a request to delete your Acely account with its private tests and history. "
            "Enter the code below in My account to confirm.",
            "expiry": "The code is valid for <strong>{minutes} minutes</strong>. Deletion cannot be undone.",
            "closing": "If this was not you, ignore this email: without the code the account stays as it is.",
            "text": (
                "Code to confirm deleting your Acely account: {code}\n\n"
                "It is valid for {minutes} minutes. Deletion cannot be undone.\n"
                "If this was not you, ignore this email.\n\n"
                "The Acely team"
            ),
            "footer": "Acely · AI practice tests",
            "lang": "en",
        },
    },
}


def _render_code_email(code: str, minutes: int, copy: dict) -> str:
    """Modelo HTML do e-mail com código. O código é gerado no servidor (só dígitos) e os
    textos são fixos; ainda assim tudo passa por escape antes de entrar no HTML."""
    site_url = (APP_URL or "https://acely.com.br").rstrip("/")
    logo_url = f"{site_url}/web/icons/favicon-192.png"
    site_label = urlparse(site_url).netloc or "acely.com.br"
    digits = escape(code)
    # Três + três dígitos, mais fáceis de ler e de digitar
    spaced = f"{digits[:3]}&nbsp;{digits[3:]}" if len(digits) == 6 else digits
    expiry = copy["expiry"].format(minutes=int(minutes))
    return f"""<!DOCTYPE html>
<html lang="{copy['lang']}">
<head>
  <meta charset="utf-8">
  <meta name="color-scheme" content="light only">
</head>
<body style="margin:0;padding:0;background-color:#f4f0e8;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#182326;">
  <div style="max-width:520px;margin:32px auto;background-color:#ffffff;border:1px solid #d8d0c3;border-radius:16px;overflow:hidden;">
    <div style="padding:24px 32px;background-color:#0d3f3d;text-align:center;">
      <img src="{escape(logo_url, quote=True)}" alt="Acely" width="40" height="40" style="display:block;margin:0 auto;border:0;">
    </div>
    <div style="padding:32px;font-size:16px;line-height:24px;">
      <h1 style="margin:0 0 12px;font-size:24px;line-height:32px;color:#182326;">{escape(copy['title'])}</h1>
      <p style="margin:0 0 24px;color:#3d4744;">{escape(copy['intro'])}</p>
      <div style="margin:0 0 24px;padding:24px 16px;background-color:#f4f0e8;border:1px solid #d8d0c3;border-radius:12px;text-align:center;">
        <span style="font-family:'DM Mono',ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:36px;line-height:40px;letter-spacing:6px;font-weight:700;color:#0d3f3d;">{spaced}</span>
      </div>
      <p style="margin:0 0 16px;font-size:14px;line-height:20px;color:#5b635e;">{expiry}</p>
      <p style="margin:0;font-size:14px;line-height:20px;color:#5b635e;">{escape(copy['closing'])}</p>
    </div>
    <div style="padding:16px 32px;background-color:#f4f0e8;border-top:1px solid #d8d0c3;font-size:12px;line-height:16px;color:#5b635e;text-align:center;">
      {escape(copy['footer'])} ·
      <a href="{escape(site_url, quote=True)}" style="color:#176b67;" target="_blank" rel="noopener">{escape(site_label)}</a>
    </div>
  </div>
</body>
</html>
"""
