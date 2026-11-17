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

    def create_user(
        self,
        username: str,
        email: str,
        password_hash: str,
        salt: str,
        role: str = "student",
        email_verified: bool = False,
    ) -> dict:
        with get_cursor() as cur:
            cur.execute("""
                INSERT INTO users (username, email, password_hash, salt, role, email_verified)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id, username, email, role, email_verified, created_at
            """, (username, email, password_hash, salt, role, email_verified))
            return dict(cur.fetchone())

    def update_email(self, user_id: int, email: str) -> None:
        with get_cursor() as cur:
            cur.execute("UPDATE users SET email = %s WHERE id = %s", (email, user_id))

    def mark_email_verified(self, user_id: int) -> None:
        with get_cursor() as cur:
            cur.execute("UPDATE users SET email_verified = TRUE WHERE id = %s", (user_id,))

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
            cur.execute(
                "SELECT id, username, email, email_verified, role, created_at FROM users WHERE id = %s", (user_id,)
            )
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
            # Códigos por e-mail não têm chave estrangeira (são ligados ao endereço): saem aqui
            cur.execute(
                "DELETE FROM email_codes WHERE email = (SELECT LOWER(email) FROM users WHERE id = %s)", (user_id,)
            )
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
                SELECT u.id, u.username, u.email, u.role, u.email_verified, s.expires_at
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

    # ─── Confirmação de e-mail ───────────────────────────────────────────────

    def create_email_verification(self, token_hash: str, user_id: int, expires_hours: int = 24) -> None:
        """Registra um link de confirmação e invalida os anteriores ainda não usados."""
        expires_at = datetime.now() + timedelta(hours=expires_hours)
        with get_cursor() as cur:
            cur.execute("UPDATE email_verifications SET used = TRUE WHERE user_id = %s AND used = FALSE", (user_id,))
            cur.execute("""
                INSERT INTO email_verifications (token_hash, user_id, expires_at, used)
                VALUES (%s, %s, %s, FALSE)
            """, (token_hash, user_id, expires_at))

    def consume_email_verification(self, token_hash: str) -> int | None:
        """Queima o link (uma vez só, de forma atômica) e marca o e-mail como confirmado."""
        with get_cursor() as cur:
            cur.execute("""
                UPDATE email_verifications
                SET used = TRUE
                WHERE token_hash = %s AND used = FALSE AND expires_at > NOW()
                RETURNING user_id
            """, (token_hash,))
            row = cur.fetchone()
            if not row:
                return None
            cur.execute("UPDATE users SET email_verified = TRUE WHERE id = %s", (row["user_id"],))
            return row["user_id"]

    # ─── Códigos de 6 dígitos por e-mail (login sem senha, exclusão da conta) ──
    # O e-mail chega aqui já em minúsculas (AuthService normaliza). Os horários usam o
    # NOW() do banco, como a comparação de validade, para não depender do fuso do servidor.

    def create_email_code(self, email: str, purpose: str, code_hash: str, ttl_minutes: int) -> dict:
        """Grava um código novo e invalida os anteriores ainda não usados do mesmo e-mail e finalidade."""
        with get_cursor() as cur:
            # Limpeza oportunista: códigos vencidos há mais de um dia não servem nem para contar envios
            cur.execute("DELETE FROM email_codes WHERE expires_at <= NOW() - INTERVAL '1 day'")
            cur.execute(
                "UPDATE email_codes SET used = TRUE WHERE email = %s AND purpose = %s AND used = FALSE",
                (email, purpose),
            )
            cur.execute("""
                INSERT INTO email_codes (email, purpose, code_hash, expires_at)
                VALUES (%s, %s, %s, NOW() + (%s * INTERVAL '1 minute'))
                RETURNING id, email, purpose, expires_at, created_at
            """, (email, purpose, code_hash, int(ttl_minutes)))
            return dict(cur.fetchone())

    def email_code_send_stats(self, email: str, purpose: str) -> dict:
        """Quantos códigos saíram na última hora e há quantos segundos saiu o último."""
        with get_cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) AS sent_last_hour,
                       EXTRACT(EPOCH FROM (NOW() - MAX(created_at))) AS seconds_since_last
                FROM email_codes
                WHERE email = %s AND purpose = %s AND created_at > NOW() - INTERVAL '1 hour'
            """, (email, purpose))
            row = dict(cur.fetchone() or {})
        since = row.get("seconds_since_last")
        return {
            "sent_last_hour": int(row.get("sent_last_hour") or 0),
            "seconds_since_last": float(since) if since is not None else None,
        }

    def take_email_code_attempt(self, email: str, purpose: str, max_attempts: int) -> dict | None:
        """Conta um palpite no código válido mais recente e devolve o hash guardado.

        O UPDATE é atômico: palpites simultâneos não passam do limite de tentativas.
        Devolve None se não há código válido ou se as tentativas acabaram.
        """
        with get_cursor() as cur:
            cur.execute("""
                UPDATE email_codes SET attempts = attempts + 1
                WHERE id = (
                    SELECT id FROM email_codes
                    WHERE email = %s AND purpose = %s AND used = FALSE AND expires_at > NOW()
                    ORDER BY created_at DESC, id DESC
                    LIMIT 1
                ) AND attempts < %s
                RETURNING id, code_hash, attempts
            """, (email, purpose, int(max_attempts)))
            row = cur.fetchone()
            return dict(row) if row else None

    def consume_email_code(self, code_id: int) -> bool:
        """Queima o código (uma vez só): dois envios simultâneos do código certo geram uma sessão."""
        with get_cursor() as cur:
            cur.execute(
                "UPDATE email_codes SET used = TRUE WHERE id = %s AND used = FALSE RETURNING id",
                (code_id,),
            )
            return cur.fetchone() is not None

    def delete_email_codes(self, email: str) -> int:
        """Apaga os códigos de um e-mail (exclusão da conta)."""
        with get_cursor() as cur:
            cur.execute("DELETE FROM email_codes WHERE email = %s", ((email or "").lower(),))
            return cur.rowcount

    def cleanup_expired_resets(self) -> int:
        """Remove solicitações expiradas ou já utilizadas com mais de 7 dias."""
        with get_cursor() as cur:
            cur.execute("""
                DELETE FROM password_resets
                WHERE expires_at <= NOW() OR (used = TRUE AND created_at <= NOW() - INTERVAL '7 days')
            """)
            return cur.rowcount

