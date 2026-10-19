"""
Testes unitários de scripts/reset_database.py (sem banco).
Valida:
1. Ordem dos DELETEs respeita chaves estrangeiras e o escopo escolhido.
2. Escopo 'all' preserva o admin; escopo inválido é rejeitado.
3. Log do alvo nunca mostra usuário/senha da DATABASE_URL.
4. Sem --yes e sem terminal interativo, nada é executado.
5. Seed do admin pula PBKDF2 + UPDATE quando a senha já está sincronizada.
"""
import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch

from scripts import reset_database
from api.services.auth_service import AuthService, hash_password


class TestResetDatabaseScript(unittest.TestCase):

    def test_content_scope_deletes_children_before_parents(self):
        labels = [label for label, _, _ in reset_database.build_steps("content", "admin")]
        self.assertEqual(labels, ["quiz_attempts", "questions", "quizzes", "rate_limits"])

    def test_all_scope_adds_accounts_and_preserves_admin(self):
        steps = reset_database.build_steps("all", "chefe")
        labels = [label for label, _, _ in steps]
        self.assertEqual(labels[-3:], ["password_resets", "sessions", "users (exceto admin)"])
        _, sql, params = steps[-1]
        self.assertIn("<> LOWER(%s)", sql)
        self.assertEqual(params, ("chefe",))

    def test_no_drop_or_truncate(self):
        for scope in reset_database.SCOPES:
            for _, sql, _ in reset_database.build_steps(scope, "admin"):
                self.assertTrue(sql.startswith("DELETE FROM "), sql)

    def test_invalid_scope_rejected(self):
        with self.assertRaises(ValueError):
            reset_database.build_steps("tudo", "admin")

    def test_describe_target_hides_credentials(self):
        target = reset_database.describe_target("postgresql://user:segredo@ep-x.neon.tech:5432/quizdb?sslmode=require")
        self.assertEqual(target, "ep-x.neon.tech:5432/quizdb")
        self.assertNotIn("segredo", target)

    def test_count_sql_keeps_where_clause(self):
        sql = reset_database._count_sql("DELETE FROM users WHERE LOWER(username) <> LOWER(%s)")
        self.assertEqual(sql, "SELECT COUNT(*) AS n FROM users WHERE LOWER(username) <> LOWER(%s)")

    def test_refuses_without_confirmation_when_not_interactive(self):
        with patch.object(reset_database, "DATABASE_URL", "postgresql://u:p@localhost/db"), \
             patch.object(reset_database, "run") as mock_run, \
             patch("sys.stdin") as mock_stdin, \
             redirect_stdout(io.StringIO()):
            mock_stdin.isatty.return_value = False
            code = reset_database.main(["--scope", "all"])
        self.assertEqual(code, 1)
        mock_run.assert_not_called()

    def test_dry_run_needs_no_confirmation(self):
        with patch.object(reset_database, "DATABASE_URL", "postgresql://u:p@localhost/db"), \
             patch.object(reset_database, "run", return_value={"quizzes": 3}) as mock_run, \
             redirect_stdout(io.StringIO()) as out:
            code = reset_database.main(["--scope", "content", "--dry-run"])
        self.assertEqual(code, 0)
        mock_run.assert_called_once_with("content", True)
        self.assertIn("seriam apagadas", out.getvalue())
        self.assertNotIn(":p@", out.getvalue())


class TestSeedAdminSkipsWhenSynced(unittest.TestCase):

    def test_synced_admin_is_not_rewritten(self):
        pwd_hash, salt = hash_password("SenhaAdminForte123")
        repo = MagicMock()
        repo.find_by_username.return_value = {
            "id": 1, "username": "admin", "role": "admin", "salt": salt, "password_hash": pwd_hash,
        }
        with patch("api.services.auth_service.ADMIN_PASSWORD", "SenhaAdminForte123"):
            AuthService(repository=repo).seed_admin_if_needed()
        repo.update_password_and_role.assert_not_called()
        repo.create_user.assert_not_called()

    def test_changed_admin_password_is_resynced(self):
        pwd_hash, salt = hash_password("SenhaAntiga123")
        repo = MagicMock()
        repo.find_by_username.return_value = {
            "id": 1, "username": "admin", "role": "admin", "salt": salt, "password_hash": pwd_hash,
        }
        with patch("api.services.auth_service.ADMIN_PASSWORD", "SenhaNova12345"):
            AuthService(repository=repo).seed_admin_if_needed()
        repo.update_password_and_role.assert_called_once()


if __name__ == "__main__":
    unittest.main()
