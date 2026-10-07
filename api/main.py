"""Servidor HTTP do Quiz - Ponto de entrada da aplicação"""
import sys
from pathlib import Path

# Garante que a raiz do repositório está no sys.path
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from http.server import ThreadingHTTPServer

from api.utils.config import HOST, PORT
from api.handlers.quiz_handler import QuizHandler
from api.database.migrations import run_migrations


def start_server():
    """Inicia o servidor HTTP na porta configurada"""
    print("Verificando banco de dados...")
    run_migrations()

    for port in range(PORT, PORT + 11):
        try:
            server = ThreadingHTTPServer((HOST, port), QuizHandler)
            display_host = "localhost" if HOST in ("0.0.0.0", "127.0.0.1") else HOST
            print(f"Servidor ativo em http://{display_host}:{port}")
            print("Banco: PostgreSQL | Upload: TXT, PDF, DOCX")
            print("Pressione Ctrl+C para encerrar.")
            server.serve_forever()
            return
        except OSError as error:
            if error.errno not in (10013, 10048, 13, 98):
                raise

    raise OSError(
        f"Nao foi possivel abrir as portas {PORT}-{PORT + 10}. "
        f"Verifique se ha outro processo em execucao ou defina PORT."
    )


if __name__ == "__main__":
    start_server()

# Compatibilidade com a Vercel caso inspecione api/main.py
class handler(QuizHandler):
    pass
