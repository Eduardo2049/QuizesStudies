"""
Gerenciamento otimizado de conexões com PostgreSQL.
Usa ThreadedConnectionPool com fallback seguro para conexões diretas.
"""
import threading
from contextlib import contextmanager
import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool
from api.utils.config import DATABASE_URL, DEBUG

_pool = None
_pool_lock = threading.Lock()


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


def _get_pool():
    """Retorna o pool de conexões ativo ou cria um novo com tolerância a falhas."""
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                clean_url = _get_database_url()
                if not clean_url:
                    return None
                try:
                    # Pool com min 1 e max 10 conexões ativas
                    _pool = ThreadedConnectionPool(minconn=1, maxconn=10, dsn=clean_url)
                    if DEBUG:
                        print("⚡ PostgreSQL connection pool inicializado (1-10 conexões)")
                except Exception as e:
                    if DEBUG:
                        print(f"⚠️ Aviso: Falha ao iniciar connection pool ({e}), usando conexões diretas")
                    _pool = False
    return _pool if _pool is not False else None


def get_raw_connection():
    """Abre uma conexão direta com o PostgreSQL."""
    return _connect_db()


@contextmanager
def get_connection():
    """
    Context manager para conexão PostgreSQL com pooling.
    Reutiliza conexões do pool quando disponível, reduzindo a latência de handshake.
    """
    pool = _get_pool()
    conn = None
    from_pool = False

    try:
        if pool:
            try:
                conn = pool.getconn()
                from_pool = True
                if conn.closed:
                    conn = _connect_db()
                    from_pool = False
            except Exception:
                conn = _connect_db()
                from_pool = False
        else:
            conn = _connect_db()
            from_pool = False

        yield conn
        conn.commit()
    except Exception:
        if conn and not conn.closed:
            conn.rollback()
        raise
    finally:
        if conn:
            if from_pool and pool and not conn.closed:
                try:
                    pool.putconn(conn)
                except Exception:
                    try:
                        conn.close()
                    except Exception:
                        pass
            else:
                try:
                    conn.close()
                except Exception:
                    pass


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
