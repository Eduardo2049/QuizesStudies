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
# Na Vercel, só o que está em public/ vai para a CDN; o resto passa pela função Python.
# public/web/app.js continua no endereço /web/app.js.
PUBLIC_DIR = ROOT / "public"
WEB_DIR = PUBLIC_DIR / "web"

# Server
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", os.getenv("QUIZ_PORT", "8000")))

# Logging
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

# Banco de dados PostgreSQL — qualquer provedor (Neon, Supabase, Docker, outro).
# Ordem: ACELY_DATABASE_URL (sua, com nome que nenhuma integração usa), DATABASE_URL e, por
# último, os outros nomes que a integração Neon da Vercel cria (POSTGRES_URL,
# DATABASE_URL_UNPOOLED, POSTGRES_PRISMA_URL). A integração ocupa e trava o nome DATABASE_URL
# na Vercel; para usar uma URL sua lá (ex.: com sslmode=verify-full), cadastre ACELY_DATABASE_URL.
_OWN_DATABASE_URL = (os.getenv("ACELY_DATABASE_URL") or "").strip()
_EXPLICIT_DATABASE_URL = _OWN_DATABASE_URL or (os.getenv("DATABASE_URL") or "").strip()
DATABASE_URL = (
    _EXPLICIT_DATABASE_URL
    or os.getenv("POSTGRES_URL")
    or os.getenv("DATABASE_URL_UNPOOLED")
    or os.getenv("POSTGRES_PRISMA_URL")
)


def _resolve_direct_database_url() -> str | None:
    """URL sem pooler, usada por migrations e scripts de manutenção.

    Ordem: ACELY_DATABASE_URL_DIRECT ou DATABASE_URL_DIRECT; se a URL da aplicação foi
    cadastrada à mão (ACELY_DATABASE_URL ou DATABASE_URL), a própria URL da aplicação (assim
    uma variável da integração Neon nunca aponta as migrations para outro banco); senão, as
    variáveis sem pooler da integração.
    """
    direct = (os.getenv("ACELY_DATABASE_URL_DIRECT") or os.getenv("DATABASE_URL_DIRECT") or "").strip()
    if direct:
        return direct
    if _EXPLICIT_DATABASE_URL:
        return _EXPLICIT_DATABASE_URL
    return (
        os.getenv("DATABASE_URL_UNPOOLED")
        or os.getenv("POSTGRES_URL_NON_POOLING")
        or DATABASE_URL
    )


DATABASE_URL_DIRECT = _resolve_direct_database_url()

# TLS do banco. DB_SSLMODE só é aplicado quando a URL não traz sslmode.
# DB_SSLROOTCERT: caminho do certificado da autoridade (ex.: o .crt baixado do Supabase).
# Vazio = arquivo do certifi (Neon e outras autoridades públicas). Ver connection._default_ca_file.
DB_SSLMODE = os.getenv("DB_SSLMODE", "verify-full").strip() or "verify-full"
DB_SSLROOTCERT = os.getenv("DB_SSLROOTCERT", "").strip()
if DB_SSLROOTCERT and DB_SSLROOTCERT != "system" and not Path(DB_SSLROOTCERT).is_absolute():
    DB_SSLROOTCERT = str(ROOT / DB_SSLROOTCERT)  # caminho relativo à raiz do projeto
# Alternativa para a Vercel: o conteúdo PEM do certificado direto na variável. O servidor grava
# num arquivo temporário e usa como DB_SSLROOTCERT (o certificado é público, não é segredo).
DB_SSLROOTCERT_PEM = os.getenv("DB_SSLROOTCERT_PEM", "").strip()

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

# ─── Vários provedores gratuitos em sequência (docs/PLANO_ACELY.md, Fase 2) ──────────────────
# Todos falam o formato de chat da OpenAI. A IA tenta os provedores na ordem de AI_PROVIDERS;
# quando um bate no limite (429), falha ou fica sem resposta, passa ao próximo. Provedor sem
# chave fica de fora: sem GROQ/GEMINI/CEREBRAS, o comportamento é o de antes (só OpenRouter).
_KNOWN_AI_PROVIDERS = ("groq", "gemini", "cerebras", "openrouter")
AI_PROVIDERS = [
    name for name in (
        p.strip().lower() for p in (os.getenv("AI_PROVIDERS") or "groq,gemini,cerebras,openrouter").split(",")
    )
    if name in _KNOWN_AI_PROVIDERS
] or ["openrouter"]


def _env_list(name: str, default: str) -> list[str]:
    return [item.strip() for item in (os.getenv(name) or default).split(",") if item.strip()]


# Groq (console.groq.com): rápido; não usa os dados para treino. Limite grátis por modelo:
# ~1.000 pedidos/dia, 200 mil tokens/dia e 8 mil tokens/min (conferir no painel).
GROQ_API_KEY = (os.getenv("GROQ_API_KEY") or "").strip()
GROQ_BASE_URL = (os.getenv("GROQ_BASE_URL") or "https://api.groq.com/openai/v1").strip()
GROQ_MODELS = _env_list("GROQ_MODELS", "openai/gpt-oss-120b,openai/gpt-oss-20b")

# Google AI Studio (Gemini), pelo endereço compatível com a OpenAI. No plano gratuito o Google
# USA o conteúdo enviado para melhorar os produtos dele (avisado em /privacidade).
GEMINI_API_KEY = (
    os.getenv("GEMINI_API_KEY")
    or os.getenv("GOOGLE_API_KEY")
    or os.getenv("GEMINI_KEY")
    or os.getenv("GOOGLE_AI_KEY")
    or ""
).strip()
GEMINI_BASE_URL = (
    os.getenv("GEMINI_BASE_URL") or "https://generativelanguage.googleapis.com/v1beta/openai"
).strip()
# GEMINI_MODEL (nome antigo, um só modelo) ainda é aceito
GEMINI_MODELS = _env_list("GEMINI_MODELS", os.getenv("GEMINI_MODEL") or "gemini-3.5-flash-lite,gemini-flash-lite-latest")

# Cerebras (cloud.cerebras.ai): opcional. O teste grátis exige cartão, expira e tem contexto
# menor (~8 mil tokens): arquivos grandes passam direto para o próximo provedor.
CEREBRAS_API_KEY = (os.getenv("CEREBRAS_API_KEY") or "").strip()
CEREBRAS_BASE_URL = (os.getenv("CEREBRAS_BASE_URL") or "https://api.cerebras.ai/v1").strip()
CEREBRAS_MODELS = _env_list("CEREBRAS_MODELS", "gpt-oss-120b")

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

# Tempo máximo, em segundos, que um modelo pode ficar sem mandar nada (antes do primeiro
# trecho da resposta ou entre dois trechos). A resposta vem em partes (streaming): um modelo
# parado na fila é abandonado nesse tempo, e um que está escrevendo continua até o tempo total.
AI_ATTEMPT_TIMEOUT = _env_int("AI_ATTEMPT_TIMEOUT", 20, 5, 120)

# Pedidos de IA com identificador (request_id): recarregar a página não refaz nem cobra de novo.
# Simulados por tema ficam guardados no banco (ai_cache) por este número de dias.
AI_CACHE_TTL_DAYS = _env_int("AI_CACHE_TTL_DAYS", 7, 0, 90)


def _provider_budget(name: str, requests_default: int, tokens_default: int) -> tuple[int, int]:
    """Orçamento diário por modelo do provedor: (pedidos, tokens). 0 = sem controle.

    Fica um pouco abaixo do limite grátis para o provedor ser pulado antes de responder 429.
    """
    return (
        _env_int(f"{name}_DAILY_REQUESTS", requests_default, 0, 10_000_000),
        _env_int(f"{name}_DAILY_TOKENS", tokens_default, 0, 1_000_000_000),
    )


GROQ_DAILY_REQUESTS, GROQ_DAILY_TOKENS = _provider_budget("GROQ", 950, 190_000)
GEMINI_DAILY_REQUESTS, GEMINI_DAILY_TOKENS = _provider_budget("GEMINI", 450, 0)
CEREBRAS_DAILY_REQUESTS, CEREBRAS_DAILY_TOKENS = _provider_budget("CEREBRAS", 0, 950_000)

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
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER or "noreply@acely.com.br").strip()
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() in ("true", "1", "yes")
SMTP_USE_SSL = os.getenv("SMTP_USE_SSL", "false").lower() in ("true", "1", "yes")
APP_URL = os.getenv("APP_URL", "").strip()

# Controle de migrações automáticas (true por padrão; defina false se as migrations rodarem no pipeline de CI/CD)
AUTO_MIGRATE = os.getenv("AUTO_MIGRATE", "true").lower() in ("true", "1", "yes")


