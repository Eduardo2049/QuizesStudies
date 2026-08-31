"""
Validadores centralizados - Padrão Spring @Validator
"""
from api.exceptions.quiz_exceptions import (
    InvalidAnswersFormat,
    InvalidJSONError,
)


class AnswerValidator:
    """Validador para respostas de quiz"""

    @staticmethod
    def validate_submit_payload(payload: dict) -> tuple[bool, str]:
        """
        Valida payload de submissão de respostas.
        
        Args:
            payload (dict): Payload a validar
            
        Returns:
            tuple[bool, str]: (válido, mensagem_erro)
        """
        if not isinstance(payload, dict):
            return False, "Payload deve ser um objeto JSON"

        if "answers" not in payload:
            return False, "Campo 'answers' é obrigatório"

        answers = payload.get("answers")
        if not isinstance(answers, dict):
            return False, "answers deve ser um dicionário"

        if len(answers) == 0:
            return False, "Pelo menos uma resposta é obrigatória"

        # Validar cada resposta
        for q_id, answer_idx in answers.items():
            try:
                int(q_id) if isinstance(q_id, str) else q_id
            except ValueError:
                return False, f"ID da questão inválido: {q_id}"

            if not isinstance(answer_idx, int) or answer_idx < 0 or answer_idx > 3:
                return False, f"Resposta inválida para questão {q_id}: deve ser 0-3"

        return True, ""

    @staticmethod
    def validate_answer_format(answers: dict) -> None:
        """
        Lança exceção se formato inválido.
        
        Args:
            answers (dict): Dicionário de respostas
            
        Raises:
            InvalidAnswersFormat: Se formato inválido
        """
        if not isinstance(answers, dict):
            raise InvalidAnswersFormat()


class MarkdownValidator:
    """Validador para conteúdo Markdown"""

    @staticmethod
    def validate_markdown_content(content: str) -> tuple[bool, str]:
        """
        Valida estrutura básica do Markdown.
        
        Args:
            content (str): Conteúdo a validar
            
        Returns:
            tuple[bool, str]: (válido, mensagem_erro)
        """
        if not content or len(content.strip()) == 0:
            return False, "Conteúdo não pode estar vazio"

        # Verificar estrutura básica
        if "**1.**" not in content:
            return False, "Deve ter pelo menos uma questão (**1.**)"

        if "# Gabarito" not in content:
            return False, "Deve ter seção '# Gabarito'"

        return True, ""
