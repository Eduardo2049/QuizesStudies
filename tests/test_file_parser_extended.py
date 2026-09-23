"""
Testes unitários estendidos para parser de arquivos e estruturação com IA.
"""
import unittest
from unittest.mock import patch, MagicMock

from api.utils.file_parser import (
    parse_txt,
    parse_questions_from_text,
    validate_questions,
    detect_has_answer_key,
)
from api.services.upload_service import UploadService
from api.services.ai_service import parse_and_structure_questions_with_ai, AIServiceError
from api.exceptions.quiz_exceptions import QuizAPIException


class TestExtendedFileParser(unittest.TestCase):
    """Testa múltiplos padrões de arquivos TXT (numeração, alternativas e gabarito)."""

    def test_parse_txt_encodings(self):
        """Suporta UTF-8, UTF-8 com BOM e Latin-1."""
        utf8_bom = b"\xef\xbb\xbf1. Quest\xc3\xa3o com BOM\na) Sim\nb) N\xc3\xa3o"
        text = parse_txt(utf8_bom)
        self.assertIn("Questão com BOM", text)

        latin1 = "1. Questão acentuada\na) Opção\nb) Outra".encode("latin-1")
        text_latin1 = parse_txt(latin1)
        self.assertIn("Questão acentuada", text_latin1)

    def test_various_question_patterns(self):
        """Reconhece múltiplos estilos de identificação de questões."""
        sample = """
Questão 1: Qual a capital da França?
a) Berlim
b) Paris
c) Roma

Questao 02 - Qual o maior planeta do sistema solar?
A. Marte
B. Júpiter
C. Saturno

(3) Quantos minutos tem uma hora?
(a) 30
(b) 60
(c) 90

[4] Qual elemento tem símbolo químico O?
[A] Ouro
[B] Oxigênio
[C] Ozônio

Q5. Quanto é 2 + 2?
a - 3
b - 4
c - 5

# Gabarito
1 - B
2. B
3: B
4: B
5. B
"""
        questions = parse_questions_from_text(sample)
        self.assertEqual(len(questions), 5)
        self.assertEqual(questions[0]["id"], 1)
        self.assertEqual(questions[0]["answer"], 1)  # B
        self.assertEqual(questions[1]["id"], 2)
        self.assertEqual(questions[1]["answer"], 1)  # B
        self.assertEqual(questions[2]["id"], 3)
        self.assertEqual(questions[2]["answer"], 1)  # B
        self.assertEqual(questions[3]["id"], 4)
        self.assertEqual(questions[3]["answer"], 1)  # B
        self.assertEqual(questions[4]["id"], 5)
        self.assertEqual(questions[4]["answer"], 1)  # B

    def test_inline_alternatives_and_inline_answers(self):
        """Reconhece alternativas inline e gabarito inline logo abaixo da questão."""
        sample = """
1. Complete a sequência: 2, 4, 8, ...
a) 12   b) 14   c) 16
Gabarito: C - Multiplica-se por 2 a cada termo.

2. Se todo A é B e B é C, então:
(A) Todo A é C   (B) Nenhum A é C
Resposta: A
"""
        questions = parse_questions_from_text(sample)
        self.assertEqual(len(questions), 2)
        self.assertEqual(len(questions[0]["options"]), 3)
        self.assertEqual(questions[0]["answer"], 2)  # C
        self.assertIn("Multiplica-se por 2", questions[0]["explanation"])

        self.assertEqual(len(questions[1]["options"]), 2)
        self.assertEqual(questions[1]["answer"], 0)  # A


class TestAIStructureAndUploadService(unittest.TestCase):
    """Testa o fallback para IA quando o arquivo não possui numeração/padrão rígido."""

    @patch("api.services.ai_service._call_openrouter")
    def test_parse_and_structure_questions_with_ai(self, mock_call):
        """Simula resposta da IA estruturando texto despadronizado."""
        mock_ai_json = """{
            "questions": [
                {
                    "id": 1,
                    "section": "Lógica",
                    "question": "Um homem tem 3 filhos. Cada filho tem 1 irmã. Quantos filhos no total?",
                    "options": ["3", "4", "6", "7"],
                    "answer": 1,
                    "explanation": "A irmã é a mesma para todos os 3 irmãos, totalizando 4 filhos."
                }
            ]
        }"""
        mock_call.return_value = (mock_ai_json, "gemini-flash-lite-latest")

        raw_unformatted_text = """
Um homem tem 3 filhos. Cada filho tem 1 irmã. Quantos filhos no total?
Primeira alternativa: 3
Segunda alternativa: 4
Terceira alternativa: 6
Quarta alternativa: 7
"""
        questions = parse_and_structure_questions_with_ai(raw_unformatted_text)
        self.assertEqual(len(questions), 1)
        self.assertEqual(questions[0]["id"], 1)
        self.assertEqual(len(questions[0]["options"]), 4)
        self.assertEqual(questions[0]["answer"], 1)
        self.assertIn("irmã é a mesma", questions[0]["explanation"])

    def test_upload_service_rejects_unsupported_extension(self):
        """Rejeita tipos de arquivos não suportados."""
        service = UploadService(repository=MagicMock())
        with self.assertRaises(QuizAPIException) as ctx:
            service.process_upload(
                filename="tabela.xlsx",
                content=b"dados",
                file_type="xlsx",
                created_by=1,
                is_public=False,
                persist=False,
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("não suportado", str(ctx.exception))

    def test_upload_service_rejects_oversized_file(self):
        """Rejeita arquivos que excedem o limite de peso."""
        service = UploadService(repository=MagicMock())
        big_content = b"A" * (UploadService.MAX_UPLOAD_BYTES + 100)
        with self.assertRaises(QuizAPIException) as ctx:
            service.process_upload(
                filename="grande.txt",
                content=big_content,
                file_type="txt",
                created_by=1,
                is_public=False,
                persist=False,
            )
        self.assertEqual(ctx.exception.status_code, 413)

    @patch("api.services.upload_service.parse_and_structure_questions_with_ai")
    def test_upload_service_triggers_ai_fallback_on_unstructured_text(self, mock_ai_parse):
        """Quando o regex não encontra questões, aciona parse_and_structure_questions_with_ai."""
        mock_ai_parse.return_value = [
            {
                "id": 1,
                "question_number": 1,
                "section": "Geral",
                "context": "",
                "question": "Pergunta livre detectada por IA?",
                "options": ["Sim", "Não"],
                "answer": 0,
                "explanation": "Resposta correta",
                "ai_generated": True,
            }
        ]

        service = UploadService(repository=MagicMock())
        with patch("api.services.upload_service.GEMINI_API_KEY", "dummy_key"):
            result = service.process_upload(
                filename="prova_livre.txt",
                content=b"Texto corrido sem numeracao nem alternativas padrao",
                file_type="txt",
                created_by=1,
                is_public=False,
                persist=False,
            )
            self.assertTrue(mock_ai_parse.called)
            self.assertEqual(result["question_count"], 1)
            self.assertTrue(result["ai_generated"])


if __name__ == "__main__":
    unittest.main()
