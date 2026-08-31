"""
Handler HTTP - Versão Consolidada

DEPRECATED: Usar quiz_handler_v2.py que usa padrão Spring Pattern
Este arquivo é mantido apenas para compatibilidade com referências antigas.

Redirecione todos os imports para quiz_handler_v2:
  from api.handlers.quiz_handler_v2 import QuizHandler
"""

# Para compatibilidade (redirect)
from api.handlers.quiz_handler_v2 import QuizHandler

__all__ = ["QuizHandler"]
