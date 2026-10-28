"""
Repository de Usuários e Sessões no PostgreSQL
"""
from datetime import datetime, timedelta
from api.database.connection import get_cursor


class UserRepository:
    """Acesso a dados de usuários e sessões"""

    def find_by_username(self, username: str) -> dict | None:
        with get_cursor() as cur:
            cur.execute("SELECT * FROM users WHERE LOWER(username) = LOWER(%s)", (username,))
            row = cur.fetchone()
            return dict(row) if row else None

    def find_by_email(self, email: str) -> dict | None:
        with get_cursor() as cur:
            cur.execute("SELECT * FROM users WHERE LOWER(email) = LOWER(%s)", (email,))
            row = cur.fetchone()
            return dict(row) if row else None

    def find_by_id(self, user_id: int) -> dict | None:
        with get_cursor() as cur:
            cur.execute("SELECT id, username, email, role, created_at FROM users WHERE id = %s", (user_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def count_users(self) -> int:
        with get_cursor() as cur:
            cur.execute("SELECT COUNT(*) as count FROM users")
            row = cur.fetchone()
            return row["count"] if row else 0

    def create_user(self, username: str, email: str, password_hash: str, salt: str, role: str = "student") -> dict:
        with get_cursor() as cur:
            cur.execute("""
                INSERT INTO users (username, email, password_hash, salt, role)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, username, email, role, created_at
            """, (username, email, password_hash, salt, role))
            return dict(cur.fetchone())

    def update_password_and_role(self, user_id: int, password_hash: str, salt: str, role: str = None) -> None:
        """Atualiza a senha e opcionalmente o papel (role) do usuário."""
        with get_cursor() as cur:
            if role:
                cur.execute("""
                    UPDATE users
                    SET password_hash = %s, salt = %s, role = %s
                    WHERE id = %s
                """, (password_hash, salt, role, user_id))
            else:
                cur.execute("""
                    UPDATE users
                    SET password_hash = %s, salt = %s
                    WHERE id = %s
                """, (password_hash, salt, user_id))

    # ─── Direitos do titular (LGPD) ──────────────────────────────────────────
    def export_user_data(self, user_id: int) -> dict:
        """Tudo o que o banco guarda sobre a pessoa, sem hashes de senha nem tokens."""
        with get_cursor() as cur:
            cur.execute("SELECT id, username, email, role, created_at FROM users WHERE id = %s", (user_id,))
            user = cur.fetchone()
            if not user:
                return {}
            cur.execute("""
                SELECT q.id, q.name, q.label, q.original_filename, q.file_type, q.ai_generated,
                       q.is_public, q.created_at
                FROM quizzes q WHERE q.created_by = %s ORDER BY q.created_at
            """, (user_id,))
            quizzes = [dict(r) for r in cur.fetchall()]
            for quiz in quizzes:
                cur.execute("""
                    SELECT question_number, section, context, question, options, answer, explanation
                    FROM questions WHERE quiz_id = %s ORDER BY question_number
                """, (quiz["id"],))
                quiz["questions"] = [dict(r) for r in cur.fetchall()]
            cur.execute("""
                SELECT quiz_name, score, total, percentage, wrong_question_ids, created_at
                FROM quiz_attempts WHERE user_id = %s ORDER BY created_at
            """, (user_id,))
            attempts = [dict(r) for r in cur.fetchall()]
            cur.execute("SELECT created_at, expires_at FROM sessions WHERE user_id = %s ORDER BY created_at", (user_id,))
            sessions = [dict(r) for r in cur.fetchall()]
        return {"user": dict(user), "quizzes": quizzes, "attempts": attempts, "sessions": sessions}

    def delete_user_and_data(self, user_id: int) -> None:
        """Exclui a conta e os dados pessoais numa única transação.

        Simulados privados da pessoa são apagados (com as questões, em cascata);
        simulados públicos continuam na plataforma sem autor. Sessões, links de
        recuperação e histórico de tentativas caem em cascata com o usuário.
        """
        with get_cursor() as cur:
            cur.execute("DELETE FROM quizzes WHERE created_by = %s AND is_public = FALSE", (user_id,))
            cur.execute("UPDATE quizzes SET created_by = NULL WHERE created_by = %s", (user_id,))
            cur.execute("DELETE FROM users WHERE id = %s", (user_id,))

    # ─── Sessões ──────────────────────────────────────────────────────────────

    def create_session(self, token: str, user_id: int, duration_days: int = 7) -> dict:
        expires_at = datetime.now() + timedelta(days=duration_days)
        with get_cursor() as cur:
            cur.execute("""
                INSERT INTO sessions (token, user_id, expires_at)
                VALUES (%s, %s, %s)
                RETURNING token, user_id, expires_at, created_at
            """, (token, user_id, expires_at))
            return dict(cur.fetchone())

    def find_session_user(self, token: str) -> dict | None:
        """Busca o usuário associado a um token válido e não expirado."""
        with get_cursor() as cur:
            cur.execute("""
                SELECT u.id, u.username, u.email, u.role, s.expires_at
                FROM sessions s
                JOIN users u ON s.user_id = u.id
                WHERE s.token = %s AND s.expires_at > NOW()
            """, (token,))
            row = cur.fetchone()
            return dict(row) if row else None

    def delete_session(self, token: str) -> bool:
        with get_cursor() as cur:
            cur.execute("DELETE FROM sessions WHERE token = %s RETURNING token", (token,))
            return cur.fetchone() is not None

    def cleanup_expired_sessions(self) -> int:
        with get_cursor() as cur:
            cur.execute("DELETE FROM sessions WHERE expires_at <= NOW()")
            return cur.rowcount

    def clear_all_sessions(self) -> int:
        """Remove todas as sessões ativas do banco (usado ao resetar a aplicação)."""
        with get_cursor() as cur:
            cur.execute("DELETE FROM sessions")
            return cur.rowcount

    def delete_user_sessions(self, user_id: int) -> int:
        """Remove todas as sessões ativas de um usuário (ex: após redefinir senha)."""
        with get_cursor() as cur:
            cur.execute("DELETE FROM sessions WHERE user_id = %s", (user_id,))
            return cur.rowcount

    # ─── Recuperação de Senha ────────────────────────────────────────────────

    def create_password_reset(self, token_hash: str, user_id: int, expires_minutes: int = 30) -> dict:
        """Registra solicitação de recuperação de senha e invalida tokens anteriores não usados."""
        expires_at = datetime.now() + timedelta(minutes=expires_minutes)
        with get_cursor() as cur:
            cur.execute("UPDATE password_resets SET used = TRUE WHERE user_id = %s AND used = FALSE", (user_id,))
            cur.execute("""
                INSERT INTO password_resets (token_hash, user_id, expires_at, used)
                VALUES (%s, %s, %s, FALSE)
                RETURNING id, token_hash, user_id, expires_at, used, created_at
            """, (token_hash, user_id, expires_at))
            return dict(cur.fetchone())

    def find_password_reset(self, token_hash: str) -> dict | None:
        """Busca solicitação válida, não expirada e não utilizada pelo hash do token."""
        with get_cursor() as cur:
            cur.execute("""
                SELECT pr.id, pr.token_hash, pr.user_id, pr.expires_at, pr.used, pr.created_at,
                       u.email, u.username
                FROM password_resets pr
                JOIN users u ON pr.user_id = u.id
                WHERE pr.token_hash = %s AND pr.used = FALSE AND pr.expires_at > NOW()
            """, (token_hash,))
            row = cur.fetchone()
            return dict(row) if row else None

    def mark_password_reset_used(self, token_hash: str) -> bool:
        """Marca a solicitação como utilizada após a redefinição de senha."""
        with get_cursor() as cur:
            cur.execute("""
                UPDATE password_resets
                SET used = TRUE
                WHERE token_hash = %s AND used = FALSE
                RETURNING id
            """, (token_hash,))
            return cur.fetchone() is not None

    def cleanup_expired_resets(self) -> int:
        """Remove solicitações expiradas ou já utilizadas com mais de 7 dias."""
        with get_cursor() as cur:
            cur.execute("""
                DELETE FROM password_resets
                WHERE expires_at <= NOW() OR (used = TRUE AND created_at <= NOW() - INTERVAL '7 days')
            """)
            return cur.rowcount

