"""
Controllers - Padrão Spring @RestController
Camada de rotas e processamento HTTP
"""
from api.services.quiz_service import QuizService
from api.services.upload_service import UploadService
from api.repositories.quiz_repository import QuizRepository
from api.middleware.http_middleware import timing_decorator, error_handler_decorator
from api.exceptions.quiz_exceptions import (
    QuizAPIException,
    InvalidAnswersFormat,
)


class QuizController:
    """Controller para rotas de quiz"""

    def __init__(self, repository: QuizRepository = None):
        self.repository = repository or QuizRepository()
        self.service = QuizService(self.repository)

    @timing_decorator
    @error_handler_decorator
    def get_quizzes(self, user_id: int = None) -> dict:
        """GET /api/quizzes - Lista todos os quizzes disponíveis"""
        quizzes = self.service.get_all_quizzes(user_id)
        return {
            "status": "success",
            "data": {"quizzes": quizzes}
        }

    @timing_decorator
    @error_handler_decorator
    def get_quiz(self, source_name: str = None, user_id: int = None) -> dict:
        """GET /api/quiz - Carrega um quiz com questões públicas"""
        quiz_dto = self.service.get_quiz(source_name, user_id)
        return {
            "status": "success",
            "data": {
                "title": quiz_dto.title,
                "source": quiz_dto.source,
                "questions": [
                    {
                        "id": q.id,
                        "section": q.section,
                        "question": q.question,
                        "options": q.options,
                        "context": q.context,
                    }
                    for q in quiz_dto.questions
                ]
            }
        }

    @timing_decorator
    @error_handler_decorator
    def submit_answers(self, payload: dict, user_id: int = None) -> dict:
        """POST /api/quiz/submit - Corrige respostas e calcula score"""
        if not isinstance(payload, dict) or "answers" not in payload:
            raise InvalidAnswersFormat()

        answers = payload.get("answers")
        if not isinstance(answers, dict):
            raise InvalidAnswersFormat()

        source_name = payload.get("source")
        result_dto = self.service.submit_answers(answers, source_name, user_id)

        return {
            "status": "success",
            "data": {
                "score": result_dto.score,
                "total": result_dto.total,
                "percentage": result_dto.percentage,
                "results": result_dto.results
            }
        }

    @timing_decorator
    @error_handler_decorator
    def generate_quiz_by_topic(
        self,
        topic: str,
        num_questions: int = 5,
        difficulty: str = "Médio",
        context: str = "",
        user_id: int = None,
        is_public: bool = False,
        persist: bool = True,
    ) -> dict:
        """Gera quiz por tema utilizando IA (OpenRouter)"""
        from api.services.ai_service import generate_quiz_by_topic, AIServiceError
        from api.services.upload_service import _slugify

        try:
            generated = generate_quiz_by_topic(
                topic=topic,
                num_questions=num_questions,
                difficulty=difficulty,
                context=context,
            )
        except AIServiceError as e:
            raise QuizAPIException(str(e), 422)

        title = generated["title"]
        topic_slug = _slugify(topic)
        base_name = f"quiz-{topic_slug}" if topic_slug else "quiz-ia"
        name = base_name
        questions = generated["questions"]

        if not persist or not user_id:
            return {
                "status": "success",
                "data": {
                    "quiz_id": None,
                    "name": name,
                    "label": title,
                    "question_count": len(questions),
                    "ai_generated": True,
                    "local_only": True,
                    "questions": questions,
                    "message": f"Quiz '{title}' gerado com sucesso por IA ({len(questions)} questões)!",
                }
            }

        counter = 1
        while self.repository.name_exists(name):
            name = f"{base_name}-{counter}"
            counter += 1

        for i, q in enumerate(questions, start=1):
            q["question_number"] = q.get("id", i)

        quiz = self.repository.save_quiz(
            name=name,
            label=title,
            questions=questions,
            original_filename=f"{topic_slug}.ai",
            file_type="ai",
            ai_generated=True,
            created_by=user_id,
            is_public=is_public,
        )

        return {
            "status": "success",
            "data": {
                "quiz_id": quiz["id"],
                "name": quiz["name"],
                "label": quiz["label"],
                "question_count": len(questions),
                "ai_generated": True,
                "local_only": False,
                "questions": [
                    {
                        "id": q["question_number"],
                        "section": q["section"],
                        "question": q["question"],
                        "options": q["options"],
                        "context": q["context"],
                    }
                    for q in questions
                ],
                "message": f"Quiz '{title}' criado e salvo com {len(questions)} questões!",
            }
        }


class UploadController:
    """Controller para upload de arquivos (TXT, PDF, DOCX)"""

    def __init__(self, repository: QuizRepository = None):
        self.upload_service = UploadService(repository or QuizRepository())

    @timing_decorator
    @error_handler_decorator
    def upload_file(
        self,
        filename: str,
        content: bytes,
        file_type: str,
        created_by: int,
        is_public: bool,
        persist: bool = True,
    ) -> dict:
        """POST /api/upload - Processa arquivo e cria quiz no banco"""
        result = self.upload_service.process_upload(
            filename, content, file_type, created_by, is_public, persist
        )
        return {
            "status": "success",
            "data": result,
        }
