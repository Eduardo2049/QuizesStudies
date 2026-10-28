"""
Sessão de convidado e cota gratuita de IA.

Quem visita o site navega e resolve simulados sem conta. Para usar a IA (gerar por
tema, enviar arquivo que precise de estruturação ou gabarito por IA, gerar variações
dos erros) a pessoa entra na conta ou escolhe "continuar como convidado".

O convidado recebe um identificador aleatório num cookie HttpOnly (`qs_guest`) e
uma cota de usos de IA (GUEST_AI_LIMIT, padrão 3) numa janela deslizante
(GUEST_AI_WINDOW_HOURS, padrão 24 h). A cota é contada no servidor, em duas chaves:

- por convidado (`guest_ai:id:<id>`), que é o limite que a pessoa vê;
- por IP (`guest_ai:ip:<ip>`, GUEST_AI_IP_LIMIT), que impede renovar a cota apagando
  o cookie sem bloquear redes compartilhadas (escola, CGNAT).

O uso é reservado antes da chamada à IA (de forma atômica, pelo RateLimitRepository)
e devolvido se a geração falhar, para que erros do provedor não consumam a cota e
requisições paralelas não passem do limite.
"""
from __future__ import annotations

import re
import secrets

from api.exceptions.quiz_exceptions import GuestAILimitReached
from api.repositories.rate_limit_repository import RateLimitRepository, rate_limit_repo
from api.utils.config import GUEST_AI_IP_LIMIT, GUEST_AI_LIMIT, GUEST_AI_WINDOW_SECONDS

GUEST_COOKIE_NAME = "qs_guest"
GUEST_COOKIE_MAX_AGE = 30 * 24 * 60 * 60  # 30 dias
_GUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{32,64}$")


class GuestAIReservation:
    """Reserva preguiçosa de um uso de IA: só consome a cota quando `acquire()` é chamado.

    O upload só usa IA quando o arquivo não tem padrão reconhecível ou não tem
    gabarito; por isso a reserva é passada como callback e só é efetivada se a IA
    for de fato acionada. `acquire()` é idempotente dentro da mesma requisição.
    """

    def __init__(self, service: "GuestService", guest_id: str, client_ip: str):
        self._service = service
        self.guest_id = guest_id
        self.client_ip = client_ip
        self._keys: list[str] = []

    @property
    def acquired(self) -> bool:
        return bool(self._keys)

    def acquire(self) -> None:
        if self._keys:
            return
        self._keys = self._service._reserve_keys(self.guest_id, self.client_ip)

    def refund(self) -> None:
        if not self._keys:
            return
        self._service._refund_keys(self._keys)
        self._keys = []


class GuestService:
    """Regras do modo convidado: identificador, status e cota de IA."""

    def __init__(
        self,
        repo: RateLimitRepository | None = None,
        limit: int = GUEST_AI_LIMIT,
        ip_limit: int = GUEST_AI_IP_LIMIT,
        window_seconds: int = GUEST_AI_WINDOW_SECONDS,
    ):
        self.repo = repo or rate_limit_repo
        self.limit = limit
        self.ip_limit = ip_limit
        self.window = window_seconds

    # ── Identificador ─────────────────────────────────────────────────────────
    @staticmethod
    def new_guest_id() -> str:
        """43 caracteres URL-safe (256 bits): não dá para adivinhar o id de outra pessoa."""
        return secrets.token_urlsafe(32)

    @staticmethod
    def is_valid_guest_id(value: str | None) -> bool:
        return bool(value) and bool(_GUEST_ID_PATTERN.match(value))

    # ── Chaves de contagem ────────────────────────────────────────────────────
    @staticmethod
    def _guest_key(guest_id: str) -> str:
        return f"guest_ai:id:{guest_id}"

    @staticmethod
    def _ip_key(client_ip: str) -> str:
        return f"guest_ai:ip:{client_ip or 'unknown'}"

    # ── Status ────────────────────────────────────────────────────────────────
    def status(self, guest_id: str | None, client_ip: str) -> dict:
        """Quantos usos de IA restam. Sem `guest_id`, considera só o teto do IP."""
        ip_used = max(0, self.repo.get_usage(self._ip_key(client_ip), self.window))
        ip_remaining = max(0, self.ip_limit - ip_used)

        used = 0
        if guest_id:
            used = max(0, self.repo.get_usage(self._guest_key(guest_id), self.window))
        remaining = max(0, min(self.limit - used, ip_remaining))

        return {
            "limit": self.limit,
            "used": min(used, self.limit),
            "remaining": remaining,
            "window_hours": self.window // 3600,
        }

    # ── Reserva e devolução ───────────────────────────────────────────────────
    def reservation(self, guest_id: str, client_ip: str) -> GuestAIReservation:
        return GuestAIReservation(self, guest_id, client_ip)

    def _reserve_keys(self, guest_id: str, client_ip: str) -> list[str]:
        if self.limit <= 0:
            raise GuestAILimitReached(self.limit, self.window)

        guest_key = self._guest_key(guest_id)
        allowed, retry_after = self.repo.check_and_record(guest_key, self.limit, self.window, cost=1)
        if not allowed:
            raise GuestAILimitReached(self.limit, retry_after)

        ip_key = self._ip_key(client_ip)
        allowed, retry_after = self.repo.check_and_record(ip_key, self.ip_limit, self.window, cost=1)
        if not allowed:
            self._refund_keys([guest_key])
            raise GuestAILimitReached(self.limit, retry_after)

        return [guest_key, ip_key]

    def _refund_keys(self, keys: list[str]) -> None:
        # Um registro de custo -1 anula o uso reservado na soma da janela,
        # tanto em memória quanto no PostgreSQL, sem precisar de DELETE.
        for key in keys:
            self.repo.record(key, -1)


guest_service = GuestService()
