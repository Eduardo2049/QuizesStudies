"""
Importação dos simulados do convidado para a conta.

O convidado guarda os simulados só no navegador (sessionStorage). Quando ele cria
a conta ou entra, o navegador envia esses simulados para cá e eles passam a ser
simulados privados da conta. Como o conteúdo vem do cliente, tudo é revalidado
e limitado aqui: nada do JSON recebido é confiado sem checagem.
"""
from __future__ import annotations

import re

from api.exceptions.quiz_exceptions import QuizAPIException
from api.repositories.quiz_repository import QuizRepository

MAX_IMPORT_QUIZZES = 20
MAX_QUESTIONS_PER_QUIZ = 100
MAX_OPTIONS = 10
MAX_TEXT_CHARS = 5000
MAX_OPTION_CHARS = 1000
MAX_LABEL_CHARS = 120


def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text[:100] or "simulado"


def _clean_text(value, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()[:limit]


def sanitize_imported_quiz(raw) -> dict | None:
    """Valida um simulado vindo do navegador. Devolve None se não der para aproveitá-lo."""
    if not isinstance(raw, dict):
        return None
    label = _clean_text(raw.get("label") or raw.get("name"), MAX_LABEL_CHARS) or "Simulado importado"
    raw_questions = raw.get("questions")
    if not isinstance(raw_questions, list) or not raw_questions:
        return None

    questions = []
    for item in raw_questions[:MAX_QUESTIONS_PER_QUIZ]:
        if not isinstance(item, dict):
            continue
        text = _clean_text(item.get("question"), MAX_TEXT_CHARS)
        options_raw = item.get("options")
        if not text or not isinstance(options_raw, list):
            continue
        options = [_clean_text(o, MAX_OPTION_CHARS) for o in options_raw[:MAX_OPTIONS]]
        options = [o for o in options if o]
        if len(options) < 2:
            continue
        answer = item.get("answer")
        if isinstance(answer, bool) or not isinstance(answer, int) or not 0 <= answer < len(options):
            continue  # sem gabarito válido não dá para corrigir
        questions.append({
            "question_number": len(questions) + 1,
            "section": _clean_text(item.get("section"), 255) or "Geral",
            "context": _clean_text(item.get("context"), MAX_TEXT_CHARS),
            "question": text,
            "options": options,
            "answer": answer,
            "explanation": _clean_text(item.get("explanation"), MAX_TEXT_CHARS),
        })

    if not questions:
        return None
    return {"label": label, "questions": questions, "ai_generated": raw.get("ai_generated") is True}


class QuizImportService:
    def __init__(self, repository: QuizRepository | None = None):
        self.repo = repository or QuizRepository()

    def import_for_user(self, user_id: int, quizzes) -> dict:
        if not user_id:
            raise QuizAPIException("Autenticação necessária", 401)
        if not isinstance(quizzes, list) or not quizzes:
            raise QuizAPIException("Nenhum simulado para importar", 400)
        if len(quizzes) > MAX_IMPORT_QUIZZES:
            raise QuizAPIException(f"Envie no máximo {MAX_IMPORT_QUIZZES} simulados por vez", 400)

        imported, skipped = [], 0
        for raw in quizzes:
            quiz = sanitize_imported_quiz(raw)
            if not quiz:
                skipped += 1
                continue
            base = _slugify(quiz["label"])
            name, counter = base, 1
            while self.repo.name_exists(name):
                name = f"{base}-{counter}"
                counter += 1
            saved = self.repo.save_quiz(
                name=name,
                label=quiz["label"],
                questions=quiz["questions"],
                original_filename=None,
                file_type="local",
                ai_generated=quiz["ai_generated"],
                created_by=user_id,
                is_public=False,
            )
            imported.append({"name": saved["name"], "label": saved["label"]})

        return {"imported": len(imported), "skipped": skipped, "quizzes": imported}
