# Como Contribuir — Quiz Study

Obrigado pelo interesse em contribuir! 🎉

## Pré-requisitos

- Python 3.11+
- PostgreSQL 14+ (ou use o `docker-compose.yml`)
- Git

## Configuração do Ambiente

```bash
# 1. Clone o repositório
git clone https://github.com/Eduardo2049/QuizesStudies.git
cd QuizesStudies

# 2. Instale as dependências
pip install -r requirements.txt

# 3. Copie e configure as variáveis de ambiente
cp .env.example .env
# Edite o .env com suas configurações locais

# 4. Inicie o servidor local
python quiz_api.py
```

## Fluxo de Contribuição (Gitflow)

1. **Crie uma branch** a partir de `develop`:
   ```bash
   git checkout develop
   git pull origin develop
   git checkout -b feature/nome-descritivo
   ```

2. **Implemente** sua mudança com commits descritivos.

3. **Execute os testes** antes de abrir o PR:
   ```bash
   python -m unittest discover tests -v
   ```

4. **Abra um Pull Request** para a branch `develop`.

5. O **CI** executará os testes automaticamente. Aguarde a aprovação.

## Padrões de Código

- **Python**: Siga o PEP 8 e use `ruff` para lint:
  ```bash
  ruff check .
  ruff format --check .
  ```
- **Frontend**: Vanilla JavaScript (ES Modules), Vanilla CSS. Sem frameworks.
- **Docstrings**: Em português, seguindo o estilo Google.
- **Commits**: Use prefixos semânticos (`feat:`, `fix:`, `docs:`, `ci:`, `refactor:`, `test:`).

## Restrições Importantes

- **NÃO** instale frameworks CSS (Tailwind, Bootstrap) ou frontend (React, Angular, Vue).
- **NÃO** use `DROP TABLE` ou `TRUNCATE` em migrations. Sempre use `IF NOT EXISTS`.
- **NÃO** exponha credenciais ou chaves de API no código. Use `.env`.
- **NÃO** desabilite rate limits, hashing de senhas ou verificações de segurança.

## Reportar Problemas

Use os [templates de issue](.github/ISSUE_TEMPLATE/) para reportar bugs ou sugerir funcionalidades.

## Licença

Ao contribuir, você concorda que sua contribuição será licenciada sob a mesma licença do projeto (MIT).
