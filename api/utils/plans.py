"""
Planos do Acely e seus limites (docs/PLANO_SAAS.md, Fase S1).

Fonte da verdade em produção: a tabela `plans` no banco. Estes valores só servem para
1. criar as linhas na primeira migration (INSERT ... ON CONFLICT DO NOTHING: um ajuste
   feito depois direto no banco não é sobrescrito no próximo deploy);
2. responder quando o banco está fora (testes e modo local).

Limites (chave → significado; None = sem limite):
- ai_generations_per_month: simulados criados com IA por mês (tema ou arquivo que precisou de IA)
- ai_remixes_per_month: rodadas de variações do caderno de erros por mês
- max_questions: questões por simulado
- max_upload_mb: tamanho máximo do arquivo enviado
- model_tier: "fast" (provedores gratuitos) ou "accurate" (API paga, Fase S5)
- cross_check: gabarito conferido por um segundo modelo (Fase S5)
- team_workspaces: pode criar workspace de equipe (Fase S2)

O Grátis segue o que a página /produto promete hoje (até 30 questões, arquivos de 20 MB).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

# Teto técnico do gerador (api/services/upload_service.py e o prompt) e do servidor
HARD_MAX_QUESTIONS = 30
HARD_MAX_UPLOAD_MB = 20

DEFAULT_PLAN_ID = "free"

DEFAULT_PLANS: dict[str, dict] = {
    "free": {
        "name": "Grátis",
        "limits": {
            "ai_generations_per_month": 30,
            "ai_remixes_per_month": 10,
            "max_questions": 30,
            "max_upload_mb": 20,
            "model_tier": "fast",
            "cross_check": False,
            "team_workspaces": False,
        },
    },
    "pro": {
        "name": "Pro",
        "limits": {
            "ai_generations_per_month": 300,
            "ai_remixes_per_month": 300,
            "max_questions": 30,
            "max_upload_mb": 20,
            "model_tier": "accurate",
            "cross_check": True,
            "team_workspaces": False,
        },
    },
    "team": {
        "name": "Equipe",
        "limits": {
            "ai_generations_per_month": 300,
            "ai_remixes_per_month": 300,
            "max_questions": 30,
            "max_upload_mb": 20,
            "model_tier": "accurate",
            "cross_check": True,
            "team_workspaces": True,
        },
    },
    "institution": {
        "name": "Instituição",
        "limits": {
            "ai_generations_per_month": None,
            "ai_remixes_per_month": None,
            "max_questions": 30,
            "max_upload_mb": 20,
            "model_tier": "accurate",
            "cross_check": True,
            "team_workspaces": True,
        },
    },
}

# Métricas contadas por mês → chave do limite correspondente
METRIC_LIMIT_KEYS = {
    "ai_generation": "ai_generations_per_month",
    "ai_remix": "ai_remixes_per_month",
}

# O Brasil não tem horário de verão desde 2019: o mês vira à meia-noite de Brasília.
# Offset fixo evita depender do banco de fusos (tzdata) no servidor.
BILLING_TZ = timezone(timedelta(hours=-3))


def current_period(now: datetime | None = None) -> str:
    """Mês de cobrança no formato 'AAAA-MM' (horário de Brasília)."""
    now = (now or datetime.now(timezone.utc)).astimezone(BILLING_TZ)  # noqa: UP017 - Python 3.10
    return f"{now.year:04d}-{now.month:02d}"


def period_renews_on(period: str) -> date:
    """Primeiro dia do mês seguinte ao período 'AAAA-MM'."""
    year, month = (int(part) for part in period.split("-"))
    return date(year + (month == 12), month % 12 + 1, 1)


def effective_limits(limits: dict | None) -> dict:
    """Completa com o Grátis o que faltar e aplica os tetos técnicos do servidor."""
    merged = dict(DEFAULT_PLANS[DEFAULT_PLAN_ID]["limits"])
    merged.update({k: v for k, v in (limits or {}).items() if k in merged})
    if merged["max_questions"] is None or merged["max_questions"] > HARD_MAX_QUESTIONS:
        merged["max_questions"] = HARD_MAX_QUESTIONS
    if merged["max_upload_mb"] is None or merged["max_upload_mb"] > HARD_MAX_UPLOAD_MB:
        merged["max_upload_mb"] = HARD_MAX_UPLOAD_MB
    return merged
