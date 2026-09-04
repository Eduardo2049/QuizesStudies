"""
Gerenciamento de conexões com PostgreSQL.
Usa psycopg2 com context manager para garantir fechamento seguro.
"""
import psycopg2
import psycopg2.extras
from contextlib import contextmanager
from api.utils.config import DATABASE_URL, DEBUG


def _get_database_url() -> str:
    """Normaliza o formato da URL do banco e assegura SSL para conexões remotas."""
    url = (DATABASE_URL or "").strip()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    
    # Adiciona sslmode=require automaticamente para bancos em nuvem se não estiver presente
    if url and "localhost" not in url and "127.0.0.1" not in url:
        if "sslmode=" not in url:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}sslmode=require"
    
    return url


def _connect_db():
    clean_url = _get_database_url()
    try:
        conn = psycopg2.connect(clean_url)
        try:
            conn.set_client_encoding('UTF8')
        except Exception:
            pass
        return conn
    except UnicodeDecodeError as e:
        msg = e.object.decode("cp1252", errors="replace") if hasattr(e, "object") else str(e)
        raise ConnectionError(f"Erro ao conectar ao PostgreSQL: {msg.strip()}") from None


def get_raw_connection():
    """Abre uma conexão direta com o PostgreSQL."""
    return _connect_db()


@contextmanager
def get_connection():
    """
    Context manager para conexão PostgreSQL.
    Garante commit/rollback e fechamento automático.
    """
    conn = None
    try:
        conn = _connect_db()
        yield conn
        conn.commit()
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()



@contextmanager
def get_cursor(dict_cursor: bool = True):
    """
    Context manager que entrega um cursor pronto para uso.
    Usa RealDictCursor por padrão (retorna rows como dict).

    Usage:
        with get_cursor() as cur:
            cur.execute("SELECT * FROM quizzes")
            rows = cur.fetchall()
    """
    factory = psycopg2.extras.RealDictCursor if dict_cursor else None
    with get_connection() as conn:
        with conn.cursor(cursor_factory=factory) as cur:
            yield cur


def ping() -> bool:
    """Testa se o banco está acessível."""
    try:
        with get_cursor() as cur:
            cur.execute("SELECT 1")
        return True
    except Exception as e:
        if DEBUG:
            print(f"⚠️  Banco de dados indisponível: {e}")
        return False
