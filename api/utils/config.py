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

# Provedores de Inteligência Artificial
# 1. Google AI Studio (Gratuito direto do Google: 1.500 req/dia)
GEMINI_API_KEY = (
    os.getenv("GEMINI_API_KEY")
    or os.getenv("GOOGLE_API_KEY")
    or os.getenv("GEMINI_KEY")
    or os.getenv("GOOGLE_AI_KEY")
    or ""
).strip()
_raw_gemini_model = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest").strip()
if _raw_gemini_model in ("gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash", "google/gemini-2.5-flash", "gemini-flash-latest", ""):
    GEMINI_MODEL = "gemini-flash-lite-latest"
else:
    GEMINI_MODEL = _raw_gemini_model
GEMINI_BASE_URL = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai").strip()

# 2. OpenRouter (Multi-provedor com créditos ou modelos gratuitos)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemini-2.5-flash").strip()
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").strip()

# 3. Provedor ativo ('google' | 'openrouter' | 'auto')
AI_PROVIDER = os.getenv("AI_PROVIDER", "google" if GEMINI_API_KEY else "openrouter").strip().lower()

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

# Cloudflare Tunnel
CLOUDFLARE_TUNNEL_TOKEN = os.getenv("CLOUDFLARE_TUNNEL_TOKEN", "")

