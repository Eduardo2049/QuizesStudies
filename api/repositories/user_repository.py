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
