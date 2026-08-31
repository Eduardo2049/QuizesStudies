"""
Parser de Markdown - SIMPLIFICADO

NOTA: Lógica de busca de sources foi movida para:
  api/repositories/quiz_repository.py

Este arquivo agora contém APENAS a lógica de parsing de conteúdo Markdown.
"""
import re


def load_questions_from_markdown(path):
    """
    Carrega questões de um arquivo Markdown.
    
    Formato esperado:
    **1.** Pergunta aqui?
    a) Opção A
    b) Opção B
    c) Opção C
    d) Opção D
    
    **2.** Próxima pergunta?
    ...
    
    # Gabarito
    1. c) resposta → explicação
    2. a) resposta → explicação
    
    Args:
        path (Path): Caminho do arquivo Markdown
        
    Returns:
        list: Lista de questões com answer e explanation
        
    Raises:
        ValueError: Se questões estão sem alternativas ou gabarito
    """
    text = path.read_text(encoding="utf-8")
    questions = {}
    answers = {}
    section = "Geral"
    section_context = []
    section_has_question = False
    in_answer_key = False
    
    option_pattern = re.compile(r"([a-d])\)\s*(.*?)(?=\s+[a-d]\)\s*|$)")
    answer_pattern = re.compile(
        r"^(\d+)\.\s*\**([a-d])\)\**\s*.*?(?:→\s*(.*))?$", 
        re.IGNORECASE
    )

    for line in text.splitlines():
        # Detectar seções (## Bloco 1)
        heading = re.match(r"^##\s+(.+)$", line)
        if heading:
            section = re.sub(
                r"^Bloco\s+\d+\s*[—-]\s*", 
                "", 
                heading.group(1), 
                flags=re.IGNORECASE
            ).strip()
            section_context = []
            section_has_question = False
            continue

        # Detectar início do gabarito
        if re.match(r"^#\s+Gabarito\b", line, re.IGNORECASE):
            in_answer_key = True
            continue

        # Processar gabarito
        if in_answer_key:
            answer = answer_pattern.match(line.strip())
            if answer:
                answers[int(answer.group(1))] = {
                    "answer": ord(answer.group(2).lower()) - ord("a"),
                    "explanation": (answer.group(3) or "").strip(),
                }
            continue

        # Detectar questão (**1.** pergunta)
        question = re.match(
            r"^\*\*(\d+)\.(?:\*\*)?\s*(.+?)(?:\*\*)?$", 
            line.strip()
        )
        if question:
            questions[int(question.group(1))] = {
                "id": int(question.group(1)),
                "section": section,
                "question": question.group(2).replace("**", "").strip(),
                "options": [],
                "context": " ".join(section_context),
            }
            section_has_question = True
            continue

        # Processar alternativas (a) b) c) d))
        if questions:
            options = option_pattern.findall(line.strip())
            if options:
                questions[max(questions)]["options"].extend(
                    value.strip() for _, value in options
                )
                continue

        # Guardar contexto antes das questões
        if not section_has_question and line.strip() and line.strip() != "---":
            section_context.append(line.strip())

    # Validar e consolidar
    parsed = []
    for question_id in sorted(questions):
        question = questions[question_id]
        answer = answers.get(question_id)
        
        if not answer or len(question["options"]) < 2:
            raise ValueError(
                f"Questao {question_id} esta sem alternativas ou gabarito no Markdown"
            )
        
        question.update(answer)
        parsed.append(question)

    if not parsed:
        raise ValueError(f"Nenhuma questao encontrada em {path}")

    return parsed
