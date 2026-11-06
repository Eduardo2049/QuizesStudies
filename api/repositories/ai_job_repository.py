"""
Pedidos de IA persistentes (ai_jobs) e cache de simulados por tema (ai_cache).

O navegador manda um identificador (request_id, uuid) em cada pedido de IA. Com ele:
- recarregar a página e repetir o pedido devolve o resultado já pronto, sem chamar a IA
  nem gastar outra cota;
- um pedido repetido enquanto o primeiro ainda roda recebe "running" e consulta depois em
  GET /api/quiz/jobs/<id>.

Tudo fica no PostgreSQL, então vale entre instâncias da Vercel. Se o banco estiver fora,
cai para a memória do processo (mesmo comportamento do RateLimitRepository), para os
testes e o modo local continuarem funcionando.
"""
from __future__ import annotations

import copy
import json
import random
import re
import time
from threading import Lock

from api.database.connection import get_cursor
from api.utils.config import AI_CACHE_TTL_DAYS, DEBUG

# Um pedido "running" mais velho que isto foi abandonado (a função da Vercel vai até 300 s).
JOB_STALE_SECONDS = 6 * 60
# Jobs são guardados por 24 h: tempo de sobra para recarregar a página e buscar o resultado.
JOB_RETENTION_SECONDS = 24 * 60 * 60
_CLEANUP_PROBABILITY = 0.02

ABANDONED_JOB_MESSAGE = "A geração foi interrompida antes de terminar. Tente novamente."

_UUID_PATTERN = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def is_valid_job_id(value) -> bool:
    return isinstance(value, str) and bool(_UUID_PATTERN.match(value))


class JobConflict(Exception):
    """O mesmo request_id já foi usado por outra pessoa ou com outros parâmetros."""


class AIJobRepository:

    def __init__(self):
        self._lock = Lock()
        self._jobs: dict[str, dict] = {}
        self._cache: dict[str, tuple[float, dict]] = {}

    # ─── Jobs ────────────────────────────────────────────────────────────────

    def start(self, job_id: str, owner_kind: str, owner_id: str, kind: str, params_hash: str) -> tuple[bool, dict]:
        """Registra o pedido como "running".

        Retorna (criado, job). `criado=False` quando o id já existia: o job devolvido diz se
        está pronto ("done"), ainda rodando ("running") ou se falhou ("failed"). Um job que
        falhou ou foi abandonado volta para "running" e é refeito (criado=True).
        Levanta JobConflict se o id pertence a outro dono, outro tipo ou outros parâmetros.
        """
        owner_id = str(owner_id)
        try:
            return self._start_db(job_id, owner_kind, owner_id, kind, params_hash)
        except JobConflict:
            raise
        except Exception as e:  # noqa: BLE001 - banco fora: segue na memória
            self._debug(f"start no banco falhou ({e}), usando memória")
            return self._start_memory(job_id, owner_kind, owner_id, kind, params_hash)

    def finish(self, job_id: str, result: dict) -> None:
        self._update(job_id, "done", result=result)

    def fail(self, job_id: str, message: str, code: str = "ERROR", status: int = 422) -> None:
        self._update(job_id, "failed", error=message, error_code=code, error_status=status)

    def get(self, job_id: str) -> dict | None:
        """Job pelo id, ou None. Um "running" abandonado aparece como "failed"."""
        try:
            with get_cursor() as cur:
                cur.execute(
                    """
                    SELECT id, owner_kind, owner_id, kind, params_hash, status, result, error,
                           error_code, error_status,
                           EXTRACT(EPOCH FROM (NOW() - updated_at)) AS age
                    FROM ai_jobs WHERE id = %s
                    """,
                    (job_id,),
                )
                row = cur.fetchone()
            if row:
                return self._normalize(dict(row))
        except Exception as e:  # noqa: BLE001
            self._debug(f"get no banco falhou ({e}), usando memória")
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            job = copy.deepcopy(job)
        job["age"] = time.time() - job.pop("updated_ts")
        return self._normalize(job)

    # ─── Cache de simulados por tema ─────────────────────────────────────────

    def cache_get(self, key: str) -> dict | None:
        if AI_CACHE_TTL_DAYS <= 0:
            return None
        ttl = AI_CACHE_TTL_DAYS * 24 * 60 * 60
        try:
            with get_cursor() as cur:
                cur.execute(
                    "SELECT result FROM ai_cache WHERE key = %s AND created_at > NOW() - make_interval(secs => %s)",
                    (key, ttl),
                )
                row = cur.fetchone()
                if random.random() < _CLEANUP_PROBABILITY:
                    cur.execute("DELETE FROM ai_cache WHERE created_at <= NOW() - make_interval(secs => %s)", (ttl,))
            if row:
                return self._load_json(row["result"])
            return None
        except Exception as e:  # noqa: BLE001
            self._debug(f"cache_get no banco falhou ({e}), usando memória")
        with self._lock:
            item = self._cache.get(key)
            if item and time.time() - item[0] < ttl:
                return copy.deepcopy(item[1])
        return None

    def cache_set(self, key: str, result: dict) -> None:
        if AI_CACHE_TTL_DAYS <= 0:
            return
        try:
            with get_cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ai_cache (key, result, created_at) VALUES (%s, %s::jsonb, NOW())
                    ON CONFLICT (key) DO UPDATE SET result = EXCLUDED.result, created_at = NOW()
                    """,
                    (key, json.dumps(result, ensure_ascii=False)),
                )
            return
        except Exception as e:  # noqa: BLE001
            self._debug(f"cache_set no banco falhou ({e}), usando memória")
        with self._lock:
            self._cache[key] = (time.time(), copy.deepcopy(result))

    def reset(self) -> None:
        """Limpa a memória (testes)."""
        with self._lock:
            self._jobs.clear()
            self._cache.clear()

    # ─── Internos ────────────────────────────────────────────────────────────

    def _start_db(self, job_id, owner_kind, owner_id, kind, params_hash):
        with get_cursor() as cur:
            cur.execute(
                """
                INSERT INTO ai_jobs (id, owner_kind, owner_id, kind, params_hash, status)
                VALUES (%s, %s, %s, %s, %s, 'running')
                ON CONFLICT (id) DO NOTHING
                RETURNING id
                """,
                (job_id, owner_kind, owner_id, kind, params_hash),
            )
            if cur.fetchone():
                if random.random() < _CLEANUP_PROBABILITY:
                    cur.execute(
                        "DELETE FROM ai_jobs WHERE created_at <= NOW() - make_interval(secs => %s)",
                        (JOB_RETENTION_SECONDS,),
                    )
                return True, {"id": job_id, "status": "running"}

            # O id já existe. FOR UPDATE: dois pedidos repetidos ao mesmo tempo não
            # reiniciam o mesmo job duas vezes.
            cur.execute(
                """
                SELECT id, owner_kind, owner_id, kind, params_hash, status, result, error,
                       error_code, error_status,
                       EXTRACT(EPOCH FROM (NOW() - updated_at)) AS age
                FROM ai_jobs WHERE id = %s FOR UPDATE
                """,
                (job_id,),
            )
            row = cur.fetchone()
            if not row:  # apagado entre o INSERT e o SELECT (limpeza): tenta de novo
                raise RuntimeError("job sumiu")
            job = self._normalize(dict(row))
            self._check_same_request(job, owner_kind, owner_id, kind, params_hash)
            if job["status"] == "failed":
                cur.execute(
                    """
                    UPDATE ai_jobs SET status = 'running', result = NULL, error = NULL,
                           error_code = NULL, error_status = NULL, updated_at = NOW()
                    WHERE id = %s
                    """,
                    (job_id,),
                )
                return True, {"id": job_id, "status": "running"}
            return False, job

    def _start_memory(self, job_id, owner_kind, owner_id, kind, params_hash):
        now = time.time()
        with self._lock:
            existing = self._jobs.get(job_id)
            if existing is None:
                self._jobs[job_id] = {
                    "id": job_id, "owner_kind": owner_kind, "owner_id": owner_id, "kind": kind,
                    "params_hash": params_hash, "status": "running", "result": None, "error": None,
                    "error_code": None, "error_status": None, "updated_ts": now, "created_ts": now,
                }
                self._prune_memory(now)
                return True, {"id": job_id, "status": "running"}
            job = copy.deepcopy(existing)
            job["age"] = now - job.pop("updated_ts")
            job = self._normalize(job)
            self._check_same_request(job, owner_kind, owner_id, kind, params_hash)
            if job["status"] == "failed":
                existing.update(status="running", result=None, error=None, error_code=None,
                                error_status=None, updated_ts=now)
                return True, {"id": job_id, "status": "running"}
            return False, job

    def _update(self, job_id: str, status: str, result=None, error=None, error_code=None, error_status=None):
        try:
            with get_cursor() as cur:
                cur.execute(
                    """
                    UPDATE ai_jobs SET status = %s, result = %s::jsonb, error = %s,
                           error_code = %s, error_status = %s, updated_at = NOW()
                    WHERE id = %s
                    RETURNING id
                    """,
                    (status, json.dumps(result, ensure_ascii=False, default=str) if result is not None else None,
                     error, error_code, error_status, job_id),
                )
                if cur.fetchone():
                    return
        except Exception as e:  # noqa: BLE001
            self._debug(f"update no banco falhou ({e}), usando memória")
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                job.update(
                    status=status, result=copy.deepcopy(result), error=error,
                    error_code=error_code, error_status=error_status, updated_ts=time.time(),
                )

    @staticmethod
    def _check_same_request(job, owner_kind, owner_id, kind, params_hash):
        if job["owner_kind"] != owner_kind or str(job["owner_id"]) != str(owner_id):
            raise JobConflict("request_id de outro dono")
        if job["kind"] != kind or job["params_hash"] != params_hash:
            raise JobConflict("request_id reutilizado com outros parâmetros")

    def _normalize(self, job: dict) -> dict:
        job["result"] = self._load_json(job.get("result"))
        age = float(job.pop("age", 0) or 0)
        if job.get("status") == "running" and age > JOB_STALE_SECONDS:
            job.update(status="failed", error=ABANDONED_JOB_MESSAGE, error_code="AI_JOB_ABANDONED", error_status=503)
        job["owner_id"] = str(job.get("owner_id"))
        return job

    @staticmethod
    def _load_json(value):
        if isinstance(value, (str, bytes)):
            try:
                return json.loads(value)
            except ValueError:
                return None
        return value

    def _prune_memory(self, now: float) -> None:
        cutoff = now - JOB_RETENTION_SECONDS
        for key in [k for k, v in self._jobs.items() if v.get("created_ts", now) <= cutoff]:
            del self._jobs[key]

    @staticmethod
    def _debug(msg: str) -> None:
        if DEBUG:
            print(f"[ai-jobs] {msg}")


ai_job_repo = AIJobRepository()
