"""Lógica de processamento e correção de quizzes"""


def public_questions(questions):
    """
    Remove respostas e explicações das questões (versão pública).
    
    Args:
        questions (list): Lista de questões com resposta
        
    Returns:
        list: Questões sem 'answer' e 'explanation'
    """
    return [
        {key: value for key, value in question.items() 
         if key not in ("answer", "explanation")}
        for question in questions
    ]


def grade_answers(answers, questions):
    """
    Corrige respostas e retorna score com detalhes.
    
    Args:
        answers (dict): Dicionário com {questao_id: indice_resposta}
        questions (list): Lista de questões com resposta correta
        
    Returns:
        dict: {score, total, percentage, results}
        
    Raises:
        ValueError: Se answers não é um dicionário
    """
    if not isinstance(answers, dict):
        raise ValueError(
            "answers deve ser um objeto com id da questao e indice da alternativa"
        )

    results = []
    score = 0
    
    for question in questions:
        # Aceita tanto string quanto int como chave
        selected = answers.get(str(question["id"]), answers.get(question["id"]))
        is_correct = selected == question["answer"]
        
        if is_correct:
            score += 1
            
        results.append({
            "id": question["id"],
            "question": question["question"],
            "selected": selected,
            "correct": question["answer"],
            "isCorrect": is_correct,
            "explanation": question["explanation"],
        })
    
    return {
        "score": score,
        "total": len(questions),
        "percentage": round(score / len(questions) * 100) if questions else 0,
        "results": results
    }
