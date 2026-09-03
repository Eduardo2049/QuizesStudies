"""
Parser de Markdown — mantido para compatibilidade com imports existentes.

Para novos uploads, use api.utils.file_parser.parse_questions_from_text,
que suporta TXT, PDF e DOCX além de Markdown.
"""
from api.utils.file_parser import parse_questions_from_text as _parse


def load_questions_from_markdown(path) -> list[dict]:
    """
    Carrega questões de um arquivo Markdown no disco.

    Args:
        path: pathlib.Path para o arquivo

    Returns:
        list[dict] com {id, section, context, question, options, answer, explanation}

    Raises:
        ValueError: se nenhuma questão for encontrada
    """
    text = path.read_text(encoding="utf-8")
    questions = _parse(text)
    if not questions:
        raise ValueError(f"Nenhuma questão encontrada em {path}")
    return questions
