"""
Parser unificado para extração de texto de diferentes formatos.
Suporta: TXT, PDF, DOCX.

O parser de questões aceita alternativas de 'a)' até qualquer letra,
sem limite fixo (2 a N alternativas por questão).
"""
import re
import io
from typing import Optional

MAX_PDF_PAGES = 100
MAX_DOCX_PARAGRAPHS = 10_000
MAX_EXTRACTED_CHARS = 1_000_000


# ─── Extração de texto bruto por formato ─────────────────────────────────────

def parse_txt(content: bytes, encoding: str = "utf-8") -> str:
    """Extrai texto de arquivo TXT."""
    try:
        return content.decode(encoding)
    except UnicodeDecodeError:
        return content.decode("latin-1", errors="replace")


def parse_pdf(content: bytes) -> str:
    """Extrai texto de arquivo PDF usando pdfplumber."""
    try:
        import pdfplumber
    except ImportError:
        raise ImportError("pdfplumber não instalado. Execute: pip install pdfplumber")

    text_parts = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            if page_number > MAX_PDF_PAGES:
                raise ValueError(f"PDF excede o limite de {MAX_PDF_PAGES} páginas")
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
                if sum(len(part) for part in text_parts) > MAX_EXTRACTED_CHARS:
                    raise ValueError("Texto extraído excede o limite permitido")
    return "\n".join(text_parts)


def parse_docx(content: bytes) -> str:
    """Extrai texto de arquivo DOCX usando python-docx."""
    try:
        from docx import Document
    except ImportError:
        raise ImportError("python-docx não instalado. Execute: pip install python-docx")

    doc = Document(io.BytesIO(content))
    if len(doc.paragraphs) > MAX_DOCX_PARAGRAPHS:
        raise ValueError(f"DOCX excede o limite de {MAX_DOCX_PARAGRAPHS} parágrafos")
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n".join(paragraphs)


def extract_text(content: bytes, file_type: str) -> str:
    """
    Dispatcher principal: extrai texto baseado no tipo do arquivo.

    Args:
        content: Bytes do arquivo
        file_type: 'txt', 'pdf' ou 'docx'

    Returns:
        Texto extraído

    Raises:
        ValueError: Se file_type não suportado
    """
    file_type = file_type.lower().lstrip(".")
    parsers = {
        "txt": parse_txt,
        "pdf": parse_pdf,
        "docx": parse_docx,
    }
    if file_type not in parsers:
        raise ValueError(f"Tipo de arquivo não suportado: {file_type}. Use: txt, pdf, docx")
    return parsers[file_type](content)


# ─── Detecção de gabarito ─────────────────────────────────────────────────────

def detect_has_answer_key(text: str) -> bool:
    """
    Verifica se o texto contém seção de gabarito.
    Aceita variações como 'Gabarito', 'GABARITO', 'Resposta', 'Answer Key'.
    """
    patterns = [
        r"#\s*gabarito\b",
        r"gabarito\s*:",
        r"\bresposta\s*correta\b",
        r"\banswer\s*key\b",
    ]
    text_lower = text.lower()
    return any(re.search(p, text_lower) for p in patterns)


# ─── Parser de questões ───────────────────────────────────────────────────────

# Padrão para letra de alternativa: a) b) c) d) e) etc. (qualquer letra minúscula)
OPTION_LINE_PATTERN = re.compile(
    r"^([a-z])\)\s*(.+)$",
    re.IGNORECASE
)

# Padrão para alternativas inline: a) X  b) Y  c) Z
OPTION_INLINE_PATTERN = re.compile(
    r"([a-z])\)\s*(.*?)(?=\s+[a-z]\)\s|$)",
    re.IGNORECASE
)

# Padrão de questão: **1.** texto ou 1. texto
QUESTION_PATTERN = re.compile(
    r"^\*{0,2}(\d+)\.\*{0,2}\s*(.+?)(?:\*{0,2})?$"
)

# Padrão de gabarito: 1. c) texto → explicação
ANSWER_PATTERN = re.compile(
    r"^(\d+)\.\s*\**([a-z])\)\**\s*.*?(?:→\s*(.*))?$",
    re.IGNORECASE
)

# Padrão de seção: ## Bloco 1 — Título
SECTION_PATTERN = re.compile(r"^##\s+(.+)$")
ANSWER_SECTION_PATTERN = re.compile(r"^#\s+gabarito\b", re.IGNORECASE)


def parse_questions_from_text(text: str) -> list[dict]:
    """
    Extrai questões de um texto estruturado (qualquer formato aceito pelo app).

    Suporta:
    - Alternativas em linhas separadas: `a) texto`
    - Alternativas inline: `a) X  b) Y  c) Z`
    - Qualquer número de alternativas (2 a N)
    - Seções de contexto (## Bloco)
    - Gabarito embutido (# Gabarito)

    Returns:
        list[dict]: [{id, section, context, question, options, answer, explanation}]
        Se não há gabarito, answer=None e explanation=''.
    """
    questions: dict[int, dict] = {}
    answers: dict[int, dict] = {}
    section = "Geral"
    section_context: list[str] = []
    section_has_question = False
    in_answer_key = False

    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Seção
        section_match = SECTION_PATTERN.match(stripped)
        if section_match:
            section = re.sub(
                r"^Bloco\s+\d+\s*[—\-]\s*", "", section_match.group(1), flags=re.IGNORECASE
            ).strip()
            section_context = []
            section_has_question = False
            i += 1
            continue

        # Início do gabarito
        if ANSWER_SECTION_PATTERN.match(stripped):
            in_answer_key = True
            i += 1
            continue

        # Processar gabarito
        if in_answer_key:
            answer_match = ANSWER_PATTERN.match(stripped)
            if answer_match:
                qnum = int(answer_match.group(1))
                answers[qnum] = {
                    "answer": ord(answer_match.group(2).lower()) - ord("a"),
                    "explanation": (answer_match.group(3) or "").strip(),
                }
            i += 1
            continue

        # Questão: **1.** ou 1. texto
        q_match = QUESTION_PATTERN.match(stripped)
        if q_match:
            qnum = int(q_match.group(1))
            question_text = q_match.group(2).replace("**", "").strip()

            # Coletar alternativas das próximas linhas
            options = []
            # Primeiro verificar se as alternativas estão na mesma linha (inline)
            inline = OPTION_INLINE_PATTERN.findall(stripped)
            # Verifica se o inline veio junto com o texto da questão
            # (ex: "**1.** 4, 9, 19... a) 149  b) 159")
            # Se a própria linha de questão contém alternativas, pega-as
            remaining_text = question_text
            inline_in_question = OPTION_INLINE_PATTERN.findall(remaining_text)
            if inline_in_question and len(inline_in_question) >= 2:
                # Alternativas estão na linha da questão — remover do texto
                question_text = OPTION_INLINE_PATTERN.sub("", question_text).strip().rstrip("?").strip() + "?"
                options = [v.strip() for _, v in inline_in_question if v.strip()]
            else:
                # Tentar próxima linha como inline ou múltiplas linhas
                j = i + 1
                while j < len(lines):
                    next_stripped = lines[j].strip()
                    if not next_stripped:
                        j += 1
                        continue
                    # Linha é inteiramente de alternativas inline?
                    inline_opts = OPTION_INLINE_PATTERN.findall(next_stripped)
                    if inline_opts and len(inline_opts) >= 2:
                        options = [v.strip() for _, v in inline_opts if v.strip()]
                        i = j  # avança para essa linha
                        break
                    # Linha começa com uma alternativa (ex: "a) texto")
                    opt_match = OPTION_LINE_PATTERN.match(next_stripped)
                    if opt_match:
                        options.append(opt_match.group(2).strip())
                        i = j
                        j += 1
                        continue
                    # Linha é nova questão ou seção — parar
                    if QUESTION_PATTERN.match(next_stripped) or SECTION_PATTERN.match(next_stripped):
                        break
                    j += 1

            questions[qnum] = {
                "id": qnum,
                "section": section,
                "context": " ".join(section_context),
                "question": question_text,
                "options": options,
                "answer": None,
                "explanation": "",
            }
            section_has_question = True
            i += 1
            continue

        # Alternativas soltas (quando não capturadas acima)
        if questions and not in_answer_key:
            opt_match = OPTION_LINE_PATTERN.match(stripped)
            if opt_match:
                last_q = max(questions)
                questions[last_q]["options"].append(opt_match.group(2).strip())
                i += 1
                continue

            # Alternativas inline sozinhas na linha
            inline_opts = OPTION_INLINE_PATTERN.findall(stripped)
            if inline_opts and len(inline_opts) >= 2 and not QUESTION_PATTERN.match(stripped):
                last_q = max(questions)
                if not questions[last_q]["options"]:
                    questions[last_q]["options"] = [v.strip() for _, v in inline_opts if v.strip()]
                    i += 1
                    continue

        # Guardar contexto antes das questões
        if not section_has_question and stripped and stripped != "---":
            section_context.append(stripped)

        i += 1

    # Consolidar questões com respostas
    parsed = []
    for qnum in sorted(questions):
        q = questions[qnum]
        ans = answers.get(qnum)
        if ans:
            q["answer"] = ans["answer"]
            q["explanation"] = ans["explanation"]
        parsed.append(q)

    return parsed


def validate_questions(questions: list[dict]) -> tuple[bool, str]:
    """
    Valida que todas as questões têm pelo menos 2 alternativas.

    Returns:
        (True, "OK") ou (False, mensagem de erro)
    """
    if not questions:
        return False, "Nenhuma questão encontrada no arquivo"

    for q in questions:
        if len(q.get("options", [])) < 2:
            return False, f"Questão {q['id']} tem menos de 2 alternativas"

    return True, "OK"
