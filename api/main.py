"""Servidor HTTP do Quiz - Ponto de entrada da aplicação"""
from http.server import ThreadingHTTPServer

from api.utils.config import HOST, PORT
from api.handlers.quiz_handler import QuizHandler


def start_server():
    """Inicia o servidor HTTP na porta configurada"""
    for port in range(PORT, PORT + 11):
        try:
            server = ThreadingHTTPServer((HOST, port), QuizHandler)
            display_host = "localhost" if HOST in ("0.0.0.0", "127.0.0.1") else HOST
            print(f"🚀 Servidor Quiz ativo em http://{display_host}:{port}")
            print(f"   Modo: Spring Pattern + Middleware")
            print(f"   Pressione Ctrl+C para encerrar.")
            server.serve_forever()
            return
        except OSError as error:
            # Tratamento de portas em uso (Windows: 10013, 10048; Unix: 13, 98)
            if error.errno not in (10013, 10048, 13, 98):
                raise

    raise OSError(
        f"✗ Não foi possível abrir as portas {PORT}-{PORT + 10}. "
        f"Verifique se há outro processo em execução ou defina a variável PORT/QUIZ_PORT."
    )


if __name__ == "__main__":
    start_server()
