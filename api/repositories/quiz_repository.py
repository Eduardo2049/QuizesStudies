"""
Repositories - Padrão Spring @Repository
Camada de acesso a dados via PostgreSQL
"""
import json
import secrets
from api.database.connection import get_cursor
from api.exceptions.quiz_exceptions import QuizNotFound


class QuizRepository:
    """Repository para operações de quiz no PostgreSQL"""

    # ─── Leitura ──────────────────────────────────────────────────────────────

    def find_all_sources(self, user_id: int = None) -> list[dict]:
        """
        Lista todos os quizzes cadastrados acessíveis ao usuário (públicos ou criados por ele).

        Returns:
            list[dict]: [{id, name, label, file_type, ai_generated, created_at, question_count}]
        """
        with get_cursor() as cur:
            if user_id:
                cur.execute("""
                    SELECT q.id, q.name, q.label, q.file_type, q.ai_generated, q.created_at,
                           q.created_by, q.is_public, COUNT(qs.id) AS question_count
                    FROM quizzes q
                    LEFT JOIN questions qs ON qs.quiz_id = q.id
                    WHERE q.is_public = TRUE OR q.created_by = %s
                    GROUP BY q.id
                    ORDER BY q.created_at ASC
                """, (user_id,))
            else:
                cur.execute("""
                    SELECT q.id, q.name, q.label, q.file_type, q.ai_generated, q.created_at,
                           q.created_by, q.is_public, COUNT(qs.id) AS question_count
                    FROM quizzes q
                    LEFT JOIN questions qs ON qs.quiz_id = q.id
                    WHERE q.is_public = TRUE
                    GROUP BY q.id
                    ORDER BY q.created_at ASC
                """)
            return [dict(row) for row in cur.fetchall()]

    def find_by_name(self, name: str, user_id: int = None) -> dict:
        """
        Encontra um quiz pelo campo `name` (se público ou se pertencente ao usuário).

        Raises:
            QuizNotFound: Se não existir
        """
        with get_cursor() as cur:
            if user_id:
                cur.execute("""
                    SELECT * FROM quizzes
                    WHERE name = %s AND (is_public = TRUE OR created_by = %s)
                """, (name, user_id))
            else:
                cur.execute("""
                    SELECT * FROM quizzes
                    WHERE name = %s AND is_public = TRUE
                """, (name,))
            row = cur.fetchone()
        if not row:
            raise QuizNotFound(name)
        return dict(row)

    def find_default(self, user_id: int = None) -> dict:
        """
        Retorna o primeiro quiz cadastrado acessível (mais antigo).

        Raises:
            QuizNotFound: Se não houver nenhum quiz
        """
        with get_cursor() as cur:
            if user_id:
                cur.execute("""
                    SELECT * FROM quizzes
                    WHERE is_public = TRUE OR created_by = %s
                    ORDER BY created_at ASC LIMIT 1
                """, (user_id,))
            else:
                cur.execute("""
                    SELECT * FROM quizzes
                    WHERE is_public = TRUE
                    ORDER BY created_at ASC LIMIT 1
                """)
            row = cur.fetchone()
        if not row:
            raise QuizNotFound("Nenhum quiz cadastrado")
        return dict(row)

    def find_questions(self, quiz_id: int) -> list[dict]:
        """
        Retorna todas as questões de um quiz, ordenadas por question_number.

        Returns:
            list[dict]: [{id, quiz_id, question_number, section, context,
                          question, options (list), answer, explanation}]
        """
        with get_cursor() as cur:
            cur.execute("""
                SELECT id, quiz_id, question_number, section, context,
                       question, options, answer, explanation
                FROM questions
                WHERE quiz_id = %s
                ORDER BY question_number ASC
            """, (quiz_id,))
            rows = cur.fetchall()

        result = []
        for row in rows:
            q = dict(row)
            # options vem como JSONB — psycopg2 já deserializa automaticamente
            if isinstance(q["options"], str):
                q["options"] = json.loads(q["options"])
            result.append(q)
        return result

    def name_exists(self, name: str) -> bool:
        """Verifica se já existe um quiz com esse nome."""
        with get_cursor() as cur:
            cur.execute("SELECT 1 FROM quizzes WHERE name = %s", (name,))
            return cur.fetchone() is not None

    # ─── Escrita ──────────────────────────────────────────────────────────────

    def save_quiz(
        self,
        name: str,
        label: str,
        questions: list[dict],
        original_filename: str = None,
        file_type: str = "txt",
        ai_generated: bool = False,
        created_by: int = None,
        is_public: bool = False,
    ) -> dict:
        """
        Persiste um quiz e suas questões no banco.

        Args:
            name: Identificador único (ex: 'meu-quiz-2024')
            label: Nome de exibição
            questions: Lista de dicts com {id/question_number, section, context,
                        question, options, answer, explanation}
            original_filename: Nome original do arquivo enviado
            file_type: 'txt', 'pdf', 'docx' ou 'md'
            ai_generated: True se o gabarito foi gerado por IA

        Returns:
            dict: Quiz salvo com id
        """
        with get_cursor() as cur:
            # Inserir quiz com proteção contra sobreescrita acidental
            target_name = name
            try:
                cur.execute("""
                    INSERT INTO quizzes
                        (name, label, original_filename, file_type, ai_generated, created_by, is_public)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, name, label, file_type, ai_generated, created_at, created_by, is_public
                """, (target_name, label, original_filename, file_type, ai_generated, created_by, is_public))
            except Exception as e:
                err_str = str(e).lower()
                if "unique" in err_str or "duplicate" in err_str or "violates unique" in err_str:
                    target_name = f"{name[:100]}-{secrets.token_hex(4)}"
                    cur.execute("""
                        INSERT INTO quizzes
                            (name, label, original_filename, file_type, ai_generated, created_by, is_public)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        RETURNING id, name, label, file_type, ai_generated, created_at, created_by, is_public
                    """, (target_name, label, original_filename, file_type, ai_generated, created_by, is_public))
                else:
                    raise

            quiz = dict(cur.fetchone())
            quiz_id = quiz["id"]

            # Inserir questões do novo quiz
            for q in questions:
                qnum = q.get("question_number") or q.get("id", 0)
                options_json = json.dumps(q.get("options", []), ensure_ascii=False)
                cur.execute("""
                    INSERT INTO questions
                        (quiz_id, question_number, section, context, question,
                         options, answer, explanation)
                    VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s)
                """, (
                    quiz_id,
                    qnum,
                    q.get("section", "Geral"),
                    q.get("context", ""),
                    q["question"],
                    options_json,
                    q.get("answer"),
                    q.get("explanation", ""),
                ))

        return quiz

    def delete_quiz(self, quiz_id: int) -> bool:
        """Remove um quiz e suas questões (CASCADE)."""
        with get_cursor() as cur:
            cur.execute("DELETE FROM quizzes WHERE id = %s RETURNING id", (quiz_id,))
            return cur.fetchone() is not None

    def save_attempt(
        self,
        user_id: int,
        quiz_id: int,
        quiz_name: str,
        score: int,
        total: int,
        percentage: int,
        wrong_question_ids: list[int],
    ) -> dict:
        """Salva a tentativa de um usuário no quiz."""
        with get_cursor() as cur:
            cur.execute("""
                INSERT INTO quiz_attempts
                    (user_id, quiz_id, quiz_name, score, total, percentage, wrong_question_ids)
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
                RETURNING id, user_id, quiz_id, quiz_name, score, total, percentage, wrong_question_ids, created_at
            """, (
                user_id,
                quiz_id,
                quiz_name,
                score,
                total,
                percentage,
                json.dumps(wrong_question_ids),
            ))
            return dict(cur.fetchone())

    def find_user_attempts(self, user_id: int, limit: int = 10) -> list[dict]:
        """Retorna as últimas tentativas realizadas pelo usuário."""
        with get_cursor() as cur:
            cur.execute("""
                SELECT id, user_id, quiz_id, quiz_name, score, total, percentage,
                       wrong_question_ids, created_at
                FROM quiz_attempts
                WHERE user_id = %s
                ORDER BY created_at DESC
                LIMIT %s
            """, (user_id, limit))
            return [dict(row) for row in cur.fetchall()]
