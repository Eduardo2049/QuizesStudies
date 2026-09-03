"""Exceções de domínio da API"""


class QuizAPIException(Exception):
    """Exceção base — carrega status HTTP e mensagem legível."""
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class QuizNotFound(QuizAPIException):
    def __init__(self, source_name: str = None):
        msg = f"Questionário não encontrado: {source_name}" if source_name else "Nenhum quiz cadastrado"
        super().__init__(msg, 404)


class InvalidAnswersFormat(QuizAPIException):
    def __init__(self):
        super().__init__("'answers' deve ser um objeto {id_questao: indice_alternativa}", 400)


class InvalidMarkdownFormat(QuizAPIException):
    def __init__(self, question_id: int = None):
        msg = (
            f"Questão {question_id} sem alternativas ou gabarito"
            if question_id else
            "Nenhuma questão encontrada no arquivo"
        )
        super().__init__(msg, 400)
