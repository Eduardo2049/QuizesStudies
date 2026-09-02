"""
Handler HTTP Principal - Arquitetura Consolidada (Spring Pattern + Middleware)
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
    """Handler HTTP principal com padrão Controller + Middleware"""

    def __init__(self, *args, **kwargs):
        self.quiz_controller = QuizController()
        self.upload_controller = UploadController()
        super().__init__(*args, **kwargs)

    def do_OPTIONS(self):
        """Handle CORS preflight requests"""
        HTTPMiddleware.handle_preflight(self)

    def do_GET(self):
        """Handle GET requests"""
        request = urlparse(self.path)
        query = parse_qs(request.query)

        try:
            # 1. API: Listar quizzes
            if request.path == "/api/quizzes":
                response = self.quiz_controller.get_quizzes()
                status, data = ResponseFormatter.success(response["data"])
                HTTPMiddleware.send_json_response(self, status, data)
                return

            # 2. API: Carregar um quiz
            if request.path == "/api/quiz":
                source_name = query.get("source", [None])[0]
                response = self.quiz_controller.get_quiz(source_name)
                status, data = ResponseFormatter.success(response["data"])
                HTTPMiddleware.send_json_response(self, status, data)
                return

            # 3. Servir HTML principal
            if request.path in ("/", "/index.html"):
                index_file = WEB_DIR / "index.html"
                if index_file.is_file():
                    content = index_file.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(content)))
                    HTTPMiddleware.add_cors_headers(self)
                    self.end_headers()
                    self.wfile.write(content)
                else:
                    status, data = ResponseFormatter.not_found("index.html não encontrado")
                    HTTPMiddleware.send_json_response(self, status, data)
                return

            # 4. Servir arquivos estáticos /web/*
            if request.path.startswith("/web/"):
                relative_path = request.path.removeprefix("/web/").split("?", 1)[0]
                static_file = (WEB_DIR / relative_path).resolve()
                web_root = WEB_DIR.resolve()

                # Prevenção de Path Traversal
                if web_root in static_file.parents and static_file.is_file():
                    content_type = "text/css; charset=utf-8" if static_file.suffix == ".css" else \
                                  "application/javascript; charset=utf-8" if static_file.suffix == ".js" else \
                                  "text/html; charset=utf-8" if static_file.suffix == ".html" else \
                                  "image/svg+xml" if static_file.suffix == ".svg" else \
                                  "image/png" if static_file.suffix == ".png" else \
                                  "application/octet-stream"
                    try:
                        content = static_file.read_bytes()
                        self.send_response(200)
                        self.send_header("Content-Type", content_type)
                        self.send_header("Content-Length", str(len(content)))
                        HTTPMiddleware.add_cors_headers(self)
                        HTTPMiddleware.add_cache_headers(self, cache=True)
                        self.end_headers()
                        self.wfile.write(content)
                    except Exception as e:
                        status, data = ResponseFormatter.error(f"Erro ao ler arquivo: {str(e)}", "FILE_ERROR", 500)
                        HTTPMiddleware.send_json_response(self, status, data)
                    return
                else:
                    status, data = ResponseFormatter.not_found("Arquivo estático não encontrado")
                    HTTPMiddleware.send_json_response(self, status, data)
                    return

            # 5. Rota não encontrada
            status, data = ResponseFormatter.not_found(f"Rota {request.path} não encontrada")
            HTTPMiddleware.send_json_response(self, status, data)

        except QuizAPIException as e:
            status, data = ResponseFormatter.error(e.message, "QUIZ_ERROR", e.status_code)
            HTTPMiddleware.send_json_response(self, status, data)
        except Exception as e:
            if DEBUG:
                print(f"❌ Erro GET inesperado: {str(e)}")
            status, data = ResponseFormatter.error("Erro interno do servidor", "INTERNAL_ERROR", 500)
            HTTPMiddleware.send_json_response(self, status, data)

    def do_POST(self):
        """Handle POST requests"""
        request = urlparse(self.path)

        try:
            length = int(self.headers.get("Content-Length", 0))
            if length == 0:
                status, data = ResponseFormatter.bad_request("Corpo da requisição vazio")
                HTTPMiddleware.send_json_response(self, status, data)
                return

            try:
                payload = json.loads(self.rfile.read(length))
            except json.JSONDecodeError:
                status, data = ResponseFormatter.bad_request("JSON inválido no corpo da requisição")
                HTTPMiddleware.send_json_response(self, status, data)
                return

            # 1. Submissão de respostas
            if request.path == "/api/quiz/submit":
                is_valid, error_msg = AnswerValidator.validate_submit_payload(payload)
                if not is_valid:
                    status, data = ResponseFormatter.bad_request(error_msg)
                    HTTPMiddleware.send_json_response(self, status, data)
                    return

                response = self.quiz_controller.submit_answers(payload)
                status, data = ResponseFormatter.success(response["data"])
                HTTPMiddleware.send_json_response(self, status, data)
                return

            # 2. Upload de novo quiz
            if request.path == "/api/upload":
                if "filename" not in payload or "content" not in payload:
                    status, data = ResponseFormatter.bad_request("filename e content são obrigatórios")
                    HTTPMiddleware.send_json_response(self, status, data)
                    return

                is_valid, error_msg = MarkdownValidator.validate_markdown_content(payload["content"])
                if not is_valid:
                    status, data = ResponseFormatter.bad_request(f"Markdown inválido: {error_msg}")
                    HTTPMiddleware.send_json_response(self, status, data)
                    return

                response = self.upload_controller.upload_file(payload["filename"], payload["content"])
                status, data = ResponseFormatter.created(response["data"], response["data"].get("message"))
                HTTPMiddleware.send_json_response(self, status, data)
                return

            # 3. Rota não encontrada
            status, data = ResponseFormatter.not_found(f"Rota {request.path} não encontrada")
            HTTPMiddleware.send_json_response(self, status, data)

        except QuizAPIException as e:
            status, data = ResponseFormatter.error(e.message, "QUIZ_ERROR", e.status_code)
            HTTPMiddleware.send_json_response(self, status, data)
        except Exception as e:
            if DEBUG:
                print(f"❌ Erro POST inesperado: {str(e)}")
            status, data = ResponseFormatter.error("Erro interno do servidor", "INTERNAL_ERROR", 500)
            HTTPMiddleware.send_json_response(self, status, data)

    def log_message(self, format, *args):
        """Custom logging para modo debug"""
        if DEBUG:
            print(f"📡 {self.command} {self.path}")
