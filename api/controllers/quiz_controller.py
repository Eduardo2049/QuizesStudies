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
    def get_quizzes(self) -> dict:
        """GET /api/quizzes - Lista todos os quizzes disponíveis"""
        quizzes = self.service.get_all_quizzes()
        return {
            "status": "success",
            "data": {"quizzes": quizzes}
        }

    @timing_decorator
    @error_handler_decorator
    def get_quiz(self, source_name: str = None) -> dict:
        """GET /api/quiz - Carrega um quiz com questões públicas"""
        quiz_dto = self.service.get_quiz(source_name)
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
    def submit_answers(self, payload: dict) -> dict:
        """POST /api/quiz/submit - Corrige respostas e calcula score"""
        if not isinstance(payload, dict) or "answers" not in payload:
            raise InvalidAnswersFormat()

        answers = payload.get("answers")
        if not isinstance(answers, dict):
            raise InvalidAnswersFormat()

        source_name = payload.get("source")
        result_dto = self.service.submit_answers(answers, source_name)

        return {
            "status": "success",
            "data": {
                "score": result_dto.score,
                "total": result_dto.total,
                "percentage": result_dto.percentage,
                "results": result_dto.results
            }
        }


class UploadController:
    """Controller para upload de arquivos (TXT, PDF, DOCX)"""

    def __init__(self, repository: QuizRepository = None):
        self.upload_service = UploadService(repository or QuizRepository())

    @timing_decorator
    @error_handler_decorator
    def upload_file(self, filename: str, content: bytes, file_type: str) -> dict:
        """POST /api/upload - Processa arquivo e cria quiz no banco"""
        result = self.upload_service.process_upload(filename, content, file_type)
        return {
            "status": "success",
            "data": result,
        }
