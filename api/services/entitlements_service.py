"""
O que cada conta pode fazer no plano dela (docs/PLANO_SAAS.md, Fase S1).

Responde "esta pessoa pode gerar mais um simulado com IA este mês?", "quantas questões
cabem num simulado?" e "qual o tamanho máximo do arquivo?". O servidor decide; o navegador
só mostra o que GET /api/me/plan devolve.

Na Fase S1 a cota vale por pessoa dentro do workspace pessoal. Os workspaces de equipe
(Fase S2) usam a mesma tabela de uso com o id do workspace da equipe.

O administrador da plataforma (role 'admin') não tem cota.
"""

from __future__ import annotations

from dataclasses import dataclass

from api.exceptions.quiz_exceptions import PlanLimitReached, PlanQuestionLimit
from api.repositories.plan_repository import PlanRepository, plan_repo
from api.utils.plans import METRIC_LIMIT_KEYS, current_period, effective_limits, period_renews_on


@dataclass
class PlanContext:
    user_id: int
    workspace: dict
    plan: dict
    limits: dict
    unlimited: bool = False


class UsageReservation:
    """Reserva preguiçosa de 1 uso do mês: só consome quando `acquire()` é chamado.

    Mesmo contrato da reserva do convidado (GuestAIReservation): o upload passa
    `acquire` como `ai_gate` e só gasta cota se a IA for de fato acionada.
    """

    def __init__(self, service: EntitlementsService, ctx: PlanContext, metric: str):
        self._service = service
        self._ctx = ctx
        self.metric = metric
        self._period: str | None = None

    @property
    def acquired(self) -> bool:
        return self._period is not None

    def acquire(self) -> None:
        if self._period is not None:
            return
        self._period = self._service._consume(self._ctx, self.metric)

    def refund(self) -> None:
        if self._period is None:
            return
        if self._period != "unlimited":
            self._service.repo.release(self._ctx.workspace["id"], self._ctx.user_id, self.metric, self._period)
        self._period = None


class EntitlementsService:
    def __init__(self, repo: PlanRepository | None = None):
        self.repo = repo or plan_repo

    # ─── Contexto ────────────────────────────────────────────────────────────

    def context(self, user: dict) -> PlanContext:
        workspace = self.repo.get_personal_workspace(int(user["id"]))
        plan = self.repo.get_plan(workspace.get("plan_id") or "free")
        return PlanContext(
            user_id=int(user["id"]),
            workspace=workspace,
            plan=plan,
            limits=effective_limits(plan.get("limits")),
            unlimited=user.get("role") == "admin",
        )

    # ─── Cota mensal ─────────────────────────────────────────────────────────

    def reservation(self, user: dict, metric: str) -> UsageReservation:
        if metric not in METRIC_LIMIT_KEYS:
            raise ValueError(f"métrica desconhecida: {metric}")
        return UsageReservation(self, self.context(user), metric)

    def _consume(self, ctx: PlanContext, metric: str) -> str:
        if ctx.unlimited:
            return "unlimited"
        period = current_period()
        limit = ctx.limits.get(METRIC_LIMIT_KEYS[metric])
        if not self.repo.try_consume(ctx.workspace["id"], ctx.user_id, metric, period, limit):
            raise PlanLimitReached(metric, limit or 0, ctx.plan.get("name") or "Grátis", period_renews_on(period))
        return period

    # ─── Limites por pedido ──────────────────────────────────────────────────

    def check_questions(self, user: dict, requested) -> None:
        """Erro claro se o pedido passa do máximo de questões do plano ('auto' sempre cabe)."""
        if requested in (None, "") or str(requested).strip().lower() == "auto":
            return
        try:
            count = int(requested)
        except (TypeError, ValueError):
            return  # a validação de formato fica com o serviço de geração
        ctx = self.context(user)
        maximum = ctx.limits["max_questions"]
        if not ctx.unlimited and count > maximum:
            raise PlanQuestionLimit(maximum, ctx.plan.get("name") or "Grátis")

    def max_upload_bytes(self, user: dict) -> int:
        ctx = self.context(user)
        return int(ctx.limits["max_upload_mb"]) * 1024 * 1024

    # ─── Situação para a tela ────────────────────────────────────────────────

    def status(self, user: dict) -> dict:
        """Plano, limites e uso do mês (GET /api/me/plan e respostas das rotas de IA)."""
        ctx = self.context(user)
        period = current_period()
        used = self.repo.get_usage(ctx.workspace["id"], ctx.user_id, period)
        usage = {}
        for metric, limit_key in METRIC_LIMIT_KEYS.items():
            limit = None if ctx.unlimited else ctx.limits.get(limit_key)
            count = used.get(metric, 0)
            usage[metric] = {
                "used": count,
                "limit": limit,
                "remaining": None if limit is None else max(0, limit - count),
            }
        return {
            "plan": {"id": ctx.plan.get("id"), "name": ctx.plan.get("name")},
            "workspace": {
                "id": ctx.workspace["id"],
                "name": ctx.workspace.get("name"),
                "kind": ctx.workspace.get("kind"),
            },
            "limits": {
                "max_questions": ctx.limits["max_questions"],
                "max_upload_mb": ctx.limits["max_upload_mb"],
                "model_tier": ctx.limits.get("model_tier"),
                "cross_check": bool(ctx.limits.get("cross_check")),
                "team_workspaces": bool(ctx.limits.get("team_workspaces")),
            },
            "usage": usage,
            "period": period,
            "renews_on": period_renews_on(period).isoformat(),
            "unlimited": ctx.unlimited,
        }


entitlements_service = EntitlementsService()
