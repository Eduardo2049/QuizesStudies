"""
Serviço de IA via OpenRouter.
Gera gabarito automaticamente para quizzes sem resposta definida.
"""
import json
import requests
from api.utils.config import OPENROUTER_API_KEY, OPENROUTER_MODEL, OPENROUTER_BASE_URL, DEBUG


class AIServiceError(Exception):
    """Erro ao chamar a API de IA"""
    pass


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


def generate_answer_key(questions: list[dict]) -> list[dict]:
    """
    Gera gabarito para uma lista de questões via OpenRouter API.

    Args:
        questions: Lista de dicts com {id, question, options, ...}

    Returns:
        Lista de {question_id, answer: int, explanation: str}

    Raises:
        AIServiceError: Se a API não responder ou retornar JSON inválido
    """
    if not OPENROUTER_API_KEY:
        raise AIServiceError(
            "OPENROUTER_API_KEY não configurada. "
            "Adicione a chave no arquivo .env para usar geração de gabarito por IA."
        )

    prompt = _build_prompt(questions)

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1,  # Baixa temperatura para respostas determinísticas
        "response_format": {"type": "json_object"},
    }

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "HTTP-Referer": "https://ifuture-study.app",
        "X-Title": "IFuture Study",
    }

    url = f"{OPENROUTER_BASE_URL}/chat/completions"

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=60)
        raw = resp.text
        if not resp.ok:
            raise AIServiceError(
                f"OpenRouter retornou erro {resp.status_code}: {raw}"
            )
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
    except requests.exceptions.RequestException as e:
        raise AIServiceError(f"Falha ao conectar ao OpenRouter: {e}")
    except (KeyError, IndexError, json.JSONDecodeError, ValueError) as e:
        raw_snippet = raw[:500] if "raw" in locals() else str(e)
        raise AIServiceError(f"Resposta inesperada da API: {raw_snippet}")

    if DEBUG:
        print(f"🤖 OpenRouter ({OPENROUTER_MODEL}) respondeu:\n{content[:300]}")

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
            result.append({
                "question_id": int(item["question_id"]),
                "answer": int(item["answer"]),
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
