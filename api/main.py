"""Servidor HTTP do Quiz - Ponto de entrada"""
from http.server import ThreadingHTTPServer

from api.utils.config import HOST, PORT
from api.handlers.quiz_handler_v2 import QuizHandler


def start_server():
    """Inicia o servidor HTTP na porta disponível"""
    
    for port in range(PORT, PORT + 11):
        try:
            server = ThreadingHTTPServer((HOST, port), QuizHandler)
            print(f"✓ Quiz online em http://localhost:{port}")
            print(f"  Arquitetura: Spring Pattern + Middleware")
            server.serve_forever()
            return
        except OSError as error:
            # errno 10013 (Windows), 10048 (Windows - port in use), 13 (Linux), 98 (Linux - port in use)
            if error.errno not in (10013, 10048, 13, 98):
                raise

    raise OSError(
        f"✗ Não foi possível abrir as portas {PORT}-{PORT + 10}. "
        f"Feche outro servidor ou defina QUIZ_PORT."
    )


if __name__ == "__main__":
    start_server()
