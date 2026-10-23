"""
Script CLI para apagar os dados do banco (massas de teste), mantendo o schema.

Escopos:
    content  -> quizzes, questões, tentativas e registros de rate limit.
    all      -> tudo de 'content' + usuários (exceto o admin), sessões e
                pedidos de redefinição de senha. Todos precisarão entrar de novo.

Uso:
    python scripts/reset_database.py --scope content --dry-run   # só conta
    python scripts/reset_database.py --scope all --yes           # apaga

Sem --yes, em um terminal interativo, pede para digitar APAGAR.
Tudo roda numa única transação: se algo falhar, nada é apagado.
Usa DELETE (não DROP/TRUNCATE): tabelas, índices e migrations ficam intactos.
"""
import argparse
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from api.database.connection import get_cursor  # noqa: E402
from api.utils.config import ADMIN_USERNAME, DATABASE_URL  # noqa: E402

CONFIRM_WORD = "APAGAR"
SCOPES = ("content", "all")


def build_steps(scope: str, admin_username: str) -> list[tuple[str, str, tuple]]:
    """Retorna [(rótulo, sql, params)] na ordem de execução (filhos antes dos pais)."""
    if scope not in SCOPES:
        raise ValueError(f"Escopo inválido: {scope}")
    steps = [
        ("quiz_attempts", "DELETE FROM quiz_attempts", ()),
        ("questions", "DELETE FROM questions", ()),
        ("quizzes", "DELETE FROM quizzes", ()),
        ("rate_limits", "DELETE FROM rate_limits", ()),
    ]
    if scope == "all":
        steps += [
            ("password_resets", "DELETE FROM password_resets", ()),
            ("sessions", "DELETE FROM sessions", ()),
            ("users (exceto admin)", "DELETE FROM users WHERE LOWER(username) <> LOWER(%s)", (admin_username,)),
        ]
    return steps


def describe_target(url: str | None) -> str:
    """Host/banco do alvo sem usuário nem senha, para conferência no log."""
    parsed = urlparse(url or "")
    host = parsed.hostname or "?"
    port = f":{parsed.port}" if parsed.port else ""
    db = (parsed.path or "/").lstrip("/") or "?"
    return f"{host}{port}/{db}"


def _count_sql(sql: str) -> str:
    """Converte 'DELETE FROM t [WHERE ...]' em 'SELECT COUNT(*) AS n FROM t [WHERE ...]'."""
    return "SELECT COUNT(*) AS n FROM " + sql.removeprefix("DELETE FROM ")


def run(scope: str, dry_run: bool, admin_username: str = ADMIN_USERNAME) -> dict[str, int]:
    """Conta (dry_run) ou apaga as linhas de cada passo. Retorna {rótulo: linhas}."""
    steps = build_steps(scope, admin_username)
    result: dict[str, int] = {}
    with get_cursor() as cur:
        for label, sql, params in steps:
            if dry_run:
                cur.execute(_count_sql(sql), params)
                result[label] = int(cur.fetchone()["n"])
            else:
                cur.execute(sql, params)
                result[label] = cur.rowcount
    return result


def _confirmed(args) -> bool:
    if args.dry_run or args.yes:
        return True
    if not sys.stdin.isatty():
        print("Sem terminal interativo: use --yes para confirmar ou --dry-run para simular.")
        return False
    try:
        typed = input(f"Digite {CONFIRM_WORD} para confirmar: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return typed == CONFIRM_WORD


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apaga dados de teste do banco mantendo o schema.")
    parser.add_argument("--scope", choices=SCOPES, default="content",
                        help="content: quizzes/tentativas; all: também usuários (exceto admin) e sessões")
    parser.add_argument("--dry-run", action="store_true", help="Só conta as linhas, não apaga nada")
    parser.add_argument("--yes", action="store_true", help="Confirma sem perguntar (CI)")
    args = parser.parse_args(argv)

    if not (DATABASE_URL or "").strip():
        print("DATABASE_URL não configurada.", file=sys.stderr)
        return 1

    mode = "SIMULAÇÃO (nada será apagado)" if args.dry_run else "LIMPEZA"
    print(f"[reset-db] {mode} | escopo: {args.scope} | alvo: {describe_target(DATABASE_URL)}")
    if args.scope == "all":
        print(f"[reset-db] O usuário admin '{ADMIN_USERNAME}' é preservado.")

    if not _confirmed(args):
        print("[reset-db] Cancelado.")
        return 1

    try:
        result = run(args.scope, args.dry_run)
    except Exception as e:
        print(f"[reset-db] Erro (transação desfeita, nada foi apagado): {e}", file=sys.stderr)
        return 1

    verb = "seriam apagadas" if args.dry_run else "apagadas"
    for label, rows in result.items():
        print(f"  {label:<22} {rows:>7} linhas {verb}")
    print(f"[reset-db] Total: {sum(result.values())} linhas {verb}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
