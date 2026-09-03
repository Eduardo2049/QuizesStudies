"""
Migrações do banco de dados — executa na inicialização.
Usa CREATE TABLE IF NOT EXISTS para ser idempotente.
"""
import json
from api.database.connection import get_cursor
from api.utils.config import DEBUG

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS quizzes (
    id               SERIAL PRIMARY KEY,
    name             VARCHAR(255) UNIQUE NOT NULL,
    label            VARCHAR(255) NOT NULL,
    original_filename VARCHAR(255),
    file_type        VARCHAR(10) DEFAULT 'txt',  -- 'txt', 'pdf', 'docx', 'md'
    has_answer_key   BOOLEAN DEFAULT TRUE,
    ai_generated     BOOLEAN DEFAULT FALSE,       -- gabarito foi gerado por IA?
    created_at       TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS questions (
    id              SERIAL PRIMARY KEY,
    quiz_id         INTEGER NOT NULL REFERENCES quizzes(id) ON DELETE CASCADE,
    question_number INTEGER NOT NULL,
    section         VARCHAR(255) DEFAULT 'Geral',
    context         TEXT DEFAULT '',
    question        TEXT NOT NULL,
    options         JSONB NOT NULL,   -- lista de strings, ex: ["Opção A", "Opção B", ...]
                                      -- suporta 2 a N alternativas sem limit fixo
    answer          INTEGER,          -- índice base-0 (0=A, 1=B, 2=C…)
    explanation     TEXT DEFAULT '',
    UNIQUE (quiz_id, question_number)
);

CREATE INDEX IF NOT EXISTS idx_questions_quiz_id ON questions(quiz_id);

CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    username      VARCHAR(50) UNIQUE NOT NULL,
    email         VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    salt          VARCHAR(64) NOT NULL,
    role          VARCHAR(20) DEFAULT 'student',
    created_at    TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sessions (
    token         VARCHAR(128) PRIMARY KEY,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at    TIMESTAMP NOT NULL,
    created_at    TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(token);
CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
"""


def run_migrations():
    """
    Executa as migrações de schema.
    Chamado na inicialização do servidor.
    """
    try:
        with get_cursor() as cur:
            cur.execute(SCHEMA_SQL)
        
        # Criar admin padrão se não houver usuários
        from api.services.auth_service import AuthService
        AuthService().seed_admin_if_needed()

        if DEBUG:
            print("[db] Migrations executadas com sucesso")
    except Exception as e:
        print(f"[db] Erro ao executar migrations: {e}")
        raise

