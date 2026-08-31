"""
Services - Padrão Spring @Service
Camada de lógica de negócio
"""
from pathlib import Path
from api.utils.markdown_parser import load_questions_from_markdown
from api.repositories.quiz_repository import QuizRepository
from api.models.dtos import QuizDTO, QuestionDTO, GradeResultDTO
from api.exceptions.quiz_exceptions import QuizNotFound
from api.utils.quiz_logic import public_questions, grade_answers


class QuizService:
    """Service para lógica de quizzes"""

    def __init__(self, repository: QuizRepository = None):
        self.repository = repository or QuizRepository()

    def get_all_quizzes(self) -> list[dict]:
        """
        Retorna lista de todos os quizzes disponíveis.
        
        Returns:
            list[dict]: Lista com nome e label de cada quiz
        """
        sources = self.repository.find_all_sources()
        return [
            {"name": path.name, "label": path.stem}
            for path in sources
        ]

    def get_quiz(self, source_name: str = None) -> QuizDTO:
        """
        Carrega um quiz com suas questões (sem respostas).
        
        Args:
            source_name (str, optional): Nome do arquivo. Se None, usa padrão.
            
        Returns:
            QuizDTO: Quiz com questões públicas
            
        Raises:
            QuizNotFound: Se quiz não encontrado
        """
        if source_name:
            source_path = self.repository.find_by_name(source_name)
        else:
            source_path = self.repository.find_default()

        # Carregar questões do Markdown
        questions_data = load_questions_from_markdown(source_path)

        # Converter para DTOs e remover respostas
        question_dtos = [
            QuestionDTO(
                id=q["id"],
                section=q["section"],
                question=q["question"],
                options=q["options"],
                context=q.get("context", "")
            )
            for q in questions_data
        ]

        return QuizDTO(
            title="Treino de raciocinio",
            source=source_path.name,
            questions=question_dtos
        )

    def submit_answers(self, answers: dict, source_name: str = None) -> GradeResultDTO:
        """
        Corrige respostas e retorna score.
        
        Args:
            answers (dict): {question_id: option_index}
            source_name (str, optional): Nome do quiz
            
        Returns:
            GradeResultDTO: Resultado da correção
            
        Raises:
            InvalidAnswersFormat: Se formato inválido
            QuizNotFound: Se quiz não encontrado
        """
        if source_name:
            source_path = self.repository.find_by_name(source_name)
        else:
            source_path = self.repository.find_default()

        # Carregar questões com respostas
        questions_data = load_questions_from_markdown(source_path)

        # Corrigir
        result = grade_answers(answers, questions_data)

        return GradeResultDTO(
            score=result["score"],
            total=result["total"],
            percentage=result["percentage"],
            results=result["results"]
        )


class MarkdownService:
    """Service para operações com Markdown"""

    def __init__(self, repository: QuizRepository = None):
        self.repository = repository or QuizRepository()

    def save_quiz_from_markdown(self, filename: str, content: str) -> Path:
        """
        Salva um novo quiz a partir de conteúdo Markdown.
        
        Args:
            filename (str): Nome do arquivo (sem path)
            content (str): Conteúdo Markdown
            
        Returns:
            Path: Caminho do arquivo salvo
        """
        path = self.repository.find_all_sources()  # Usar ROOT
        
        # Sanitizar filename
        safe_filename = "".join(
            c for c in filename 
            if c.isalnum() or c in (' ', '_', '-', '.')
        ).rstrip()
        
        if not safe_filename.endswith('.md'):
            safe_filename += '.md'

        save_path = Path(self.repository.find_default()).parent / safe_filename
        self.repository.save_file(save_path, content)
        
        return save_path

    def validate_markdown(self, content: str) -> tuple[bool, str]:
        """
        Valida se conteúdo Markdown tem formato correto.
        
        Args:
            content (str): Conteúdo a validar
            
        Returns:
            tuple[bool, str]: (válido, mensagem_erro)
        """
        try:
            # Tentar parsear
            from pathlib import Path
            import tempfile
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
                f.write(content)
                temp_path = Path(f.name)
            
            load_questions_from_markdown(temp_path)
            temp_path.unlink()  # Deletar temp
            
            return True, "OK"
        except Exception as e:
            return False, str(e)
