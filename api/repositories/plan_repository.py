"""
Planos, workspace pessoal e contadores de uso mensal (docs/PLANO_SAAS.md, Fase S1).

Tudo no PostgreSQL. Se o banco estiver fora, cai para a memória do processo, como o
RateLimitRepository e o AIJobRepository, para os testes e o modo local funcionarem.

A reserva de uso é atômica: um único UPSERT só soma 1 se o total ainda estiver abaixo do
limite, então dois pedidos ao mesmo tempo não passam da cota.
"""

from __future__ import annotations

import copy
import json
import uuid
from datetime import datetime
from threading import Lock

from api.database.connection import get_cursor
from api.utils.config import DEBUG
from api.utils.plans import DEFAULT_PLAN_ID, DEFAULT_PLANS

PERSONAL_WORKSPACE_NAME = "Pessoal"


class PlanRepository:
    def __init__(self, use_db: bool = True):
        # use_db=False: só memória (testes que não podem depender de um banco ligado)
        self._use_db = use_db
        self._lock = Lock()
        self._plans: dict[str, dict] = {pid: {"id": pid, **copy.deepcopy(p)} for pid, p in DEFAULT_PLANS.items()}
        self._workspaces: dict[int, dict] = {}  # user_id → workspace pessoal
        self._usage: dict[tuple, int] = {}  # (workspace_id, user_id, metric, period) → total

    # ─── Planos ──────────────────────────────────────────────────────────────

    def get_plan(self, plan_id: str) -> dict:
        """Plano pelo id; um id desconhecido ou inativo vira o Grátis."""
        try:
            if not self._use_db:
                raise RuntimeError("banco desligado neste repositório")
            with get_cursor() as cur:
                cur.execute("SELECT id, name, limits FROM plans WHERE id = %s AND active", (plan_id,))
                row = cur.fetchone()
                if not row and plan_id != DEFAULT_PLAN_ID:
                    cur.execute("SELECT id, name, limits FROM plans WHERE id = %s", (DEFAULT_PLAN_ID,))
                    row = cur.fetchone()
            if row:
                limits = row["limits"]
                if isinstance(limits, str):
                    limits = json.loads(limits)
                return {"id": row["id"], "name": row["name"], "limits": limits or {}}
        except Exception as e:  # banco fora: segue na memória
            self._debug(f"get_plan no banco falhou ({e}), usando memória")
        plan = self._plans.get(plan_id) or self._plans[DEFAULT_PLAN_ID]
        return copy.deepcopy(plan)

    # ─── Workspace pessoal ───────────────────────────────────────────────────

    def get_personal_workspace(self, user_id: int) -> dict:
        """Workspace pessoal da pessoa, criado na hora se ainda não existir."""
        try:
            if not self._use_db:
                raise RuntimeError("banco desligado neste repositório")
            with get_cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO workspaces (name, kind, plan_id, owner_user_id)
                    SELECT %s, 'personal', %s, %s
                    WHERE NOT EXISTS (
                        SELECT 1 FROM workspaces WHERE owner_user_id = %s AND kind = 'personal'
                    )
                    ON CONFLICT DO NOTHING
                """,
                    (PERSONAL_WORKSPACE_NAME, DEFAULT_PLAN_ID, user_id, user_id),
                )
                cur.execute(
                    """
                    SELECT id, name, kind, plan_id, seats, owner_user_id, created_at
                    FROM workspaces WHERE owner_user_id = %s AND kind = 'personal'
                """,
                    (user_id,),
                )
                workspace = dict(cur.fetchone())
                cur.execute(
                    """
                    INSERT INTO workspace_members (workspace_id, user_id, role)
                    VALUES (%s, %s, 'owner')
                    ON CONFLICT DO NOTHING
                """,
                    (workspace["id"], user_id),
                )
            workspace["id"] = str(workspace["id"])
            return workspace
        except Exception as e:
            self._debug(f"get_personal_workspace no banco falhou ({e}), usando memória")
        with self._lock:
            workspace = self._workspaces.get(user_id)
            if not workspace:
                workspace = {
                    "id": str(uuid.uuid4()),
                    "name": PERSONAL_WORKSPACE_NAME,
                    "kind": "personal",
                    "plan_id": DEFAULT_PLAN_ID,
                    "seats": 1,
                    "owner_user_id": user_id,
                    "created_at": datetime.now(),
                }
                self._workspaces[user_id] = workspace
            return dict(workspace)

    def set_workspace_plan(self, workspace_id: str, plan_id: str) -> None:
        """Troca o plano do workspace (usado pela cobrança na Fase S4 e pelo admin)."""
        try:
            if not self._use_db:
                raise RuntimeError("banco desligado neste repositório")
            with get_cursor() as cur:
                cur.execute("UPDATE workspaces SET plan_id = %s WHERE id = %s", (plan_id, workspace_id))
            return
        except Exception as e:
            self._debug(f"set_workspace_plan no banco falhou ({e}), usando memória")
        with self._lock:
            for workspace in self._workspaces.values():
                if workspace["id"] == workspace_id:
                    workspace["plan_id"] = plan_id

    # ─── Uso mensal ──────────────────────────────────────────────────────────

    def get_usage(self, workspace_id: str, user_id: int, period: str) -> dict[str, int]:
        """Total de cada métrica no período: {'ai_generation': 3, ...}."""
        try:
            if not self._use_db:
                raise RuntimeError("banco desligado neste repositório")
            with get_cursor() as cur:
                cur.execute(
                    """
                    SELECT metric, amount FROM usage_counters
                    WHERE workspace_id = %s AND user_id = %s AND period = %s
                """,
                    (workspace_id, user_id, period),
                )
                return {row["metric"]: max(0, int(row["amount"])) for row in cur.fetchall()}
        except Exception as e:
            self._debug(f"get_usage no banco falhou ({e}), usando memória")
        with self._lock:
            return {
                metric: max(0, amount)
                for (ws, uid, metric, per), amount in self._usage.items()
                if ws == workspace_id and uid == user_id and per == period
            }

    def try_consume(self, workspace_id: str, user_id: int, metric: str, period: str, limit: int | None) -> bool:
        """Soma 1 ao uso se ainda couber no limite (None = sem limite). Atômico."""
        if limit is not None and limit <= 0:
            return False
        try:
            if not self._use_db:
                raise RuntimeError("banco desligado neste repositório")
            with get_cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO usage_counters (workspace_id, user_id, metric, period, amount)
                    VALUES (%s, %s, %s, %s, 1)
                    ON CONFLICT (workspace_id, user_id, metric, period)
                    DO UPDATE SET amount = usage_counters.amount + 1, updated_at = NOW()
                    WHERE %s::integer IS NULL OR usage_counters.amount < %s::integer
                    RETURNING amount
                """,
                    (workspace_id, user_id, metric, period, limit, limit),
                )
                return cur.fetchone() is not None
        except Exception as e:
            self._debug(f"try_consume no banco falhou ({e}), usando memória")
        key = (workspace_id, user_id, metric, period)
        with self._lock:
            used = self._usage.get(key, 0)
            if limit is not None and used >= limit:
                return False
            self._usage[key] = used + 1
            return True

    def release(self, workspace_id: str, user_id: int, metric: str, period: str) -> None:
        """Devolve 1 uso (a IA falhou ou o resultado veio do cache)."""
        try:
            if not self._use_db:
                raise RuntimeError("banco desligado neste repositório")
            with get_cursor() as cur:
                cur.execute(
                    """
                    UPDATE usage_counters SET amount = GREATEST(amount - 1, 0), updated_at = NOW()
                    WHERE workspace_id = %s AND user_id = %s AND metric = %s AND period = %s
                """,
                    (workspace_id, user_id, metric, period),
                )
            return
        except Exception as e:
            self._debug(f"release no banco falhou ({e}), usando memória")
        key = (workspace_id, user_id, metric, period)
        with self._lock:
            if self._usage.get(key, 0) > 0:
                self._usage[key] -= 1

    def export_for_user(self, user_id: int) -> dict:
        """Workspaces e uso da pessoa, para a cópia de dados da LGPD."""
        with get_cursor() as cur:
            cur.execute(
                """
                SELECT w.id, w.name, w.kind, w.plan_id, m.role, m.joined_at
                FROM workspace_members m JOIN workspaces w ON w.id = m.workspace_id
                WHERE m.user_id = %s ORDER BY m.joined_at
            """,
                (user_id,),
            )
            workspaces = [{**dict(r), "id": str(r["id"])} for r in cur.fetchall()]
            cur.execute(
                """
                SELECT workspace_id, metric, period, amount FROM usage_counters
                WHERE user_id = %s ORDER BY period, metric
            """,
                (user_id,),
            )
            usage = [{**dict(r), "workspace_id": str(r["workspace_id"])} for r in cur.fetchall()]
        return {"workspaces": workspaces, "usage": usage}

    def reset_memory(self) -> None:
        """Limpa o estado em memória (testes)."""
        with self._lock:
            self._workspaces.clear()
            self._usage.clear()
            self._plans = {pid: {"id": pid, **copy.deepcopy(p)} for pid, p in DEFAULT_PLANS.items()}

    @staticmethod
    def _debug(message: str) -> None:
        if DEBUG:
            print(f"[planos] {message}")


plan_repo = PlanRepository()
