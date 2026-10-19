"""
Vercel Serverless Function Entry Point
Exporta o QuizHandler compatível com a infraestrutura serverless da Vercel.
"""
import sys
from pathlib import Path

# Garante que a raiz do repositório está no sys.path para importação do pacote 'api'
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from api.handlers.quiz_handler import QuizHandler, _ensure_migrations

# Executa migrações no startup do serverless (cria tabelas e admin se não existirem).
# Usa o mesmo guard do handler: chamar run_migrations() direto deixava a flag
# desligada e a primeira requisição /api/* rodava tudo de novo.
_ensure_migrations()

# Vercel espera uma classe chamada 'handler' herdando de BaseHTTPRequestHandler.
# NÃO defina 'app' ou 'application', pois a Vercel interpretaria como WSGI/ASGI e falharia.
class handler(QuizHandler):
    pass
