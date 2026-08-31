"""
Controllers - Padrão Spring @RestController
Camada de rotas HTTP
"""
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
import json

from api.utils.config import WEB_DIR
from api.services.quiz_service import QuizService, MarkdownService
from api.repositories.quiz_repository import QuizRepository
from api.models.dtos import SubmitAnswersDTO
from api.exceptions.quiz_exceptions import (
    QuizAPIException,
    InvalidAnswersFormat,
    InvalidJSONError,
    RouteNotFoundError,
)


class QuizController:
    """Controller para rotas de quiz"""

    def __init__(self):
        self.repository = QuizRepository()
        self.service = QuizService(self.repository)
        self.markdown_service = MarkdownService(self.repository)

    def get_quizzes(self) -> dict:
        """GET /api/quizzes - Lista todos os quizzes"""
        quizzes = self.service.get_all_quizzes()
        return {
            "status": "success",
            "data": {"quizzes": quizzes}
        }

    def get_quiz(self, source_name: str = None) -> dict:
        """GET /api/quiz - Carrega um quiz"""
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

    def submit_answers(self, payload: dict) -> dict:
        """POST /api/quiz/submit - Corrige respostas"""
        # Validar formato
        if "answers" not in payload:
            raise InvalidAnswersFormat()

        answers = payload.get("answers")
        if not isinstance(answers, dict):
            raise InvalidAnswersFormat()

        source_name = payload.get("source")

        # Corrigir
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
    """Controller para upload de arquivos (futuro n8n)"""

    def __init__(self):
        self.markdown_service = MarkdownService()

    def upload_file(self, filename: str, content: str) -> dict:
        """POST /api/upload - Upload de novo quiz"""
        # Validar conteúdo
        is_valid, error_msg = self.markdown_service.validate_markdown(content)
        if not is_valid:
            raise QuizAPIException(f"Markdown inválido: {error_msg}", 400)

        # Salvar
        path = self.markdown_service.save_quiz_from_markdown(filename, content)

        return {
            "status": "success",
            "data": {
                "filename": path.name,
                "message": f"Quiz '{filename}' criado com sucesso!"
            }
        }
