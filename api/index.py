"""
Vercel Serverless Function Entry Point
Exporta o QuizHandler compatível com a infraestrutura serverless da Vercel.
"""
from api.handlers.quiz_handler import QuizHandler

# Vercel espera 'handler' ou 'app'
handler = QuizHandler
