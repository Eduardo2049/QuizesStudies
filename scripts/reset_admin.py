"""
Utilitário para redefinir ou criar a senha do usuário Administrador.

Uso:
    python scripts/reset_admin.py [nova_senha] [novo_usuario]
"""
import sys
import os
from pathlib import Path

# Adiciona a raiz do projeto ao path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from api.database.migrations import run_migrations
from api.repositories.user_repository import UserRepository
from api.services.auth_service import hash_password
from api.utils.config import ADMIN_USERNAME, ADMIN_PASSWORD

def main():
    new_password = sys.argv[1] if len(sys.argv) > 1 else ADMIN_PASSWORD
    if not new_password:
        print("Uso: python scripts/reset_admin.py \"NovaSenha123*\"")
        print("Ou defina ADMIN_PASSWORD no ambiente.")
        sys.exit(1)
    username = sys.argv[2] if len(sys.argv) > 2 else (ADMIN_USERNAME or "admin")

    try:
        run_migrations()
        repo = UserRepository()
        pwd_hash, salt = hash_password(new_password)

        user = repo.find_by_username(username)
        if user:
            repo.update_password_and_role(user["id"], pwd_hash, salt, role="admin")
            print(f"✅ Senha do administrador '{username}' atualizada com sucesso para: {new_password}")
        else:
            created = repo.create_user(
                username=username,
                email="admin@ifuture.study",
                password_hash=pwd_hash,
                salt=salt,
                role="admin",
            )
            print(f"✅ Administrador '{username}' criado com sucesso com ID {created['id']} e senha: {new_password}")
    except Exception as e:
        print(f"❌ Não foi possível conectar ao banco de dados: {e}")
        print("Dica: Certifique-se de que o PostgreSQL está rodando (ex: 'docker compose up -d') ou que DATABASE_URL está configurada corretamente.")
        sys.exit(1)

if __name__ == "__main__":
    main()
