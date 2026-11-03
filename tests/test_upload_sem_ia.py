"""
Arquivo que já traz questões e gabarito vira simulado sem chamar a IA e sem gastar cota.

1. Formatos comuns de gabarito em provas e PDFs reconhecidos pelo parser:
   vários pares na linha, "Gabarito: 1-B, 2-C", "GABARITO OFICIAL", tabela número/letra,
   "QUESTÃO 01" sozinha na linha, "Resposta: Letra B", alternativa marcada como correta.
2. Proteções: "Letra B" não vira a letra "L"; letra fora das alternativas é descartada;
   lista em markdown ("* a)", "* b)") não conta como marcação; frase comum não abre gabarito.
3. UploadService: com gabarito reconhecido, nem o `ai_gate` (cota do convidado) nem a IA são
   chamados, inclusive num PDF de verdade; a mensagem avisa que nenhum uso de IA foi gasto.
"""
import unittest
from unittest.mock import MagicMock, patch

from api.services.upload_service import UploadService
from api.utils.file_parser import parse_questions_from_text, validate_questions


def _answers(text):
    return [(q["id"], len(q["options"]), q["answer"]) for q in parse_questions_from_text(text)]


TWO_QUESTIONS = """1) Qual a capital do Brasil?
a) Rio de Janeiro
b) Brasília
c) São Paulo
2) Quanto é 2 + 2?
a) 3
b) 4
c) 5
"""


class AnswerKeyFormatsTests(unittest.TestCase):
    def test_several_pairs_per_line(self):
        self.assertEqual(_answers(TWO_QUESTIONS + "GABARITO\n1-B 2-B"), [(1, 3, 1), (2, 3, 1)])

    def test_pairs_on_header_line(self):
        self.assertEqual(_answers(TWO_QUESTIONS + "Gabarito: 1-B, 2-C"), [(1, 3, 1), (2, 3, 2)])

    def test_header_with_qualifier(self):
        self.assertEqual(_answers(TWO_QUESTIONS + "GABARITO OFICIAL\n1. B\n2. A"), [(1, 3, 1), (2, 3, 0)])

    def test_table_layout_from_pdf(self):
        self.assertEqual(_answers(TWO_QUESTIONS + "Gabarito\n1 2\nB C"), [(1, 3, 1), (2, 3, 2)])

    def test_question_header_alone_on_line(self):
        text = (
            "QUESTÃO 01\nQual a capital do Brasil?\n(A) Rio\n(B) Brasília\n(C) SP\n"
            "QUESTÃO 02\nQuanto é 2 + 2?\n(A) 3\n(B) 4\n"
            "Gabarito\n01 - B\n02 - B"
        )
        questions = parse_questions_from_text(text)
        self.assertEqual([(q["id"], len(q["options"]), q["answer"]) for q in questions], [(1, 3, 1), (2, 2, 1)])
        self.assertEqual(questions[0]["question"], "Qual a capital do Brasil?")

    def test_inline_answer_with_word_letra(self):
        text = (
            "1. Capital?\na) Rio\nb) Brasília\nResposta: Letra B\n"
            "2. Soma?\na) 3\nb) 4\nAlternativa correta: B"
        )
        self.assertEqual(_answers(text), [(1, 2, 1), (2, 2, 1)])

    def test_option_marked_as_correct(self):
        text = "1. Capital?\na) Rio\n*b) Brasília\n2. Soma?\na) 3\nb) 4 (correta)\nc) 5"
        questions = parse_questions_from_text(text)
        self.assertEqual([(q["id"], q["answer"]) for q in questions], [(1, 1), (2, 1)])
        self.assertEqual(questions[0]["options"], ["Rio", "Brasília"])
        self.assertEqual(questions[1]["options"], ["3", "4", "5"])

    def test_existing_formats_still_work(self):
        text = TWO_QUESTIONS + "\n# Gabarito\n1. B — Brasília é a capital\n2. B"
        questions = parse_questions_from_text(text)
        self.assertEqual([(q["id"], q["answer"]) for q in questions], [(1, 1), (2, 1)])
        self.assertEqual(questions[0]["explanation"], "Brasília é a capital")


class AnswerKeySafetyTests(unittest.TestCase):
    def test_letter_out_of_range_is_dropped(self):
        self.assertEqual(_answers("1. Capital?\na) Rio\nb) Brasília\nGabarito\n1-E"), [(1, 2, None)])

    def test_markdown_bullets_are_not_answers(self):
        text = "1. Capital?\n* a) Rio\n* b) Brasília\n2. Soma?\n* a) 3\n* b) 4"
        self.assertEqual(_answers(text), [(1, 2, None), (2, 2, None)])

    def test_plain_sentence_does_not_open_answer_key(self):
        text = "Respostas devem ser marcadas no cartão.\n" + TWO_QUESTIONS
        self.assertEqual(_answers(text), [(1, 3, None), (2, 3, None)])

    def test_word_starting_with_letter_is_not_an_answer(self):
        self.assertEqual(_answers("1. Capital?\na) Rio\nb) Brasília\nResposta: Brasília"), [(1, 2, None)])


def _minimal_pdf(lines: list[str]) -> bytes:
    """PDF de uma página só com texto ASCII (sem dependências extras)."""
    stream_lines = ["BT", "/F1 11 Tf", "14 TL", "50 780 Td"]
    for line in lines:
        safe = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream_lines.append(f"({safe}) Tj T*")
    stream_lines.append("ET")
    stream = "\n".join(stream_lines).encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


class UploadWithoutAITests(unittest.TestCase):
    def setUp(self):
        self.service = UploadService(repository=MagicMock())
        self.no_ai = [
            patch("api.services.upload_service.OPENROUTER_API_KEY", "fake-key"),
            patch("api.services.upload_service.parse_and_structure_questions_with_ai",
                  side_effect=AssertionError("IA não devia ser chamada")),
            patch("api.services.upload_service.generate_answer_key",
                  side_effect=AssertionError("IA não devia ser chamada")),
        ]
        for p in self.no_ai:
            p.start()

    def tearDown(self):
        for p in self.no_ai:
            p.stop()

    def _guest_upload(self, filename, content, file_type):
        gate = MagicMock()
        result = self.service.process_upload(
            filename, content, file_type, created_by=None, is_public=False,
            persist=False, ai_gate=gate,
        )
        return result, gate

    def test_txt_with_answer_key_uses_no_quota(self):
        content = (TWO_QUESTIONS + "Gabarito: 1-B, 2-B").encode("utf-8")
        result, gate = self._guest_upload("prova.txt", content, "txt")
        gate.assert_not_called()
        self.assertFalse(result["ai_used"])
        self.assertEqual(result["question_count"], 2)
        self.assertIn("sem gastar usos de IA", result["message"])

    def test_pdf_with_answer_key_uses_no_quota(self):
        pdf = _minimal_pdf([
            "QUESTAO 01",
            "Qual a capital do Brasil?",
            "(A) Rio de Janeiro",
            "(B) Brasilia",
            "(C) Sao Paulo",
            "QUESTAO 02",
            "Quanto e 2 + 2?",
            "(A) 3",
            "(B) 4",
            "GABARITO OFICIAL",
            "01 - B 02 - B",
        ])
        result, gate = self._guest_upload("prova.pdf", pdf, "pdf")
        gate.assert_not_called()
        self.assertEqual([q["answer"] for q in result["questions"]], [1, 1])
        ok, _ = validate_questions(result["questions"])
        self.assertTrue(ok)

    def test_logged_user_message_says_no_ai(self):
        self.service.repo.name_exists.return_value = False
        self.service.repo.save_quiz.return_value = {"id": 7, "name": "prova", "label": "Prova"}
        content = (TWO_QUESTIONS + "GABARITO\n1-B 2-B").encode("utf-8")
        result = self.service.process_upload("prova.txt", content, "txt", created_by=1, is_public=False)
        self.assertFalse(result["ai_used"])
        self.assertTrue(result["message"].endswith("sem gastar usos de IA."))

    def test_missing_answers_still_go_through_the_gate(self):
        for p in self.no_ai[2:]:
            p.stop()
        with patch("api.services.upload_service.generate_answer_key", return_value=[]) as gen, \
             patch("api.services.upload_service.apply_ai_answers",
                   side_effect=lambda qs, _a: [dict(q, answer=0) for q in qs]):
            result, gate = self._guest_upload("prova.txt", TWO_QUESTIONS.encode("utf-8"), "txt")
        gate.assert_called_once()
        gen.assert_called_once()
        self.assertTrue(result["ai_used"])
        self.no_ai[2].start()


if __name__ == "__main__":
    unittest.main()
