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

from api.handlers.quiz_handler import QuizHandler
from api.database.migrations import run_migrations

# Executa migrações no startup do serverless (cria tabelas e admin se não existirem)
try:
    run_migrations()
except Exception as e:
    print(f"[vercel] Aviso ao executar migrations na inicialização: {e}")

# Vercel espera uma classe chamada 'handler' herdando de BaseHTTPRequestHandler.
# NÃO defina 'app' ou 'application', pois a Vercel interpretaria como WSGI/ASGI e falharia.
class handler(QuizHandler):
    pass
