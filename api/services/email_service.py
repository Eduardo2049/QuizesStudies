"""
Serviço de envio de e-mails para recuperação de senha e notificações
Utiliza a biblioteca padrão do Python (smtplib e email.mime).
Quando o SMTP não está configurado, opera em modo simulado para desenvolvimento e testes.
"""
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, parseaddr
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
            # Sem emoji: consoles Windows (cp1252) lançam UnicodeEncodeError no print
            msg_log = (
                f"[auth:simulated] Link de recuperação para '{username}' <{to_email}>: "
                f"{reset_url} (token: {token})"
            )
            print(msg_log)
            return True, "simulated"

        subject = "Recuperação de Senha — Acely"
        # Logo em PNG (clientes de e-mail bloqueiam SVG) no mesmo domínio do link enviado
        parsed = urlparse(reset_url)
        site_url = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else "https://acely.com.br"
        logo_url = f"{site_url}/web/icons/favicon-192.png"
        site_label = parsed.netloc or "acely.com.br"

        text_content = (
            f"Olá, {username}!\n\n"
            f"Recebemos uma solicitação para redefinir a senha da sua conta no Acely.\n"
            f"Para definir sua nova senha, acesse o link abaixo:\n\n"
            f"{reset_url}\n\n"
            f"Este link é válido por 30 minutos.\n"
            f"Se você não solicitou a recuperação, pode ignorar este e-mail com segurança.\n\n"
            f"— Equipe Acely"
        )

        html_content = f"""<!DOCTYPE html>
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
      <p>Olá, <strong>{username}</strong>,</p>
      <p>Recebemos uma solicitação para redefinir a senha da sua conta no <strong>Acely</strong>. Clique no botão abaixo para prosseguir:</p>
      <div class="btn-wrapper">
        <a href="{reset_url}" class="btn" target="_blank" rel="noopener">Redefinir Minha Senha</a>
      </div>
      <p style="font-size: 13px; color: #5b635e;">
        Este link expira em <strong>30 minutos</strong> e só pode ser utilizado uma vez. Se o botão não funcionar, copie e cole o endereço abaixo no seu navegador:
      </p>
      <div class="fallback-link">{reset_url}</div>
      <p style="font-size: 12px; color: #5b635e; margin-top: 24px;">
        Se você não fez essa solicitação, nenhuma ação é necessária — sua conta continua segura.
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
                print(f"[email] E-mail de redefinição enviado com sucesso para {to_email}")
            return True, "sent"
        except Exception as e:
            print(f"[email] Erro ao enviar e-mail via SMTP ({self.host}:{self.port}): {e}")
            return False, str(e)
