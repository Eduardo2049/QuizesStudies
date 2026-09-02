"""
Testes Unitários da Aplicação (Python stdlib unittest)

Execução:
  python -m unittest discover tests
"""
import unittest
from pathlib import Path

from api.repositories.quiz_repository import QuizRepository
from api.exceptions.quiz_exceptions import QuizNotFound, InvalidAnswersFormat
from api.utils.validators import AnswerValidator, MarkdownValidator
from api.utils.markdown_parser import load_questions_from_markdown
from api.utils.quiz_logic import grade_answers, public_questions
from api.services.quiz_service import QuizService
from api.controllers.quiz_controller import QuizController


class TestAnswerValidator(unittest.TestCase):
    """Testes para validador de respostas"""

    def test_valid_submit_payload(self):
        """Valida payload correto"""
        payload = {
            "answers": {1: 0, 2: 1},
            "source": "1 test"
        }
        is_valid, msg = AnswerValidator.validate_submit_payload(payload)
        self.assertTrue(is_valid)
        self.assertEqual(msg, "")

    def test_missing_answers_field(self):
        """Detecta campo 'answers' faltando"""
        payload = {"source": "1 test"}
        is_valid, msg = AnswerValidator.validate_submit_payload(payload)
        self.assertFalse(is_valid)
        self.assertIn("answers", msg)

    def test_answers_not_dict(self):
        """Detecta 'answers' que não é dict"""
        payload = {"answers": [1, 2, 3]}
        is_valid, msg = AnswerValidator.validate_submit_payload(payload)
        self.assertFalse(is_valid)
        self.assertIn("dicionário", msg)

    def test_empty_answers(self):
        """Detecta 'answers' vazio"""
        payload = {"answers": {}}
        is_valid, msg = AnswerValidator.validate_submit_payload(payload)
        self.assertFalse(is_valid)
        self.assertIn("Pelo menos", msg)

    def test_invalid_answer_index(self):
        """Detecta índice de resposta inválido (> 3)"""
        payload = {"answers": {1: 5}}
        is_valid, msg = AnswerValidator.validate_submit_payload(payload)
        self.assertFalse(is_valid)
        self.assertIn("Resposta inválida", msg)


class TestMarkdownValidator(unittest.TestCase):
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
        self.assertTrue(is_valid)

    def test_empty_content(self):
        """Detecta conteúdo vazio"""
        is_valid, msg = MarkdownValidator.validate_markdown_content("")
        self.assertFalse(is_valid)
        self.assertIn("vazio", msg)

    def test_missing_question(self):
        """Detecta falta de questões"""
        content = "Apenas texto sem questões\n# Gabarito"
        is_valid, msg = MarkdownValidator.validate_markdown_content(content)
        self.assertFalse(is_valid)
        self.assertIn("questão", msg)

    def test_missing_gabarito(self):
        """Detecta falta de seção Gabarito"""
        content = "**1.** Pergunta?\na) Opção A"
        is_valid, msg = MarkdownValidator.validate_markdown_content(content)
        self.assertFalse(is_valid)
        self.assertIn("Gabarito", msg)


class TestQuizRepository(unittest.TestCase):
    """Testes para repository de quizzes"""

    def test_find_all_sources(self):
        """Encontra todas as fontes de quiz disponíveis"""
        sources = QuizRepository.find_all_sources()
        self.assertIsInstance(sources, list)
        self.assertGreater(len(sources), 0)
        # Garante que encontrou '1 test'
        names = [s.name for s in sources]
        self.assertIn("1 test", names)

    def test_find_default(self):
        """Encontra quiz padrão"""
        source = QuizRepository.find_default()
        self.assertIsInstance(source, Path)
        self.assertTrue(source.exists())

    def test_find_by_name_success(self):
        """Encontra quiz existente pelo nome"""
        source = QuizRepository.find_by_name("1 test")
        self.assertEqual(source.name, "1 test")

    def test_find_by_name_not_found(self):
        """Lança QuizNotFound se não existir"""
        with self.assertRaises(QuizNotFound):
            QuizRepository.find_by_name("arquivo_inexistente_xyz")


class TestQuizServiceAndLogic(unittest.TestCase):
    """Testes para QuizService e lógica de correção"""

    def setUp(self):
        self.service = QuizService()
        self.controller = QuizController()

    def test_get_all_quizzes(self):
        quizzes = self.service.get_all_quizzes()
        self.assertIsInstance(quizzes, list)
        self.assertGreater(len(quizzes), 0)
        self.assertIn("name", quizzes[0])
        self.assertIn("label", quizzes[0])

    def test_get_quiz(self):
        quiz_dto = self.service.get_quiz("1 test")
        self.assertEqual(quiz_dto.source, "1 test")
        self.assertEqual(len(quiz_dto.questions), 16)
        # Respostas não devem estar visíveis no DTO público
        self.assertIsNone(quiz_dto.questions[0].answer)

    def test_submit_answers(self):
        # 1 test gabarito da questão 1 é c (índice 2)
        answers = {1: 2, 2: 1}  # questão 1 acertou, questão 2 (b = 1) acertou
        result = self.service.submit_answers(answers, "1 test")
        self.assertEqual(result.total, 16)
        self.assertEqual(result.score, 2)
        self.assertTrue(result.results[0]["isCorrect"])

    def test_controller_get_quizzes(self):
        res = self.controller.get_quizzes()
        self.assertEqual(res["status"], "success")
        self.assertIn("quizzes", res["data"])

    def test_controller_get_quiz(self):
        res = self.controller.get_quiz("1 test")
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["data"]["source"], "1 test")
        self.assertEqual(len(res["data"]["questions"]), 16)


if __name__ == "__main__":
    unittest.main()
