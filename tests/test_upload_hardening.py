"""
Testes automatizados para o endurecimento de upload de arquivos (TXT, PDF, DOCX)
e diferenciação de cotas entre convidados e usuários autenticados.
"""
import io
import unittest
import zipfile
from unittest.mock import MagicMock, patch

from api.utils.file_parser import (
    parse_pdf,
    parse_docx,
    _validate_docx_zip,
    extract_text,
    MAX_GUEST_PDF_PAGES,
    MAX_GUEST_DOCX_PARAGRAPHS,
    MAX_GUEST_DOCX_UNCOMPRESSED_BYTES,
)
from api.services.upload_service import UploadService
from api.exceptions.quiz_exceptions import QuizAPIException


class TestUploadHardening(unittest.TestCase):
    """Testa restrições e segurança no parsing de arquivos."""

    def test_guest_pdf_page_limit_exceeded(self):
        """PDF de convidado deve estourar com mais de 20 páginas."""
        mock_pdf = MagicMock()
        # Simula 25 páginas com índice bound corretamente
        mock_pdf.pages = [MagicMock(extract_text=lambda idx=i: f"Conteudo pagina {idx}") for i in range(25)]

        with patch("pdfplumber.open") as mock_open:
            mock_open.return_value.__enter__.return_value = mock_pdf
            dummy_bytes = b"%PDF-1.4 dummy content"

            # Convidado (is_guest=True): deve rejeitar
            with self.assertRaises(ValueError) as ctx:
                parse_pdf(dummy_bytes, is_guest=True)
            self.assertIn("excede o limite de 20 páginas", str(ctx.exception))

            # Autenticado (is_guest=False): deve aceitar até 100
            text = parse_pdf(dummy_bytes, is_guest=False)
            self.assertIn("Conteudo pagina 0", text)

    def test_guest_docx_paragraph_limit_exceeded(self):
        """DOCX de convidado deve rejeitar mais de 500 parágrafos."""
        mock_doc = MagicMock()
        # Simula 600 parágrafos
        mock_doc.paragraphs = [MagicMock(text=f"Paragrafo {i}") for i in range(600)]

        with patch("docx.Document", return_value=mock_doc), \
             patch("api.utils.file_parser._validate_docx_zip"):
            dummy_bytes = b"PK dummy docx"

            with self.assertRaises(ValueError) as ctx:
                parse_docx(dummy_bytes, is_guest=True)
            self.assertIn("excede o limite de 500 parágrafos", str(ctx.exception))

            # Autenticado aceita até 10.000
            text = parse_docx(dummy_bytes, is_guest=False)
            self.assertIn("Paragrafo 0", text)

    def test_zip_bomb_detection_high_compression_ratio(self):
        """Detecta e bloqueia tentativa de Zip Bomb por alta taxa de compressão."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            # 1 MB de zeros comprime para quase nada
            large_zeros = b"0" * (1024 * 1024)
            zf.writestr("word/document.xml", large_zeros)

        zip_bytes = buf.getvalue()
        # Deve acusar taxa excessiva de compressão
        with self.assertRaises(ValueError) as ctx:
            _validate_docx_zip(zip_bytes, is_guest=False)
        self.assertIn("Zip Bomb", str(ctx.exception))

    def test_guest_upload_size_limit_in_upload_service(self):
        """UploadService deve rejeitar payloads acima de 5 MB para convidados."""
        service = UploadService(repository=MagicMock())
        # Cria payload fake de 6 MB
        fake_content = b"a" * (6 * 1024 * 1024)

        with self.assertRaises(QuizAPIException) as ctx:
            service.process_upload(
                filename="simulado.txt",
                content=fake_content,
                file_type="txt",
                created_by=None,  # Convidado
                is_public=False,
                persist=False,
            )
        self.assertEqual(ctx.exception.status_code, 413)
        self.assertIn("5 MB para convidados", ctx.exception.message)


if __name__ == "__main__":
    unittest.main()
