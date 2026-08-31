"""
Testes Básicos - Padrão pytest

Execute:
  pip install pytest
  pytest tests/ -v
  
Para cobertura:
  pip install pytest-cov
  pytest tests/ --cov=api/
"""
import pytest
from pathlib import Path
from api.repositories.quiz_repository import QuizRepository
from api.exceptions.quiz_exceptions import QuizNotFound
from api.utils.validators import AnswerValidator, MarkdownValidator


class TestAnswerValidator:
    """Testes para validador de respostas"""

    def test_valid_submit_payload(self):
        """Válida payload correto"""
        payload = {
            "answers": {1: 0, 2: 1},
            "source": "1 test"
        }
        is_valid, msg = AnswerValidator.validate_submit_payload(payload)
        assert is_valid is True
        assert msg == ""

    def test_missing_answers_field(self):
        """Detecta campo 'answers' faltando"""
        payload = {"source": "1 test"}
        is_valid, msg = AnswerValidator.validate_submit_payload(payload)
        assert is_valid is False
        assert "answers" in msg

    def test_answers_not_dict(self):
        """Detecta 'answers' não é dict"""
        payload = {"answers": [1, 2, 3]}
        is_valid, msg = AnswerValidator.validate_submit_payload(payload)
        assert is_valid is False
        assert "dicionário" in msg

    def test_empty_answers(self):
        """Detecta 'answers' vazio"""
        payload = {"answers": {}}
        is_valid, msg = AnswerValidator.validate_submit_payload(payload)
        assert is_valid is False
        assert "Pelo menos" in msg

    def test_invalid_answer_index(self):
        """Detecta índice de resposta inválido (> 3)"""
        payload = {"answers": {1: 5}}  # 5 é inválido, válido é 0-3
        is_valid, msg = AnswerValidator.validate_submit_payload(payload)
        assert is_valid is False
        assert "Resposta inválida" in msg


class TestMarkdownValidator:
    """Testes para validador de Markdown"""

    def test_valid_markdown(self):
        """Valida Markdown correto"""
        content = """
**1.** Pergunta 1?
a) Opção A
b) Opção B

# Gabarito
1. a) Resposta
"""
        is_valid, msg = MarkdownValidator.validate_markdown_content(content)
        assert is_valid is True

    def test_empty_content(self):
        """Detecta conteúdo vazio"""
        is_valid, msg = MarkdownValidator.validate_markdown_content("")
        assert is_valid is False
        assert "vazio" in msg

    def test_missing_question(self):
        """Detecta falta de questões"""
        content = "Apenas texto sem questões\n# Gabarito"
        is_valid, msg = MarkdownValidator.validate_markdown_content(content)
        assert is_valid is False
        assert "questão" in msg

    def test_missing_gabarito(self):
        """Detecta falta de seção Gabarito"""
        content = "**1.** Pergunta?\na) Opção A"
        is_valid, msg = MarkdownValidator.validate_markdown_content(content)
        assert is_valid is False
        assert "Gabarito" in msg


class TestQuizRepository:
    """Testes para repository de quizzes"""

    def test_find_all_sources(self):
        """Encontra todas as fontes de quiz"""
        sources = QuizRepository.find_all_sources()
        assert isinstance(sources, list)
        # Deve ter pelo menos um quiz de teste
        assert len(sources) > 0

    def test_find_default(self):
        """Encontra quiz padrão"""
        source = QuizRepository.find_default()
        assert isinstance(source, Path)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
