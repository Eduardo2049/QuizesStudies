"""
Handler HTTP Refatorado - Usa Controllers/Services/Repositories
Segue padrão Spring @RestController
"""
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
import json

from api.utils.config import WEB_DIR, DEBUG
from api.controllers.quiz_controller import QuizController, UploadController
from api.exceptions.quiz_exceptions import QuizAPIException
from api.middleware.http_middleware import HTTPMiddleware, ResponseFormatter
from api.utils.validators import AnswerValidator, MarkdownValidator


class QuizHandler(BaseHTTPRequestHandler):
    """Handler HTTP com padrão Spring + Middleware"""

    def __init__(self, *args, **kwargs):
        self.quiz_controller = QuizController()
        self.upload_controller = UploadController()
        super().__init__(*args, **kwargs)

    def do_OPTIONS(self):
        """Handle CORS preflight"""
        HTTPMiddleware.handle_preflight(self)

    def do_GET(self):
        """Handle GET requests"""
        request = urlparse(self.path)
        query = parse_qs(request.query)

        try:
            # /api/quizzes
            if request.path == "/api/quizzes":
                response = self.quiz_controller.get_quizzes()
                status, data = ResponseFormatter.success(response["data"])
                HTTPMiddleware.send_json_response(self, status, data)
                return

            # /api/quiz?source=...
            if request.path == "/api/quiz":
                source_name = query.get("source", [None])[0]
                response = self.quiz_controller.get_quiz(source_name)
                status, data = ResponseFormatter.success(response["data"])
                HTTPMiddleware.send_json_response(self, status, data)
                return

            # Serve HTML principal
            if request.path in ("/", "/index.html"):
                try:
                    content = (WEB_DIR / "index.html").read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(content)))
                    self.end_headers()
                    self.wfile.write(content)
                except FileNotFoundError:
                    status, data = ResponseFormatter.not_found("index.html não encontrado")
                    HTTPMiddleware.send_json_response(self, status, data)
                return

            # Serve arquivos estáticos /web/*
            if request.path.startswith("/web/"):
                relative_path = request.path.removeprefix("/web/").split("?", 1)[0]
                static_file = (WEB_DIR / relative_path).resolve()
                web_root = WEB_DIR.resolve()

                if web_root in static_file.parents and static_file.is_file():
                    content_type = "text/css; charset=utf-8" if static_file.suffix == ".css" else \
                                  "application/javascript; charset=utf-8" if static_file.suffix == ".js" else \
                                  "application/octet-stream"
                    try:
                        content = static_file.read_bytes()
                        self.send_response(200)
                        self.send_header("Content-Type", content_type)
                        self.send_header("Content-Length", str(len(content)))
                        self.end_headers()
                        self.wfile.write(content)
                    except FileNotFoundError:
                        status, data = ResponseFormatter.not_found("Arquivo não encontrado")
                        HTTPMiddleware.send_json_response(self, status, data)
                    return

            # Rota não encontrada
            status, data = ResponseFormatter.not_found(f"Rota {request.path} não encontrada")
            HTTPMiddleware.send_json_response(self, status, data)

        except QuizAPIException as e:
            status, data = ResponseFormatter.error(e.message, "QUIZ_ERROR", e.status_code)
            HTTPMiddleware.send_json_response(self, status, data)

    def do_POST(self):
        """Handle POST requests"""
        request = urlparse(self.path)

        try:
            # Parse JSON body
            length = int(self.headers.get("Content-Length", 0))
            if length == 0:
                status, data = ResponseFormatter.bad_request("Corpo da requisição vazio")
                HTTPMiddleware.send_json_response(self, status, data)
                return

            try:
                payload = json.loads(self.rfile.read(length))
            except json.JSONDecodeError:
                status, data = ResponseFormatter.bad_request("JSON inválido")
                HTTPMiddleware.send_json_response(self, status, data)
                return

            # /api/quiz/submit
            if request.path == "/api/quiz/submit":
                # Validar payload
                is_valid, error_msg = AnswerValidator.validate_submit_payload(payload)
                if not is_valid:
                    status, data = ResponseFormatter.bad_request(error_msg)
                    HTTPMiddleware.send_json_response(self, status, data)
                    return

                response = self.quiz_controller.submit_answers(payload)
                status, data = ResponseFormatter.success(response["data"])
                HTTPMiddleware.send_json_response(self, status, data)
                return

            # /api/upload (futuro)
            if request.path == "/api/upload":
                if "filename" not in payload or "content" not in payload:
                    status, data = ResponseFormatter.bad_request(
                        "filename e content são obrigatórios"
                    )
                    HTTPMiddleware.send_json_response(self, status, data)
                    return

                # Validar conteúdo
                is_valid, error_msg = MarkdownValidator.validate_markdown_content(
                    payload["content"]
                )
                if not is_valid:
                    status, data = ResponseFormatter.bad_request(f"Markdown inválido: {error_msg}")
                    HTTPMiddleware.send_json_response(self, status, data)
                    return

                response = self.upload_controller.upload_file(
                    payload["filename"],
                    payload["content"]
                )
                status, data = ResponseFormatter.created(response["data"], response["data"].get("message"))
                HTTPMiddleware.send_json_response(self, status, data)
                return

            # Rota não encontrada
            status, data = ResponseFormatter.not_found(f"Rota {request.path} não encontrada")
            HTTPMiddleware.send_json_response(self, status, data)

        except QuizAPIException as e:
            status, data = ResponseFormatter.error(e.message, "QUIZ_ERROR", e.status_code)
            HTTPMiddleware.send_json_response(self, status, data)
        except Exception as e:
            if DEBUG:
                print(f"❌ Erro inesperado: {str(e)}")
            status, data = ResponseFormatter.error(
                "Erro interno do servidor",
                "INTERNAL_ERROR",
                500
            )
            HTTPMiddleware.send_json_response(self, status, data)

    def log_message(self, format, *args):
        """Suprime logs padrão do servidor"""
        if DEBUG:
            print(f"📡 {self.command} {self.path}")
        return
