"""
Serviço de IA via OpenRouter.
Gera gabarito automaticamente para quizzes sem resposta definida.
"""
import copy
import hashlib
import json
import os
import re
import time
import requests
from collections import defaultdict, deque
from threading import Lock
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from api.repositories.rate_limit_repository import rate_limit_repo, RateLimitRepository
from api.utils.config import (
    OPENROUTER_API_KEY,
    OPENROUTER_MODEL,
    OPENROUTER_BASE_URL,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    GEMINI_BASE_URL,
    AI_PROVIDER,
    DEBUG,
)

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
        adapter = HTTPAdapter(max_retries=retries, pool_connections=5, pool_maxsize=10)
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
_quiz_generation_cache: dict[str, tuple[float, dict]] = {}
_QUIZ_CACHE_TTL = 3600  # 1 hora de cache para temas idênticos
_quiz_cache_lock = Lock()


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
            used = self.repo.get_usage(quota_key, self.window)
            if not allowed:
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

    if status_code == 404 or "no endpoints found" in lower_msg or "model not found" in lower_msg:
        return "O modelo de IA selecionado está indisponível no provedor no momento. Tente novamente em instantes."
    if status_code == 401 or "unauthorized" in lower_msg or "invalid api key" in lower_msg:
        return "A chave da API de inteligência artificial é inválida ou expirou. Verifique as configurações."
    if status_code == 402 or "credit" in lower_msg or "quota" in lower_msg or "balance" in lower_msg:
        return "Créditos insuficientes ou limite de tokens atingido na conta de IA. Por favor, recarregue os créditos."
    if status_code == 429 or "rate limit" in lower_msg:
        return "Muitas requisições enviadas à inteligência artificial. Por favor, aguarde alguns segundos e tente novamente."
    if status_code >= 500:
        return "O provedor de inteligência artificial está temporariamente instável. Tente novamente em instantes."

    return "Não foi possível comunicar com o serviço de inteligência artificial. Tente novamente mais tarde."


def _get_model_candidates(configured_model: str) -> list[str]:
    """
    Retorna uma lista ordenada de modelos para tentar.
    Se o modelo configurado falhar (404/sem endpoint), tenta alternativas conhecidas.
    """
    candidates = []
    if configured_model and configured_model.strip():
        candidates.append(configured_model.strip())

    is_gemini = "gemini" in (configured_model or "").lower()
    if is_gemini:
        fallbacks = [
            "google/gemini-2.5-flash",
            "google/gemini-2.5-flash-lite",
            "openai/gpt-4o-mini",
        ]
    else:
        fallbacks = [
            "openai/gpt-4o-mini",
            "google/gemini-2.5-flash",
            "google/gemini-2.5-flash-lite",
        ]

    for fb in fallbacks:
        if fb not in candidates:
            candidates.append(fb)

    return candidates


def _log_ai(msg: str) -> None:
    if not DEBUG:
        return
    try:
        print(msg)
    except UnicodeEncodeError:
        safe_msg = msg.encode("ascii", errors="replace").decode("ascii")
        print(safe_msg)


def _call_openrouter(
    messages: list[dict],
    temperature: float,
    max_tokens: int,
    timeout: int = 75,
) -> tuple[str, str, dict]:
    """
    Chama a API de Inteligência Artificial:
    - Se AI_PROVIDER for 'google'/'gemini' ou se GEMINI_API_KEY estiver configurada,
      conecta diretamente ao Google AI Studio (100% gratuito).
    - Caso contrário ou se AI_PROVIDER for 'openrouter', conecta via OpenRouter.
    Retorna (content, used_model, usage).
    """
    force_google = AI_PROVIDER in ("google", "gemini")
    force_openrouter = AI_PROVIDER == "openrouter"

    if force_openrouter:
        is_gemini_direct = False
        api_key = OPENROUTER_API_KEY
    elif force_google:
        is_gemini_direct = True
        api_key = GEMINI_API_KEY
    else:
        # Padrão: prioriza Google AI Studio direto se chave estiver presente
        is_gemini_direct = bool(GEMINI_API_KEY)
        api_key = GEMINI_API_KEY if is_gemini_direct else OPENROUTER_API_KEY

    provider_name = "Google AI Studio" if is_gemini_direct else "OpenRouter"

    if not api_key:
        if is_gemini_direct:
            raise AIServiceError(
                "Chave do Google AI Studio não encontrada. "
                "Adicione GEMINI_API_KEY no arquivo .env."
            )
        else:
            raise AIServiceError(
                "Chave da OpenRouter não encontrada. "
                "Adicione OPENROUTER_API_KEY no arquivo .env ou configure GEMINI_API_KEY."
            )

    session = _get_http_session()
    base_url = GEMINI_BASE_URL if is_gemini_direct else OPENROUTER_BASE_URL
    url = f"{base_url.rstrip('/')}/chat/completions"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if not is_gemini_direct:
        headers["HTTP-Referer"] = "https://ifuture-study.app"
        headers["X-Title"] = "IFuture Study"

    if is_gemini_direct:
        model = (GEMINI_MODEL or "gemini-flash-lite-latest").removeprefix("google/")
        if model in ("gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash", "gemini-flash-latest", ""):
            model = "gemini-flash-lite-latest"
        candidates = [model]
        if "gemini-3.5-flash-lite" not in candidates:
            candidates.append("gemini-3.5-flash-lite")
    else:
        candidates = [OPENROUTER_MODEL or "google/gemini-2.5-flash"]

    last_status = 500
    last_raw = ""

    for idx, model in enumerate(candidates):
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        try:
            _log_ai(f"[IA] Conectando ao {provider_name} (Modelo: '{model}')...")
            resp = session.post(url, json=payload, headers=headers, timeout=timeout)
            raw = resp.text
            last_status = resp.status_code
            last_raw = raw

            if resp.ok:
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                usage = data.get("usage") or {}
                _log_ai(f"[IA] Sucesso com {provider_name} (Modelo: '{model}') | Tokens: {usage}")
                return content, model, usage

            if idx < len(candidates) - 1:
                _log_ai(f"[IA AVISO] Modelo '{model}' retornou {resp.status_code}. Tentando '{candidates[idx+1]}'...")
                continue

            raise AIServiceError(_format_user_friendly_error(resp.status_code, raw))

        except requests.exceptions.RequestException as e:
            _log_ai(f"[IA AVISO] Falha de conexao com '{model}': {e}")
            if idx < len(candidates) - 1:
                continue
            raise AIServiceError("Falha na conexao com o servico de inteligencia artificial. Verifique sua rede e tente novamente.")

    if last_raw:
        raise AIServiceError(_format_user_friendly_error(last_status, last_raw))
    raise AIServiceError("Não foi possível conectar ao provedor de inteligência artificial.")


def _unpack_call_result(res) -> tuple[str, str, dict]:
    """Suporta retorno de 2-tupla (mocks em testes) e 3-tupla (chamadas reais com usage)."""
    if isinstance(res, tuple) and len(res) == 3:
        return res[0], res[1], res[2]
    elif isinstance(res, tuple) and len(res) == 2:
        return res[0], res[1], {}
    return str(res), "mock", {}


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
    prompt = _build_prompt(questions)
    check_ai_token_quota(prompt, ip=client_ip)
    max_tokens = min(3500, max(500, len(questions) * 120))
    call_res = _call_openrouter(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=max_tokens,
        timeout=35,  # Gemini Flash Lite responde em <10s; 35s = margem segura
    )
    content, used_model, usage = _unpack_call_result(call_res)

    if DEBUG:
        print(f"🤖 IA [{used_model}] respondeu:\n{content[:300]}")

    # Parsear a resposta JSON do LLM
    try:
        # O LLM pode retornar o array direto ou dentro de um objeto
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            # Tentar extrair array de dentro do objeto
            parsed = next(
                (v for v in parsed.values() if isinstance(v, list)),
                []
            )
        if not isinstance(parsed, list):
            raise ValueError("Esperado array JSON")
    except (json.JSONDecodeError, ValueError) as e:
        raise AIServiceError(
            f"O modelo não retornou JSON válido. Resposta: {content[:300]}"
        )

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


def generate_quiz_by_topic(
    topic: str,
    num_questions: int = 5,
    difficulty: str = "Médio",
    context: str = "",
    client_ip: str | None = None,
) -> dict:
    """
    Gera um conjunto completo de questões de quiz sobre um tema especificado via OpenRouter API.

    Args:
        topic: Tema ou assunto do simulado (ex: "Raciocínio Lógico Proposicional")
        num_questions: Quantidade de questões (1 a 20, padrão 5)
        difficulty: Nível ("Fácil", "Médio", "Difícil")
        context: Diretrizes ou instruções adicionais opcionais
        client_ip: IP do cliente para controle de cota de tokens (opcional).

    Returns:
        dict: {
            "title": str,
            "topic": str,
            "questions": list[dict]
        }

    Raises:
        AIServiceError: Se falhar a comunicação ou o modelo não gerar questões válidas
        AIQuotaExceededError: Se o IP exceder a cota de tokens por hora
    """
    if not (GEMINI_API_KEY or OPENROUTER_API_KEY):
        raise AIServiceError(
            "Nenhuma chave de IA configurada. "
            "Adicione GEMINI_API_KEY ou OPENROUTER_API_KEY no arquivo .env."
        )

    clean_topic = str(topic or "").strip()
    if not clean_topic:
        raise AIServiceError("Por favor, informe um tema ou assunto para gerar o quiz.")

    try:
        qty = max(1, min(int(num_questions or 5), 30))
    except (ValueError, TypeError):
        qty = 5

    diff = difficulty if difficulty in ("Fácil", "Médio", "Difícil") else "Médio"

    # ── Cache de simulação para evitar requisições idênticas duplicadas ──────
    cache_key = hashlib.sha256(
        f"{clean_topic.lower()}:{qty}:{diff}:{str(context).strip().lower()}".encode("utf-8")
    ).hexdigest()

    now = time.time()
    with _quiz_cache_lock:
        if cache_key in _quiz_generation_cache:
            ts, cached_result = _quiz_generation_cache[cache_key]
            if now - ts < _QUIZ_CACHE_TTL:
                if DEBUG:
                    print(f"⚡ [ai_cache] Retornando simulado em cache para '{clean_topic}'")
                return copy.deepcopy(cached_result)

    prompt_lines = [
        "Você é um professor e elaborador sênior de provas e simulados acadêmicos e de concursos.",
        f"Crie um simulado de múltipla escolha com exatamente {qty} questões sobre o seguinte tema: '{clean_topic}'.",
        f"Nível de dificuldade exigido: {diff}.",
    ]
    if context and str(context).strip():
        prompt_lines.append(f"Diretrizes e foco específico adicional: {str(context).strip()}")

    prompt_lines.extend([
        "",
        "Regras obrigatórias:",
        "1. O idioma das questões DEVE ser Português do Brasil (pt-BR).",
        "2. Todas as questões devem ser inéditas, com enunciados claros, sem ambiguidades.",
        "3. Cada questão deve possuir exatamente 4 ou 5 alternativas em formato de texto limpo (não coloque 'a)', 'b)' dentro do texto da alternativa).",
        "4. Apenas UMA alternativa deve ser a correta.",
        "5. O campo 'answer' deve ser o índice numérico (base 0) da alternativa correta (0 = primeira opção, 1 = segunda opção, 2 = terceira opção...).",
        "6. O campo 'explanation' deve fornecer uma justificativa didática detalhada de 2 a 4 frases explicando por que a alternativa está correta.",
        "7. Forneça um título atraente e descritivo para o quiz no campo 'title'.",
        "",
        "IMPORTANTE: Retorne SOMENTE um objeto JSON válido, sem qualquer texto ou formatação fora do JSON, no seguinte formato estrito:",
        """{
  "title": "Título Descritivo do Quiz",
  "questions": [
    {
      "id": 1,
      "section": "Subtema ou disciplina",
      "context": "Breve contexto introdutório se necessário (ou vazio)",
      "question": "Enunciado completo da pergunta?",
      "options": [
        "Texto da opção A",
        "Texto da opção B",
        "Texto da opção C",
        "Texto da opção D"
      ],
      "answer": 0,
      "explanation": "Explicação detalhada do porquê a opção A é a correta."
    }
  ]
}"""
    ])
    prompt = "\n".join(prompt_lines)
    check_ai_token_quota(prompt, ip=client_ip)
    max_tokens = min(4096, max(800, qty * 320))
    call_res = _call_openrouter(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5,
        max_tokens=max_tokens,
        timeout=75,  # Geração completa: timeout de 75s para suportar volumes maiores
    )
    content, used_model, usage = _unpack_call_result(call_res)

    if DEBUG:
        print(f"🤖 IA Quiz Gerado [{used_model}]:\n{content[:300]}")

    try:
        parsed = json.loads(content)
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
        raise AIServiceError(f"O modelo não retornou JSON válido para o quiz: {e}")

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
        cleaned_options = []
        for opt in options:
            opt_str = str(opt).strip()
            # Remove a), A), a - etc
            import re
            opt_str = re.sub(r"^[a-eA-E][\)\.\-]\s*", "", opt_str)
            cleaned_options.append(opt_str)

        # Tratar índice da resposta correta
        raw_answer = item.get("answer") if "answer" in item else item.get("resposta")
        answer_idx = 0
        if isinstance(raw_answer, int):
            answer_idx = raw_answer
        elif isinstance(raw_answer, str):
            raw_answer_clean = raw_answer.strip().upper()
            if len(raw_answer_clean) == 1 and "A" <= raw_answer_clean <= "E":
                answer_idx = ord(raw_answer_clean) - ord("A")
            else:
                try:
                    answer_idx = int(raw_answer_clean)
                except ValueError:
                    answer_idx = 0

        if answer_idx < 0 or answer_idx >= len(cleaned_options):
            answer_idx = 0

        explanation = str(item.get("explanation") or item.get("explicacao") or "").strip()
        section = str(item.get("section") or item.get("secao") or clean_topic).strip()
        item_context = str(item.get("context") or item.get("contexto") or "").strip()

        valid_questions.append({
            "id": idx,
            "question_number": idx,
            "section": section or clean_topic,
            "context": item_context,
            "question": q_text,
            "options": cleaned_options,
            "answer": answer_idx,
            "explanation": explanation or "Resposta correta conforme gabarito oficial.",
        })

    if not valid_questions:
        raise AIServiceError("Não foi possível extrair questões válidas da resposta da IA.")

    provider_name = "Google AI Studio" if AI_PROVIDER in ("google", "gemini") or GEMINI_API_KEY else "OpenRouter"
    result = {
        "title": str(title).strip(),
        "topic": clean_topic,
        "questions": valid_questions,
        "usage": usage,
        "model": used_model,
        "provider": provider_name,
    }

    # Armazena no cache local
    with _quiz_cache_lock:
        _quiz_generation_cache[cache_key] = (time.time(), copy.deepcopy(result))

    return result


def remix_questions_by_ai(questions: list[dict], client_ip: str | None = None) -> list[dict]:
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

    call_res = _call_openrouter(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.6,
        max_tokens=max_tokens,
        timeout=35,  # Remix de erros: mesmo prazo do gabarito
    )
    content, used_model, usage = _unpack_call_result(call_res)

    try:
        parsed = json.loads(content)
        raw_list = parsed.get("questions") if isinstance(parsed, dict) else parsed
        if not isinstance(raw_list, list):
            raw_list = next((v for v in parsed.values() if isinstance(v, list)), [])
    except Exception as e:
        raise AIServiceError(f"A IA não retornou JSON válido para as variações: {e}")

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
    if num_questions and int(num_questions) > 0:
        target_count = max(1, min(int(num_questions), 30))
        qty_instruction = f"Você DEVE produzir e retornar exatamente {target_count} questões de múltipla escolha a partir do conteúdo."
    else:
        qty_instruction = "Identifique e extraia todas as questões contidas no texto. Se o texto for dissertativo/resumo, elabore entre 5 e 10 questões relevantes."

    prompt_lines = [
        "Você é um professor e elaborador sênior de provas e simulados acadêmicos e de concursos.",
        "Sua tarefa é analisar o documento em anexo (extraído de um TXT, PDF ou DOCX).",
        "O documento pode ser:",
        "  A) Um arquivo com questões de prova/simulado já existentes (com ou sem numeração, com ou sem gabarito); OU",
        "  B) Um texto teórico, resumo, apostila ou anotações de estudo que você DEVE ADAPTAR E TRANSFORMAR em um simulado com questões inéditas de múltipla escolha.",
        "",
        f"Instrução de quantidade: {qty_instruction}",
    ]
    if context and str(context).strip():
        prompt_lines.append(f"Diretrizes e foco específico adicional: {str(context).strip()}")

    prompt_lines.extend([
        "",
        "Instruções obrigatórias:",
        "1. O idioma de todas as questões e explicações DEVE ser Português do Brasil (pt-BR).",
        "2. Para cada questão, isole o enunciado limpo no campo 'question'.",
        "3. Isole cada alternativa no campo 'options' (como lista de strings, SEM prefixos como 'a)', 'b)', '1.', etc.). Cada questão deve ter exatamente 4 ou 5 alternativas.",
        "4. Resposta ('answer'):",
        "   - Se o documento contiver gabarito explícito para aquela questão, utilize-o.",
        "   - Se o documento NÃO contiver resposta/gabarito ou for um texto teórico adaptado, você DEVE resolver a questão com precisão, definindo em 'answer' o índice numérico (base 0) da alternativa correta.",
        "5. Forneça no campo 'explanation' uma explicação didática detalhada (2 a 4 frases) justificando por que aquela alternativa é a correta.",
        "6. Identifique a disciplina ou subtema no campo 'section' (ex: 'Raciocínio Lógico', 'Português', 'Direito', ou tema central se for texto geral).",
        "",
        "IMPORTANTE: Retorne SOMENTE um objeto JSON válido, sem texto adicional, no formato estrito:",
        '{"questions": [{"id": 1, "section": "Geral", "context": "", "question": "Enunciado da pergunta?", "options": ["Opção A", "Opção B", "Opção C", "Opção D"], "answer": 0, "explanation": "Explicação detalhada."}]}',
        "",
        "--- INÍCIO DO DOCUMENTO ---",
        truncated_text,
        "--- FIM DO DOCUMENTO ---",
    ])

    prompt = "\n".join(prompt_lines)
    check_ai_token_quota(prompt, ip=client_ip)
    needed_tokens = (target_count or 10) * 320
    max_tokens = min(4096, max(1200, needed_tokens))

    call_res = _call_openrouter(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.25,
        max_tokens=max_tokens,
        timeout=75,
    )
    content, used_model, usage = _unpack_call_result(call_res)

    if DEBUG:
        _log_ai(f"🤖 IA [{used_model}] estruturou documento:\n{content[:400]}")

    try:
        parsed = json.loads(content)
        raw_list = parsed.get("questions") if isinstance(parsed, dict) else parsed
        if not isinstance(raw_list, list):
            raw_list = next((v for v in parsed.values() if isinstance(v, list)), [])
        if not isinstance(raw_list, list):
            raise ValueError("Esperado array de questões no JSON retornado.")
    except Exception as e:
        raise AIServiceError(f"A IA não retornou JSON válido ao estruturar o arquivo: {e}")

    structured_questions = []
    for idx, item in enumerate(raw_list, start=1):
        if not isinstance(item, dict):
            continue
        q_text = str(item.get("question") or "").strip()
        opts = item.get("options") or []
        if not q_text or not isinstance(opts, list) or len(opts) < 2:
            continue

        clean_opts = [re.sub(r"^[a-eA-E0-9][)\s\-\.:]+", "", str(o)).strip() for o in opts]
        try:
            ans = int(item.get("answer", 0))
        except (ValueError, TypeError):
            ans = 0

        if ans < 0 or ans >= len(clean_opts):
            ans = 0

        structured_questions.append({
            "id": idx,
            "question_number": idx,
            "section": str(item.get("section") or "Geral").strip(),
            "context": str(item.get("context") or "").strip(),
            "question": q_text,
            "options": clean_opts,
            "answer": ans,
            "explanation": str(item.get("explanation") or "").strip(),
            "ai_generated": True,
        })

    if not structured_questions:
        raise AIServiceError(
            "A inteligência artificial não conseguiu identificar ou gerar questões válidas para o texto fornecido."
        )

    if target_count and len(structured_questions) > target_count:
        structured_questions = structured_questions[:target_count]
        for idx, q in enumerate(structured_questions, start=1):
            q["id"] = idx
            q["question_number"] = idx

    return structured_questions



