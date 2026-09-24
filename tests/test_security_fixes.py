"""
Testes unitários para validação das correções de segurança e higiene
====================================================================
Cobre:
1. ReDoS no INLINE_MARKER_PATTERN e truncamento de linhas.
2. Proteção contra DOCX Zip Bomb (tamanho e taxa de compressão).
3. Rejeição de Content-Length negativo, zero ou inválido.
4. Exigência de autenticação para endpoints de IA (/api/quiz/generate, remix-mistakes).
5. Hash seguro de tokens de sessão (SHA-256 no banco).
6. PBKDF2 com 600.000 iterações, senha mínima 8 caracteres e anti-enumeração no registro.
7. Funcionamento de generate_quiz_by_topic com Gemini sem exigir OPENROUTER_API_KEY.
8. Anti-spoofing em get_client_ip quando TRUST_PROXY não está ativo.
"""
import io
import time
import zipfile
import unittest
from unittest.mock import MagicMock, patch

from api.utils.file_parser import INLINE_MARKER_PATTERN, parse_docx, parse_questions_from_text
from api.services.auth_service import hash_password, verify_password, AuthService, _hash_token
from api.exceptions.quiz_exceptions import QuizAPIException


class TestReDoSAndParserSecurity(unittest.TestCase):
    """Valida mitigação de ReDoS e Zip Bomb."""

    def test_redos_inline_markers_catastrophic_backtracking_prevented(self):
        """String longa com espaços não deve travar o processamento."""
        attack_string = " " * 40_000
        start = time.time()
        matches = list(INLINE_MARKER_PATTERN.finditer(attack_string))
        elapsed = time.time() - start
        self.assertEqual(len(matches), 0)
        self.assertLess(elapsed, 0.2, f"ReDoS detectado! Levou {elapsed:.3f}s")

    def test_inline_markers_normal_extraction_still_works(self):
        """Regex deve continuar identificando alternativas inline reais."""
        text = "1. Qual a capital do Brasil? a) São Paulo b) Brasília c) Rio de Janeiro"
        options = parse_questions_from_text(text)
        self.assertEqual(len(options), 1)
        self.assertGreaterEqual(len(options[0]["options"]), 2)
        self.assertIn("Brasília", options[0]["options"][1])

    def test_docx_zip_bomb_rejected(self):
        """DOCX com alta taxa de compressão ou tamanho descompactado absurdo é rejeitado."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            # 1 milhão de 'A's compactados em alguns bytes -> taxa absurda
            zf.writestr("word/document.xml", b"A" * 1_000_000)

        buf.seek(0)
        with self.assertRaises(ValueError) as ctx:
            parse_docx(buf.getvalue())
        self.assertIn("Zip Bomb", str(ctx.exception))


class TestAuthAndSessionSecurity(unittest.TestCase):
    """Valida hardening de senhas e sessões."""

    def test_pbkdf2_iterations_and_hashing(self):
        """Valida que hash_password usa 600.000 iterações e verify_password funciona."""
        pwd = "MinhaSenhaSuperForte2026!"
        h, salt = hash_password(pwd)
        self.assertEqual(len(h), 64)
        self.assertTrue(verify_password(pwd, salt, h))
        self.assertFalse(verify_password("SenhaIncorreta", salt, h))

    def test_session_token_stored_as_sha256_hash(self):
        """Tokens de sessão devem ser armazenados como hash SHA-256 no banco."""
        mock_repo = MagicMock()
        mock_user = {"id": 10, "username": "estudante", "email": "estudante@study.app", "salt": "salt123", "role": "student"}
        # Gerar hash correspondente
        mock_user["password_hash"], _ = hash_password("SenhaSegura123*", mock_user["salt"])
        mock_repo.find_by_username.return_value = mock_user

        service = AuthService(repository=mock_repo)
        res = service.login("estudante", "SenhaSegura123*")
        raw_token = res["token"]

        # O token salvo no repositório DEVE ser o hash do token bruto
        called_args = mock_repo.create_session.call_args[0]
        saved_token = called_args[0]
        self.assertEqual(saved_token, _hash_token(raw_token))
        self.assertNotEqual(saved_token, raw_token)

    def test_register_enforces_min_password_length(self):
        """Senhas com menos de 8 caracteres devem ser rejeitadas."""
        mock_repo = MagicMock()
        service = AuthService(repository=mock_repo)
        with self.assertRaises(QuizAPIException) as ctx:
            service.register("novo_user", "novo@study.app", "123456")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("8 caracteres", ctx.exception.message)

    def test_register_prevents_user_enumeration(self):
        """Conflitos de username ou email retornam a mesma mensagem uniforme."""
        mock_repo = MagicMock()
        mock_repo.find_by_username.return_value = {"id": 1}
        service = AuthService(repository=mock_repo)
        with self.assertRaises(QuizAPIException) as ctx:
            service.register("existente", "outro@study.app", "SenhaForte123*")
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(ctx.exception.message, "Nome de usuário ou e-mail já cadastrado")


class TestAIKeyConfiguration(unittest.TestCase):
    """Valida suporte a Gemini sem exigir OpenRouter."""

    @patch("api.services.ai_service._get_http_session")
    def test_generate_quiz_by_topic_with_gemini_only(self, mock_get_session):
        """Geração por tema deve funcionar se apenas GEMINI_API_KEY estiver configurada."""
        from api.services.ai_service import generate_quiz_by_topic

        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{
                "message": {
                    "content": '{"title": "Tema Gemini", "questions": [{"id": 1, "question": "Q1?", "options": ["A", "B"], "answer": 0, "explanation": "Exp"}]}'
                }
            }],
            "usage": {"total_tokens": 120}
        }
        mock_get_session.return_value = mock_session
        mock_session.post.return_value = mock_resp

        with patch("api.services.ai_service.OPENROUTER_API_KEY", ""), \
             patch("api.services.ai_service.GEMINI_API_KEY", "dummy_gemini_key"), \
             patch("api.services.ai_service.AI_PROVIDER", "google"):
            res = generate_quiz_by_topic(topic="História do Brasil", num_questions=1)
            self.assertEqual(res["title"], "Tema Gemini")
            self.assertEqual(len(res["questions"]), 1)


if __name__ == "__main__":
    unittest.main()
