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
    """Extrai texto de arquivo TXT com suporte resiliente a UTF-8 (com/sem BOM), CP1252 e Latin-1."""
    encodings_to_try = [encoding, "utf-8-sig", "utf-8", "cp1252", "latin-1"]
    tried = set()
    for enc in encodings_to_try:
        if not enc or enc in tried:
            continue
        tried.add(enc)
        try:
            return content.decode(enc)
        except UnicodeDecodeError:
            continue
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
    Verifica se o texto contém seção de gabarito ou respostas inline.
    Aceita variações como 'Gabarito', 'GABARITO', 'Resposta', 'Answer Key'.
    """
    patterns = [
        r"(?:^|\n)\s*#*\s*gabarito\b",
        r"\bgabarito\s*:",
        r"\bresposta\s*correta\b",
        r"\bchave\s+de\s+respostas?\b",
        r"\banswer\s*key\b",
    ]
    text_lower = text.lower()
    return any(re.search(p, text_lower) for p in patterns)


# ─── Parser flexível de questões e alternativas ──────────────────────────────

# Padrão para marcador de alternativas (usado para detecção inline via finditer)
INLINE_MARKER_PATTERN = re.compile(
    r"(?:^|\s+)(?:\(([a-z])\)|\[([a-z])\]|([a-z])\*{0,2}\s*[\.\-\)\:\—\–])\s*",
    re.IGNORECASE
)

# Padrão flexível de questão:
# Aceita: 1. texto | **1.** texto | Questão 1: texto | Questao 02 - texto | (1) texto | [1] texto | Q1. texto
QUESTION_PATTERN = re.compile(
    r"^\*{0,2}(?:(?:Quest[ãa]o|Pergunta|Item|Q\.?)\s*(?:\*{0,2}\s*)?)?(?:\((\d{1,4})\)|\[(\d{1,4})\]|(\d{1,4})\*{0,2}\s*[\.\-\)\:\—\–])\*{0,2}\s*(.+)$",
    re.IGNORECASE
)

# Padrão de gabarito inline logo abaixo da questão ou alternativa:
# Ex: "Gabarito: B", "Resposta: A", "Resposta correta: C - explicação"
INLINE_ANSWER_HEADER = re.compile(
    r"^(?:gabarito|resposta(?:\s+correta)?|resp)\b",
    re.IGNORECASE
)


def _parse_inline_answer(text: str) -> tuple[Optional[int], str]:
    """Extrai (answer_index, explanation) de uma linha de gabarito inline (ex: 'Gabarito: B')."""
    m = re.match(
        r"^(?:gabarito|resposta(?:\s+correta)?|resp)[\s\:\—\-]+(?:\(([a-z])\)|\[([a-z])\]|\**([a-z])\**[\.\)\:\—\-]?)",
        text,
        re.IGNORECASE
    )
    if not m:
        return None, ""
    raw_letter = m.group(1) or m.group(2) or m.group(3)
    if not raw_letter:
        return None, ""
    letter_idx = ord(raw_letter.lower()) - ord("a")
    after = text[m.end():].strip()
    exp_match = re.search(r"^[—\-\:→]\s*(.+)$", after)
    explanation = exp_match.group(1).strip() if exp_match else after
    return letter_idx, explanation


def _parse_answer_line(text: str) -> tuple[Optional[int], Optional[int], str]:
    """Extrai (qnum, answer_index, explanation) de uma linha de gabarito na seção de respostas."""
    q_match = re.match(
        r"^(?:(?:Quest[ãa]o|Pergunta|Item|Q\.?)\s*)?(?:\((\d{1,4})\)|\[(\d{1,4})\]|(\d{1,4}))[\.\-\)\:\—\–\s]+",
        text,
        re.IGNORECASE
    )
    if not q_match:
        return None, None, ""

    raw_qnum = q_match.group(1) or q_match.group(2) or q_match.group(3)
    qnum = int(raw_qnum)
    rest = text[q_match.end():].strip()

    ans_match = re.match(
        r"^\**(?:\(([a-z])\)|\[([a-z])\]|([a-z]))\**[\.\)\:\—\-]?",
        rest,
        re.IGNORECASE
    )
    if not ans_match:
        return None, None, ""

    raw_letter = ans_match.group(1) or ans_match.group(2) or ans_match.group(3)
    letter_idx = ord(raw_letter.lower()) - ord("a")
    after_letter = rest[ans_match.end():].strip()

    exp_match = re.search(r"[—\-\:→]\s*(.+)$", after_letter)
    if exp_match:
        explanation = exp_match.group(1).strip()
    else:
        explanation = ""

    return qnum, letter_idx, explanation


# Padrão de seção: ## Bloco 1 — Título
SECTION_PATTERN = re.compile(r"^##\s+(.+)$")
ANSWER_SECTION_PATTERN = re.compile(
    r"^(?:#+\s*(?:gabarito|respostas?|chave\s+de\s+respostas?|answer\s*key)\b|(?:gabarito|respostas?|chave\s+de\s+respostas?|answer\s*key)\s*[:\-—]?\s*$)",
    re.IGNORECASE
)


# Padrão flexível para letra de alternativa individual em início de linha: a) A. (a) [a] a - A: etc.
OPTION_LINE_PATTERN = re.compile(
    r"^(?:\(([a-z])\)|\[([a-z])\]|([a-z])\*{0,2}\s*[\.\-\)\:\—\–])\s*(.+)$",
    re.IGNORECASE
)


def _extract_qnum_and_text(match: re.Match) -> tuple[int, str]:
    """Extrai número da questão e texto limpo do match de QUESTION_PATTERN."""
    g1, g2, g3, text = match.groups()
    raw_num = g1 or g2 or g3
    qnum = int(raw_num) if raw_num else 1
    clean_text = text.replace("**", "").strip()
    return qnum, clean_text


def _extract_inline_options(text: str) -> list[str]:
    """Extrai alternativas em linha única se houver pelo menos 2 marcadores identificados."""
    matches = list(INLINE_MARKER_PATTERN.finditer(text))
    if len(matches) < 2:
        return []

    options = []
    for idx, match in enumerate(matches):
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        opt_text = text[start:end].strip()
        if opt_text:
            options.append(opt_text)

    return options if len(options) >= 2 else []


def parse_questions_from_text(text: str) -> list[dict]:
    """
    Extrai questões de um texto estruturado (qualquer formato aceito pelo app).

    Suporta:
    - Múltiplos formatos de questão (1., Questão 1:, [1], (1), Q1., etc.)
    - Alternativas em linhas separadas: `a) texto`, `A. texto`, `(a) texto`, `[A] texto`
    - Alternativas inline: `a) X  b) Y  c) Z` ou `(A) X (B) Y`
    - Qualquer número de alternativas (2 a N)
    - Gabarito inline logo após a questão: `Gabarito: B` ou `Resposta: C`
    - Seções de contexto (## Bloco)
    - Gabarito embutido no final (# Gabarito, Chave de Respostas, etc.)

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
    current_qnum = None

    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        # Seção
        section_match = SECTION_PATTERN.match(stripped)
        if section_match:
            section = re.sub(
                r"^Bloco\s+\d+\s*[—\-]\s*", "", section_match.group(1), flags=re.IGNORECASE
            ).strip()
            section_context = []
            section_has_question = False
            current_qnum = None
            i += 1
            continue

        # Detectar gabarito inline (ex: "Gabarito: B", "Resposta: C")
        if current_qnum is not None and not in_answer_key and INLINE_ANSWER_HEADER.match(stripped):
            letter_idx, explanation = _parse_inline_answer(stripped)
            if letter_idx is not None:
                answers[current_qnum] = {
                    "answer": letter_idx,
                    "explanation": explanation,
                }
                i += 1
                continue

        # Início de seção de gabarito dedicada
        if ANSWER_SECTION_PATTERN.match(stripped):
            in_answer_key = True
            current_qnum = None
            i += 1
            continue

        # Processar gabarito na seção de gabarito
        if in_answer_key:
            qnum, letter_idx, explanation = _parse_answer_line(stripped)
            if qnum is not None and letter_idx is not None:
                answers[qnum] = {
                    "answer": letter_idx,
                    "explanation": explanation,
                }
            i += 1
            continue

        # Questão: 1. texto | Questão 1: texto | (1) texto, etc.
        q_match = QUESTION_PATTERN.match(stripped)
        if q_match:
            qnum, question_text = _extract_qnum_and_text(q_match)
            current_qnum = qnum

            # Coletar alternativas
            options = []
            # Verificar se as alternativas estão na própria linha da questão
            inline_opts = _extract_inline_options(question_text)
            if inline_opts:
                # Remove as alternativas do texto do enunciado a partir do primeiro marcador inline
                first_marker = next(INLINE_MARKER_PATTERN.finditer(question_text), None)
                if first_marker:
                    question_text = question_text[:first_marker.start()].strip().rstrip("?").strip() + "?"
                options = inline_opts
            else:
                # Verificar próximas linhas
                j = i + 1
                while j < len(lines):
                    next_stripped = lines[j].strip()
                    if not next_stripped:
                        j += 1
                        continue

                    # Nova questão ou nova seção -> interromper
                    if (
                        QUESTION_PATTERN.match(next_stripped)
                        or SECTION_PATTERN.match(next_stripped)
                        or ANSWER_SECTION_PATTERN.match(next_stripped)
                    ):
                        break

                    # Linha de gabarito inline
                    if INLINE_ANSWER_HEADER.match(next_stripped):
                        break

                    # Próxima linha é alternativa inline múltipla?
                    next_inline = _extract_inline_options(next_stripped)
                    if next_inline:
                        options = next_inline
                        i = j
                        break

                    # Próxima linha começa com alternativa individual (ex: a) ou A. ou [A])
                    opt_match = OPTION_LINE_PATTERN.match(next_stripped)
                    if opt_match:
                        opt_text = opt_match.group(4).strip()
                        options.append(opt_text)
                        i = j
                        j += 1
                        continue

                    # Linha complementar de texto do enunciado (caso de enunciado multilinhas)
                    if not options:
                        question_text += " " + next_stripped
                        i = j
                        j += 1
                        continue

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

        # Alternativas soltas posteriores
        if current_qnum is not None and not in_answer_key:
            opt_match = OPTION_LINE_PATTERN.match(stripped)
            if opt_match:
                questions[current_qnum]["options"].append(opt_match.group(4).strip())
                i += 1
                continue

            inline_opts = _extract_inline_options(stripped)
            if inline_opts and not questions[current_qnum]["options"]:
                questions[current_qnum]["options"] = inline_opts
                i += 1
                continue

        # Guardar contexto antes da primeira questão
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
