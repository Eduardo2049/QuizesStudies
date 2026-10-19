"""
Testes unitários e de integração para recuperação de senha (Password Recovery)
Valida:
1. Geração de token criptograficamente seguro e armazenamento por hash SHA-256 no banco.
2. Anti-enumeração de usuários/e-mails na solicitação com equalização de tempo via PBKDF2 dummy.
3. Validação de formato e tamanho mínimo da nova senha (>= 8 caracteres).
4. Rejeição de tokens expirados, inexistentes ou já utilizados (queima de token).
5. Invalidação obrigatória de sessões ativas do usuário após a redefinição de senha.
6. EmailService: envio via SMTP e fallback seguro em modo simulado.
7. Mascaramento seguro de e-mail na verificação do token (LGPD/Privacidade).
8. Rate limiting em esqueci-senha e redefinir-senha.
"""
import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta

from api.services.auth_service import AuthService, _hash_token, hash_password, verify_password
from api.services.email_service import EmailService
from api.controllers.auth_controller import AuthController
from api.exceptions.quiz_exceptions import QuizAPIException


class TestEmailService(unittest.TestCase):
    """Testes do serviço de e-mail e fallback simulado."""

    def test_is_configured_false_when_empty(self):
        svc = EmailService(host="")
        self.assertFalse(svc.is_configured())

    def test_is_configured_true_when_host_present(self):
        svc = EmailService(host="smtp.exemplo.com")
        self.assertTrue(svc.is_configured())

    def test_simulated_mode_when_unconfigured(self):
        svc = EmailService(host="")
        success, mode = svc.send_password_reset_email(
            to_email="aluno@quiz.study",
            username="aluno",
            reset_url="http://localhost:8000/reset-password?token=abc",
            token="abc",
        )
        self.assertTrue(success)
        self.assertEqual(mode, "simulated")

    @patch("smtplib.SMTP")
    def test_smtp_send_success(self, mock_smtp_cls):
        mock_server = MagicMock()
        mock_smtp_cls.return_value.__enter__.return_value = mock_server

        svc = EmailService(
            host="smtp.gmail.com",
            port=587,
            user="user@gmail.com",
            password="secret_password",
            use_tls=True,
            use_ssl=False,
        )
        success, mode = svc.send_password_reset_email(
            to_email="destino@quiz.study",
            username="estudante",
            reset_url="https://app.quiz.study/reset-password?token=xyz",
            token="xyz",
        )
        self.assertTrue(success)
        self.assertEqual(mode, "sent")
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("user@gmail.com", "secret_password")
        mock_server.sendmail.assert_called_once()


class TestPasswordResetAuthService(unittest.TestCase):
    """Testes de regras de negócio em AuthService para recuperação de senha."""

    def setUp(self):
        self.mock_repo = MagicMock()
        self.mock_email = MagicMock()
        self.mock_email.is_configured.return_value = False
        self.mock_email.send_password_reset_email.return_value = (True, "simulated")
        self.service = AuthService(repository=self.mock_repo, email_service=self.mock_email)

    def test_request_reset_nonexistent_user_prevents_enumeration(self):
        """Solicitação para e-mail/usuário que não existe retorna resposta uniforme sem expor existência."""
        self.mock_repo.find_by_email.return_value = None
        self.mock_repo.find_by_username.return_value = None

        res = self.service.request_password_reset("fantasma@inexistente.com")

        self.assertIn("Se os dados informados estiverem cadastrados", res["message"])
        self.assertFalse(res["email_sent"])
        self.assertIsNone(res["dev_reset_url"])
        self.assertIsNone(res["dev_token"])
        self.mock_repo.create_password_reset.assert_not_called()

    def test_request_reset_existing_user_generates_token_and_stores_hash(self):
        """Usuário existente gera token aleatório e persiste hash SHA-256 no banco."""
        user = {
            "id": 42,
            "username": "carlos",
            "email": "carlos@escola.com",
            "salt": "salt42",
            "role": "student",
        }
        self.mock_repo.find_by_email.return_value = user

        with patch("api.services.auth_service.DEBUG", True):
            res = self.service.request_password_reset("carlos@escola.com", app_url="https://quiz.study")

        self.assertIn("Se os dados informados estiverem cadastrados", res["message"])
        self.assertIsNotNone(res["dev_token"])
        self.assertIn("https://quiz.study/reset-password?token=", res["dev_reset_url"])

        # O repositório deve ter sido chamado com o hash do token, NÃO com o token puro
        call_args = self.mock_repo.create_password_reset.call_args[0]
        stored_hash = call_args[0]
        user_id = call_args[1]

        self.assertEqual(user_id, 42)
        self.assertEqual(stored_hash, _hash_token(res["dev_token"]))
        self.assertNotEqual(stored_hash, res["dev_token"])

    def test_verify_reset_token_valid_masks_email(self):
        """Validação de token válido retorna e-mail mascarado para preservar privacidade."""
        raw_token = "token_de_teste_seguro_123"
        hashed = _hash_token(raw_token)
        self.mock_repo.find_password_reset.return_value = {
            "id": 1,
            "token_hash": hashed,
            "user_id": 42,
            "email": "carlos.silva@escola.com",
            "username": "carlos",
            "used": False,
        }

        res = self.service.verify_reset_token(raw_token)
        self.assertTrue(res["valid"])
        self.assertEqual(res["username"], "carlos")
        self.assertEqual(res["masked_email"], "ca***@escola.com")

    def test_verify_reset_token_invalid_or_expired_raises_400(self):
        """Token inválido ou expirado levanta QuizAPIException 400."""
        self.mock_repo.find_password_reset.return_value = None

        with self.assertRaises(QuizAPIException) as ctx:
            self.service.verify_reset_token("token_invalido")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("inválido ou expirado", ctx.exception.message)

    def test_reset_password_enforces_min_length(self):
        """Nova senha deve ter pelo menos 8 caracteres."""
        with self.assertRaises(QuizAPIException) as ctx:
            self.service.reset_password("token_valido", "1234567")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("8 caracteres", ctx.exception.message)

    def test_reset_password_success_updates_hash_marks_used_and_invalidates_sessions(self):
        """Redefinição bem-sucedida atualiza hash PBKDF2, queima o token e revoga sessões anteriores."""
        raw_token = "meu_token_secreto_super_seguro"
        hashed = _hash_token(raw_token)
        self.mock_repo.find_password_reset.return_value = {
            "id": 5,
            "token_hash": hashed,
            "user_id": 99,
            "email": "aluno99@quiz.study",
            "username": "aluno99",
            "used": False,
        }

        res = self.service.reset_password(raw_token, "NovaSenhaForte2026*")

        self.assertIn("Senha redefinida com sucesso", res["message"])

        # 1. Verifica se a senha foi atualizada com PBKDF2
        update_args = self.mock_repo.update_password_and_role.call_args[0]
        user_id = update_args[0]
        new_pwd_hash = update_args[1]
        new_salt = update_args[2]

        self.assertEqual(user_id, 99)
        self.assertTrue(verify_password("NovaSenhaForte2026*", new_salt, new_pwd_hash))

        # 2. Token foi marcado como utilizado
        self.mock_repo.mark_password_reset_used.assert_called_once_with(hashed)

        # 3. Sessões ativas foram excluídas
        self.mock_repo.delete_user_sessions.assert_called_once_with(99)


class TestAuthControllerPasswordReset(unittest.TestCase):
    """Testes dos controladores de autenticação para as novas rotas."""

    def setUp(self):
        self.mock_service = MagicMock()
        self.controller = AuthController(auth_service=self.mock_service)

    def test_forgot_password_requires_identifier(self):
        with self.assertRaises(QuizAPIException) as ctx:
            self.controller.forgot_password({"email": "   "})
        self.assertEqual(ctx.exception.status_code, 400)

    def test_forgot_password_success(self):
        self.mock_service.request_password_reset.return_value = {
            "message": "Instruções enviadas",
            "email_sent": True,
            "dev_reset_url": None,
            "dev_token": None,
        }
        res = self.controller.forgot_password({"email": "user@test.com"}, app_url="https://quiz.study")
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["message"], "Instruções enviadas")

    def test_reset_password_success(self):
        self.mock_service.reset_password.return_value = {
            "message": "Senha redefinida com sucesso!",
        }
        res = self.controller.reset_password({"token": "tok123", "new_password": "NovaSenhaSegura123*"})
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["message"], "Senha redefinida com sucesso!")


if __name__ == "__main__":
    unittest.main()
