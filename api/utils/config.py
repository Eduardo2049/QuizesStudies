"""Configurações da aplicação"""
import os
from pathlib import Path

# Carregar variáveis do .env se existir
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent.parent / ".env", encoding="utf-8", override=True)
except ImportError:
    pass  # python-dotenv não instalado; usar env vars do SO

# Caminhos
ROOT = Path(__file__).parent.parent.parent
API_DIR = ROOT / "api"
WEB_DIR = ROOT / "web"

# Server
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", os.getenv("QUIZ_PORT", "8000")))

# Logging
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

# Banco de dados PostgreSQL (suporta DATABASE_URL, POSTGRES_URL e DATABASE_URL_UNPOOLED da Vercel/Neon)
DATABASE_URL = (
    os.getenv("DATABASE_URL")
    or os.getenv("POSTGRES_URL")
    or os.getenv("DATABASE_URL_UNPOOLED")
    or os.getenv("POSTGRES_PRISMA_URL")
)

# Provedor de Inteligência Artificial: OpenRouter, só com modelos gratuitos (id terminado em ":free").
# Enquanto não houver faturamento, nenhum modelo pago é chamado.
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").strip()
# Modelos gratuitos preferidos, em ordem, separados por vírgula. Ids sem ":free" são ignorados.
_DEFAULT_FREE_MODELS = (
    "nvidia/nemotron-3.5-lightning:free,"
    "nvidia/nemotron-3-ultra-550b-a55b:free,"
    "nvidia/nemotron-3.5-super-vl:free"
)
OPENROUTER_FREE_MODELS = [
    model.strip()
    for model in (os.getenv("OPENROUTER_FREE_MODELS") or _DEFAULT_FREE_MODELS).split(",")
    if model.strip().endswith(":free")
]
# O catálogo gratuito muda com frequência: com a descoberta ligada, o servidor consulta a lista
# pública de modelos do OpenRouter (cache de 6 h), descarta os preferidos que saíram do ar e
# usa os outros gratuitos como reserva.
OPENROUTER_DISCOVER_FREE_MODELS = os.getenv("OPENROUTER_DISCOVER_FREE_MODELS", "true").lower() == "true"

# Google AI Studio (Gemini) — desativado por enquanto. Para voltar a usar no futuro:
# descomente o bloco abaixo, o import em ai_service.py e o trecho "Google AI Studio" em _call_openrouter().
# GEMINI_API_KEY = (
#     os.getenv("GEMINI_API_KEY")
#     or os.getenv("GOOGLE_API_KEY")
#     or os.getenv("GEMINI_KEY")
#     or os.getenv("GOOGLE_AI_KEY")
#     or ""
# ).strip()
# GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest").strip()
# GEMINI_BASE_URL = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai").strip()

# Autenticação e Segurança
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
# ADMIN_PASSWORD deve ser sempre definido via variável de ambiente.
# O fallback abaixo é apenas para desenvolvimento local — nunca use em produção.
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "").split(",")
    if origin.strip() and origin.strip() != "*"
]
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "true").lower() == "true"
TRUST_PROXY = os.getenv("TRUST_PROXY", "false").lower() == "true" or os.getenv("VERCEL") == "1"

def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    """Lê um inteiro do ambiente limitado a [minimum, maximum]; valor inválido usa o padrão."""
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


# Modo convidado (acesso sem conta) — cota gratuita de IA
# GUEST_AI_LIMIT: usos de IA por convidado na janela (gerar por tema, upload que precisa de IA, variações).
# GUEST_AI_IP_LIMIT: teto por IP somando todos os convidados (barra quem apaga cookies para renovar a cota
#   sem punir redes compartilhadas como escolas e CGNAT de operadoras móveis).
# A janela é limitada a 24 h porque a tabela rate_limits descarta registros mais antigos que isso.
GUEST_AI_LIMIT = _env_int("GUEST_AI_LIMIT", 3, 0, 50)
GUEST_AI_IP_LIMIT = _env_int("GUEST_AI_IP_LIMIT", 10, 1, 500)
GUEST_AI_WINDOW_SECONDS = _env_int("GUEST_AI_WINDOW_HOURS", 24, 1, 24) * 60 * 60

# Teto global de chamadas à IA por 24 h, somando todos os usuários (trava de emergência
# contra a conta do provedor estourar). 0 desliga. Os modelos gratuitos do OpenRouter têm
# limite diário por conta (50 pedidos sem créditos comprados; 1.000 com pelo menos US$ 10
# comprados); ajuste para ficar abaixo dele.
AI_DAILY_CALL_LIMIT = _env_int("AI_DAILY_CALL_LIMIT", 1000, 0, 1_000_000)

# Quantos modelos gratuitos tentar em um mesmo pedido antes de desistir (cada tentativa
# conta no limite diário do OpenRouter).
OPENROUTER_MAX_ATTEMPTS = _env_int("OPENROUTER_MAX_ATTEMPTS", 4, 1, 8)

# Entrar com Google (OAuth). Vazio = botão escondido e rotas desligadas.
# URI de redirecionamento a cadastrar no Google Cloud: <APP_URL>/api/auth/google/callback
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()

# Cloudflare Tunnel
CLOUDFLARE_TUNNEL_TOKEN = os.getenv("CLOUDFLARE_TUNNEL_TOKEN", "")

# E-mail e SMTP (Recuperação de Senha)
SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").strip()
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER or "noreply@quiz.study").strip()
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() in ("true", "1", "yes")
SMTP_USE_SSL = os.getenv("SMTP_USE_SSL", "false").lower() in ("true", "1", "yes")
APP_URL = os.getenv("APP_URL", "").strip()

# Controle de migrações automáticas (true por padrão; defina false se as migrations rodarem no pipeline de CI/CD)
AUTO_MIGRATE = os.getenv("AUTO_MIGRATE", "true").lower() in ("true", "1", "yes")


