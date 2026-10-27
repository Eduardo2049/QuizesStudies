"""Exceções de domínio da API"""


class QuizAPIException(Exception):
    """Exceção base — carrega status HTTP, mensagem legível e código de erro estável.

    O `error_code` vai no campo "error" da resposta JSON para o cliente decidir o que
    fazer (ex.: abrir o modal de login em AUTH_REQUIRED) sem depender do texto.
    """
    def __init__(self, message: str, status_code: int = 400, error_code: str = "QUIZ_ERROR"):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        super().__init__(message)


class AuthOrGuestRequired(QuizAPIException):
    """Ação que exige conta ou sessão de convidado (ex.: usar a IA)."""
    def __init__(self, message: str = "Entre na sua conta ou continue como convidado para usar a IA."):
        super().__init__(message, 401, "AUTH_REQUIRED")


class GuestAILimitReached(QuizAPIException):
    """Convidado esgotou os usos gratuitos de IA da janela atual."""
    def __init__(self, limit: int, retry_after: int):
        self.retry_after = max(1, int(retry_after))
        hours = max(1, round(self.retry_after / 3600))
        when = "em cerca de 1 hora" if hours == 1 else f"em cerca de {hours} horas"
        message = (
            f"Você já usou as {limit} gerações gratuitas com IA do modo convidado. "
            f"Crie uma conta grátis para continuar agora ou volte {when}."
        )
        super().__init__(message, 403, "GUEST_AI_LIMIT_REACHED")


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
