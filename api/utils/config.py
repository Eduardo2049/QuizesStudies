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

# ─── Vários provedores em sequência (docs/ARQUITETURA.md, seção da IA) ──────────────────────
# Todos falam OpenAI Chat Completions (ou Responses API na OpenAI). A IA tenta os provedores
# na ordem de AI_PROVIDERS; quando um bate no limite (429), falha ou fica sem resposta, passa
# ao próximo. Provedor sem chave fica de fora. Internamente a OpenAI se chama "codex" (nome
# antigo); "openai" é aceito em AI_PROVIDERS e é o nome que aparece nos logs.
_KNOWN_AI_PROVIDERS = ("codex", "groq", "gemini", "cerebras", "openrouter")
_AI_PROVIDER_ALIASES = {"openai": "codex", "google": "gemini"}
_DEFAULT_AI_PROVIDERS = "codex,groq,gemini,cerebras,openrouter"


def _split_ai_providers(raw: str | None) -> tuple[list[str], list[str]]:
    """(ordem reconhecida, nomes ignorados) de AI_PROVIDERS; aceita 'openai' como apelido de 'codex'."""
    source = raw if raw is not None and raw.strip() else _DEFAULT_AI_PROVIDERS
    ordered: list[str] = []
    ignored: list[str] = []
    for item in source.split(","):
        raw_name = item.strip().lower()
        if not raw_name:
            continue
        name = _AI_PROVIDER_ALIASES.get(raw_name, raw_name)
        if name not in _KNOWN_AI_PROVIDERS:
            ignored.append(item.strip())
        elif name not in ordered:
            ordered.append(name)
    return ordered or ["openrouter"], ignored


def _parse_ai_providers(raw: str | None) -> list[str]:
    """Lê a ordem de prioridade dos provedores de IA (aceita 'openai' como apelido de 'codex')."""
    return _split_ai_providers(raw)[0]


AI_PROVIDERS, AI_PROVIDERS_IGNORED = _split_ai_providers(os.getenv("AI_PROVIDERS"))
# True quando AI_PROVIDERS veio do ambiente (o diagnóstico avisa se ele deixa de fora uma chave)
AI_PROVIDERS_FROM_ENV = bool((os.getenv("AI_PROVIDERS") or "").strip())


def _env_list(name: str, default: str) -> list[str]:
    return [item.strip() for item in (os.getenv(name) or default).split(",") if item.strip()]


# OpenAI (platform.openai.com): usada primeiro quando OPENAI_API_KEY (ou o nome antigo
# CODEX_API_KEY) estiver configurada; vazio = pulada. Para usar SOMENTE a OpenAI, defina
# AI_PROVIDERS=openai.
# Modelos (OPENAI_MODELS; o nome antigo CODEX_MODELS ainda vale): o padrão é o gpt-6-luna
# (substituto indicado pela OpenAI para gpt-5-nano e gpt-4o-mini) com o gpt-4o-mini de reserva.
# gpt-5-nano e gpt-5-mini saem do ar em 11/12/2026 e codex-mini-latest já saiu (lista em
# OPENAI_MODEL_SHUTDOWNS, no ai_service.py: modelo vencido é pulado sem gastar pedido).
# CODEX_API_MODE: "auto" (usa /responses em modelos *codex* e /chat/completions nos demais,
# com troca automática), "responses" ou "chat".
CODEX_API_KEY = (os.getenv("OPENAI_API_KEY") or os.getenv("CODEX_API_KEY") or "").strip()
CODEX_BASE_URL = (os.getenv("OPENAI_BASE_URL") or os.getenv("CODEX_BASE_URL") or "https://api.openai.com/v1").strip()
_DEFAULT_OPENAI_MODELS = "gpt-6-luna,gpt-4o-mini"
if (os.getenv("OPENAI_MODELS") or "").strip():
    CODEX_MODELS_SOURCE = "OPENAI_MODELS"
elif (os.getenv("CODEX_MODELS") or "").strip():
    CODEX_MODELS_SOURCE = "CODEX_MODELS"
else:
    CODEX_MODELS_SOURCE = "padrão"
CODEX_MODELS = _env_list("OPENAI_MODELS", os.getenv("CODEX_MODELS") or _DEFAULT_OPENAI_MODELS)
_codex_mode = (os.getenv("CODEX_API_MODE") or os.getenv("OPENAI_API_MODE") or "auto").strip().lower()
CODEX_API_MODE = _codex_mode if _codex_mode in ("auto", "responses", "chat") else "auto"

# Conferência de gabarito por um segundo modelo (docs/ARQUITETURA.md, seção da IA).
# "account" (padrão): só quem tem conta; "all": conta e convidado; "off": desligada.
_cross_check_mode = (os.getenv("AI_CROSS_CHECK") or "account").strip().lower()
AI_CROSS_CHECK = _cross_check_mode if _cross_check_mode in ("account", "all", "off") else "account"


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

# Pedidos de IA por minuto por usuário (ou convidado), somando gerar por tema, variações e
# upload que precisa de IA. 0 desliga. Protege o saldo da API contra rajadas. Conta o pedido
# da pessoa (um simulado de 20 questões em 4 partes é 1 pedido) e devolve a vaga quando a IA
# falha ou quando o resultado vem pronto (cache ou tema de exemplo).
AI_USER_REQUESTS_PER_MINUTE = _env_int("AI_USER_REQUESTS_PER_MINUTE", 10, 0, 120)

# Teto global de chamadas à IA por 24 h, somando todos os usuários (trava de emergência
# contra a conta do provedor estourar). 0 desliga. Conta CADA chamada ao provedor: com a OpenAI na
# frente, um simulado usa uma chamada por parte de 3 questões e outra para conferir cada parte
# (média ~8; até 20 num de 30 questões); nos gratuitos, partes de 5. O custo em tokens quase não
# muda com as partes. Com só os modelos gratuitos do OpenRouter sem créditos (50/dia), use 40.
AI_DAILY_CALL_LIMIT = _env_int("AI_DAILY_CALL_LIMIT", 3000, 0, 1_000_000)

# Quantos modelos gratuitos tentar em um mesmo pedido antes de desistir (cada tentativa
# conta no limite diário do OpenRouter).
OPENROUTER_MAX_ATTEMPTS = _env_int("OPENROUTER_MAX_ATTEMPTS", 4, 1, 8)

# Tempo máximo, em segundos, que um modelo pode ficar sem mandar nada (antes do primeiro
# trecho da resposta ou entre dois trechos). A resposta vem em partes (streaming): um modelo
# parado na fila é abandonado nesse tempo, e um que está escrevendo continua até o tempo total.
AI_ATTEMPT_TIMEOUT = _env_int("AI_ATTEMPT_TIMEOUT", 20, 5, 120)

# Velocidade da geração por tema. Mais de AI_PART_SIZE questões viram partes geradas ao mesmo
# tempo (até AI_PARALLEL_PARTS), e a conferência do gabarito roda em cada parte assim que ela fica
# pronta. 0 = automático: com a OpenAI na frente, partes de 3 e até 10 ao mesmo tempo (o total fica
# perto do tempo de uma parte pequena); só com provedores gratuitos, partes de 5 e até 3 ao mesmo
# tempo (respeita os limites por minuto do Groq). Cada parte conta uma chamada em AI_DAILY_CALL_LIMIT.
AI_PART_SIZE = _env_int("AI_PART_SIZE", 0, 0, 10)
AI_PARALLEL_PARTS = _env_int("AI_PARALLEL_PARTS", 0, 0, 12)

# Parte da geração por tema que não respondeu em AI_HEDGE_AFTER_SECONDS ganha um segundo pedido
# igual (de preferência em outro provedor); vale o que chegar primeiro. 0 desliga.
AI_HEDGE_AFTER_SECONDS = _env_int("AI_HEDGE_AFTER_SECONDS", 12, 0, 60)

# OpenAI "Fast mode" (service_tier=fast): respostas até ~2,5x mais rápidas nos modelos aceitos, com
# preço por token maior. Vazio = padrão da conta. Modelo que recusar o parâmetro é pedido sem ele.
_openai_tier = (os.getenv("OPENAI_SERVICE_TIER") or "").strip().lower()
OPENAI_SERVICE_TIER = _openai_tier if _openai_tier in ("auto", "default", "flex", "fast", "priority") else ""

# Pedidos de IA com identificador (request_id): recarregar a página não refaz nem cobra de novo.
# Simulados por tema ficam guardados no banco (ai_cache) por este número de dias.
AI_CACHE_TTL_DAYS = _env_int("AI_CACHE_TTL_DAYS", 7, 0, 90)


def _provider_budget(
    name: str, requests_default: int, tokens_default: int, alias: str | None = None
) -> tuple[int, int]:
    """Orçamento diário por modelo do provedor: (pedidos, tokens). 0 = sem controle.

    Fica um pouco abaixo do limite grátis para o provedor ser pulado antes de responder 429.
    `alias` é um prefixo que vale antes de `name` (ex.: OPENAI_DAILY_* antes de CODEX_DAILY_*).
    """
    def pick(suffix: str) -> str:
        if alias and (os.getenv(f"{alias}_{suffix}") or "").strip():
            return f"{alias}_{suffix}"
        return f"{name}_{suffix}"

    return (
        _env_int(pick("DAILY_REQUESTS"), requests_default, 0, 10_000_000),
        _env_int(pick("DAILY_TOKENS"), tokens_default, 0, 1_000_000_000),
    )


CODEX_DAILY_REQUESTS, CODEX_DAILY_TOKENS = _provider_budget("CODEX", 500, 500_000, alias="OPENAI")
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

# Entrar com código de 6 dígitos enviado por e-mail (substitui usuário e senha na tela de login).
# LOGIN_CODE_TTL_MINUTES: validade do código. LOGIN_CODE_MAX_ATTEMPTS: palpites errados antes de o
# código ser descartado. LOGIN_CODE_RESEND_SECONDS: espera entre dois envios para o mesmo e-mail.
# LOGIN_CODE_MAX_PER_HOUR: códigos por e-mail por hora (impede usar o Acely para lotar a caixa de alguém).
LOGIN_CODE_TTL_MINUTES = _env_int("LOGIN_CODE_TTL_MINUTES", 10, 3, 60)
LOGIN_CODE_MAX_ATTEMPTS = _env_int("LOGIN_CODE_MAX_ATTEMPTS", 5, 3, 10)
LOGIN_CODE_RESEND_SECONDS = _env_int("LOGIN_CODE_RESEND_SECONDS", 60, 15, 600)
LOGIN_CODE_MAX_PER_HOUR = _env_int("LOGIN_CODE_MAX_PER_HOUR", 5, 1, 50)
# Chave secreta do HMAC que guarda os códigos no banco: com ela fora do banco, uma cópia vazada
# da tabela não permite testar os 1 milhão de códigos possíveis. Sem a variável, a chave é
# derivada de ADMIN_PASSWORD (trocar a senha do admin só invalida os códigos dos últimos minutos).
AUTH_CODE_SECRET = os.getenv("AUTH_CODE_SECRET", "").strip()

# Controle de migrações automáticas (true por padrão; defina false se as migrations rodarem no pipeline de CI/CD)
AUTO_MIGRATE = os.getenv("AUTO_MIGRATE", "true").lower() in ("true", "1", "yes")


