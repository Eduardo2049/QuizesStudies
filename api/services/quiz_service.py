"""
Services - Padrão Spring @Service
Camada de lógica de negócio — opera sobre PostgreSQL
"""
from api.repositories.quiz_repository import QuizRepository
from api.models.dtos import QuizDTO, QuestionDTO, GradeResultDTO
from api.exceptions.quiz_exceptions import QuizNotFound
from api.utils.quiz_logic import grade_answers


class QuizService:
    """Service para lógica de quizzes (leitura do banco)"""

    def __init__(self, repository: QuizRepository = None):
        self.repository = repository or QuizRepository()

    def get_all_quizzes(self, user_id: int = None) -> list[dict]:
        """
        Retorna lista de todos os quizzes disponíveis.

        Returns:
            list[dict]: [{name, label, file_type, ai_generated}]
        """
        sources = self.repository.find_all_sources(user_id)
        return [
            {
                "name": row["name"],
                "label": row["label"],
                "file_type": row.get("file_type", ""),
                "ai_generated": row.get("ai_generated", False),
            }
            for row in sources
        ]

    def get_quiz(self, source_name: str = None, user_id: int = None) -> QuizDTO:
        """
        Carrega um quiz com suas questões (sem respostas expostas ao cliente).

        Args:
            source_name: Campo `name` do quiz. Se None, usa o primeiro.

        Returns:
            QuizDTO com questões públicas (sem answer/explanation)

        Raises:
            QuizNotFound: Se quiz não encontrado
        """
        if source_name:
            quiz_row = self.repository.find_by_name(source_name, user_id)
        else:
            quiz_row = self.repository.find_default(user_id)

        questions_data = self.repository.find_questions(quiz_row["id"])

        question_dtos = [
            QuestionDTO(
                id=q["question_number"],
                section=q["section"],
                question=q["question"],
                options=q["options"],
                context=q.get("context", ""),
            )
            for q in questions_data
        ]

        return QuizDTO(
            title=quiz_row["label"],
            source=quiz_row["name"],
            questions=question_dtos,
        )

    def submit_answers(
        self,
        answers: dict,
        source_name: str = None,
        user_id: int = None,
    ) -> GradeResultDTO:
        """
        Corrige respostas e retorna score detalhado.

        Args:
            answers: {question_id_str: option_index}
            source_name: Campo `name` do quiz

        Returns:
            GradeResultDTO com score, total, percentage e results
        """
        if source_name:
            quiz_row = self.repository.find_by_name(source_name, user_id)
        else:
            quiz_row = self.repository.find_default(user_id)

        questions_data = self.repository.find_questions(quiz_row["id"])

        # Converter para formato esperado por grade_answers
        questions_for_grading = [
            {
                "id": q["question_number"],
                "question": q["question"],
                "answer": q["answer"],
                "explanation": q.get("explanation", ""),
                "options": q["options"],
            }
            for q in questions_data
        ]

        result = grade_answers(answers, questions_for_grading)

        return GradeResultDTO(
            score=result["score"],
            total=result["total"],
            percentage=result["percentage"],
            results=result["results"],
        )
