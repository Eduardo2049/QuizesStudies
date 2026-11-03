"""
Parser unificado para extração de texto de diferentes formatos.
Suporta: TXT, PDF, DOCX.

O parser de questões aceita alternativas de 'a)' até qualquer letra,
sem limite fixo (2 a N alternativas por questão).
"""
import re
import io
import zipfile
from typing import Optional

MAX_PDF_PAGES = 100
MAX_GUEST_PDF_PAGES = 20
MAX_DOCX_PARAGRAPHS = 10_000
MAX_GUEST_DOCX_PARAGRAPHS = 500
MAX_EXTRACTED_CHARS = 1_000_000
MAX_GUEST_EXTRACTED_CHARS = 250_000
MAX_DOCX_UNCOMPRESSED_BYTES = 30 * 1024 * 1024  # 30 MB
MAX_GUEST_DOCX_UNCOMPRESSED_BYTES = 5 * 1024 * 1024  # 5 MB
MAX_DOCX_COMPRESSION_RATIO = 100
MAX_DOCX_ENTRIES = 1_000
MAX_GUEST_DOCX_ENTRIES = 200
MAX_LINE_PARSE_CHARS = 2_000


# ─── Extração de texto bruto por formato ─────────────────────────────────────

def parse_txt(content: bytes, encoding: str = "utf-8", is_guest: bool = False) -> str:
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


def parse_pdf(content: bytes, is_guest: bool = False) -> str:
    """Extrai texto de arquivo PDF usando pdfplumber com limites diferenciados para convidados."""
    try:
        import pdfplumber
    except ImportError:
        raise ImportError("pdfplumber não instalado. Execute: pip install pdfplumber")

    max_pages = MAX_GUEST_PDF_PAGES if is_guest else MAX_PDF_PAGES
    max_chars = MAX_GUEST_EXTRACTED_CHARS if is_guest else MAX_EXTRACTED_CHARS

    text_parts = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            if page_number > max_pages:
                raise ValueError(
                    f"PDF excede o limite de {max_pages} páginas"
                    + (" para convidados. Faça login para enviar até 100 páginas." if is_guest else "")
                )
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
                if sum(len(part) for part in text_parts) > max_chars:
                    raise ValueError("Texto extraído excede o limite permitido")
    return "\n".join(text_parts)


def _validate_docx_zip(content: bytes, is_guest: bool = False) -> None:
    """Verifica proteção contra ZIP Bomb e integridade em arquivos DOCX."""
    max_entries = MAX_GUEST_DOCX_ENTRIES if is_guest else MAX_DOCX_ENTRIES
    max_bytes = MAX_GUEST_DOCX_UNCOMPRESSED_BYTES if is_guest else MAX_DOCX_UNCOMPRESSED_BYTES

    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            infolist = zf.infolist()
            if len(infolist) > max_entries:
                raise ValueError(f"DOCX contém muitas entradas internas ({len(infolist)}).")
            total_uncompressed = 0
            total_compressed = 0
            for info in infolist:
                total_uncompressed += info.file_size
                total_compressed += info.compress_size
                if info.compress_size > 0 and (info.file_size / info.compress_size) > MAX_DOCX_COMPRESSION_RATIO:
                    raise ValueError("Arquivo DOCX suspeito de Zip Bomb (razão de compressão individual excessiva).")
            if total_uncompressed > max_bytes:
                mb_limit = max_bytes // (1024 * 1024)
                raise ValueError(
                    f"DOCX descompactado excede o limite de tamanho permitido ({mb_limit} MB)"
                    + (" para convidados. Faça login para enviar até 30 MB." if is_guest else "")
                )
            if total_compressed > 0 and (total_uncompressed / total_compressed) > MAX_DOCX_COMPRESSION_RATIO:
                raise ValueError("Arquivo DOCX suspeito de Zip Bomb (razão de compressão total excessiva).")
    except zipfile.BadZipFile:
        raise ValueError("Arquivo DOCX inválido ou corrompido.")


def parse_docx(content: bytes, is_guest: bool = False) -> str:
    """Extrai texto de arquivo DOCX usando python-docx com proteção contra Zip Bomb e limites para convidados."""
    _validate_docx_zip(content, is_guest=is_guest)
    try:
        from docx import Document
    except ImportError:
        raise ImportError("python-docx não instalado. Execute: pip install python-docx")

    max_paragraphs = MAX_GUEST_DOCX_PARAGRAPHS if is_guest else MAX_DOCX_PARAGRAPHS

    doc = Document(io.BytesIO(content))
    if len(doc.paragraphs) > max_paragraphs:
        raise ValueError(
            f"DOCX excede o limite de {max_paragraphs} parágrafos"
            + (" para convidados. Faça login para documentos maiores." if is_guest else "")
        )
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n".join(paragraphs)


def extract_text(content: bytes, file_type: str, is_guest: bool = False) -> str:
    """
    Dispatcher principal: extrai texto baseado no tipo do arquivo.

    Args:
        content: Bytes do arquivo
        file_type: 'txt', 'pdf' ou 'docx'
        is_guest: Se o upload foi realizado por visitante não autenticado

    Returns:
        Texto extraído

    Raises:
        ValueError: Se file_type não suportado ou limites excedidos
    """
    file_type = file_type.lower().lstrip(".")
    parsers = {
        "txt": lambda c: parse_txt(c, is_guest=is_guest),
        "pdf": lambda c: parse_pdf(c, is_guest=is_guest),
        "docx": lambda c: parse_docx(c, is_guest=is_guest),
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
# Usa lookbehind (?<=\s) em vez de \s+ para evitar comportamento quadrático/ReDoS
INLINE_MARKER_PATTERN = re.compile(
    r"(?:^|(?<=\s))(?:\(([a-z])\)|\[([a-z])\]|([a-z])\*{0,2}\s*[\.\-\)\:\—\–])\s*",
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
    r"^(?:gabarito|resposta(?:\s+correta)?|resp|alternativa\s+correta|correct\s+answer|answer)\b",
    re.IGNORECASE
)

# Letra da resposta: "B", "(B)", "[B]", "Letra B", "alternativa B". A letra não pode ser
# seguida de outra letra, para "Letra B" não virar a letra "L" e "Brasília" não virar "B".
_ANSWER_LETTER = (
    r"(?:(?:letra|alternativa|op[çc][ãa]o|option)\s+)?\**"
    r"(?:\(([a-z])\)|\[([a-z])\]|([a-z])(?![^\W\d_]))\**"
)


def _parse_inline_answer(text: str) -> tuple[Optional[int], str]:
    """Extrai (answer_index, explanation) de uma linha de gabarito inline (ex: 'Gabarito: B')."""
    m = re.match(
        r"^(?:gabarito|resposta(?:\s+correta)?|resp|alternativa\s+correta|correct\s+answer|answer)"
        r"[\s\:\—\-=]+" + _ANSWER_LETTER + r"[\.\)\:\—\-]?",
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
        r"^" + _ANSWER_LETTER + r"[\.\)\:\—\-]?",
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

# Cabeçalho de gabarito com complemento ("GABARITO OFICIAL", "Gabarito da prova",
# "Respostas corretas") ou já com os pares na mesma linha ("Gabarito: 1-B, 2-C").
ANSWER_HEADER_PREFIX = re.compile(
    r"^(?:#+\s*)?\**\s*(gabarito|respostas?(?:\s+corretas?)?|chave\s+de\s+respostas?|answer\s*key|answers)\b\**(.*)$",
    re.IGNORECASE
)
_HEADER_QUALIFIER = re.compile(
    r"^(?:(?:oficial|definitivo|preliminar|comentado|final|corretas?|d[aoe]s?|prova|simulado|"
    r"avalia[çc][ãa]o|teste|exame|quest[õo]es|lista|exerc[íi]cios?|caderno|vers[ãa]o)\b\.?\s*|\d{1,3}\s*)*$",
    re.IGNORECASE
)
_SINGLE_ANSWER_REST = re.compile(r"^" + _ANSWER_LETTER + r"(?:[\.\)\:\—\-]|\s|$)", re.IGNORECASE)

# Par número→letra numa linha de gabarito: "1-B", "01 - B", "2) c", "3. (D)", "Questão 4: E"
ANSWER_PAIR_PATTERN = re.compile(
    r"(?<!\w)(?:Quest[ãa]o\s*|Q\.?\s*)?(\d{1,4})\s*(?:[\.\-\)\:\—\–=→]\s*)?"
    r"(?:(?:letra|alternativa)\s+)?[\(\[]?([a-z])[\)\]]?(?![^\W\d_])",
    re.IGNORECASE
)
_NUMBERS_ONLY = re.compile(r"^\d{1,4}(?:[\s|;,]+\d{1,4})+$")
_LETTERS_ONLY = re.compile(r"^[a-z](?:[\s|;,]+[a-z])+$", re.IGNORECASE)

# "QUESTÃO 01" sozinha na linha (comum em PDFs de provas): o enunciado vem na linha seguinte
QUESTION_HEADER_ONLY = re.compile(
    r"^\*{0,2}(?:Quest[ãa]o|Pergunta|Item)\s*(?:n[º°o]\.?\s*)?(\d{1,4})\s*[\.\-\)\:\—\–]?\*{0,2}\s*$",
    re.IGNORECASE
)

# Alternativa marcada como correta no próprio arquivo: "*b) texto", "✓ b) texto",
# "b) texto (correta)", "b) texto ✔", "b) texto *"
_LEADING_CORRECT = re.compile(r"^(?:\*(?!\*)|[✓✔☑→➔]|\[x\]|\(x\))\s*", re.IGNORECASE)
_TRAILING_CORRECT = re.compile(
    r"\s*(?:\((?:correta|certa|correto|certo|correct|resposta)\)|\[(?:correta|correct)\]|[✓✔☑]|(?<=\S)\s\*)\s*$",
    re.IGNORECASE
)


def _mark_correct(marked: dict[int, int], ambiguous: set[int], qnum: int, idx: int) -> None:
    """Guarda a alternativa marcada; duas marcas na mesma questão (ex.: lista "* a)", "* b)")
    não valem como gabarito."""
    if qnum in marked and marked[qnum] != idx:
        ambiguous.add(qnum)
    else:
        marked[qnum] = idx


def _strip_trailing_marker(text: str) -> tuple[str, bool]:
    cleaned = _TRAILING_CORRECT.sub("", text)
    return cleaned.strip(), cleaned != text


def _match_option_line(stripped: str) -> tuple[str, bool] | None:
    """Alternativa em linha própria → (texto, marcada_como_correta) ou None."""
    lead = _LEADING_CORRECT.match(stripped)
    candidate = stripped[lead.end():] if lead else stripped
    m = OPTION_LINE_PATTERN.match(candidate)
    if not m:
        return None
    text, trailing = _strip_trailing_marker(m.group(4).strip())
    return text, bool(lead) or trailing


def _inline_options_with_marks(text: str) -> tuple[list[str], int | None]:
    """Alternativas na mesma linha + índice da marcada como correta (se houver)."""
    options = _extract_inline_options(text)
    marked = None
    cleaned = []
    for idx, opt in enumerate(options):
        opt_text, is_marked = _strip_trailing_marker(opt)
        if is_marked and marked is None:
            marked = idx
        cleaned.append(opt_text)
    return cleaned, marked


def _answer_header(stripped: str) -> tuple[bool, list[tuple[int, int]]]:
    """(é início de seção de gabarito, pares já presentes na mesma linha)."""
    if ANSWER_SECTION_PATTERN.match(stripped):
        return True, []
    m = ANSWER_HEADER_PREFIX.match(stripped)
    if not m:
        return False, []
    rest = m.group(2).strip().lstrip(":-—–*").strip()
    pairs = _parse_answer_pairs(rest)
    if pairs:
        return True, pairs
    if not rest:
        return True, []
    if len(rest) <= 40 and _HEADER_QUALIFIER.match(rest) and not _SINGLE_ANSWER_REST.match(rest):
        return True, []
    return False, []


def _parse_answer_pairs(text: str) -> list[tuple[int, int]]:
    """Todos os pares número→índice da letra de uma linha ("1-B 2-C 3-A")."""
    return [
        (int(num), ord(letter.lower()) - ord("a"))
        for num, letter in ANSWER_PAIR_PATTERN.findall(text)
    ]


def _merge_question_headers(lines: list[str]) -> list[str]:
    """Junta "QUESTÃO 01" sozinha na linha com a linha seguinte do enunciado."""
    merged: list[str] = []
    i = 0
    while i < len(lines):
        m = QUESTION_HEADER_ONLY.match(lines[i].strip())
        if m:
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines) and not OPTION_LINE_PATTERN.match(lines[j].strip()):
                merged.append(f"Questão {m.group(1)}: {lines[j].strip()}")
                i = j + 1
                continue
        merged.append(lines[i])
        i += 1
    return merged


def _extract_qnum_and_text(match: re.Match) -> tuple[int, str]:
    """Extrai número da questão e texto limpo do match de QUESTION_PATTERN."""
    g1, g2, g3, text = match.groups()
    raw_num = g1 or g2 or g3
    qnum = int(raw_num) if raw_num else 1
    clean_text = text.replace("**", "").strip()
    return qnum, clean_text


def _extract_inline_options(text: str) -> list[str]:
    """Extrai alternativas em linha única se houver pelo menos 2 marcadores identificados."""
    if len(text) > MAX_LINE_PARSE_CHARS:
        text = text[:MAX_LINE_PARSE_CHARS]
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
    marked: dict[int, int] = {}
    ambiguous_marks: set[int] = set()
    pending_numbers: list[int] | None = None

    lines = _merge_question_headers(text.splitlines())
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if len(stripped) > MAX_LINE_PARSE_CHARS:
            stripped = stripped[:MAX_LINE_PARSE_CHARS]

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
        if not in_answer_key:
            is_header, header_pairs = _answer_header(stripped)
            if is_header:
                in_answer_key = True
                current_qnum = None
                for qnum, letter_idx in header_pairs:
                    answers[qnum] = {"answer": letter_idx, "explanation": ""}
                i += 1
                continue

        # Processar gabarito na seção de gabarito
        if in_answer_key:
            # Tabela: uma linha só com números e a seguinte só com letras
            if _NUMBERS_ONLY.match(stripped):
                pending_numbers = [int(n) for n in re.findall(r"\d{1,4}", stripped)]
                i += 1
                continue
            if pending_numbers and _LETTERS_ONLY.match(stripped):
                letters = re.findall(r"[a-z]", stripped, re.IGNORECASE)
                if len(letters) == len(pending_numbers):
                    for qnum, letter in zip(pending_numbers, letters):
                        answers[qnum] = {"answer": ord(letter.lower()) - ord("a"), "explanation": ""}
                pending_numbers = None
                i += 1
                continue
            pending_numbers = None

            pairs = _parse_answer_pairs(stripped)
            if len(pairs) >= 2:
                for qnum, letter_idx in pairs:
                    answers[qnum] = {"answer": letter_idx, "explanation": ""}
                i += 1
                continue

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
            inline_opts, inline_mark = _inline_options_with_marks(question_text)
            if inline_mark is not None:
                _mark_correct(marked, ambiguous_marks, qnum, inline_mark)
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
                        or _answer_header(next_stripped)[0]
                    ):
                        break

                    # Linha de gabarito inline
                    if INLINE_ANSWER_HEADER.match(next_stripped):
                        break

                    # Próxima linha é alternativa inline múltipla?
                    next_inline, next_mark = _inline_options_with_marks(next_stripped)
                    if next_inline:
                        options = next_inline
                        if next_mark is not None:
                            _mark_correct(marked, ambiguous_marks, qnum, next_mark)
                        i = j
                        break

                    # Próxima linha começa com alternativa individual (ex: a) ou A. ou [A])
                    opt = _match_option_line(next_stripped)
                    if opt:
                        opt_text, is_marked = opt
                        if is_marked:
                            _mark_correct(marked, ambiguous_marks, qnum, len(options))
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
            opt = _match_option_line(stripped)
            if opt:
                opt_text, is_marked = opt
                current_options = questions[current_qnum]["options"]
                if is_marked:
                    _mark_correct(marked, ambiguous_marks, current_qnum, len(current_options))
                current_options.append(opt_text)
                i += 1
                continue

            inline_opts, inline_mark = _inline_options_with_marks(stripped)
            if inline_opts and not questions[current_qnum]["options"]:
                questions[current_qnum]["options"] = inline_opts
                if inline_mark is not None:
                    _mark_correct(marked, ambiguous_marks, current_qnum, inline_mark)
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
        elif qnum in marked and qnum not in ambiguous_marks:
            q["answer"] = marked[qnum]
        # Letra fora das alternativas (ex.: gabarito "E" numa questão de 4 opções) não vale:
        # a questão fica sem gabarito em vez de virar um simulado com resposta impossível.
        if q["answer"] is not None and not (0 <= q["answer"] < len(q["options"])):
            q["answer"] = None
            q["explanation"] = ""
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
