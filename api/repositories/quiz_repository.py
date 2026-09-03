"""
Repositories - Padrão Spring @Repository
Camada de acesso a dados via PostgreSQL
"""
import json
from api.database.connection import get_cursor
from api.exceptions.quiz_exceptions import QuizNotFound


class QuizRepository:
    """Repository para operações de quiz no PostgreSQL"""

    # ─── Leitura ──────────────────────────────────────────────────────────────

    def find_all_sources(self) -> list[dict]:
        """
        Lista todos os quizzes cadastrados.

        Returns:
            list[dict]: [{id, name, label, file_type, ai_generated, created_at}]
        """
        with get_cursor() as cur:
            cur.execute("""
                SELECT id, name, label, file_type, ai_generated, created_at
                FROM quizzes
                ORDER BY created_at ASC
            """)
            return [dict(row) for row in cur.fetchall()]

    def find_by_name(self, name: str) -> dict:
        """
        Encontra um quiz pelo campo `name`.

        Raises:
            QuizNotFound: Se não existir
        """
        with get_cursor() as cur:
            cur.execute("SELECT * FROM quizzes WHERE name = %s", (name,))
            row = cur.fetchone()
        if not row:
            raise QuizNotFound(name)
        return dict(row)

    def find_default(self) -> dict:
        """
        Retorna o primeiro quiz cadastrado (mais antigo).

        Raises:
            QuizNotFound: Se não houver nenhum quiz
        """
        with get_cursor() as cur:
            cur.execute("SELECT * FROM quizzes ORDER BY created_at ASC LIMIT 1")
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
            # Inserir ou atualizar quiz
            cur.execute("""
                INSERT INTO quizzes (name, label, original_filename, file_type, ai_generated)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (name) DO UPDATE SET
                    label = EXCLUDED.label,
                    original_filename = EXCLUDED.original_filename,
                    file_type = EXCLUDED.file_type,
                    ai_generated = EXCLUDED.ai_generated
                RETURNING id, name, label, file_type, ai_generated, created_at
            """, (name, label, original_filename, file_type, ai_generated))
            quiz = dict(cur.fetchone())
            quiz_id = quiz["id"]

            # Remover questões antigas (em caso de re-upload)
            cur.execute("DELETE FROM questions WHERE quiz_id = %s", (quiz_id,))

            # Inserir questões
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
