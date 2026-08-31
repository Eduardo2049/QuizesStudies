"""
Handler HTTP - Consolidado e Simplificado

Usa padrão Spring Pattern com Middleware
Remova duplicatas: tudo agora é gerenciado por controllers/services/repositories
"""

# Redirect para evitar duplicação
from api.handlers.quiz_handler_v2 import QuizHandler

__all__ = ["QuizHandler"]
