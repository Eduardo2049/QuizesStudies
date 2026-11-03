"""
Gerenciamento otimizado de conexões com PostgreSQL.
Usa ThreadedConnectionPool com fallback seguro para conexões diretas.
"""
import os
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from urllib.parse import parse_qsl, quote, urlsplit
import psycopg2
import psycopg2.extensions
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool
from api.utils.config import (
    DATABASE_URL,
    DATABASE_URL_DIRECT,
    DB_SSLMODE,
    DB_SSLROOTCERT,
    DB_SSLROOTCERT_PEM,
    DEBUG,
)

_pool = None
_pool_lock = threading.Lock()
_tls_warning_shown = False

# Modos que validam o certificado do servidor (os demais só cifram ou nem isso)
_VERIFYING_SSLMODES = {"verify-ca", "verify-full"}


def _url_params(url: str) -> dict:
    return {k.lower(): v for k, v in parse_qsl(urlsplit(url).query, keep_blank_values=True)}


def _is_local(url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return host in ("", "localhost", "127.0.0.1", "::1") or "localhost" in url or "127.0.0.1" in url


def _append_param(url: str, key: str, value: str) -> str:
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}{key}={quote(value, safe='/:')}"


_pem_path: str | None = None


def _sslrootcert() -> str:
    """Certificado para verify-full: DB_SSLROOTCERT_PEM (gravado em /tmp), DB_SSLROOTCERT ou "system"."""
    global _pem_path
    if DB_SSLROOTCERT_PEM:
        if _pem_path is None:
            pem = DB_SSLROOTCERT_PEM.replace("\\n", "\n")
            fd, path = tempfile.mkstemp(prefix="acely-db-ca-", suffix=".crt")
            with os.fdopen(fd, "w", encoding="ascii") as fh:
                fh.write(pem if pem.endswith("\n") else pem + "\n")
            _pem_path = path
        return _pem_path
    return DB_SSLROOTCERT or "system"


def build_database_url(raw_url: str | None) -> str:
    """Normaliza a URL do banco e completa SSL e timeout para conexões remotas.

    - `postgres://` vira `postgresql://`.
    - Sem `sslmode` na URL, usa DB_SSLMODE (padrão verify-full).
    - Com verify-ca/verify-full e sem `sslrootcert`, usa DB_SSLROOTCERT ou, na falta dele,
      `system` (certificados do sistema; libpq 16+). Sem isso o libpq procura
      ~/.postgresql/root.crt e a conexão falha.
    """
    url = (raw_url or "").strip()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if not url or _is_local(url):
        return url

    params = _url_params(url)
    if "sslmode" not in params:
        url = _append_param(url, "sslmode", DB_SSLMODE)
        params["sslmode"] = DB_SSLMODE
    if params["sslmode"].lower() in _VERIFYING_SSLMODES and "sslrootcert" not in params:
        url = _append_param(url, "sslrootcert", _sslrootcert())
    if "connect_timeout" not in params:
        url = _append_param(url, "connect_timeout", "5")
    # Keepalive TCP: detecta conexão derrubada pelo provedor em vez de esperar
    if "keepalives" not in params:
        for key, value in (("keepalives", "1"), ("keepalives_idle", "30"),
                           ("keepalives_interval", "10"), ("keepalives_count", "3")):
            url = _append_param(url, key, value)
    return url


def describe_database_target(raw_url: str | None) -> str:
    """Host, porta e banco, sem usuário nem senha (para logs)."""
    url = (raw_url or "").strip()
    if not url:
        return "(não configurado)"
    parts = urlsplit(url.replace("postgres://", "postgresql://", 1))
    host = parts.hostname or "?"
    port = parts.port or 5432
    db = (parts.path or "/").lstrip("/") or "postgres"
    return f"{host}:{port}/{db}"


def _warn_if_weak_tls(url: str) -> None:
    """Avisa uma vez quando um banco remoto não valida o certificado do servidor."""
    global _tls_warning_shown
    if _tls_warning_shown or not url or _is_local(url):
        return
    mode = _url_params(url).get("sslmode", "").lower()
    if mode in _VERIFYING_SSLMODES:
        return
    _tls_warning_shown = True
    print(
        f"[db] Aviso: conexão com {describe_database_target(url)} usa sslmode={mode or '(vazio)'}, "
        "que não valida o certificado do servidor. Prefira sslmode=verify-full "
        "(veja docs/BANCO_DE_DADOS.md).",
        file=sys.stderr,
    )


def _get_database_url() -> str:
    return build_database_url(DATABASE_URL)


def _get_direct_database_url() -> str:
    return build_database_url(DATABASE_URL_DIRECT or DATABASE_URL)


def _connect_db(direct: bool = False):
    clean_url = _get_direct_database_url() if direct else _get_database_url()
    if not clean_url:
        raise ConnectionError("DATABASE_URL não configurada no ambiente.")
    _warn_if_weak_tls(clean_url)
    try:
        conn = psycopg2.connect(clean_url, connect_timeout=5)
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
                _warn_if_weak_tls(clean_url)
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


def get_raw_connection(direct: bool = False):
    """Abre uma conexão nova (fora do pool). `direct=True` usa DATABASE_URL_DIRECT."""
    return _connect_db(direct=direct)


@contextmanager
def get_direct_cursor(dict_cursor: bool = True):
    """Cursor numa conexão sem pooler, para migrations e scripts de manutenção.

    Sem DATABASE_URL_DIRECT, usa a mesma URL da aplicação.
    """
    factory = psycopg2.extras.RealDictCursor if dict_cursor else None
    conn = _connect_db(direct=True)
    try:
        with conn.cursor(cursor_factory=factory) as cur:
            yield cur
        conn.commit()
    except Exception:
        if not conn.closed:
            conn.rollback()
        raise
    finally:
        conn.close()


# Conexão parada há mais que isto é testada (SELECT 1) antes de ser reaproveitada.
# Na Vercel a instância da função guarda o pool entre visitas, e a Neon desliga após
# 5 min sem uso (o Supabase também derruba conexões ociosas): sem o teste, a primeira
# requisição depois da pausa pegava uma conexão morta e falhava ou esperava o timeout.
POOL_CHECK_AFTER_S = 30
_last_used: dict[int, float] = {}


def _is_alive(conn) -> bool:
    """Uma ida ao banco (SELECT 1) sem abrir transação."""
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
        conn.autocommit = False
        return True
    except Exception:
        return False


def _discard(pool, conn) -> None:
    """Fecha a conexão e libera a vaga dela no pool."""
    _last_used.pop(id(conn), None)
    try:
        pool.putconn(conn, close=True)
    except Exception:
        try:
            conn.close()
        except Exception:
            pass


def _checkout(pool):
    """Pega uma conexão do pool já validada; troca por uma nova se estiver morta."""
    for _ in range(2):
        conn = pool.getconn()
        last = _last_used.get(id(conn))  # None = acabou de ser aberta pelo pool
        idle = 0.0 if last is None else time.monotonic() - last
        if not conn.closed and (idle < POOL_CHECK_AFTER_S or _is_alive(conn)):
            return conn
        _discard(pool, conn)
    return pool.getconn()


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
                conn = _checkout(pool)
                from_pool = True
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
            try:
                conn.rollback()
            except Exception:
                pass
        raise
    finally:
        if conn:
            if from_pool and pool:
                broken = bool(conn.closed) or (
                    conn.info.transaction_status != psycopg2.extensions.TRANSACTION_STATUS_IDLE
                )
                if broken:
                    _discard(pool, conn)
                else:
                    _last_used[id(conn)] = time.monotonic()
                    try:
                        pool.putconn(conn)
                    except Exception:
                        _discard(pool, conn)
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
