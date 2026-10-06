"""
Testes automatizados para caching HTTP (ETag, If-None-Match e HTTP 304)
e cache local de simulação com IA.
"""
import copy
import hashlib
import json
import unittest
from unittest.mock import MagicMock, patch

from api.middleware.http_middleware import HTTPMiddleware
from api.services.ai_service import generate_quiz_by_topic, _quiz_generation_cache


class TestHttpCacheAndEtag(unittest.TestCase):
    """Testa cabeçalhos ETag, If-None-Match e resposta 304 Not Modified."""

    def test_send_cached_json_response_generates_etag(self):
        """send_cached_json_response deve gerar ETag correspondente ao payload."""
        handler = MagicMock()
        handler.headers = {}
        handler.wfile = MagicMock()

        test_data = {"message": "ok", "quizzes": [{"id": 1, "title": "Direito Penal"}]}
        HTTPMiddleware.send_cached_json_response(handler, 200, test_data, max_age=60)

        # Verifica se o handler enviou status 200 e cabeçalhos de ETag e Cache-Control
        handler.send_response.assert_called_with(200)

        # Procura o header ETag nas chamadas
        header_calls = {call[0][0]: call[0][1] for call in handler.send_header.call_args_list}
        self.assertIn("ETag", header_calls)
        self.assertIn("Cache-Control", header_calls)
        self.assertIn("max-age=60", header_calls["Cache-Control"])

    def test_send_cached_json_response_returns_304_on_etag_match(self):
        """Quando If-None-Match coincide com o ETag do payload, deve retornar 304 sem enviar body."""
        test_data = {"message": "ok", "count": 42}
        body_bytes = json.dumps(test_data, ensure_ascii=False).encode("utf-8")
        expected_etag = f'"{hashlib.sha256(body_bytes).hexdigest()[:16]}"'

        handler = MagicMock()
        handler.headers = {"If-None-Match": expected_etag}
        handler.wfile = MagicMock()

        HTTPMiddleware.send_cached_json_response(handler, 200, test_data, max_age=60)

        # Deve responder com 304 Not Modified
        handler.send_response.assert_called_with(304)
        # Corpo não deve ser escrito na resposta 304
        handler.wfile.write.assert_not_called()

    def test_send_cached_json_response_returns_200_on_etag_mismatch(self):
        """Quando If-None-Match for diferente do ETag atual, deve retornar 200 e novo conteúdo."""
        test_data = {"message": "novo conteudo"}

        handler = MagicMock()
        handler.headers = {"If-None-Match": '"etag_antigo_desatualizado"'}
        handler.wfile = MagicMock()

        HTTPMiddleware.send_cached_json_response(handler, 200, test_data, max_age=60)

        # Deve responder com 200 OK e escrever o corpo
        handler.send_response.assert_called_with(200)
        handler.wfile.write.assert_called_once()

    def test_ai_generation_caches_identical_requests(self):
        """Simulados de IA com mesmo tema, dificuldade e quantidade devem ser servidos do cache."""
        fake_quiz = {
            "title": "Quiz de História",
            "topic": "Revolução Francesa",
            "questions": [
                {
                    "id": 1,
                    "question_number": 1,
                    "section": "História",
                    "context": "",
                    "question": "Em que ano ocorreu a queda da Bastilha?",
                    "options": ["1789", "1799", "1804", "1776"],
                    "answer": 0,
                    "explanation": "1789 marca o início da Revolução Francesa.",
                }
            ],
            "usage": {"total_tokens": 150},
            "model": "gemini-test",
            "provider": "Google AI Studio",
        }

        # Popula o cache para o tema 'Revolução Francesa'
        clean_topic = "revolucao francesa"
        qty = 5
        diff = "Médio"
        cache_key = hashlib.sha256(f"{clean_topic}:{qty}:{diff}:".encode("utf-8")).hexdigest()

        with patch("api.services.ai_service._call_openrouter") as mock_call, \
             patch("api.services.ai_service.check_ai_token_quota"), \
             patch("api.services.ai_service.GEMINI_API_KEY", "fake_key"):

            # Primeira chamada: simula retorno da API
            mock_call.return_value = (
                json.dumps({
                    "title": "Quiz de História",
                    "questions": fake_quiz["questions"]
                }),
                "gemini-test",
                {"total_tokens": 150}
            )

            res1 = generate_quiz_by_topic("Revolucao Francesa", num_questions=5, difficulty="Médio")
            self.assertEqual(res1["title"], "Quiz de História")
            self.assertEqual(mock_call.call_count, 1)

            # Segunda chamada idêntica: deve vir do cache SEM chamar a API de novo
            res2 = generate_quiz_by_topic("Revolucao Francesa", num_questions=5, difficulty="Médio")
            self.assertEqual(res2["title"], "Quiz de História")
            self.assertEqual(mock_call.call_count, 1, "A API não deveria ter sido chamada uma segunda vez")


if __name__ == "__main__":
    unittest.main()
