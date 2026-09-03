"""Lógica de correção de quizzes"""


def grade_answers(answers: dict, questions: list[dict]) -> dict:
    """
    Corrige as respostas e retorna o score detalhado.

    Args:
        answers: {str(question_id) | int: option_index}
        questions: lista com {id, question, answer, explanation, options}

    Returns:
        {score, total, percentage, results}
    """
    if not isinstance(answers, dict):
        raise ValueError("'answers' deve ser um dicionário")

    score = 0
    results = []

    for q in questions:
        selected = answers.get(str(q["id"]), answers.get(q["id"]))
        is_correct = selected == q["answer"]
        if is_correct:
            score += 1
        results.append({
            "id": q["id"],
            "question": q["question"],
            "selected": selected,
            "correct": q["answer"],
            "isCorrect": is_correct,
            "explanation": q["explanation"],
        })

    total = len(questions)
    return {
        "score": score,
        "total": total,
        "percentage": round(score / total * 100) if total else 0,
        "results": results,
    }
