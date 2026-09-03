"""Validadores de payload HTTP"""
from api.exceptions.quiz_exceptions import InvalidAnswersFormat


class AnswerValidator:
    """Valida payload de submissão de respostas do quiz"""

    @staticmethod
    def validate_submit_payload(payload: dict) -> tuple[bool, str]:
        """
        Verifica se o payload de submit é válido.

        Returns:
            (True, '') ou (False, mensagem_de_erro)
        """
        if not isinstance(payload, dict):
            return False, "Payload deve ser um objeto JSON"

        if "answers" not in payload:
            return False, "Campo 'answers' é obrigatório"

        answers = payload.get("answers")
        if not isinstance(answers, dict):
            return False, "answers deve ser um dicionário"

        if not answers:
            return False, "Pelo menos uma resposta é obrigatória"

        for q_id, answer_idx in answers.items():
            if isinstance(q_id, str):
                try:
                    int(q_id)
                except ValueError:
                    return False, f"ID da questão inválido: {q_id}"

            if not isinstance(answer_idx, int) or answer_idx < 0:
                return False, f"Índice de resposta inválido para questão {q_id}: deve ser inteiro >= 0"

        return True, ""
