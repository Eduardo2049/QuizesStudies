"""
Tratamento centralizado de exceções - Padrão Spring @ExceptionHandler
"""


class QuizAPIException(Exception):
    """Exceção base da API"""
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class QuizNotFound(QuizAPIException):
    """Quiz não encontrado"""
    def __init__(self, source_name: str = None):
        msg = f"Questionario nao encontrado: {source_name}" if source_name else "Quiz não encontrado"
        super().__init__(msg, 404)


class InvalidAnswersFormat(QuizAPIException):
    """Formato de respostas inválido"""
    def __init__(self):
        super().__init__(
            "answers deve ser um objeto com id da questao e indice da alternativa",
            400
        )


class InvalidMarkdownFormat(QuizAPIException):
    """Arquivo Markdown mal formatado"""
    def __init__(self, question_id: int = None):
        if question_id:
            msg = f"Questao {question_id} esta sem alternativas ou gabarito no Markdown"
        else:
            msg = "Nenhuma questao encontrada no Markdown"
        super().__init__(msg, 400)


class FileNotFoundError(QuizAPIException):
    """Arquivo não encontrado"""
    def __init__(self, path: str):
        super().__init__(f"Arquivo nao encontrado: {path}", 404)


class InvalidJSONError(QuizAPIException):
    """JSON inválido"""
    def __init__(self):
        super().__init__("JSON inválido", 400)


class RouteNotFoundError(QuizAPIException):
    """Rota não encontrada"""
    def __init__(self, path: str):
        super().__init__(f"Rota nao encontrada: {path}", 404)
