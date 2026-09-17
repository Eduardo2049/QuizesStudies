"""Servidor HTTP do Quiz - Ponto de entrada da aplicação"""
from http.server import ThreadingHTTPServer

from api.utils.config import HOST, PORT
from api.handlers.quiz_handler import QuizHandler
from api.database.migrations import run_migrations


def start_server():
    """Inicia o servidor HTTP na porta configurada"""
    print("Verificando banco de dados...")
    run_migrations()

    try:
        from api.repositories.user_repository import UserRepository
        cleared = UserRepository().clear_all_sessions()
        if cleared > 0:
            print(f"Sessões anteriores invalidadas ({cleared} ativas removidas). Novo login necessário.")
    except Exception:
        pass

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

