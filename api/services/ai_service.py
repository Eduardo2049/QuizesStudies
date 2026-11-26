"""
Serviço de IA com vários provedores em sequência (OpenAI, Groq, Gemini, Cerebras, OpenRouter).
Gera simulados, gabaritos e variações de questões.

Todos os provedores falam o formato de chat da OpenAI. `_call_ai` percorre os que têm chave,
na ordem de AI_PROVIDERS; quando um bate no limite, falha ou fica sem resposta, passa ao
próximo. No OpenRouter só modelos gratuitos (":free") são usados. `ai_diagnostics()` e
`test_ai_providers()` alimentam o diagnóstico do admin (GET/POST /api/admin/ia).
"""
import contextlib
import copy
import hashlib
import json
import os
import re
import time
import unicodedata
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, as_completed, wait
from typing import Any
import requests
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from collections import defaultdict, deque
from threading import Lock
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from api.repositories.rate_limit_repository import rate_limit_repo, RateLimitRepository
from api.utils.config import (
    AI_HEDGE_AFTER_SECONDS,
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    OPENROUTER_FREE_MODELS,
    OPENROUTER_DISCOVER_FREE_MODELS,
    OPENROUTER_MAX_ATTEMPTS,
    AI_ATTEMPT_TIMEOUT,
    AI_CROSS_CHECK,
    AI_DAILY_CALL_LIMIT,
    AI_PARALLEL_PARTS,
    AI_PART_SIZE,
    AI_PROVIDERS,
    AI_PROVIDERS_FROM_ENV,
    AI_PROVIDERS_IGNORED,
    AI_USER_REQUESTS_PER_MINUTE,
    CODEX_API_KEY,
    CODEX_BASE_URL,
    CODEX_MODELS,
    CODEX_API_MODE,
    CODEX_MODELS_SOURCE,
    CODEX_DAILY_REQUESTS,
    OPENAI_SERVICE_TIER,
    CODEX_DAILY_TOKENS,
    GROQ_API_KEY,
    GROQ_BASE_URL,
    GROQ_MODELS,
    GROQ_DAILY_REQUESTS,
    GROQ_DAILY_TOKENS,
    GEMINI_API_KEY,
    GEMINI_BASE_URL,
    GEMINI_MODELS,
    GEMINI_DAILY_REQUESTS,
    GEMINI_DAILY_TOKENS,
    CEREBRAS_API_KEY,
    CEREBRAS_BASE_URL,
    CEREBRAS_MODELS,
    CEREBRAS_DAILY_REQUESTS,
    CEREBRAS_DAILY_TOKENS,
    DEBUG,
)
from api.repositories.ai_job_repository import ai_job_repo
import sys

# Mensagem única para o aluno quando a falha é de configuração ou de conta do provedor
# (chave ausente/inválida, créditos): o detalhe vai só para o log do servidor.
AI_UNAVAILABLE_MESSAGE = "A geração com IA está indisponível no momento. Tente novamente mais tarde."
AI_DAILY_LIMIT_MESSAGE = "A IA atingiu o limite de uso de hoje na plataforma. Tente novamente amanhã."
AI_BUSY_MESSAGE = "Os modelos gratuitos de IA estão ocupados agora. Tente novamente em alguns instantes."
_NO_KEY_LOG = (
    "nenhuma chave de IA configurada (defina OPENAI_API_KEY, GROQ_API_KEY, GEMINI_API_KEY, "
    "CEREBRAS_API_KEY ou OPENROUTER_API_KEY, e confira AI_PROVIDERS)"
)


# Últimas linhas do log da IA nesta instância (o diagnóstico do admin mostra; some no deploy)
_ai_events: deque = deque(maxlen=80)


def _log_ops(msg: str) -> None:
    """Log operacional (sempre ligado, vai para stderr): problemas que o dono precisa ver."""
    with contextlib.suppress(Exception):
        _ai_events.append((time.time(), msg))
    try:
        print(f"[ia] {msg}", file=sys.stderr)
    except Exception:
        pass

_session = None


def _get_http_session() -> requests.Session:
    """Retorna uma sessão HTTP reutilizável com connection pooling e retry automático."""
    global _session
    if _session is None:
        _session = requests.Session()
        retries = Retry(
            total=2,
            backoff_factor=0.3,
            status_forcelist=[502, 503, 504],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retries, pool_connections=16, pool_maxsize=32)
        _session.mount("https://", adapter)
        _session.mount("http://", adapter)
    return _session


class AIServiceError(Exception):
    """Erro ao chamar a API de IA"""
    pass


class AIQuotaExceededError(Exception):
    """
    Levantada quando o IP/sessão excede a cota de tokens permitida por hora.
    Atributo `retry_after` informa quantos segundos aguardar até a janela reiniciar.
    """
    def __init__(self, message: str, retry_after: int = 3600):
        super().__init__(message)
        self.retry_after = retry_after


# ─── Cota de tokens de IA por IP ─────────────────────────────────────────────
# Limite padrão: 50.000 tokens estimados/hora por IP.
# Pode ser ajustado via variável de ambiente AI_TOKEN_QUOTA_PER_HOUR.
_AI_TOKEN_QUOTA_PER_HOUR = int(os.getenv("AI_TOKEN_QUOTA_PER_HOUR", "50000"))
_AI_TOKEN_WINDOW_SECONDS = 3600  # 1 hora


# ─── Cache de geração de simulados por IA ────────────────────────────────────
# Dois níveis: memória do processo (1 h, resposta imediata) e a tabela ai_cache no banco
# (AI_CACHE_TTL_DAYS, compartilhada entre as instâncias da Vercel).
_quiz_generation_cache: dict[str, tuple[float, dict]] = {}
_QUIZ_CACHE_TTL = 3600  # 1 hora de cache para temas idênticos
_quiz_cache_lock = Lock()


class _AttemptTimeout(Exception):
    """O modelo ficou AI_ATTEMPT_TIMEOUT segundos sem mandar nada."""


class _QuotaUsageDict(defaultdict):
    """defaultdict especializado que sincroniza remoção com a tabela rate_limits."""
    def __init__(self, default_factory=deque, repo=None):
        super().__init__(default_factory)
        self.repo = repo

    def pop(self, key, *args):
        if self.repo is not None:
            self.repo.reset(key)
            self.repo.reset(f"token_quota:{key}")
        return super().pop(key, *args)


class _TokenQuota:
    """
    Rastreia o consumo estimado de tokens de IA por chave (IP do cliente ou usuário).
    Usa persistência compartilhada (PostgreSQL) quando repo é informado
    e mantém compatibilidade total com testes locais mantendo self._lock e self._usage.
    """

    def __init__(self, quota: int, window_seconds: int, repo: RateLimitRepository | None = None):
        self.quota = quota
        self.window = window_seconds
        self.repo = repo
        self._usage = _QuotaUsageDict(deque, repo=self.repo)
        self._lock = Lock()

    def estimate_tokens(self, text: str) -> int:
        """Estima tokens como len(text) / 4, mínimo 1."""
        return max(1, len(text) // 4)

    def check_and_record(self, key: str, estimated_tokens: int) -> tuple[bool, int, int]:
        """
        Verifica se a chave tem quota disponível e registra o consumo.
        Retorna (permitido, tokens_usados_na_janela, retry_after_segundos).
        """
        now = time.time()
        cutoff = now - self.window
        with self._lock:
            entries = self._usage[key]
            while entries and entries[0][0] <= cutoff:
                entries.popleft()

            local_used = sum(t for _, t in entries)
            if local_used + estimated_tokens > self.quota:
                oldest = entries[0][0] if entries else now
                retry_after = max(1, int(oldest - cutoff + 1))
                return False, local_used, retry_after

        if self.repo is not None:
            quota_key = f"token_quota:{key}"
            allowed, retry_after = self.repo.check_and_record(
                quota_key,
                limit=self.quota,
                window_seconds=self.window,
                cost=estimated_tokens,
            )
            if not allowed:
                used = self.repo.get_usage(quota_key, self.window)
                return False, used, retry_after

        with self._lock:
            self._usage[key].append((now, estimated_tokens))
            used = sum(t for _, t in self._usage[key])

        return True, used, 0

    def get_usage(self, key: str) -> int:
        """Retorna o total de tokens estimados usados na janela atual."""
        cutoff = time.time() - self.window
        with self._lock:
            entries = self._usage.get(key, deque())
            return sum(t for ts, t in entries if ts > cutoff)


# Instância global do controle de quota com persistência
_token_quota = _TokenQuota(_AI_TOKEN_QUOTA_PER_HOUR, _AI_TOKEN_WINDOW_SECONDS, repo=rate_limit_repo)

# Chave padrão usada quando não há IP disponível (ex: chamadas internas)
_DEFAULT_QUOTA_KEY = "internal"


def check_ai_token_quota(prompt: str, ip: str | None = None) -> int:
    """
    Verifica e registra o consumo estimado de tokens para um prompt.

    Args:
        prompt: Texto do prompt a ser enviado à IA.
        ip: IP do cliente (None usa chave interna, sem limite por IP).

    Returns:
        Tokens estimados consumidos nesta chamada.

    Raises:
        AIQuotaExceededError: Se a cota horária por IP for excedida.
    """
    key = ip or _DEFAULT_QUOTA_KEY
    # Não aplica cota para chamadas internas sem IP
    if key == _DEFAULT_QUOTA_KEY:
        return _token_quota.estimate_tokens(prompt)

    estimated = _token_quota.estimate_tokens(prompt)
    allowed, used, retry_after = _token_quota.check_and_record(key, estimated)

    if not allowed:
        raise AIQuotaExceededError(
            f"Cota de tokens de IA excedida ({used:,} tokens usados na última hora). "
            f"Tente novamente em {retry_after // 60 + 1} minuto(s).",
            retry_after=retry_after,
        )

    if DEBUG:
        print(f"[ai_quota] IP={key} estimated={estimated} used_after={used}/{_AI_TOKEN_QUOTA_PER_HOUR}")

    return estimated


def _build_prompt(questions: list[dict]) -> str:
    """
    Monta o prompt para o LLM gerar o gabarito.
    Inclui todas as alternativas para que o modelo saiba quantas existem por questão.
    """
    lines = [
        "Você é um especialista em testes psicométricos e de raciocínio.",
        "Analise as questões abaixo e determine a resposta correta para cada uma.",
        "Para cada questão, informe:",
        "  - O número da questão",
        "  - O índice (base 0) da alternativa correta: 0=A, 1=B, 2=C, 3=D, 4=E, etc.",
        "  - Uma explicação concisa (1-2 frases) do raciocínio",
        "",
        "IMPORTANTE: Retorne SOMENTE um array JSON válido, sem texto adicional, no formato:",
        '[{"question_id": 1, "answer": 2, "explanation": "..."}]',
        "",
        "Questões:",
        "",
    ]

    for q in questions:
        options_text = "  ".join(
            f"{chr(65 + i)}) {opt}"
            for i, opt in enumerate(q.get("options", []))
        )
        lines.append(f"{q['id']}. {q['question']}")
        lines.append(f"   Alternativas ({len(q.get('options', []))}): {options_text}")
        lines.append("")

    return "\n".join(lines)


def _format_user_friendly_error(status_code: int, raw_text: str) -> str:
    """
    Transforma respostas de erro da API de IA em mensagens claras,
    amigáveis e sem expor detalhes técnicos, JSONs brutos ou user_id para o usuário.
    """
    msg = ""
    try:
        err_json = json.loads(raw_text)
        if isinstance(err_json, dict):
            error_obj = err_json.get("error", {})
            if isinstance(error_obj, dict):
                msg = str(error_obj.get("message", "")).strip()
            elif isinstance(error_obj, str):
                msg = error_obj.strip()
    except Exception:
        pass

    lower_msg = (msg or raw_text).lower()

    if "data policy" in lower_msg or "zdr" in lower_msg or "guardrail" in lower_msg:
        _log_ops(
            "o OpenRouter recusou os modelos gratuitos pela política de dados da conta "
            "(ex.: só endpoints ZDR): em https://openrouter.ai/settings/privacy desligue a exigência "
            "de ZDR e permita os endpoints gratuitos"
        )
        return AI_UNAVAILABLE_MESSAGE
    if status_code == 404 or "no endpoints found" in lower_msg or "model not found" in lower_msg:
        return "O modelo de IA selecionado está indisponível no provedor no momento. Tente novamente em instantes."
    if status_code in (401, 403) or "unauthorized" in lower_msg or "invalid api key" in lower_msg:
        _log_ops(f"provedor recusou a chave (HTTP {status_code}): verifique OPENROUTER_API_KEY")
        return AI_UNAVAILABLE_MESSAGE
    if status_code == 402 or "credit" in lower_msg or "quota" in lower_msg or "balance" in lower_msg:
        _log_ops(f"provedor sem créditos ou cota (HTTP {status_code}): recarregue a conta de IA")
        return AI_UNAVAILABLE_MESSAGE
    if status_code == 429 or "rate limit" in lower_msg:
        return "Muitas requisições enviadas à inteligência artificial. Por favor, aguarde alguns segundos e tente novamente."
    if status_code >= 500:
        return "O provedor de inteligência artificial está temporariamente instável. Tente novamente em instantes."

    return "Não foi possível comunicar com o serviço de inteligência artificial. Tente novamente mais tarde."


def _log_ai(msg: str) -> None:
    if not DEBUG:
        return
    try:
        print(msg)
    except UnicodeEncodeError:
        safe_msg = msg.encode("ascii", errors="replace").decode("ascii")
        print(safe_msg)


def _check_daily_ai_budget() -> None:
    """Teto global de chamadas à IA por 24 h (AI_DAILY_CALL_LIMIT; 0 desliga).

    Trava de emergência contra uma conta de IA estourada: vale para todos os
    usuários juntos e é contado no PostgreSQL, então serve entre instâncias.
    """
    if AI_DAILY_CALL_LIMIT <= 0:
        return
    allowed, _retry = rate_limit_repo.check_and_record(
        "ai_global:calls", AI_DAILY_CALL_LIMIT, 24 * 60 * 60, cost=1
    )
    if not allowed:
        _log_ops(f"teto diário global de {AI_DAILY_CALL_LIMIT} chamadas de IA atingido")
        raise AIServiceError(AI_DAILY_LIMIT_MESSAGE)


# ─── Modelos gratuitos do OpenRouter ──────────────────────────────────────────
# Só ids terminados em ":free" são usados: assim nenhum pedido gera cobrança.
_FREE_SUFFIX = ":free"
_FREE_MODELS_TTL = 6 * 60 * 60        # catálogo consultado no máximo a cada 6 h
_FREE_MODELS_RETRY = 5 * 60           # se a consulta falhar, tenta de novo em 5 min
_MIN_CONTEXT_TOKENS = 32_000          # documentos chegam a ~40 mil caracteres + resposta
# Modelos gratuitos que não servem para gerar questões (reranqueadores, moderação, código...)
_UNSUITABLE_MODEL_HINTS = ("rerank", "safety", "guard", "embed", "moderation", "coder", "-code")
# Pausa de um modelo depois de falhar, para os próximos pedidos irem direto a outro
_COOLDOWN_RATE_LIMIT = 60
_COOLDOWN_UNAVAILABLE = 15 * 60
# Folga no max_tokens de modelos que não deixam desligar o raciocínio (esforço "low" ≈ 20%)
_REASONING_TOKEN_HEADROOM = 1.5

_free_models_lock = Lock()
_free_models_cache: dict = {"fetched_at": 0.0, "models": {}}
_model_cooldown: dict[str, float] = {}
_reasoning_required: set[str] = set()  # modelos que recusaram reasoning effort "none"


def _discover_free_models() -> dict[str, set]:
    """Modelos ":free" que o OpenRouter oferece agora -> parâmetros suportados.

    Usa a lista pública de modelos (não gasta cota). Em caso de falha devolve o
    último resultado conhecido, ou {} para cair só na lista configurada.
    """
    if not OPENROUTER_DISCOVER_FREE_MODELS:
        return {}
    now = time.time()
    with _free_models_lock:
        if now - _free_models_cache["fetched_at"] < _FREE_MODELS_TTL:
            cached_models: dict[str, set] = _free_models_cache["models"]
            return cached_models

    try:
        resp = _get_http_session().get(f"{OPENROUTER_BASE_URL.rstrip('/')}/models", timeout=8)
        resp.raise_for_status()
        catalog = resp.json().get("data") or []
    except Exception as e:  # noqa: BLE001 - qualquer falha cai na lista configurada
        _log_ops(f"não foi possível consultar os modelos gratuitos do OpenRouter ({e})")
        with _free_models_lock:
            _free_models_cache["fetched_at"] = now - _FREE_MODELS_TTL + _FREE_MODELS_RETRY
            fallback_models: dict[str, set] = _free_models_cache["models"]
            return fallback_models

    found: dict[str, set] = {}
    for model in catalog:
        model_id = str(model.get("id") or "")
        if not model_id.endswith(_FREE_SUFFIX):
            continue
        if any(hint in model_id.lower() for hint in _UNSUITABLE_MODEL_HINTS):
            continue
        if int(model.get("context_length") or 0) < _MIN_CONTEXT_TOKENS:
            continue
        outputs = (model.get("architecture") or {}).get("output_modalities") or ["text"]
        if "text" not in outputs:
            continue
        found[model_id] = set(model.get("supported_parameters") or [])

    with _free_models_lock:
        _free_models_cache["fetched_at"] = now
        if found:
            _free_models_cache["models"] = found
        updated_models: dict[str, set] = _free_models_cache["models"]
        return updated_models


def _free_model_candidates() -> list[tuple[str, set | None]]:
    """Ordem de tentativa: preferidos que ainda existem, depois os outros gratuitos.

    Modelos em pausa (falharam há pouco) vão para o fim. Cada item traz os
    parâmetros suportados, ou None quando a descoberta não está disponível.
    """
    discovered = _discover_free_models()
    preferred = [m for m in OPENROUTER_FREE_MODELS if m.endswith(_FREE_SUFFIX)]
    if discovered:
        ordered = [m for m in preferred if m in discovered]
        ordered += [m for m in discovered if m not in ordered]
    else:
        ordered = preferred

    now = time.time()
    ready = [m for m in ordered if _model_cooldown.get(m, 0) <= now]
    paused = [m for m in ordered if m not in ready]
    return [(m, discovered.get(m) if discovered else None) for m in (ready + paused)[:OPENROUTER_MAX_ATTEMPTS]]


def _pause_model(model: str, seconds: int) -> None:
    _model_cooldown[model] = time.time() + seconds


def _log_latency(model: str, outcome: str, started: float, provider: str = "openrouter") -> None:
    """Uma linha por tentativa no log do servidor: mostra qual modelo está lento ou parado."""
    _log_ops(f"{provider} {model}: {outcome} ({time.monotonic() - started:.1f} s)")


def _close_quietly(resp) -> None:
    try:
        resp.close()
    except Exception:  # noqa: BLE001
        pass


def parse_json_response(content: str):
    """Lê o JSON da resposta da IA, tolerando o que modelos gratuitos costumam acrescentar:
    blocos <think>, cercas ```json e texto antes ou depois do objeto."""
    text = re.sub(r"<think>.*?</think>", "", content or "", flags=re.S).strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.S)
    if fenced:
        text = fenced.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        starts = [i for i in (text.find("{"), text.find("[")) if i != -1]
        end = max(text.rfind("}"), text.rfind("]"))
        if not starts or end <= min(starts):
            raise
        return json.loads(text[min(starts):end + 1])


class _StreamError(Exception):
    """O provedor abriu a resposta (200) e mandou um erro no meio dela."""


def _read_chat_response(resp, attempt_timeout: float, deadline: float) -> dict:
    """Lê a resposta de /chat/completions no formato sem streaming ({"choices": ..., "usage": ...}).

    Com streaming (text/event-stream) junta os trechos e levanta _AttemptTimeout se o modelo
    ainda não mandou nada depois de `attempt_timeout` s ou se o tempo total acabou. O OpenRouter
    manda comentários ": OPENROUTER PROCESSING" enquanto o pedido está na fila: eles mantêm a
    conexão viva mas não contam como resposta. Sem streaming (provedor que ignora o pedido, ou
    respostas simuladas nos testes), usa resp.json().
    """
    try:
        content_type = str(resp.headers.get("Content-Type") or "")
    except Exception:  # noqa: BLE001
        content_type = ""
    if "text/event-stream" not in content_type:
        data = resp.json()
        return data if isinstance(data, dict) else {}

    try:
        return _read_event_stream(resp, attempt_timeout, deadline)
    finally:
        _close_quietly(resp)  # devolve a conexão mesmo se o [DONE] chegou antes do fim do corpo


def _read_event_stream(resp, attempt_timeout: float, deadline: float) -> dict:
    started = time.monotonic()
    parts: list[str] = []
    usage: dict = {}
    alive = False  # o modelo já mandou algum trecho (texto ou raciocínio)
    for line in resp.iter_lines(chunk_size=1024):
        now = time.monotonic()
        if now > deadline or (not alive and now - started > attempt_timeout):
            raise _AttemptTimeout()
        if not line or line.startswith(b":") or not line.startswith(b"data:"):
            continue
        data = line[5:].strip()
        if data == b"[DONE]":
            break
        try:
            chunk = json.loads(data)
        except ValueError:
            continue
        if chunk.get("error"):
            err = chunk["error"]
            raise _StreamError(str(err.get("message") if isinstance(err, dict) else err))
        if chunk.get("usage"):
            usage = chunk["usage"]
        for choice in chunk.get("choices") or []:
            delta = choice.get("delta") or {}
            piece = delta.get("content")
            if piece:
                parts.append(piece)
                alive = True
            elif delta.get("reasoning") or delta.get("reasoning_content"):
                alive = True
            if choice.get("finish_reason") == "error":
                raise _StreamError("finish_reason=error")
    return {"choices": [{"message": {"content": "".join(parts)}}], "usage": usage}


def _extract_responses_text(data: dict) -> str:
    """Extrai o texto final de um payload JSON da OpenAI Responses API (/v1/responses)."""
    direct = data.get("output_text")
    if isinstance(direct, str) and direct:
        return direct
    parts: list[str] = []
    for item in data.get("output") or []:
        if not isinstance(item, dict):
            continue
        for block in item.get("content") or []:
            if isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str) and text:
                    parts.append(text)
    return "".join(parts)


def _read_responses_response(resp, attempt_timeout: float, deadline: float) -> tuple[str, dict]:
    """Lê a resposta de /v1/responses (streaming SSE ou JSON direto) devolvendo (texto, usage)."""
    try:
        content_type = str(resp.headers.get("Content-Type") or "")
    except Exception:  # noqa: BLE001
        content_type = ""
    if "text/event-stream" not in content_type:
        data = resp.json()
        return _extract_responses_text(data), (data.get("usage") or {})

    try:
        return _read_responses_event_stream(resp, attempt_timeout, deadline)
    finally:
        _close_quietly(resp)


def _read_responses_event_stream(resp, attempt_timeout: float, deadline: float) -> tuple[str, dict]:
    started = time.monotonic()
    parts: list[str] = []
    usage: dict = {}
    alive = False
    for line in resp.iter_lines(chunk_size=1024):
        now = time.monotonic()
        if now > deadline or (not alive and now - started > attempt_timeout):
            raise _AttemptTimeout()
        if not line or line.startswith(b":") or not line.startswith(b"data:"):
            continue
        raw = line[5:].strip()
        if raw == b"[DONE]":
            break
        try:
            event = json.loads(raw)
        except ValueError:
            continue
        ev_type = str(event.get("type") or "")
        if ev_type in ("error", "response.failed"):
            err = event.get("error") or (event.get("response") or {}).get("error") or ev_type
            raise _StreamError(str(err.get("message") if isinstance(err, dict) else err))
        if ev_type == "response.output_text.delta":
            piece = event.get("delta")
            if isinstance(piece, str) and piece:
                parts.append(piece)
                alive = True
        elif ev_type in ("response.reasoning_text.delta", "response.reasoning_summary_text.delta"):
            alive = True
        elif ev_type == "response.output_text.done" and not parts:
            text = event.get("text")
            if isinstance(text, str) and text:
                parts.append(text)
                alive = True
        elif ev_type == "response.completed":
            completed = event.get("response") or {}
            if completed.get("usage"):
                usage = completed["usage"]
            if not parts:
                fallback_text = _extract_responses_text(completed)
                if fallback_text:
                    parts.append(fallback_text)
            break
    return "".join(parts), usage


def _call_openrouter(
    messages: list[dict],
    temperature: float,
    max_tokens: int,
    timeout: int = 75,
    count_budget: bool = True,
) -> tuple[str, str, dict]:
    """
    Chama o OpenRouter usando só modelos gratuitos, tentando o próximo quando um
    falha (limite por minuto, fora do ar, resposta vazia ou sem JSON válido).
    `timeout` é o tempo total do pedido, somando todas as tentativas.
    Retorna (content, used_model, usage).
    """
    if not OPENROUTER_API_KEY:
        _log_ops(_NO_KEY_LOG)
        raise AIServiceError(AI_UNAVAILABLE_MESSAGE)

    candidates = _free_model_candidates()
    if not candidates:
        _log_ops("nenhum modelo gratuito configurado ou disponível (veja OPENROUTER_FREE_MODELS)")
        raise AIServiceError(AI_UNAVAILABLE_MESSAGE)

    if count_budget:  # _call_ai já contou o pedido no teto global
        _check_daily_ai_budget()

    session = _get_http_session()
    url = f"{OPENROUTER_BASE_URL.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://acely.com.br",
        "X-Title": "Acely",
    }

    deadline = time.monotonic() + timeout
    last_status = 0
    last_raw = ""

    queue = list(candidates)
    while queue:
        model, params = queue.pop(0)
        remaining = deadline - time.monotonic()
        if remaining < 5:
            break
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            # Em partes: um modelo parado na fila é abandonado em AI_ATTEMPT_TIMEOUT s sem
            # cortar o que já está escrevendo (ver _read_chat_response)
            "stream": True,
        }
        # Só pede JSON estruturado a quem declara suporte; sem a lista, confia no prompt
        if params and ("response_format" in params or "structured_outputs" in params):
            payload["response_format"] = {"type": "json_object"}
        # Os modelos gratuitos atuais raciocinam antes de responder, e o raciocínio gasta o
        # mesmo max_tokens da resposta: com ele ligado, o JSON sai vazio ou cortado. Desliga o
        # raciocínio; quem não permite desligar recebe esforço baixo e folga no limite.
        if params is None or "reasoning" in params:
            if model in _reasoning_required:
                payload["reasoning"] = {"effort": "low", "exclude": True}
                payload["max_tokens"] = int(max_tokens * _REASONING_TOKEN_HEADROOM)
            else:
                payload["reasoning"] = {"effort": "none", "exclude": True}

        attempt_timeout = min(float(AI_ATTEMPT_TIMEOUT), remaining)
        attempt_started = time.monotonic()
        try:
            _log_ai(f"[IA] OpenRouter: tentando '{model}'...")
            # (conexão, leitura): a leitura vale para cada trecho, não para a resposta inteira
            resp = session.post(
                url, json=payload, headers=headers, timeout=(5, attempt_timeout), stream=True
            )
        except requests.exceptions.RequestException as e:
            _log_latency(model, "conexão falhou", attempt_started)
            _log_ai(f"[IA AVISO] Falha de conexão com '{model}': {e}")
            _pause_model(model, _COOLDOWN_RATE_LIMIT)
            last_status, last_raw = 0, ""
            continue

        if resp.ok:
            try:
                data = _read_chat_response(resp, attempt_timeout, deadline)
                content = data["choices"][0]["message"].get("content") or ""
                parse_json_response(content)
            except (_AttemptTimeout, requests.exceptions.RequestException) as e:
                # Parado na fila ou conexão caiu no meio: abandona e passa ao próximo
                _close_quietly(resp)
                _log_latency(model, "sem resposta", attempt_started)
                _log_ai(f"[IA AVISO] '{model}' abandonado sem resposta ({type(e).__name__})")
                _pause_model(model, _COOLDOWN_RATE_LIMIT)
                last_status, last_raw = 0, ""
                continue
            except _StreamError as e:
                _close_quietly(resp)
                _log_latency(model, "erro no meio da resposta", attempt_started)
                _log_ai(f"[IA AVISO] '{model}' mandou erro no meio da resposta ({e})")
                _pause_model(model, _COOLDOWN_RATE_LIMIT)
                last_status, last_raw = 0, ""
                continue
            except (ValueError, KeyError, IndexError, TypeError) as e:
                # Modelo respondeu, mas vazio, cortado ou fora do formato: tenta o próximo
                _log_latency(model, "fora do formato", attempt_started)
                _log_ai(f"[IA AVISO] '{model}' respondeu fora do formato JSON ({e})")
                last_status, last_raw = resp.status_code, "fora do formato"
                continue
            usage = data.get("usage") or {}
            _log_latency(model, "ok", attempt_started)
            _log_ai(f"[IA] Sucesso com '{model}' | Tokens: {usage}")
            return content, model, usage

        raw = resp.text
        last_status, last_raw = resp.status_code, raw
        _reason = _provider_error_summary(resp.text or "")
        _log_latency(model, f"HTTP {resp.status_code}" + (f": {_reason}" if _reason else ""), attempt_started)
        lower_raw = raw.lower()
        if resp.status_code == 400 and "reasoning" in lower_raw and model not in _reasoning_required:
            # Modelo não aceita desligar o raciocínio: repete o mesmo modelo com esforço baixo
            _reasoning_required.add(model)
            queue.insert(0, (model, params))
            continue
        if resp.status_code == 429 and ("per-day" in lower_raw or "per day" in lower_raw):
            # Limite diário da conta: os outros modelos gratuitos também recusariam
            _log_ops("limite diário de modelos gratuitos do OpenRouter atingido")
            raise AIServiceError(AI_DAILY_LIMIT_MESSAGE)
        if resp.status_code in (401, 402, 403) or "data policy" in lower_raw or "zdr" in lower_raw:
            # Problema da conta (chave, créditos, privacidade): trocar de modelo não resolve
            raise AIServiceError(_format_user_friendly_error(resp.status_code, raw))

        _log_ai(f"[IA AVISO] '{model}' retornou {resp.status_code}; tentando o próximo")
        _pause_model(model, _COOLDOWN_RATE_LIMIT if resp.status_code == 429 else _COOLDOWN_UNAVAILABLE)

    if last_status in (429, 0) or last_status >= 500 or not last_raw:
        raise AIServiceError(AI_BUSY_MESSAGE)
    raise AIServiceError(_format_user_friendly_error(last_status, last_raw))


# ─── Vários provedores em sequência (docs/ARQUITETURA.md, seção da IA) ─────────
_DAY_SECONDS = 24 * 60 * 60
_COOLDOWN_PROVIDER_ACCOUNT = 15 * 60   # chave recusada ou conta sem crédito
_DAILY_LIMIT_HINTS = ("per day", "per-day", "perday", "per_day", "tokens per day", "requests per day",
                      "(tpd)", "(rpd)", "daily")


@dataclass(frozen=True)
class Provider:
    name: str
    label: str
    base_url: str
    api_key: str
    models: tuple
    daily_requests: int = 0       # orçamento por modelo a cada 24 h (0 = sem controle)
    daily_tokens: int = 0
    max_tokens_field: str = "max_tokens"
    json_mode: bool = True
    api_mode: str = "chat"        # "chat", "responses" ou "auto"


class _ProviderSkip(Exception):
    """O provedor não conseguiu responder agora: passa ao próximo."""
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


# Provedor pausado: nome -> (até quando, mensagem para a pessoa se todos estiverem pausados)
_provider_pause: dict[str, tuple[float, str]] = {}
# Modelos que recusaram parâmetros opcionais ou exigem outro endpoint: tentados de novo ajustados
_no_reasoning_param: set[str] = set()
_no_json_mode: set[str] = set()
_no_temperature_param: set[str] = set()
_force_responses_api: set[str] = set()
_force_chat_api: set[str] = set()
# Modelos que a conta não pode receber em partes (OpenAI exige organização verificada para
# streaming de gpt-5/gpt-6): pedidos seguintes vão sem streaming
_no_stream: set[str] = set()
# Modelos que recusaram raciocínio "none" (ex.: gpt-5-nano só aceita "minimal"): vão com "low"
_reasoning_none_refused: set[str] = set()
# Modelos que recusaram o service_tier da OpenAI (Fast mode): vão sem ele
_no_service_tier: set[str] = set()
# Modelo que não existe ou que a conta não pode usar: fica de fora por mais tempo
_COOLDOWN_MODEL_MISSING = 6 * 60 * 60

_KEY_ENV_NAMES = {
    "codex": "OPENAI_API_KEY",
    "groq": "GROQ_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "cerebras": "CEREBRAS_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}
_MODELS_ENV_NAMES = {
    "codex": "OPENAI_MODELS",
    "groq": "GROQ_MODELS",
    "gemini": "GEMINI_MODELS",
    "cerebras": "CEREBRAS_MODELS",
    "openrouter": "OPENROUTER_FREE_MODELS",
}

# Datas em que a OpenAI desliga modelos (https://developers.openai.com/api/docs/deprecations,
# conferido em 24/11/2026). Modelo vencido é pulado sem gastar pedido; o que vence em até 60 dias
# aparece como aviso no log e no diagnóstico. Atualize ao trocar OPENAI_MODELS.
OPENAI_MODEL_SHUTDOWNS: dict[str, str] = {
    "codex-mini-latest": "2026-02-12",
    "gpt-5-chat-latest": "2026-07-23",
    "gpt-5-codex": "2026-07-23",
    "gpt-5.1-chat-latest": "2026-07-23",
    "gpt-5.1-codex": "2026-07-23",
    "gpt-5.1-codex-max": "2026-07-23",
    "gpt-5.1-codex-mini": "2026-07-23",
    "gpt-5.2-codex": "2026-07-23",
    "gpt-5": "2026-12-11",
    "gpt-5-mini": "2026-12-11",
    "gpt-5-nano": "2026-12-11",
    "gpt-4o-mini": "2027-01-14",
    "gpt-5.1": "2027-04-01",
    "gpt-5.4-nano": "2027-04-01",
}
_SHUTDOWN_WARNING_DAYS = 60
_retired_logged: set[str] = set()


def _provider_log_name(provider: "Provider") -> str:
    """Nome do provedor nos logs: a OpenAI aparece como "openai" (o nome interno é "codex")."""
    return "openai" if provider.name == "codex" else provider.name


def _key_env_name(provider: "Provider") -> str:
    return _KEY_ENV_NAMES.get(provider.name, f"{provider.name.upper()}_API_KEY")


def _models_env_name(provider: "Provider") -> str:
    return _MODELS_ENV_NAMES.get(provider.name, f"{provider.name.upper()}_MODELS")


def _is_reasoning_model(model: str) -> bool:
    """Modelos que raciocinam antes de responder (gpt-5, gpt-6, o1/o3/o4, gpt-oss, codex)."""
    base = (model or "").lower().rsplit("/", 1)[-1]
    return base.startswith(("gpt-5", "gpt-6", "o1", "o3", "o4")) or "gpt-oss" in base or "codex" in base


def _openai_shutdown_date(model: str):
    """Data de desligamento conhecida do modelo da OpenAI (aceita snapshots com data no fim)."""
    base = (model or "").lower().rsplit("/", 1)[-1]
    raw = OPENAI_MODEL_SHUTDOWNS.get(base) or OPENAI_MODEL_SHUTDOWNS.get(re.sub(r"-\d{4}-\d{2}-\d{2}$", "", base))
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None


def _model_retired(provider: "Provider", model: str) -> bool:
    """Modelo da OpenAI que já saiu do ar: pulado sem fazer o pedido (avisa uma vez no log)."""
    if provider.name != "codex":
        return False
    shutdown = _openai_shutdown_date(model)
    if not shutdown or shutdown > datetime.now(timezone.utc).date():
        return False
    if model not in _retired_logged:
        _retired_logged.add(model)
        _log_ops(
            f"openai {model}: modelo desligado pela OpenAI em {shutdown:%d/%m/%Y}; pulando "
            f"(tire de {_models_env_name(provider)})"
        )
    return True


_SECRET_PATTERN = re.compile(r"(sk-[A-Za-z0-9_\-*]{3,}|gsk_[A-Za-z0-9_\-*]{3,}|AIza[A-Za-z0-9_\-]{10,})")


def _provider_error_summary(raw: str, limit: int = 180) -> str:
    """Motivo curto do erro do provedor para o log (código + mensagem), sem chaves."""
    text = raw.strip() if isinstance(raw, str) else ""
    if not text:
        return ""
    summary = ""
    try:
        data = json.loads(text)
        if isinstance(data, list) and data:
            data = data[0]
        err = data.get("error") if isinstance(data, dict) else None
        if isinstance(err, dict):
            code = err.get("code") or err.get("type") or err.get("status") or ""
            message = str(err.get("message") or "")
            summary = f"{code}: {message}" if code and str(code) not in message else message
        elif isinstance(err, str):
            summary = err
        elif isinstance(data, dict) and data.get("message"):
            summary = str(data["message"])
    except (ValueError, AttributeError, TypeError):
        summary = ""
    if not summary:
        summary = re.sub(r"<[^>]+>", " ", text)
    summary = _SECRET_PATTERN.sub("[chave]", " ".join(summary.split()))
    return summary[:limit] + ("…" if len(summary) > limit else "")


def _is_stream_refused(lower: str) -> bool:
    """O provedor recusou o streaming deste modelo para a conta (OpenAI sem verificação)."""
    return (
        "verified to stream" in lower
        or bool(re.search(r'"param"\s*:\s*"stream"', lower))
        or ("stream" in lower and "not supported" in lower)
    )


def _is_out_of_credits(status: int, lower: str) -> bool:
    """Conta sem créditos ou sem faturamento (OpenAI: 429 insufficient_quota; outros: 402)."""
    return status == 402 or "insufficient_quota" in lower


def _is_model_unavailable(status: int, lower: str) -> bool:
    """Modelo inexistente, desligado ou sem acesso para esta conta."""
    if status not in (400, 403, 404):
        return False
    if "model_not_found" in lower:
        return True
    if "model" not in lower:
        return False
    if status == 400:
        # 400 também vem de parâmetro recusado ("... not supported with this model"): só conta
        # quando o provedor diz que o modelo não existe
        return "does not exist" in lower
    hints = ("does not exist", "not found", "do not have access", "does not have access",
             "no longer available", "has been shut down", "has been deprecated")
    return any(h in lower for h in hints)


def _uses_responses_api(provider: Provider, model: str, key: str) -> bool:
    """Define se o modelo deve chamar /v1/responses ou /v1/chat/completions."""
    if provider.api_mode == "responses" or key in _force_responses_api:
        return True
    if provider.api_mode == "chat" or key in _force_chat_api:
        return False
    return "codex" in model.lower()


def _provider_table() -> dict[str, Provider]:
    """Todos os provedores conhecidos, com ou sem chave (lidos na hora: os testes trocam as chaves)."""
    return {
        "codex": Provider("codex", "OpenAI", CODEX_BASE_URL, CODEX_API_KEY, tuple(CODEX_MODELS),
                          CODEX_DAILY_REQUESTS, CODEX_DAILY_TOKENS,
                          max_tokens_field="max_completion_tokens", api_mode=CODEX_API_MODE),
        # Groq não aceita o modo JSON junto com a resposta em partes: vale o prompt + leitura tolerante
        "groq": Provider("groq", "Groq", GROQ_BASE_URL, GROQ_API_KEY, tuple(GROQ_MODELS),
                         GROQ_DAILY_REQUESTS, GROQ_DAILY_TOKENS, json_mode=False),
        "gemini": Provider("gemini", "Gemini", GEMINI_BASE_URL, GEMINI_API_KEY, tuple(GEMINI_MODELS),
                           GEMINI_DAILY_REQUESTS, GEMINI_DAILY_TOKENS),
        "cerebras": Provider("cerebras", "Cerebras", CEREBRAS_BASE_URL, CEREBRAS_API_KEY,
                             tuple(CEREBRAS_MODELS), CEREBRAS_DAILY_REQUESTS, CEREBRAS_DAILY_TOKENS,
                             max_tokens_field="max_completion_tokens"),
        "openrouter": Provider("openrouter", "OpenRouter", OPENROUTER_BASE_URL, OPENROUTER_API_KEY,
                               tuple(OPENROUTER_FREE_MODELS)),
    }


def _configured_providers() -> list[Provider]:
    """Provedores com chave, na ordem de AI_PROVIDERS (lidos na hora: os testes trocam as chaves)."""
    table = _provider_table()
    found = []
    for name in AI_PROVIDERS:
        provider = table.get(name)
        if provider and provider.api_key and (provider.models or name == "openrouter"):
            found.append(provider)
    return found


def ai_configured() -> bool:
    """Há pelo menos um provedor de IA com chave."""
    return bool(_configured_providers())


# ─── Diagnóstico (log de partida e painel do admin) ──────────────────────────
_setup_logged = False


def _display_name(name: str) -> str:
    return "openai" if name == "codex" else name


def ai_setup_warnings() -> list[str]:
    """Problemas de configuração que fazem um provedor nunca ser usado ou gastar à toa."""
    warnings: list[str] = []
    table = _provider_table()
    order = ", ".join(_display_name(n) for n in AI_PROVIDERS)
    for name, provider in table.items():
        if provider.api_key and name not in AI_PROVIDERS:
            warnings.append(
                f"{_key_env_name(provider)} está definida, mas '{_display_name(name)}' não está em "
                f"AI_PROVIDERS ({order}): esse provedor nunca é chamado"
            )
    if AI_PROVIDERS_IGNORED:
        warnings.append(
            "AI_PROVIDERS tem nomes desconhecidos, ignorados: " + ", ".join(AI_PROVIDERS_IGNORED)
            + " (use openai, groq, gemini, cerebras ou openrouter)"
        )
    codex = table["codex"]
    if codex.api_key:
        if CODEX_MODELS_SOURCE == "CODEX_MODELS":
            warnings.append("os modelos da OpenAI vêm de CODEX_MODELS (nome antigo): prefira OPENAI_MODELS")
        today = datetime.now(timezone.utc).date()
        active = 0
        for model in codex.models:
            shutdown = _openai_shutdown_date(model)
            if shutdown and shutdown <= today:
                warnings.append(f"openai {model}: desligado pela OpenAI em {shutdown:%d/%m/%Y}; tire de OPENAI_MODELS")
                continue
            active += 1
            if shutdown and (shutdown - today).days <= _SHUTDOWN_WARNING_DAYS:
                warnings.append(f"openai {model}: sai do ar em {shutdown:%d/%m/%Y}; troque em OPENAI_MODELS antes")
        if not active:
            warnings.append("nenhum modelo de OPENAI_MODELS está ativo: a OpenAI nunca responde")
    # Chamadas por simulado (média): com a OpenAI na frente, partes de 3 e conferência por parte
    # (~8; um de 30 questões com conferência usa 20); nos gratuitos, partes de 5 (~3)
    calls_per_quiz = 8 if _topic_speed_profile()[0] <= FAST_TOPIC_CHUNK_SIZE else 3
    if 0 < AI_DAILY_CALL_LIMIT and AI_DAILY_CALL_LIMIT // calls_per_quiz < 100:
        warnings.append(
            f"AI_DAILY_CALL_LIMIT={AI_DAILY_CALL_LIMIT}: cada simulado usa em média {calls_per_quiz} chamadas "
            f"(até 20 num de 30 questões), então a IA do site inteiro para depois de uns "
            f"{max(1, AI_DAILY_CALL_LIMIT // calls_per_quiz)} simulados por dia"
        )
    return warnings


def _log_setup_once() -> None:
    """Na primeira chamada de cada instância: ordem dos provedores e avisos de configuração."""
    global _setup_logged
    if _setup_logged:
        return
    _setup_logged = True
    try:
        providers = _configured_providers()
        order = " → ".join(
            f"{_provider_log_name(p)} ({', '.join(p.models) if p.models else 'modelos gratuitos'})"
            for p in providers
        ) or "nenhum"
        table = _provider_table()
        missing = [_display_name(n) for n in AI_PROVIDERS if n in table and not table[n].api_key]
        _log_ops(f"ordem dos provedores: {order}" + (f"; sem chave: {', '.join(missing)}" if missing else ""))
        for warning in ai_setup_warnings():
            _log_ops(f"aviso de configuração: {warning}")
    except Exception as e:  # o log nunca derruba um pedido
        _log_ai(f"[IA] falha ao montar o log de partida: {e}")


def _budget_usage(key: str) -> int | None:
    try:
        return int(rate_limit_repo.get_usage(key, _DAY_SECONDS))
    except Exception:
        return None


def _generation_time() -> dict | None:
    try:
        return ai_job_repo.generation_stats(24)
    except Exception as e:
        _log_ai(f"[IA] tempo das gerações indisponível: {e}")
        return None


def ai_diagnostics() -> dict:
    """Situação da IA para o admin: ordem, chaves (só se existem), modelos, pausas, uso e avisos.

    Pausas e eventos são desta instância do servidor; o uso do dia vem do banco.
    """
    now = time.time()
    today = datetime.now(timezone.utc).date()
    table = _provider_table()
    configured = {p.name for p in _configured_providers()}
    providers = []
    for name in list(AI_PROVIDERS) + [n for n in table if n not in AI_PROVIDERS]:
        provider = table.get(name)
        if not provider:
            continue
        pause_until = _provider_pause.get(name, (0, ""))[0]
        models = []
        for model in provider.models:
            key = f"{name}:{model}"
            shutdown = _openai_shutdown_date(model) if name == "codex" else None
            cooldown = _model_cooldown.get(key, 0)
            if shutdown and shutdown <= today:
                state = "desligado"
            elif cooldown > now:
                state = "pausado"
            else:
                state = "ativo"
            info: dict[str, Any] = {
                "id": model,
                "state": state,
                "paused_seconds": max(0, int(cooldown - now)),
                "shutdown": shutdown.isoformat() if shutdown else None,
                "streaming": key not in _no_stream,
            }
            if name != "openrouter" and name in configured:
                req_key, tok_key = _budget_keys(provider, model)
                info["requests_today"] = _budget_usage(req_key) if provider.daily_requests else None
                info["requests_limit"] = provider.daily_requests or None
                info["tokens_today"] = _budget_usage(tok_key) if provider.daily_tokens else None
                info["tokens_limit"] = provider.daily_tokens or None
            models.append(info)
        providers.append({
            "name": _display_name(name),
            "label": provider.label,
            "position": AI_PROVIDERS.index(name) + 1 if name in AI_PROVIDERS else None,
            "has_key": bool(provider.api_key),
            "key_env": _key_env_name(provider),
            "models_env": _models_env_name(provider),
            "active": name in configured,
            "paused_seconds": max(0, int(pause_until - now)),
            "models": models,
        })
    events = [
        {"at": datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="seconds"), "message": msg}
        for ts, msg in reversed(list(_ai_events))
    ][:40]
    return {
        "order": [_display_name(n) for n in AI_PROVIDERS],
        "providers": providers,
        "warnings": ai_setup_warnings(),
        "settings": {
            "ai_providers_from_env": AI_PROVIDERS_FROM_ENV,
            "openai_models_source": CODEX_MODELS_SOURCE,
            "openai_api_mode": CODEX_API_MODE,
            "attempt_timeout_seconds": AI_ATTEMPT_TIMEOUT,
            "cross_check": AI_CROSS_CHECK,
            "user_requests_per_minute": AI_USER_REQUESTS_PER_MINUTE,
            "openai_service_tier": OPENAI_SERVICE_TIER or None,
            "part_size_env": AI_PART_SIZE or None,
            "parallel_parts_env": AI_PARALLEL_PARTS or None,
        },
        "daily_calls": {
            "limit": AI_DAILY_CALL_LIMIT or None,
            "used_24h": _budget_usage("ai_global:calls"),
        },
        "generation_time": _generation_time(),
        "speed_profile": dict(zip(("part_size", "parallel_parts"), _topic_speed_profile(), strict=True)),
        "events": events,
    }


_PROBE_MESSAGES = [{"role": "user", "content": 'Responda somente com este JSON, sem mais nada: {"ok": true}'}]


def probe_ai_providers(timeout_per_provider: int = 25) -> list[dict]:
    """Faz um pedido mínimo a cada provedor com chave e conta o que aconteceu (para o admin).

    Os provedores são testados ao mesmo tempo (o total fica perto do mais lento). Ignora a pausa
    do provedor (o objetivo é ver se ele voltou) e não conta no teto diário do site, mas conta no
    orçamento do modelo. Uma falha aqui pausa o provedor como num pedido real.
    """
    providers = _configured_providers()
    if not providers:
        return []
    started_wall = time.time()

    def probe(provider: Provider) -> dict:
        started = time.monotonic()
        entry: dict[str, Any] = {"provider": _provider_log_name(provider), "label": provider.label}
        try:
            if provider.name == "openrouter":
                _content, model, _usage = _unpack_call_result(_call_openrouter(
                    _PROBE_MESSAGES, 0.0, 300, timeout=timeout_per_provider, count_budget=False,
                ))[:3]
            else:
                _content, model, _usage = _call_compatible(
                    provider, _PROBE_MESSAGES, 0.0, 300, time.monotonic() + timeout_per_provider,
                    reasoning="none",
                )
            entry.update(ok=True, model=model)
        except _ProviderSkip as e:
            entry.update(ok=False, message=e.message)
        except AIServiceError as e:
            entry.update(ok=False, message=str(e))
        except Exception as e:
            entry.update(ok=False, message=f"erro inesperado ({type(e).__name__})")
        entry["seconds"] = round(time.monotonic() - started, 1)
        return entry

    with ThreadPoolExecutor(max_workers=len(providers)) as pool:
        results = list(pool.map(probe, providers))
    events = [(ts, msg) for ts, msg in list(_ai_events) if ts >= started_wall]
    for entry in results:
        name = entry["provider"]
        entry["log"] = [msg for _ts, msg in events if msg.lower().startswith(name) or f" {name} " in msg.lower()]
    return results


def _seconds_until_utc_midnight() -> int:
    now = datetime.now(timezone.utc)
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(60, int((tomorrow - now).total_seconds()))


def _pause_provider(name: str, seconds: int, message: str) -> None:
    """Pula o provedor nos próximos pedidos. Com um provedor só não há para onde ir: não pausa."""
    if len(_configured_providers()) > 1:
        _provider_pause[name] = (time.time() + seconds, message)


def _budget_keys(provider: Provider, model: str) -> tuple[str, str]:
    base = f"ai_budget:{provider.name}:{model}"
    return f"{base}:requests", f"{base}:tokens"


def _within_budget(provider: Provider, model: str) -> bool:
    """O modelo ainda cabe no orçamento diário (contado no banco, vale entre instâncias)."""
    req_key, tok_key = _budget_keys(provider, model)
    try:
        if provider.daily_requests and provider.daily_tokens and hasattr(rate_limit_repo, "get_usages"):
            usages = rate_limit_repo.get_usages([req_key, tok_key], _DAY_SECONDS)
            if usages.get(req_key, 0) >= provider.daily_requests:
                return False
            if usages.get(tok_key, 0) >= provider.daily_tokens:
                return False
            return True
        if provider.daily_requests and rate_limit_repo.is_blocked(req_key, provider.daily_requests, _DAY_SECONDS)[0]:
            return False
        if provider.daily_tokens and rate_limit_repo.is_blocked(tok_key, provider.daily_tokens, _DAY_SECONDS)[0]:
            return False
    except Exception:  # noqa: BLE001 - sem contagem, deixa o provedor responder 429 se for o caso
        return True
    return True


def _record_budget(provider: Provider, model: str, tokens: int = 0, request: bool = False) -> None:
    req_key, tok_key = _budget_keys(provider, model)
    try:
        if request and provider.daily_requests:
            rate_limit_repo.record(req_key, 1)
        if tokens and provider.daily_tokens:
            rate_limit_repo.record(tok_key, tokens)
    except Exception:  # noqa: BLE001
        pass


def _is_daily_limit(raw: str) -> bool:
    lower = (raw or "").lower()
    return any(hint in lower for hint in _DAILY_LIMIT_HINTS)


def _call_compatible(
    provider: Provider,
    messages: list[dict],
    temperature: float,
    max_tokens: int,
    deadline: float,
    reasoning: str = "low",
) -> tuple[str, str, dict]:
    """OpenAI, Groq, Gemini e Cerebras: mesmo formato de chat da OpenAI, com resposta em partes.

    Tenta os modelos do provedor em ordem (pausados por último). Levanta _ProviderSkip quando
    nenhum responde, para `_call_ai` passar ao próximo provedor. Cada falha vai para o log do
    servidor com o motivo dado pelo provedor (sem a chave), para o dono saber o que ajustar.

    `reasoning` é o esforço pedido aos modelos que raciocinam: "none" (mais rápido; a geração de
    questões usa) ou "low". gpt-oss não aceita "none" e vai com "low"; um modelo que recusar "none"
    passa a receber "low".
    """
    session = _get_http_session()
    base = provider.base_url.rstrip("/")
    headers = {"Authorization": f"Bearer {provider.api_key}", "Content-Type": "application/json"}
    prompt_chars = sum(len(str(m.get("content") or "")) for m in messages)
    log_name = _provider_log_name(provider)

    now = time.time()
    keys = {model: f"{provider.name}:{model}" for model in provider.models}
    ready = [m for m in provider.models if _model_cooldown.get(keys[m], 0) <= now]
    queue = ready + [m for m in provider.models if m not in ready]
    skip_message = AI_BUSY_MESSAGE

    while queue:
        model = queue.pop(0)
        key = keys[model]
        if _model_retired(provider, model):
            continue
        if not _within_budget(provider, model):
            _log_ops(f"{log_name} {model}: orçamento diário do modelo esgotado; pulando")
            continue
        remaining = deadline - time.monotonic()
        if remaining < 5:
            break

        use_responses = _uses_responses_api(provider, model, key)
        use_stream = key not in _no_stream
        is_reasoning = _is_reasoning_model(model)
        effort = reasoning if reasoning in ("none", "low") else "low"
        if effort == "none" and ("gpt-oss" in model.lower() or key in _reasoning_none_refused):
            effort = "low"
        # Modelos de raciocínio da OpenAI só aceitam a temperatura padrão: nem envia
        send_temperature = key not in _no_temperature_param and not (provider.name == "codex" and is_reasoning)
        send_effort = is_reasoning and key not in _no_reasoning_param
        # O raciocínio gasta o mesmo limite de tokens da resposta: folga quando ele está ligado
        token_cap = int(max_tokens * _REASONING_TOKEN_HEADROOM) if send_effort and effort != "none" else max_tokens
        if use_responses:
            url = f"{base}/responses"
            payload: dict[str, Any] = {
                "model": model,
                "input": messages,
                "max_output_tokens": token_cap,
                "stream": use_stream,
            }
            if send_temperature:
                payload["temperature"] = temperature
            if provider.json_mode and key not in _no_json_mode:
                payload["text"] = {"format": {"type": "json_object"}}
            if send_effort:
                payload["reasoning"] = {"effort": effort}
        else:
            url = f"{base}/chat/completions"
            payload: dict[str, Any] = {
                "model": model,
                "messages": messages,
                provider.max_tokens_field: token_cap,
                "stream": use_stream,
            }
            if send_temperature:
                payload["temperature"] = temperature
            if provider.json_mode and key not in _no_json_mode:
                payload["response_format"] = {"type": "json_object"}
            if send_effort:
                payload["reasoning_effort"] = effort
        if provider.name == "codex" and OPENAI_SERVICE_TIER and key not in _no_service_tier:
            payload["service_tier"] = OPENAI_SERVICE_TIER

        # Em partes, um modelo parado é abandonado em AI_ATTEMPT_TIMEOUT s; sem partes a resposta
        # chega inteira no fim, então a espera vai até o tempo total
        attempt_timeout = min(float(AI_ATTEMPT_TIMEOUT), remaining) if use_stream else remaining
        _record_budget(provider, model, request=True)
        started = time.monotonic()
        try:
            resp = session.post(url, json=payload, headers=headers, timeout=(5, attempt_timeout), stream=use_stream)
        except requests.exceptions.RequestException as e:
            _log_latency(model, f"conexão falhou ({type(e).__name__})", started, log_name)
            _pause_model(key, _COOLDOWN_RATE_LIMIT)
            continue

        if resp.ok:
            try:
                if use_responses:
                    content, usage = _read_responses_response(resp, attempt_timeout, deadline)
                else:
                    data = _read_chat_response(resp, attempt_timeout, deadline)
                    choice0 = data["choices"][0]
                    finish_reason = choice0.get("finish_reason")
                    content = choice0["message"].get("content") or ""
                    usage = data.get("usage") or {}
                parse_json_response(content)
            except (_AttemptTimeout, _StreamError, requests.exceptions.RequestException) as e:
                _close_quietly(resp)
                _log_latency(model, f"sem resposta ({type(e).__name__}); abandonado", started, log_name)
                _pause_model(key, _COOLDOWN_RATE_LIMIT)
                continue
            except (ValueError, KeyError, IndexError, TypeError) as e:
                suffix = " (cortado por max_tokens)" if not use_responses and locals().get("finish_reason") == "length" else ""
                _log_latency(model, f"respondeu fora do formato JSON ({type(e).__name__}){suffix}", started, log_name)
                continue
            _log_latency(model, "ok" if use_stream else "ok (sem streaming)", started, log_name)
            tokens = int(usage.get("total_tokens") or 0) or (prompt_chars + len(content)) // 4
            _record_budget(provider, model, tokens=tokens)
            return content, model, usage

        raw = resp.text or ""
        lower = raw.lower()
        status = resp.status_code
        reason = _provider_error_summary(raw)
        _log_latency(model, f"HTTP {status}" + (f": {reason}" if reason else ""), started, log_name)

        if provider.api_mode == "auto" and status in (400, 404, 405):
            if (
                not use_responses
                and ("v1/responses" in lower or "not a chat model" in lower or "responses api" in lower)
                and key not in _force_responses_api
            ):
                _force_responses_api.add(key)
                queue.insert(0, model)
                continue
            if (
                use_responses
                and (status == 405 or "unknown url" in lower or "not found" in lower)
                and key not in _force_chat_api
            ):
                _force_chat_api.add(key)
                queue.insert(0, model)
                continue
        if status == 400 and use_stream and _is_stream_refused(lower):
            # OpenAI: organização não verificada não pode receber gpt-5/gpt-6 em partes, mas pode
            # receber a resposta inteira. Tenta de novo sem streaming (vale até o fim do processo).
            _log_ops(
                f"{log_name} {model}: a conta não pode usar streaming neste modelo; usando a resposta "
                "inteira (para liberar, verifique a organização em "
                "https://platform.openai.com/settings/organization/general)"
            )
            _no_stream.add(key)
            queue.insert(0, model)
            continue
        if status == 400 and "temperature" in lower and "temperature" in payload:
            _no_temperature_param.add(key)
            queue.insert(0, model)
            continue
        if status == 400 and "service_tier" in lower and "service_tier" in payload:
            _log_ops(f"{log_name} {model}: service_tier={OPENAI_SERVICE_TIER} recusado; pedindo sem ele")
            _no_service_tier.add(key)
            queue.insert(0, model)
            continue
        if status == 400 and "reasoning" in lower and ("reasoning_effort" in payload or "reasoning" in payload):
            if effort == "none":
                # Aceita raciocínio, só não "none": repete com "low" em vez de tirar o parâmetro
                _reasoning_none_refused.add(key)
            else:
                _no_reasoning_param.add(key)
            queue.insert(0, model)
            continue
        if (
            status == 400
            and ("response_format" in lower or "text.format" in lower or "json" in lower)
            and ("response_format" in payload or "text" in payload)
        ):
            _no_json_mode.add(key)
            queue.insert(0, model)
            continue
        if _is_out_of_credits(status, lower):
            # OpenAI responde 429 "insufficient_quota" quando a conta não tem crédito: não adianta
            # tentar outro modelo do mesmo provedor
            _log_ops(
                f"{log_name}: a conta está sem créditos ou sem faturamento ativo; pulando o provedor por "
                f"{_COOLDOWN_PROVIDER_ACCOUNT // 60} min (adicione créditos no painel do provedor)"
            )
            _pause_provider(provider.name, _COOLDOWN_PROVIDER_ACCOUNT, AI_UNAVAILABLE_MESSAGE)
            raise _ProviderSkip(AI_UNAVAILABLE_MESSAGE)
        if status == 429 and _is_daily_limit(raw):
            # Limite diário: os outros modelos deste provedor podem ter cota própria (Groq conta
            # por modelo); este fica parado até a virada do dia
            _log_ops(f"{log_name} {model}: limite diário atingido")
            _pause_model(key, _seconds_until_utc_midnight())
            skip_message = AI_DAILY_LIMIT_MESSAGE
            continue
        if _is_model_unavailable(status, lower):
            # Modelo que não existe ou que a conta não pode usar: os outros modelos ainda podem servir
            _log_ops(
                f"{log_name} {model}: modelo inexistente ou sem acesso nesta conta; pausado por "
                f"{_COOLDOWN_MODEL_MISSING // 3600} h (confira {_models_env_name(provider)})"
            )
            _pause_model(key, _COOLDOWN_MODEL_MISSING)
            continue
        if status in (401, 402, 403):
            _log_ops(
                f"{log_name} recusou o pedido (HTTP {status}): verifique a chave {_key_env_name(provider)}; "
                f"provedor pausado por {_COOLDOWN_PROVIDER_ACCOUNT // 60} min"
            )
            _pause_provider(provider.name, _COOLDOWN_PROVIDER_ACCOUNT, AI_UNAVAILABLE_MESSAGE)
            raise _ProviderSkip(AI_UNAVAILABLE_MESSAGE)
        if status in (400, 413) or "context" in lower:
            # Pedido grande demais para este modelo (ex.: contexto pequeno no plano grátis)
            continue
        _pause_model(key, _COOLDOWN_RATE_LIMIT if status == 429 else _COOLDOWN_UNAVAILABLE)

    if skip_message == AI_DAILY_LIMIT_MESSAGE and all(
        _model_cooldown.get(keys[m], 0) > time.time() + _COOLDOWN_UNAVAILABLE for m in provider.models
    ):
        _pause_provider(provider.name, _seconds_until_utc_midnight(), AI_DAILY_LIMIT_MESSAGE)
    raise _ProviderSkip(skip_message)


def _call_ai(
    messages: list[dict],
    temperature: float,
    max_tokens: int,
    timeout: int = 75,
    prefer_different_from: str | None = None,
    reasoning: str = "low",
) -> tuple[str, str, dict, str]:
    """Pede a resposta ao primeiro provedor que conseguir, na ordem de AI_PROVIDERS.

    `timeout` é o tempo total, somando provedores e modelos. Quando `prefer_different_from`
    é informado (conferência por segundo modelo), provedores diferentes são tentados antes.
    Retorna (content, modelo, usage, nome do provedor).
    """
    _log_setup_once()
    providers = _configured_providers()
    if not providers:
        _log_ops(_NO_KEY_LOG)
        raise AIServiceError(AI_UNAVAILABLE_MESSAGE)

    now = time.time()
    for p in providers:
        until = _provider_pause.get(p.name, (0, ""))[0]
        if until > now:
            _log_ops(f"{_provider_log_name(p)} pausado por mais {int(until - now)} s nesta instância; pulando")
    ready = [p for p in providers if _provider_pause.get(p.name, (0, ""))[0] <= now]
    if not ready:
        # Todos pausados: a mensagem é a do que volta primeiro
        soonest = min(providers, key=lambda p: _provider_pause[p.name][0])
        raise AIServiceError(_provider_pause[soonest.name][1])

    if prefer_different_from and len(ready) > 1:
        excluded = prefer_different_from.strip().lower()
        # Só coloca na frente outro provedor rápido; nunca prioriza o OpenRouter gratuito na frente
        # de provedores rápidos (ex.: OpenAI) durante hedge ou conferência de gabarito.
        fast_others = [
            p for p in ready
            if p.name != "openrouter" and p.name.lower() != excluded and p.label.lower() != excluded
        ]
        same = [p for p in ready if p.name.lower() == excluded or p.label.lower() == excluded]
        slow_others = [p for p in ready if p not in fast_others and p not in same]
        ready = fast_others + same + slow_others

    _check_daily_ai_budget()
    deadline = time.monotonic() + timeout
    last_message = AI_BUSY_MESSAGE
    for provider in ready:
        remaining = deadline - time.monotonic()
        if remaining < 5:
            break
        try:
            if provider.name == "openrouter":
                content, model, usage = _unpack_call_result(_call_openrouter(
                    messages, temperature, max_tokens, timeout=int(remaining), count_budget=False,
                ))[:3]
                return content, model, usage, provider.label
            content, model, usage = _call_compatible(
                provider, messages, temperature, max_tokens, deadline, reasoning=reasoning
            )
            return content, model, usage, provider.label
        except _ProviderSkip as e:
            last_message = e.message
        except AIServiceError as e:  # vindo do OpenRouter
            last_message = str(e)
            if last_message == AI_DAILY_LIMIT_MESSAGE:
                _pause_provider(provider.name, _seconds_until_utc_midnight(), last_message)
            elif last_message == AI_UNAVAILABLE_MESSAGE:
                _pause_provider(provider.name, _COOLDOWN_PROVIDER_ACCOUNT, last_message)
        _log_ops(f"{_provider_log_name(provider)} não respondeu; tentando o próximo provedor")
    raise AIServiceError(last_message)


def _unpack_call_result(res) -> tuple[str, str, dict, str]:
    """Aceita 2-tupla (mocks), 3-tupla (OpenRouter) e 4-tupla (_call_ai, com o provedor)."""
    if isinstance(res, tuple) and len(res) == 4:
        return res[0], res[1], res[2], res[3]
    if isinstance(res, tuple) and len(res) == 3:
        return res[0], res[1], res[2], "OpenRouter"
    elif isinstance(res, tuple) and len(res) == 2:
        return res[0], res[1], {}, "OpenRouter"
    return str(res), "mock", {}, "OpenRouter"


_ANSWER_KEY_BATCH_SIZE = 40


def generate_answer_key(questions: list[dict], client_ip: str | None = None) -> list[dict]:
    """
    Gera gabarito para uma lista de questões via OpenRouter API.

    Args:
        questions: Lista de dicts com {id, question, options, ...}
        client_ip: IP do cliente para controle de cota de tokens (opcional).

    Returns:
        Lista de {question_id, answer: int, explanation: str}

    Raises:
        AIServiceError: Se a API não responder ou retornar JSON inválido
        AIQuotaExceededError: Se o IP exceder a cota de tokens por hora
    """
    if len(questions) > _ANSWER_KEY_BATCH_SIZE:
        combined: list[dict] = []
        for start in range(0, len(questions), _ANSWER_KEY_BATCH_SIZE):
            batch = questions[start:start + _ANSWER_KEY_BATCH_SIZE]
            combined.extend(generate_answer_key(batch, client_ip=client_ip))
        return combined

    prompt = _build_prompt(questions)
    check_ai_token_quota(prompt, ip=client_ip)
    max_tokens = min(3500, max(500, len(questions) * 120))
    call_res = _call_ai(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=max_tokens,
        timeout=60,  # tempo total, somando provedores e modelos
    )
    content, used_model, usage, provider_name = _unpack_call_result(call_res)

    if DEBUG:
        print(f"🤖 IA [{used_model}] respondeu:\n{content[:300]}")

    # Parsear a resposta JSON do LLM
    try:
        # O LLM pode retornar o array direto ou dentro de um objeto
        parsed = parse_json_response(content)
        if isinstance(parsed, dict):
            # Tentar extrair array de dentro do objeto
            parsed = next(
                (v for v in parsed.values() if isinstance(v, list)),
                []
            )
        if not isinstance(parsed, list):
            raise ValueError("Esperado array JSON")
    except (json.JSONDecodeError, ValueError) as e:
        _log_ops(f"gabarito: resposta da IA fora do formato JSON ({e})")
        raise AIServiceError("A IA respondeu em um formato inesperado. Tente novamente.")

    # Normalizar e validar cada item
    result = []
    for item in parsed:
        try:
            question_id = int(item["question_id"])
            answer = int(item["answer"])
            question = next((q for q in questions if q["id"] == question_id), None)
            if question is None or answer < 0 or answer >= len(question.get("options", [])):
                continue
            result.append({
                "question_id": question_id,
                "answer": answer,
                "explanation": str(item.get("explanation", "")).strip(),
            })
        except (KeyError, TypeError, ValueError):
            continue  # Ignorar itens malformados

    if not result:
        raise AIServiceError("A IA não retornou nenhum item de gabarito válido")

    return result


def apply_ai_answers(questions: list[dict], ai_answers: list[dict]) -> list[dict]:
    """
    Aplica as respostas geradas pela IA nas questões.

    Args:
        questions: Lista de questões (sem respostas)
        ai_answers: Lista retornada por generate_answer_key()

    Returns:
        Lista de questões com answer e explanation preenchidos
    """
    answers_map = {item["question_id"]: item for item in ai_answers}
    for q in questions:
        ai = answers_map.get(q["id"])
        if ai:
            q["answer"] = ai["answer"]
            q["explanation"] = ai["explanation"]
    return questions


# Idiomas aceitos para o conteúdo gerado pela IA (código enviado pelo cliente -> nome no prompt).
AI_LANGUAGES = {
    "pt-BR": "Português do Brasil (pt-BR)",
    "en": "inglês (English, en)",
}
DEFAULT_AI_LANGUAGE = "pt-BR"


def normalize_language(value) -> str:
    """Converte o idioma pedido pelo cliente num código suportado (padrão pt-BR)."""
    raw = str(value or "").strip()
    if raw in AI_LANGUAGES:
        return raw
    base = raw.split("-")[0].lower()
    if base == "pt":
        return "pt-BR"
    return base if base in AI_LANGUAGES else DEFAULT_AI_LANGUAGE


def _language_rule(language: str, subject: str) -> str:
    return f"O idioma de {subject} DEVE ser {AI_LANGUAGES[normalize_language(language)]}."


TOPIC_CHUNK_SIZE = 5
TOPIC_CHUNK_MAX_WORKERS = 3
# Com a OpenAI na frente (paga, limites altos por minuto): partes menores e todas ao mesmo tempo.
# O tempo do simulado fica perto do tempo de uma parte pequena, qualquer que seja o tamanho.
FAST_TOPIC_CHUNK_SIZE = 3
FAST_TOPIC_MAX_WORKERS = 10
# Só pede as questões que faltaram se ainda sobra tempo (a função da Vercel vai até 300 s)
_TOPUP_TIME_BUDGET_SECONDS = 90
_TOPUP_MAX_ROUNDS = 2


def _topic_part_max_tokens(qty: int, diff: str) -> int:
    """Folga de tokens por parte: questões difíceis têm enunciado e explicação mais longos.

    A API cobra apenas os tokens realmente gerados; dar folga evita cortar o JSON no meio.
    """
    per_question = 650 if diff == "Difícil" else 500
    return min(8192, max(1600, qty * per_question))


def _short_error(exc: Exception) -> str:
    """Motivo curto da falha de uma parte, seguro para mostrar (sem detalhes internos)."""
    if isinstance(exc, (AIServiceError, AIQuotaExceededError)):
        return str(exc)[:120]
    return type(exc).__name__


def _topic_speed_profile() -> tuple[int, int]:
    """(questões por parte, partes ao mesmo tempo) para a geração por tema.

    AI_PART_SIZE e AI_PARALLEL_PARTS mandam quando definidos. No automático, a OpenAI na frente
    (primeiro provedor com chave e sem pausa) usa partes de 3 e até 10 ao mesmo tempo; os
    gratuitos ficam com partes de 5 e até 3 ao mesmo tempo, por causa dos limites por minuto.
    """
    now = time.time()
    ready = [p for p in _configured_providers() if _provider_pause.get(p.name, (0, ""))[0] <= now]
    fast = bool(ready) and ready[0].name == "codex"
    size = AI_PART_SIZE or (FAST_TOPIC_CHUNK_SIZE if fast else TOPIC_CHUNK_SIZE)
    workers = AI_PARALLEL_PARTS or (FAST_TOPIC_MAX_WORKERS if fast else TOPIC_CHUNK_MAX_WORKERS)
    return max(1, size), max(1, workers)


def _plan_question_chunks(qty: int, chunk_size: int = TOPIC_CHUNK_SIZE) -> list[int]:
    """Divide uma quantidade > chunk_size em partes equilibradas de até chunk_size questões."""
    if qty <= chunk_size:
        return [qty]
    chunks: list[int] = []
    remaining = qty
    while remaining > 0:
        size = min(chunk_size, remaining)
        chunks.append(size)
        remaining -= size
    return chunks


def _normalize_question_key(text: str) -> str:
    """Normaliza o enunciado para detectar e remover questões repetidas entre partes."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    ascii_like = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    cleaned = re.sub(r"[^a-z0-9\s]", " ", ascii_like.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def _deduplicate_questions(questions: list[dict], limit: int | None = None) -> list[dict]:
    """Remove enunciados duplicados preservando a ordem e renumera id/question_number de 1..N."""
    seen: set[str] = set()
    unique: list[dict] = []
    for item in questions:
        key = _normalize_question_key(str(item.get("question") or ""))
        if not key or key in seen:
            continue
        seen.add(key)
        idx = len(unique) + 1
        unique.append({**item, "id": idx, "question_number": idx})
        if limit is not None and len(unique) >= limit:
            break
    return unique


def _merge_usage(usages: list[dict | None]) -> dict:
    """Soma as contagens de tokens de várias chamadas de IA."""
    merged: dict[str, int] = {}
    for usage in usages:
        if not isinstance(usage, dict):
            continue
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            val = usage.get(key)
            if isinstance(val, (int, float)):
                merged[key] = merged.get(key, 0) + int(val)
    return merged


# Provas, bancas e certificações: trocar uma pela outra (ENEM no lugar de ENADE) é erro
_EXAM_TOKENS = frozenset({
    "enem", "enade", "encceja", "oab", "fuvest", "unicamp", "vunesp", "unesp", "cespe", "cebraspe", "fgv",
    "fcc", "ibfc", "cesgranrio", "quadrix", "idecan", "consulplan", "aocp", "inep", "sisu", "uerj", "ufrgs",
    "ita", "ime", "afa", "espcex", "efomm", "revalida", "enare", "cfc", "cpa", "pmp", "toefl", "ielts",
    "sat", "gre", "gmat", "poscomp",
})
_YEAR_PATTERN = re.compile(r"(19|20)\d\d")


def _topic_exam_and_years(clean_topic: str) -> tuple[list[str], list[str]]:
    """Provas/bancas e anos citados no tema, na ordem em que aparecem (provas em maiúsculas)."""
    exams: list[str] = []
    years: list[str] = []
    for token in _normalize_question_key(clean_topic).split():
        if token in _EXAM_TOKENS and token.upper() not in exams:
            exams.append(token.upper())
        elif _YEAR_PATTERN.fullmatch(token) and token not in years:
            years.append(token)
    return exams, years


# Cada parte de um simulado recebe um foco diferente: sem isso, partes com o mesmo prompt tendem a
# repetir as mesmas questões (e as repetidas são removidas, deixando o simulado menor que o pedido).
_PART_FOCUSES = (
    "conceitos, definições e princípios centrais do tema",
    "aplicação em situações práticas, casos e exemplos",
    "comparação entre conceitos parecidos e erros comuns",
    "análise de cenários, dados, código, cálculos ou procedimentos, conforme o tema",
    "detalhes, exceções e pontos que costumam cair em prova",
    "interpretação de enunciados mais longos e situações-problema",
    "relações entre subtemas diferentes do tema",
    "fundamentos e pré-requisitos do tema",
    "tópicos avançados ou menos óbvios do tema",
    "revisão geral cobrindo subtemas ainda não abordados",
)


def _build_topic_prompt(
    clean_topic: str,
    qty: int,
    diff: str,
    context_str: str,
    lang: str,
    part_index: int | None = None,
    total_parts: int | None = None,
    avoid_questions: list[str] | None = None,
) -> str:
    # Prefixo estático primeiro (regras fixas e formato JSON) e dados variáveis no final:
    # mantém o prompt enxuto e compatível com Prompt Caching automático por prefixo.
    # Resposta enxuta = geração mais rápida: o tempo da IA cresce com cada token escrito. Explicação
    # de 1 a 2 frases e JSON em uma linha cortam cerca de metade dos tokens do formato anterior
    # (explicação de 2 a 4 frases, campo "context" e JSON indentado).
    prompt_lines = [
        "Você é um professor e elaborador sênior de provas e simulados acadêmicos e de concursos.",
        "",
        "Regras obrigatórias:",
        f"1. {_language_rule(lang, 'todas as questões, alternativas, explicações e do título')}",
        "2. Todas as questões devem ser inéditas, com enunciados claros, sem ambiguidades.",
        "3. Cada questão deve possuir exatamente 4 ou 5 alternativas em formato de texto limpo (não coloque 'a)', 'b)' dentro do texto da alternativa).",
        "4. Apenas UMA alternativa deve ser a correta.",
        "5. O campo 'answer' deve ser o índice numérico (base 0) da alternativa correta (0 = primeira opção, 1 = segunda opção, 2 = terceira opção...).",
        "6. O campo 'explanation' deve justificar a resposta em 1 a 2 frases objetivas, citando o conceito que a torna correta.",
        "7. No campo 'title', um título curto que repita os nomes, siglas e anos do tema exatamente como foram "
        "escritos, sem mencionar partes; em 'section', um subtema curto.",
        "",
        "IMPORTANTE: Retorne SOMENTE um objeto JSON válido, em uma linha só, sem texto, quebras de linha ou espaços extras fora dos textos, no formato:",
        '{"title":"Título do simulado","questions":[{"id":1,"section":"Subtema","question":"Enunciado completo da pergunta?",'
        '"options":["Opção A","Opção B","Opção C","Opção D"],"answer":0,"explanation":"Por que a opção A é a correta."}]}',
        "",
        f"Crie um simulado de múltipla escolha com exatamente {qty} questões sobre o seguinte tema: '{clean_topic}'.",
        f"Nível de dificuldade exigido: {diff}.",
    ]
    exams, years = _topic_exam_and_years(clean_topic)
    if exams or years:
        cited = " ".join(exams + years)
        prompt_lines.append(
            f"O tema cita {cited}: as questões devem seguir exatamente essa prova e esse ano, com o estilo, "
            f"o curso e o conteúdo que ela cobra. Não troque por outra prova nem por outro ano."
        )
    else:
        prompt_lines.append(
            "Se o tema citar uma prova, banca, curso, órgão ou ano, siga exatamente essa prova, esse curso e "
            "esse ano. Não troque por outra prova."
        )
    if part_index is not None and total_parts is not None and total_parts > 1:
        focus = _PART_FOCUSES[(part_index - 1) % len(_PART_FOCUSES)]
        prompt_lines.append(
            f"Esta é a parte {part_index} de {total_parts} de um simulado maior: as outras partes são geradas "
            f"ao mesmo tempo. Nesta parte, priorize {focus}, sempre dentro do tema, para não repetir as outras."
        )
    if avoid_questions:
        prompt_lines.append("Não repita nem reescreva estas questões, que já estão no simulado:")
        prompt_lines.extend(f"- {q[:140]}" for q in avoid_questions[:30])
    if context_str:
        prompt_lines.append(f"Diretrizes e foco específico adicional: {context_str}")

    return "\n".join(prompt_lines)


_PT_STOPWORDS = frozenset({
    "qual", "quais", "sobre", "para", "como", "entre", "pelo", "pela", "pelos", "pelas",
    "isso", "esta", "este", "esse", "essa", "mais", "menos", "pode", "devem", "deve",
    "correta", "incorreta", "alternativa", "questao", "assinale", "indique", "segundo",
    "conforme", "porque", "quando", "onde", "numa", "num", "uma", "uns", "umas", "nao",
})
_EN_STOPWORDS = frozenset({
    "which", "what", "about", "with", "from", "that", "this", "these", "those", "their",
    "there", "where", "when", "does", "should", "would", "could", "following", "correct",
    "incorrect", "statement", "option", "choose", "select", "according", "between", "under",
})


def should_cross_check(has_account: bool) -> bool:
    """Decide se a conferência por segundo modelo deve rodar (AI_CROSS_CHECK=account|all|off)."""
    mode = (AI_CROSS_CHECK or "account").strip().lower()
    if mode == "all":
        return True
    if mode == "account":
        return bool(has_account)
    return False


def _matches_requested_language(text: str, language: str) -> bool:
    """Heurística leve para detectar idioma claramente trocado (pt-BR vs en)."""
    norm = _normalize_question_key(text)
    tokens = [t for t in norm.split() if len(t) >= 3]
    if len(tokens) < 4:
        return True
    pt_hits = sum(1 for t in tokens if t in _PT_STOPWORDS)
    en_hits = sum(1 for t in tokens if t in _EN_STOPWORDS)
    lang = normalize_language(language)
    if lang == "pt-BR":
        return not (en_hits >= 2 and pt_hits == 0)
    if lang == "en":
        return not (pt_hits >= 2 and en_hits == 0)
    return True


def validate_question(
    item: dict,
    language: str = DEFAULT_AI_LANGUAGE,
    require_explanation: bool = False,
) -> tuple[bool, str]:
    """Valida uma questão gerada no servidor (qualidade da IA, ver docs/ARQUITETURA.md).

    Retorna (valida, motivo). Reprova: enunciado vazio, menos de 2 ou mais de 5 alternativas,
    alternativas repetidas, gabarito fora do intervalo, idioma trocado ou explicação ausente
    (quando exigida).
    """
    q_text = str(item.get("question") or "").strip()
    if not q_text:
        return False, "empty_question"

    options = item.get("options")
    if not isinstance(options, list) or len(options) < 2 or len(options) > 5:
        return False, "invalid_options_count"

    norm_opts: set[str] = set()
    for opt in options:
        opt_text = str(opt or "").strip()
        if not opt_text:
            return False, "empty_option"
        decomposed = unicodedata.normalize("NFKD", opt_text)
        no_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
        # Preserva símbolos matemáticos/lógicos (∧, ∨, →, +, -, =) e ignora pontuação final
        opt_key = re.sub(r"[.!?,;:]+$", "", re.sub(r"\s+", " ", no_accents.lower())).strip()
        if not opt_key:
            return False, "empty_option"
        if opt_key in norm_opts:
            return False, "duplicate_options"
        norm_opts.add(opt_key)

    answer = item.get("answer")
    if not isinstance(answer, int) or isinstance(answer, bool) or answer < 0 or answer >= len(options):
        return False, "answer_out_of_range"

    if require_explanation:
        explanation = str(item.get("explanation") or "").strip()
        if len(explanation) < 8:
            return False, "missing_explanation"

    combined = " ".join([q_text, *[str(o) for o in options]])
    if not _matches_requested_language(combined, language):
        return False, "wrong_language"

    return True, "ok"


def _parse_raw_answer_index(raw_answer: Any) -> int | None:
    """Converte índice/letra de gabarito em int sem mascarar valores inválidos."""
    if isinstance(raw_answer, bool) or raw_answer is None:
        return None
    if isinstance(raw_answer, int):
        return raw_answer
    if isinstance(raw_answer, str):
        cleaned = raw_answer.strip().upper()
        if len(cleaned) == 1 and "A" <= cleaned <= "E":
            return ord(cleaned) - ord("A")
        try:
            return int(cleaned)
        except ValueError:
            return None
    return None


def cross_check_questions(
    questions: list[dict],
    language: str = DEFAULT_AI_LANGUAGE,
    source_provider: str | None = None,
    client_ip: str | None = None,
) -> tuple[list[dict], int, dict]:
    """Confere o gabarito de cada questão com um segundo modelo (temperatura 0), sem mostrar o gabarito.

    Questões em que o segundo modelo concorda recebem `verified=True`. Questões em que discorda
    são descartadas (exceto se todas discordarem, caso em que devolve as originais sem selo).
    Em erro de rede/IA, faz fallback gracioso mantendo as questões originais com `verified_count=0`.
    """
    if not questions:
        return [], 0, {}

    items_for_prompt = [
        {"id": q["id"], "question": q["question"], "options": q["options"]}
        for q in questions
    ]
    prompt = "\n".join([
        "Você é um revisor rigoroso de provas e simulados.",
        "Resolva cada questão abaixo de forma independente e retorne APENAS o índice (base 0) da alternativa correta.",
        f"{_language_rule(language, 'a análise')}",
        "Retorne SOMENTE um objeto JSON válido no formato:",
        '{"answers": [{"id": 1, "answer": 0}]}',
        "",
        json.dumps(items_for_prompt, ensure_ascii=False),
    ])

    try:
        check_ai_token_quota(prompt, ip=client_ip)
        max_tokens = min(2048, max(300, len(questions) * 40))
        call_res = _call_ai(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=max_tokens,
            timeout=15,
            prefer_different_from=source_provider,
        )
        content, _model, usage, _provider = _unpack_call_result(call_res)
        parsed = parse_json_response(content)
        raw_answers = (
            parsed.get("answers")
            if isinstance(parsed, dict)
            else parsed
        )
        if not isinstance(raw_answers, list):
            return questions, 0, usage
    except Exception as e:  # noqa: BLE001 - falha na conferência não bloqueia o simulado
        _log_ops(f"conferência de gabarito ignorada ({e})")
        return questions, 0, {}

    checked_by_id: dict[int, int] = {}
    for entry in raw_answers:
        if not isinstance(entry, dict):
            continue
        qid = entry.get("id")
        ans = _parse_raw_answer_index(entry.get("answer"))
        if isinstance(qid, int) and ans is not None:
            checked_by_id[qid] = ans

    if not checked_by_id:
        return questions, 0, usage

    kept: list[dict] = []
    verified_count = 0
    for q in questions:
        qid = q["id"]
        if qid in checked_by_id:
            if checked_by_id[qid] == q["answer"]:
                kept.append({**q, "verified": True})
                verified_count += 1
            else:
                _log_ai(f"[IA] conferência descartou questão {qid} (gabarito {q['answer']} != {checked_by_id[qid]})")
        else:
            kept.append({**q, "verified": False})

    if not kept:
        # Evita devolver simulado vazio se o segundo modelo divergir de todas
        return [{**q, "verified": False} for q in questions], 0, usage

    renumbered = [
        {**q, "id": idx, "question_number": idx}
        for idx, q in enumerate(kept, start=1)
    ]
    return renumbered, verified_count, usage


def _parse_topic_questions(
    content: str,
    clean_topic: str,
    language: str = DEFAULT_AI_LANGUAGE,
    discarded: dict | None = None,
) -> tuple[str, list[dict]]:
    try:
        parsed = parse_json_response(content)
        if isinstance(parsed, list):
            raw_questions = parsed
            title = f"Quiz: {clean_topic.title()}"
        elif isinstance(parsed, dict):
            raw_questions = (
                parsed.get("questions")
                or parsed.get("questoes")
                or parsed.get("data")
                or next((v for v in parsed.values() if isinstance(v, list)), [])
            )
            title = parsed.get("title") or parsed.get("titulo") or f"Quiz: {clean_topic.title()}"
        else:
            raise ValueError("Formato JSON retornado não reconhecido")
    except (json.JSONDecodeError, ValueError) as e:
        _log_ops(f"quiz por tema: resposta da IA fora do formato JSON ({e})")
        raise AIServiceError("A IA respondeu em um formato inesperado. Tente novamente.")

    if not isinstance(raw_questions, list) or not raw_questions:
        raise AIServiceError("A IA não gerou nenhuma questão para o tema solicitado.")

    valid_questions = []
    for idx, item in enumerate(raw_questions, start=1):
        if not isinstance(item, dict):
            continue

        q_text = str(item.get("question") or item.get("enunciado") or "").strip()
        options = item.get("options") or item.get("alternativas") or []
        if not q_text or not isinstance(options, list) or len(options) < 2:
            continue

        # Limpar texto de opções caso venham com prefixos como a), A - , etc.
        cleaned_options = [
            re.sub(r"^[a-eA-E][\)\.\-]\s*", "", str(opt).strip())
            for opt in options
        ]

        raw_answer = item.get("answer") if "answer" in item else item.get("resposta")
        answer_idx = _parse_raw_answer_index(raw_answer)

        explanation = str(item.get("explanation") or item.get("explicacao") or "").strip()
        section = str(item.get("section") or item.get("secao") or clean_topic).strip()
        item_context = str(item.get("context") or item.get("contexto") or "").strip()

        candidate = {
            "id": idx,
            "question_number": idx,
            "section": section or clean_topic,
            "context": item_context,
            "question": q_text,
            "options": cleaned_options,
            "answer": answer_idx,
            "explanation": explanation or "Resposta correta conforme gabarito oficial.",
        }
        is_valid, reason = validate_question(candidate, language=language, require_explanation=False)
        if not is_valid:
            _log_ops(f"questão {idx} descartada na validação ({reason})")
            if discarded is not None:
                discarded[reason] = discarded.get(reason, 0) + 1
            continue
        valid_questions.append(candidate)

    if not valid_questions:
        raise AIServiceError("Não foi possível extrair questões válidas da resposta da IA.")

    return str(title).strip(), valid_questions


_TITLE_PART_PATTERN = re.compile(
    r"\s*[-–—:|,]?\s*[(\[]?\s*\b(parte|part)\s+\d+(\s*(de|of|/)\s*\d+)?\s*[)\]]?\s*", re.IGNORECASE
)
_TITLE_SMALL_WORDS = frozenset({"de", "da", "do", "das", "dos", "e", "em", "na", "no", "nas", "nos", "a", "o",
                                "as", "os", "of", "the", "and", "in", "on", "for", "to"})


def _topic_title(clean_topic: str, lang: str) -> str:
    """Título feito do próprio tema, quando o da IA não serve."""
    words = []
    for i, word in enumerate(clean_topic.split()):
        if _normalize_question_key(word) in _EXAM_TOKENS:
            words.append(word.upper())
        elif word.isupper() or any(ch.isdigit() for ch in word) or (i > 0 and word.lower() in _TITLE_SMALL_WORDS):
            words.append(word)
        else:
            words.append(word[:1].upper() + word[1:])
    prefix = "Quiz" if normalize_language(lang) == "en" else "Simulado"
    return f"{prefix}: {' '.join(words)}"


def _clean_quiz_title(title: str, clean_topic: str, lang: str = DEFAULT_AI_LANGUAGE) -> str:
    """Tira "Parte N" do título e confere se a IA manteve a prova e o ano do tema.

    Se o título cita uma prova ou banca que o tema não cita (ex.: ENEM quando o tema era ENADE),
    esquece a do tema ou esquece o ano, o título passa a ser feito do próprio tema. Paráfrases
    comuns ("Lógica Proposicional" para "raciocínio lógico") continuam valendo.
    """
    cleaned = _TITLE_PART_PATTERN.sub(" ", str(title or "")).strip(" -–—:|,")
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    title_tokens = set(_normalize_question_key(cleaned).split())
    exams, years = _topic_exam_and_years(clean_topic)
    exams_in_topic = {e.lower() for e in exams}
    if (
        not cleaned
        or (title_tokens & _EXAM_TOKENS) - exams_in_topic
        or exams_in_topic - title_tokens
        or set(years) - title_tokens
    ):
        return _topic_title(clean_topic, lang)
    return cleaned[:120]


def _call_ai_hedged(
    messages: list[dict],
    temperature: float,
    max_tokens: int,
    timeout: int,
    reasoning: str,
    hedge_after: float,
) -> tuple[tuple, bool]:
    """Chama a IA e, se não responder em `hedge_after` s, faz um segundo pedido igual.

    O segundo pedido vai de preferência para outro provedor. Vale a primeira resposta boa; a
    outra é ignorada (corta a cauda lenta: uma parte presa não segura o simulado inteiro).
    Retorna (resultado de _call_ai, se o segundo pedido foi feito).
    """
    if hedge_after <= 0:
        return _call_ai(
            messages=messages, temperature=temperature, max_tokens=max_tokens, timeout=timeout, reasoning=reasoning,
        ), False
    pool = ThreadPoolExecutor(max_workers=2)
    try:
        primary = pool.submit(
            _call_ai, messages=messages, temperature=temperature, max_tokens=max_tokens, timeout=timeout,
            reasoning=reasoning,
        )
        done, _pending = wait([primary], timeout=hedge_after)
        if done:
            return primary.result(), False
        now = time.time()
        ready = [p for p in _configured_providers() if _provider_pause.get(p.name, (0, ""))[0] <= now]
        _log_ops(f"parte sem resposta em {hedge_after:g} s; fazendo um segundo pedido em paralelo")
        backup = pool.submit(
            _call_ai, messages=messages, temperature=temperature, max_tokens=max_tokens, timeout=timeout,
            reasoning=reasoning, prefer_different_from=ready[0].label if ready else None,
        )
        pending = {primary, backup}
        first_error: Exception | None = None
        while pending:
            done, pending = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                try:
                    return future.result(), True
                except Exception as e:  # a outra ainda pode responder
                    first_error = first_error or e
        raise first_error or AIServiceError(AI_BUSY_MESSAGE)
    finally:
        pool.shutdown(wait=False)


def _generate_topic_part(
    clean_topic: str,
    qty: int,
    diff: str,
    context_str: str,
    lang: str,
    client_ip: str | None = None,
    part_index: int | None = None,
    total_parts: int | None = None,
    cross_check: bool = False,
    avoid_questions: list[str] | None = None,
) -> dict:
    started = time.monotonic()
    prompt = _build_topic_prompt(
        clean_topic, qty, diff, context_str, lang,
        part_index=part_index, total_parts=total_parts, avoid_questions=avoid_questions,
    )
    check_ai_token_quota(prompt, ip=client_ip)
    max_tokens = _topic_part_max_tokens(qty, diff)
    call_res, hedged = _call_ai_hedged(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5,
        max_tokens=max_tokens,
        timeout=75,  # tempo total, somando provedores e modelos
        reasoning="none",  # escrever questões não precisa de raciocínio longo; a conferência usa "low"
        hedge_after=float(AI_HEDGE_AFTER_SECONDS),
    )
    content, used_model, usage, provider_name = _unpack_call_result(call_res)
    if DEBUG:
        print(f"🤖 IA Quiz Gerado [{used_model}]:\n{content[:300]}")
    discarded: dict[str, int] = {}
    title, valid_questions = _parse_topic_questions(content, clean_topic, language=lang, discarded=discarded)
    part = {
        "title": title,
        "questions": valid_questions,
        "usage": usage,
        "model": used_model,
        "provider": provider_name,
        "verified_count": 0,
        "requested": qty,
        "discarded": discarded,
        "hedged": hedged,
    }
    if cross_check and valid_questions:
        # Confere esta parte assim que ela fica pronta, enquanto as outras ainda são geradas
        before = len(valid_questions)
        checked, verified_count, check_usage = cross_check_questions(
            valid_questions, language=lang, source_provider=provider_name, client_ip=client_ip,
        )
        part["questions"] = checked
        part["verified_count"] = verified_count
        if len(checked) < before:
            discarded["cross_check"] = discarded.get("cross_check", 0) + before - len(checked)
        if check_usage:
            part["usage"] = _merge_usage([usage, check_usage])
    part["seconds"] = round(time.monotonic() - started, 1)
    return part


def generate_quiz_by_topic(
    topic: str,
    num_questions: int = 5,
    difficulty: str = "Médio",
    context: str = "",
    client_ip: str | None = None,
    language: str = DEFAULT_AI_LANGUAGE,
    on_progress=None,
    cross_check: bool = False,
) -> dict:
    """
    Gera um conjunto completo de questões de quiz sobre um tema especificado.

    Divide em partes (tamanho e paralelismo em `_topic_speed_profile`: com a OpenAI na frente,
    partes de 3 e até 10 ao mesmo tempo; nos gratuitos, partes de 5 e até 3), reportando
    progresso via `on_progress(done, total)` e removendo enunciados repetidos no servidor.
    Quando `cross_check=True`, um segundo modelo confere o gabarito de cada parte assim que ela
    fica pronta (sem ver a resposta original) e o resultado registra `verified_count`.
    """
    clean_topic = topic.strip() if topic else ""
    if not clean_topic:
        raise AIServiceError("Por favor, informe um tema ou assunto para gerar o quiz.")

    try:
        qty = max(1, min(num_questions, 30))
    except (ValueError, TypeError):
        qty = 5

    diff = difficulty if difficulty in ("Fácil", "Médio", "Difícil") else "Médio"
    context_str = context.strip() if context else ""
    lang = normalize_language(language)

    # Fase 5: temas de exemplo prontos respondem na hora sem chamar a IA nem gastar cota
    from api.utils.sample_quizzes import get_preset_quiz

    preset = get_preset_quiz(clean_topic, qty=qty, difficulty=diff, context=context_str, language=lang)
    if preset is not None:
        return preset

    # Os temas de exemplo respondem mesmo sem chave de IA; o resto precisa de um provedor
    if not ai_configured():
        _log_ops(_NO_KEY_LOG)
        raise AIServiceError(AI_UNAVAILABLE_MESSAGE)

    # ── Cache de simulação para evitar requisições idênticas duplicadas ──────
    cache_suffix = ":cc" if cross_check else ""
    cache_key = hashlib.sha256(
        f"{clean_topic.lower()}:{qty}:{diff}:{context_str.lower()}:{lang}{cache_suffix}".encode("utf-8")
    ).hexdigest()

    now = time.time()
    with _quiz_cache_lock:
        if cache_key in _quiz_generation_cache:
            ts, cached_result = _quiz_generation_cache[cache_key]
            if now - ts < _QUIZ_CACHE_TTL:
                if DEBUG:
                    print(f"⚡ [ai_cache] Retornando simulado em cache para '{clean_topic}'")
                return {**copy.deepcopy(cached_result), "cached": True}

    # Segundo nível: tabela ai_cache, compartilhada entre as instâncias
    stored = ai_job_repo.cache_get(cache_key)
    if isinstance(stored, dict) and stored.get("questions"):
        with _quiz_cache_lock:
            _quiz_generation_cache[cache_key] = (now, copy.deepcopy(stored))
        _log_ai(f"⚡ [ai_cache] Simulado de '{clean_topic}' lido do banco")
        return {**copy.deepcopy(stored), "cached": True}

    def _report_progress(done: int, total: int) -> None:
        if callable(on_progress):
            try:
                on_progress(done, total)
            except Exception as e:  # noqa: BLE001
                _log_ops(f"falha ao reportar progresso ({done}/{total}): {e}")

    started = time.monotonic()
    part_size, parallel_parts = _topic_speed_profile()
    chunks = _plan_question_chunks(qty, chunk_size=part_size)
    total_parts = len(chunks)
    max_workers = min(parallel_parts, total_parts)

    if total_parts > 1:
        _report_progress(0, total_parts)
    parts_by_index: dict[int, dict] = {}
    errors: list[Exception] = []
    done_count = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(
                _generate_topic_part,
                clean_topic,
                chunk_qty,
                diff,
                context_str,
                lang,
                client_ip,
                idx if total_parts > 1 else None,
                total_parts if total_parts > 1 else None,
                cross_check,
            ): idx
            for idx, chunk_qty in enumerate(chunks, start=1)
        }
        for future in as_completed(future_map):
            part_idx = future_map[future]
            try:
                parts_by_index[part_idx] = future.result()
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)
                _log_ops(f"quiz por tema parte {part_idx}/{total_parts} falhou: {exc}")
            done_count += 1
            if total_parts > 1:
                _report_progress(done_count, total_parts)

    if not parts_by_index:
        if total_parts == 1 and errors:
            raise errors[0]
        for exc in errors:
            if isinstance(exc, AIQuotaExceededError):
                raise exc
        for exc in errors:
            if isinstance(exc, AIServiceError):
                raise exc
        raise AIServiceError("Não foi possível gerar questões válidas para o tema solicitado.")

    ordered_parts = [parts_by_index[i] for i in sorted(parts_by_index)]
    merged_questions = [q for part in ordered_parts for q in part["questions"]]
    unique_questions = _deduplicate_questions(merged_questions)
    duplicates_removed = len(merged_questions) - len(unique_questions)
    valid_questions = unique_questions[:qty]

    # Faltou questão (parte que falhou, questões reprovadas ou repetidas): pede só o que falta,
    # dividindo em partes paralelas quando missing > part_size e tentando até _TOPUP_MAX_ROUNDS.
    topup_used = False
    for _round in range(_TOPUP_MAX_ROUNDS):
        missing = qty - len(valid_questions)
        if missing <= 0 or time.monotonic() - started >= _TOPUP_TIME_BUDGET_SECONDS:
            break
        topup_used = True
        _log_ops(f"simulado por tema: faltaram {missing} de {qty} questões; pedindo só as que faltam")
        avoid = [str(q.get("question") or "") for q in valid_questions]
        extra_chunks = _plan_question_chunks(missing, chunk_size=part_size)
        added_this_round = 0
        if len(extra_chunks) == 1:
            try:
                extra = _generate_topic_part(
                    clean_topic, extra_chunks[0], diff, context_str, lang, client_ip, None, None, cross_check,
                    avoid_questions=avoid,
                )
                ordered_parts.append(extra)
                merged_questions.extend(extra["questions"])
                added_this_round += len(extra["questions"])
            except Exception as exc:  # noqa: BLE001 - devolve o que já tem
                errors.append(exc)
                _log_ops(f"pedido das questões que faltaram falhou: {exc}")
        else:
            extra_workers = min(parallel_parts, len(extra_chunks))
            with ThreadPoolExecutor(max_workers=extra_workers) as executor:
                extra_futures = [
                    executor.submit(
                        _generate_topic_part,
                        clean_topic,
                        chunk_qty,
                        diff,
                        context_str,
                        lang,
                        client_ip,
                        idx,
                        len(extra_chunks),
                        cross_check,
                        avoid,
                    )
                    for idx, chunk_qty in enumerate(extra_chunks, start=1)
                ]
                for future in as_completed(extra_futures):
                    try:
                        extra = future.result()
                        ordered_parts.append(extra)
                        merged_questions.extend(extra["questions"])
                        added_this_round += len(extra["questions"])
                    except Exception as exc:  # noqa: BLE001
                        errors.append(exc)
                        _log_ops(f"pedido parcial das questões que faltaram falhou: {exc}")
        unique_questions = _deduplicate_questions(merged_questions)
        duplicates_removed = len(merged_questions) - len(unique_questions)
        valid_questions = unique_questions[:qty]
        if added_this_round == 0:
            break

    if not valid_questions:
        raise AIServiceError("Não foi possível extrair questões válidas da resposta da IA.")

    first_part = ordered_parts[0]
    elapsed = time.monotonic() - started
    discarded: dict[str, int] = {}
    for part in ordered_parts:
        for reason, count in (part.get("discarded") or {}).items():
            discarded[reason] = discarded.get(reason, 0) + count
    generation = {
        "requested": qty,
        "delivered": len(valid_questions),
        "parts": total_parts,
        "part_size": part_size,
        "parallel": max_workers,
        "failed_parts": len(errors),
        "errors": [_short_error(e) for e in errors][:5],
        "discarded": discarded,
        "duplicates_removed": duplicates_removed,
        "hedged_parts": sum(1 for p in ordered_parts if p.get("hedged")),
        "topup": topup_used,
        "cross_check": bool(cross_check),
        "seconds": round(elapsed, 1),
        "part_seconds": [p.get("seconds") for p in ordered_parts],
        "models": sorted({f"{p.get('provider')} {p.get('model')}" for p in ordered_parts}),
    }
    result = {
        "title": _clean_quiz_title(first_part["title"], clean_topic, lang),
        "topic": clean_topic,
        "questions": valid_questions,
        "usage": _merge_usage([p.get("usage") for p in ordered_parts]),
        "model": first_part["model"],
        "provider": first_part["provider"],
        "requested": qty,
        "generation": generation,
    }
    if total_parts > 1:
        result["parts"] = {"done": len(parts_by_index), "total": total_parts}
    if cross_check:
        # Cada parte já foi conferida no próprio trabalho (ver _generate_topic_part)
        result["verified_count"] = sum(1 for q in valid_questions if q.get("verified"))

    _log_ops(
        f"simulado por tema: {len(valid_questions)} de {qty} questões em {total_parts} "
        f"parte(s) de até {part_size}, {max_workers} ao mesmo tempo"
        f"{', com conferência' if cross_check else ''}, via {', '.join(generation['models'])}; "
        f"falhas {len(errors)}, repetidas {duplicates_removed}, reprovadas {sum(discarded.values())}"
        f"{', pedido extra' if topup_used else ''} ({elapsed:.1f} s)"
    )

    # Só guarda no cache o simulado completo: um incompleto seria repetido para quem pedir de novo
    if len(valid_questions) >= qty:
        with _quiz_cache_lock:
            _quiz_generation_cache[cache_key] = (time.time(), copy.deepcopy(result))
        ai_job_repo.cache_set(cache_key, result)

    return result


def remix_questions_by_ai(
    questions: list[dict],
    client_ip: str | None = None,
    language: str = DEFAULT_AI_LANGUAGE,
) -> list[dict]:
    """
    Gera variações inéditas para uma lista de questões (ex: questões que o aluno errou).
    Mantém o mesmo conceito e nível de dificuldade, mas altera os dados/cenário para
    garantir aprendizado real em vez de mera memorização mecânica da alternativa.
    """
    if not questions:
        return []

    selected_questions = questions[:10]

    lines = [
        "Você é um professor especialista em provas de alto rendimento.",
        "O aluno errou as questões abaixo. Crie uma NOVA VARIAÇÃO INÉDITA para cada uma delas:",
        "- Mantenha exatamente o mesmo conceito teórico, subtema e nível de dificuldade da questão original.",
        "- Altere o cenário, os números, os nomes ou o exemplo prático para que seja uma pergunta nova e desafiadora.",
        "- Cada questão deve ter exatamente entre 4 e 5 opções limpas (sem letras como 'a)' no texto).",
        "- O campo 'answer' deve ser o índice numérico (0 a N-1) da opção correta.",
        "- O campo 'explanation' deve conter uma explicação didática detalhada de 2 a 3 frases.",
        f"- {_language_rule(language, 'todas as questões, alternativas e explicações')}",
        "",
        "Retorne SOMENTE um JSON válido no formato:",
        '{"questions": [{"id": 1, "section": "Subtema", "question": "Nova pergunta?", "options": ["A", "B", "C", "D"], "answer": 0, "explanation": "..."}]}',
        "",
        "Questões originais a variar:",
        "",
    ]

    for idx, q in enumerate(selected_questions, start=1):
        lines.append(f"Questão {idx} (Tema: {q.get('section', 'Geral')}): {q.get('question')}")
        opts = q.get("options", [])
        if isinstance(opts, list):
            for oi, opt in enumerate(opts):
                lines.append(f"  {chr(65+oi)}) {opt}")
        lines.append("")

    prompt = "\n".join(lines)
    check_ai_token_quota(prompt, ip=client_ip)
    max_tokens = min(3500, max(800, len(selected_questions) * 320))

    call_res = _call_ai(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.6,
        max_tokens=max_tokens,
        timeout=60,  # tempo total, somando provedores e modelos
        reasoning="none",  # gerar variações não precisa de tokens ocultos de raciocínio
    )
    content, used_model, usage, provider_name = _unpack_call_result(call_res)

    try:
        parsed = parse_json_response(content)
        raw_list = parsed.get("questions") if isinstance(parsed, dict) else parsed
        if not isinstance(raw_list, list):
            raw_list = next((v for v in parsed.values() if isinstance(v, list)), [])
    except Exception as e:
        _log_ops(f"variações: resposta da IA fora do formato JSON ({e})")
        raise AIServiceError("A IA respondeu em um formato inesperado. Tente novamente.")

    remixed = []
    for idx, item in enumerate(raw_list, start=1):
        if not isinstance(item, dict):
            continue
        q_text = str(item.get("question") or "").strip()
        opts = item.get("options") or []
        if not q_text or not isinstance(opts, list) or len(opts) < 2:
            continue

        clean_opts = [re.sub(r"^[a-eA-E][)\s\-\.]+", "", str(o)).strip() for o in opts]
        ans = int(item.get("answer", 0))
        if ans < 0 or ans >= len(clean_opts):
            ans = 0

        orig_q = selected_questions[idx - 1] if idx - 1 < len(selected_questions) else {}
        remixed.append({
            "id": idx,
            "question_number": idx,
            "section": str(item.get("section") or orig_q.get("section") or "Caderno de Erros (Variação IA)").strip(),
            "context": str(item.get("context") or "").strip(),
            "question": q_text,
            "options": clean_opts,
            "answer": ans,
            "explanation": str(item.get("explanation") or "Explicação didática da variação.").strip(),
            "is_remix": True,
        })

    if not remixed:
        raise AIServiceError("Não foi possível gerar variações para as questões selecionadas.")

    return remixed


def parse_and_structure_questions_with_ai(
    text: str,
    max_chars: int = 40_000,
    client_ip: str | None = None,
    num_questions: int | None = None,
    context: str = "",
    language: str = DEFAULT_AI_LANGUAGE,
) -> list[dict]:
    """
    Analisa texto bruto e despadronizado de uma prova/simulado ou material de estudo (TXT, PDF, DOCX),
    usando IA para estruturar ou adaptar em questões de múltipla escolha com gabarito e explicações.

    Args:
        text: Texto cru extraído do arquivo
        max_chars: Limite seguro de caracteres para análise do LLM
        client_ip: IP do cliente para controle de cota
        num_questions: Quantidade desejada de questões (opcional, 1 a 30)
        context: Instruções adicionais de foco ou adaptação
        language: Idioma das questões e explicações ("pt-BR" ou "en")

    Returns:
        list[dict]: [{id, question, options, answer, explanation, section, context}]

    Raises:
        AIServiceError: Se a IA falhar ou não conseguir estruturar questões válidas
    """
    if not text or not text.strip():
        raise AIServiceError("Texto vazio fornecido para estruturação por IA.")

    # Respeitar limite de caracteres para evitar estouro de tokens/timeout
    truncated_text = text.strip()
    if len(truncated_text) > max_chars:
        truncated_text = truncated_text[:max_chars]

    qty_instruction = ""
    target_count = None
    if num_questions and num_questions > 0:
        target_count = max(1, min(num_questions, 30))
        qty_instruction = f"Você DEVE produzir e retornar exatamente {target_count} questões de múltipla escolha a partir do conteúdo."
    else:
        qty_instruction = "Identifique e extraia todas as questões contidas no texto. Se o texto for dissertativo/resumo, elabore entre 5 e 10 questões relevantes."

    # Prefixo estático primeiro (papel, regras e esquema JSON) e dados variáveis/documento no final
    # para maximizar reuso de prefixo (Prompt Caching automático) sem inflar o prompt.
    prompt_lines = [
        "Você é um professor e elaborador sênior de provas e simulados acadêmicos e de concursos.",
        "Sua tarefa é analisar o documento em anexo (extraído de um TXT, PDF ou DOCX).",
        "O documento pode ser:",
        "  A) Um arquivo com questões de prova/simulado já existentes (com ou sem numeração, com ou sem gabarito); OU",
        "  B) Um texto teórico, resumo, apostila ou anotações de estudo que você DEVE ADAPTAR E TRANSFORMAR em um simulado com questões inéditas de múltipla escolha.",
        "",
        "Instruções obrigatórias:",
        f"1. {_language_rule(language, 'todas as questões e explicações')}",
        "2. Para cada questão, isole o enunciado limpo no campo 'question'.",
        "3. Isole cada alternativa no campo 'options' (como lista de strings, SEM prefixos como 'a)', 'b)', '1.', etc.). Cada questão deve ter exatamente 4 ou 5 alternativas.",
        "4. Resposta ('answer'):",
        "   - Se o documento contiver gabarito explícito para aquela questão, utilize-o.",
        "   - Se o documento NÃO contiver resposta/gabarito ou for um texto teórico adaptado, você DEVE resolver a questão com precisão, definindo em 'answer' o índice numérico (base 0) da alternativa correta.",
        "5. Baseie todas as questões estritamente no documento enviado; na 'explanation' (2 a 4 frases), cite o conceito ou trecho do material que justifica a alternativa correta.",
        "6. Identifique a disciplina ou subtema no campo 'section' (ex: 'Raciocínio Lógico', 'Português', 'Direito', ou tema central se for texto geral).",
        "",
        "IMPORTANTE: Retorne SOMENTE um objeto JSON válido, sem texto adicional, no formato estrito:",
        '{"questions": [{"id": 1, "section": "Geral", "context": "", "question": "Enunciado da pergunta?", "options": ["Opção A", "Opção B", "Opção C", "Opção D"], "answer": 0, "explanation": "Explicação detalhada."}]}',
        "",
        f"Instrução de quantidade: {qty_instruction}",
    ]
    context_clean = context.strip() if context else ""
    if context_clean:
        prompt_lines.append(f"Diretrizes e foco específico adicional: {context_clean}")

    prompt_lines.extend([
        "",
        "--- INÍCIO DO DOCUMENTO ---",
        truncated_text,
        "--- FIM DO DOCUMENTO ---",
    ])

    prompt = "\n".join(prompt_lines)
    check_ai_token_quota(prompt, ip=client_ip)
    needed_tokens = (target_count or 10) * 320
    max_tokens = min(4096, max(1200, needed_tokens))

    call_res = _call_ai(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.25,
        max_tokens=max_tokens,
        timeout=75,
        reasoning="none",  # extração e estruturação não precisam de tokens ocultos de raciocínio
    )
    content, used_model, usage, provider_name = _unpack_call_result(call_res)

    if DEBUG:
        _log_ai(f"🤖 IA [{used_model}] estruturou documento:\n{content[:400]}")

    try:
        parsed = parse_json_response(content)
        raw_list = parsed.get("questions") if isinstance(parsed, dict) else parsed
        if not isinstance(raw_list, list):
            raw_list = next((v for v in parsed.values() if isinstance(v, list)), [])
        if not isinstance(raw_list, list):
            raise ValueError("Esperado array de questões no JSON retornado.")
    except Exception as e:
        _log_ops(f"estruturar arquivo: resposta da IA fora do formato JSON ({e})")
        raise AIServiceError("A IA respondeu em um formato inesperado. Tente novamente.")

    structured_questions = []
    for idx, item in enumerate(raw_list, start=1):
        if not isinstance(item, dict):
            continue
        q_text = str(item.get("question") or "").strip()
        opts = item.get("options") or []
        if not q_text or not isinstance(opts, list) or len(opts) < 2:
            continue

        clean_opts = [re.sub(r"^[a-eA-E0-9][)\s\-\.:]+", "", str(o)).strip() for o in opts]
        ans = _parse_raw_answer_index(item.get("answer"))

        candidate = {
            "id": idx,
            "question_number": idx,
            "section": str(item.get("section") or "Geral").strip(),
            "context": str(item.get("context") or "").strip(),
            "question": q_text,
            "options": clean_opts,
            "answer": ans,
            "explanation": str(item.get("explanation") or "").strip(),
            "ai_generated": True,
        }
        is_valid, reason = validate_question(candidate, language=language, require_explanation=False)
        if not is_valid:
            _log_ai(f"[IA] questão de arquivo {idx} descartada na validação ({reason})")
            continue
        structured_questions.append(candidate)

    structured_questions = _deduplicate_questions(structured_questions, limit=target_count)
    if not structured_questions:
        raise AIServiceError(
            "A inteligência artificial não conseguiu identificar ou gerar questões válidas para o texto fornecido."
        )

    return structured_questions



