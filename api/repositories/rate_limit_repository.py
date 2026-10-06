"""
Repositório de persistência para Rate Limiting e Controle de Quotas.
Armazena registros de requisição na tabela rate_limits (PostgreSQL) com
sincronização rápida em memória e fallback gracioso caso o banco esteja indisponível.
"""
import time
import random
from collections import defaultdict, deque
from threading import Lock
from api.database.connection import get_cursor
from api.utils.config import DEBUG


class RateLimitRepository:
    """
    Controlador de janela deslizante persistente com camada rápida em memória e
    persistência no PostgreSQL para suporte cross-process e serverless.
    """

    def __init__(self):
        self._memory_storage: dict[str, deque] = defaultdict(deque)
        self._lock = Lock()
        self._clean_counter = 0

    def check_and_record(
        self,
        key: str,
        limit: int,
        window_seconds: int,
        cost: int = 1
    ) -> tuple[bool, int]:
        """
        Verifica se a chave tem limite disponível na janela e registra o consumo.
        
        Args:
            key: Identificador único (ex: 'POST:/api/upload:192.168.1.1')
            limit: Quantidade máxima permitida na janela
            window_seconds: Tamanho da janela deslizante em segundos
            cost: Custo da operação atual (padrão: 1)

        Returns:
            tuple[bool, int]: (permitido, retry_after_segundos)
        """
        now = time.time()
        cutoff = now - window_seconds

        # 1. Checagem atômica rápida em memória para proteger concorrência intra-processo
        with self._lock:
            self._clean_counter += 1
            entries = self._memory_storage[key]
            while entries and entries[0][0] <= cutoff:
                entries.popleft()

            local_used = sum(t for _, t in entries)
            if local_used + cost > limit:
                oldest = entries[0][0] if entries else now
                retry_after = max(1, int(oldest - cutoff + 1))
                return False, retry_after

        # 2. Persistência e validação no banco de dados compartilhado (Postgres/Serverless)
        try:
            with get_cursor() as cur:
                cur.execute(
                    "SELECT COALESCE(SUM(tokens), 0) AS used FROM rate_limits WHERE key = %s AND timestamp > %s",
                    (key, cutoff)
                )
                row = cur.fetchone()
                db_used = int(row["used"]) if row and row.get("used") is not None else 0
                total_used = max(local_used, db_used)

                if total_used + cost > limit:
                    cur.execute(
                        "SELECT MIN(timestamp) AS oldest FROM rate_limits WHERE key = %s AND timestamp > %s",
                        (key, cutoff)
                    )
                    row_oldest = cur.fetchone()
                    oldest = float(row_oldest["oldest"]) if row_oldest and row_oldest.get("oldest") is not None else now
                    retry_after = max(1, int(oldest - cutoff + 1))
                    return False, retry_after

                cur.execute(
                    "INSERT INTO rate_limits (key, timestamp, tokens) VALUES (%s, %s, %s)",
                    (key, now, cost)
                )

                if random.random() < 0.05:
                    cur.execute(
                        "DELETE FROM rate_limits WHERE key = %s AND timestamp <= %s",
                        (key, cutoff)
                    )
        except Exception as e:
            if DEBUG:
                print(f"[rate-limit] Falha de persistência no banco ({e}), operando em modo memória")

        # 3. Registra na memória local
        with self._lock:
            self._memory_storage[key].append((now, cost))
            if self._clean_counter % 100 == 0:
                expired = [k for k, v in self._memory_storage.items() if not v or v[-1][0] <= cutoff]
                for k in expired:
                    del self._memory_storage[k]

        return True, 0

    def get_usage(self, key: str, window_seconds: int) -> int:
        """Retorna o total consumido na janela atual para a chave."""
        cutoff = time.time() - window_seconds
        try:
            with get_cursor() as cur:
                cur.execute(
                    "SELECT COALESCE(SUM(tokens), 0) AS used FROM rate_limits WHERE key = %s AND timestamp > %s",
                    (key, cutoff)
                )
                row = cur.fetchone()
                db_used = int(row["used"]) if row and row.get("used") is not None else 0
                with self._lock:
                    local_used = sum(t for ts, t in self._memory_storage.get(key, deque()) if ts > cutoff)
                return max(local_used, db_used)
        except Exception:
            with self._memory_lock if hasattr(self, '_memory_lock') else self._lock:
                reqs = self._memory_storage.get(key, deque())
                return sum(t for ts, t in reqs if ts > cutoff)

    def reset(self, key: str | None = None) -> None:
        """Limpa registros de memória e banco para uma chave ou tudo (útil em testes e resets administrativos)."""
        with self._lock:
            if key:
                self._memory_storage.pop(key, None)
            else:
                self._memory_storage.clear()
        try:
            with get_cursor() as cur:
                if key:
                    cur.execute("DELETE FROM rate_limits WHERE key = %s", (key,))
                else:
                    cur.execute("DELETE FROM rate_limits")
        except Exception:
            pass


# Instância global singleton
rate_limit_repo = RateLimitRepository()
