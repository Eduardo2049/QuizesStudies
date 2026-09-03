"""
Vercel Serverless Function Entry Point
Exporta o QuizHandler compatível com a infraestrutura serverless da Vercel.
"""
from api.handlers.quiz_handler import QuizHandler
from api.database.migrations import run_migrations

# Executa migrações no startup do serverless (cria tabelas e admin se não existirem)
try:
    run_migrations()
except Exception as e:
    print(f"[vercel] Aviso ao executar migrations na inicialização: {e}")

# Vercel espera 'handler' ou 'app'
handler = QuizHandler

