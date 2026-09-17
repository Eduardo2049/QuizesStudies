"""
Testes Unitários da Aplicação (Python stdlib unittest)

Execução:
  python -m unittest discover tests
"""
import unittest
from unittest.mock import patch, MagicMock

from api.utils.validators import AnswerValidator
from api.utils.file_parser import detect_has_answer_key, parse_questions_from_text, validate_questions
from api.services.auth_service import hash_password, verify_password, AuthService
from api.services.ai_service import generate_quiz_by_topic, AIServiceError


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
        """Detecta índice de resposta negativo"""
        payload = {"answers": {1: -1}}
        is_valid, msg = AnswerValidator.validate_submit_payload(payload)
        self.assertFalse(is_valid)
        self.assertIn("inválido", msg)


class TestFileParser(unittest.TestCase):
    """Testes para parser de questões e gabarito"""

    def test_detect_has_answer_key(self):
        """Detecta se há seção de gabarito"""
        self.assertTrue(detect_has_answer_key("# Gabarito\n1. a)"))
        self.assertTrue(detect_has_answer_key("Gabarito:\n1. a)"))
        self.assertFalse(detect_has_answer_key("Apenas perguntas sem gabarito"))

    def test_parse_questions_from_text(self):
        """Parse de questões com alternativas"""
        text = """
**1.** Qual é a capital do Brasil?
a) São Paulo
b) Brasília
c) Rio de Janeiro
d) Salvador

# Gabarito
1. b) Brasília → É a capital federal.
"""
        questions = parse_questions_from_text(text)
        self.assertEqual(len(questions), 1)
        self.assertEqual(questions[0]["id"], 1)
        self.assertEqual(len(questions[0]["options"]), 4)
        self.assertEqual(questions[0]["answer"], 1)  # b = index 1
        self.assertEqual(questions[0]["explanation"], "É a capital federal.")


class TestAuthService(unittest.TestCase):
    """Testes para regras de senha e seed do admin"""

    def test_hash_and_verify_password(self):
        pwd = "CofeDev2468*"
        pwd_hash, salt = hash_password(pwd)
        self.assertTrue(verify_password(pwd, salt, pwd_hash))
        self.assertFalse(verify_password("senhaErrada", salt, pwd_hash))

    def test_seed_admin_creates_or_updates(self):
        mock_repo = MagicMock()
        mock_repo.find_by_username.return_value = None
        service = AuthService(repository=mock_repo)

        service.seed_admin_if_needed()
        self.assertTrue(mock_repo.create_user.called)

        # Se já existe, atualiza senha
        mock_repo.reset_mock()
        mock_repo.find_by_username.return_value = {"id": 1, "username": "admin"}
        service.seed_admin_if_needed()
        self.assertTrue(mock_repo.update_password_and_role.called)


class TestAITopicGeneration(unittest.TestCase):
    """Testes para geração de quiz por tema via IA"""

    @patch("api.services.ai_service._get_http_session")
    def test_generate_quiz_by_topic_success(self, mock_get_session):
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": """{
                        "title": "Simulado de Lógica Proposicional",
                        "questions": [
                            {
                                "id": 1,
                                "section": "Lógica",
                                "context": "",
                                "question": "Se chove, a rua molha. Qual a negação?",
                                "options": [
                                    "Chove e a rua não molha",
                                    "Não chove e a rua molha",
                                    "Não chove e a rua não molha",
                                    "Chove e a rua molha"
                                ],
                                "answer": 0,
                                "explanation": "Negação de condicional P -> Q é P e ~Q."
                            }
                        ]
                    }"""
                }
            }]
        }
        mock_session.post.return_value = mock_response
        mock_get_session.return_value = mock_session

        with patch("api.services.ai_service.OPENROUTER_API_KEY", "dummy_key"):
            result = generate_quiz_by_topic("Raciocínio Lógico", num_questions=1)
            self.assertEqual(result["title"], "Simulado de Lógica Proposicional")
            self.assertEqual(len(result["questions"]), 1)
            self.assertEqual(result["questions"][0]["answer"], 0)
            self.assertEqual(len(result["questions"][0]["options"]), 4)

    def test_generate_quiz_by_topic_empty_topic(self):
        with patch("api.services.ai_service.OPENROUTER_API_KEY", "dummy_key"):
            with self.assertRaises(AIServiceError):
                generate_quiz_by_topic("")


class TestSessionAndCacheClearing(unittest.TestCase):
    """Testes para invalidação de sessões e limpeza de cookies"""

    def test_clear_all_sessions(self):
        from api.repositories.user_repository import UserRepository
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 5
        with patch("api.repositories.user_repository.get_cursor") as mock_get_cursor:
            mock_get_cursor.return_value.__enter__.return_value = mock_cursor
            repo = UserRepository()
            count = repo.clear_all_sessions()
            self.assertEqual(count, 5)
            mock_cursor.execute.assert_called_once_with("DELETE FROM sessions")

    def test_session_cookie_clear(self):
        from api.middleware.http_middleware import HTTPMiddleware
        cookie = HTTPMiddleware.session_cookie(None, secure=True, max_age=0)
        self.assertIn("Max-Age=0", cookie)
        self.assertIn("Secure", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("Path=/", cookie)

    def test_send_json_response_clear_cookie(self):
        from api.middleware.http_middleware import HTTPMiddleware
        handler = MagicMock()
        handler.headers = {}
        handler.wfile = MagicMock()
        HTTPMiddleware.send_json_response(handler, 401, {"error": "unauthorized"}, clear_cookie=True)
        set_cookie_calls = [
            call for call in handler.send_header.call_args_list if call[0][0] == "Set-Cookie"
        ]
        self.assertEqual(len(set_cookie_calls), 1)
        self.assertIn("Max-Age=0", set_cookie_calls[0][0][1])


if __name__ == "__main__":
    unittest.main()
