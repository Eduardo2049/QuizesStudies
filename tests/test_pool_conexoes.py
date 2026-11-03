"""
Pool de conexões resistente a pausas do provedor (Neon desliga após 5 min sem uso).

1. Conexão parada há mais de POOL_CHECK_AFTER_S é testada; se morreu, é trocada sem erro.
2. Conexão fechada ou quebrada no meio da requisição volta ao pool com close=True,
   liberando a vaga (antes as 10 vagas ficavam presas e toda requisição abria conexão nova).
3. Com banco local (QUIZ_DB_INTEGRATION=1, como no CI), o mesmo cenário com
   pg_terminate_backend num PostgreSQL de verdade.
"""
import os
import unittest
from unittest.mock import patch
from urllib.parse import urlparse

import psycopg2
import psycopg2.extensions
from psycopg2.pool import ThreadedConnectionPool

from api.database import connection as c
from api.utils.config import DATABASE_URL


class FakeConn:
    def __init__(self, alive=True):
        self.closed = 0
        self.alive = alive
        self.autocommit = False
        self.info = type("Info", (), {"transaction_status": psycopg2.extensions.TRANSACTION_STATUS_IDLE})()
        self.executed = []

    def cursor(self, cursor_factory=None):
        conn = self

        class Cur:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def execute(self, sql, params=None):
                if not conn.alive:
                    conn.closed = 2
                    raise psycopg2.OperationalError("server closed the connection unexpectedly")
                conn.executed.append(sql)

        return Cur()

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        self.closed = 1


class FakePool:
    def __init__(self, conns):
        self.free = list(conns)
        self.used = set()
        self.discarded = []
        self.created = 0

    def getconn(self):
        if self.free:
            conn = self.free.pop(0)
        else:
            self.created += 1
            conn = FakeConn()
        self.used.add(id(conn))
        return conn

    def putconn(self, conn, close=False):
        self.used.discard(id(conn))
        if close:
            conn.close()
            self.discarded.append(conn)
        else:
            self.free.append(conn)


class PoolLogicTests(unittest.TestCase):
    def setUp(self):
        self.saved_last_used = dict(c._last_used)
        c._last_used.clear()

    def tearDown(self):
        c._last_used.clear()
        c._last_used.update(self.saved_last_used)

    def _use(self, pool, sql="SELECT 1"):
        with patch.object(c, "_get_pool", return_value=pool):
            with c.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql)
                return conn

    def test_recent_connection_is_reused_without_ping(self):
        conn = FakeConn()
        pool = FakePool([conn])
        self._use(pool)
        self._use(pool)
        self.assertEqual(conn.executed, ["SELECT 1", "SELECT 1"])  # nenhum SELECT 1 extra de teste
        self.assertEqual(pool.created, 0)

    def test_idle_dead_connection_is_replaced(self):
        dead = FakeConn()
        pool = FakePool([dead])
        self._use(pool)
        dead.alive = False
        c._last_used[id(dead)] -= 3600  # parada há uma hora
        used = self._use(pool)
        self.assertIsNot(used, dead)
        self.assertIn(dead, pool.discarded)
        self.assertEqual(pool.used, set())

    def test_broken_connection_frees_its_slot(self):
        conn = FakeConn(alive=False)
        pool = FakePool([conn])
        with self.assertRaises(psycopg2.OperationalError):
            self._use(pool)
        self.assertIn(conn, pool.discarded)
        self.assertEqual(pool.used, set())

    def test_connection_left_in_transaction_is_discarded(self):
        conn = FakeConn()
        conn.info.transaction_status = psycopg2.extensions.TRANSACTION_STATUS_INERROR
        pool = FakePool([conn])
        self._use(pool)
        self.assertIn(conn, pool.discarded)

    def test_keepalives_added_to_remote_url(self):
        url = c.build_database_url("postgresql://u:p@h.example.com/db")
        self.assertIn("keepalives=1", url)
        self.assertIn("keepalives_idle=30", url)


def _local_db_enabled() -> bool:
    if os.getenv("QUIZ_DB_INTEGRATION") != "1":
        return False
    return (urlparse(DATABASE_URL or "").hostname or "") in ("localhost", "127.0.0.1")


@unittest.skipUnless(_local_db_enabled(), "QUIZ_DB_INTEGRATION=1 com banco local não configurado")
class PoolRealDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.pool = ThreadedConnectionPool(1, 3, dsn=c.build_database_url(DATABASE_URL))
        self.pool_patch = patch.object(c, "_get_pool", return_value=self.pool)
        self.pool_patch.start()
        self.admin = psycopg2.connect(c.build_database_url(DATABASE_URL))
        self.admin.autocommit = True

    def tearDown(self):
        self.pool_patch.stop()
        self.pool.closeall()
        self.admin.close()

    def _pid(self):
        with c.get_cursor() as cur:
            cur.execute("SELECT pg_backend_pid() AS pid")
            return cur.fetchone()["pid"]

    def _kill(self, pid):
        with self.admin.cursor() as cur:
            cur.execute("SELECT pg_terminate_backend(%s)", (pid,))

    def test_connection_killed_while_idle_is_replaced(self):
        pid = self._pid()
        self._kill(pid)
        for key in list(c._last_used):
            c._last_used[key] -= 3600
        self.assertNotEqual(self._pid(), pid)

    def test_slots_are_not_leaked(self):
        for _ in range(6):
            pid = self._pid()
            self._kill(pid)
            try:
                self._pid()
            except psycopg2.Error:
                pass
        self.assertEqual(len(self.pool._used), 0)
        self.assertGreater(self._pid(), 0)


if __name__ == "__main__":
    unittest.main()
