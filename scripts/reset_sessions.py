"""
Script CLI para invalidar todas as sessões de usuários no banco de dados.
Uso:
    python scripts/reset_sessions.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from api.repositories.user_repository import UserRepository


def reset_sessions():
    print("Invalidando todas as sessões ativas no banco de dados...")
    try:
        repo = UserRepository()
        cleared = repo.clear_all_sessions()
        print(f"Sucesso: {cleared} sessões foram removidas.")
        print("Todos os usuários anteriores precisarão realizar login novamente.")
    except Exception as e:
        print(f"Erro ao invalidar sessões: {e}")
        sys.exit(1)


if __name__ == "__main__":
    reset_sessions()
