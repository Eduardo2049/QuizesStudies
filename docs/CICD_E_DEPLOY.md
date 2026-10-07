# Guia de CI/CD, Gitflow e Deploy — Quiz Study

Este documento descreve o fluxo de trabalho de desenvolvimento, integração contínua (CI), homologação e deploy em produção do **Quiz Study** via GitHub Actions e Vercel.

---

## 🌳 1. Estrutura de Branches e Ambientes

Adotamos um fluxo baseado em **Gitflow moderno** com promoção controlada por Pull Requests e deploy automático por ambiente:

```
feature/xyz ──PR──▶ develop ──PR──▶ homolog ──▶ release/x.x.x ──PR+tag──▶ main
     │                 │                │               │                    │
     ▼                 ▼                ▼               ▼                    ▼
Preview temporário   DEV env         STAGING env    (sem deploy)          PRODUÇÃO
  (Vercel Preview)  (Vercel Preview) (Vercel Preview) só prepara tag    (Vercel Production)
```

### Mapa de Branches

| Branch | Finalidade | Ambiente Vercel | Deploy | Quem faz merge? |
|---|---|---|---|---|
| `main` | **Produção** | Production | Automático no push/merge | Recebe PR de `release/*` |
| `homolog` | **Staging / QA** | Preview (staging) | Automático no push/merge | Recebe PR de `develop` |
| `develop` | **Desenvolvimento Integrado** | Preview (dev) | Automático no push/merge | Recebe PR de `feature/*` |
| `feature/*` | Desenvolvimento de funcionalidade | Preview temporário | Automático no push | Nasce de `develop`, volta via PR |
| `release/x.x.x` | Preparação de release | — | Sem deploy próprio | Nasce de `homolog`, PR para `main` com tag |

---

## ⚙️ 2. Pipelines do GitHub Actions

Os workflows estão configurados em `.github/workflows/`:

### 2.1 `ci.yml` — Testes Automatizados (CI)
- **Gatilho:** Pushes e Pull Requests nas branches `develop`, `homolog` e `main`.
- **Ambiente:** Ubuntu Latest, Python 3.11 com cache de dependências `pip`.
- **Banco de Dados:** Fallback automático para SQLite em memória (`DATABASE_URL: ""`), garantindo testes independentes e rápidos sem necessidade de container PostgreSQL no runner.
- **Comando:** `python -m unittest discover tests -v`.
- **Regra:** Deve passar 100% como status check obrigatório antes de qualquer merge.

### 2.2 `release.yml` — Deploy e Changelog de Produção
- **Gatilho:** Criação de tags no padrão `v*` (ex: `v1.0.0`, `v1.1.0`).
- **Passos:**
  1. Executa a suíte completa de testes para validação final.
  2. Extrai o log de commits desde a tag anterior.
  3. Cria um **GitHub Release** formal com changelog automático.
  4. O deploy de produção é efetuado automaticamente pela Vercel assim que o commit correspondente está na `main`.

---

## 🚀 3. Configuração na Vercel

O projeto roda como uma aplicação unificada na Vercel:
- **Frontend:** Estáticos servidos a partir de `web/` com rotas e headers definidos em `vercel.json`.
- **Backend:** Funções serverless Python servidas a partir de `api/index.py`.

### 3.1 Configuração de Branch de Produção
1. No painel do projeto na Vercel, acesse **Settings > Git**.
2. Garanta que o **Production Branch** seja `main`.
3. Pushes para `main` geram deploy de Produção (`production`).
4. Pushes para qualquer outro branch (`develop`, `homolog`, `feature/*`) geram deploys de **Preview** com URLs isoladas.

### 3.2 Variáveis de Ambiente por Escopo
Acesse **Settings > Environment Variables** no painel da Vercel e cadastre as variáveis marcando o ambiente correspondente:

| Variável | Escopo Production (`main`) | Escopo Preview (`develop`, `homolog`) |
|---|---|---|
| `DATABASE_URL` | String de conexão do PostgreSQL de produção | String do PostgreSQL de homolog/dev |
| `ADMIN_USERNAME` | Nome seguro do administrador | `admin` |
| `ADMIN_PASSWORD` | Senha forte e exclusiva | Senha de homologação |
| `AI_PROVIDER` | `google` | `google` |
| `GEMINI_API_KEY` | Chave de API Google AI Studio de produção | Chave de homolog/dev |
| `COOKIE_SECURE` | `true` | `true` |
| `DEBUG` | `false` | `false` |

---

## 🛡️ 4. Regras de Proteção de Branches (GitHub)

Para garantir a estabilidade do fluxo, configure no GitHub (**Settings > Branches > Add branch ruleset / protection rule**):

### Regra para `main`
- **Branch name pattern:** `main`
- ☑ **Require a pull request before merging** (mínimo de 1 aprovação)
- ☑ **Require status checks to pass before merging**:
  - Selecione o status check: `Testes Python`
- ☑ **Require branches to be up to date before merging**
- ☑ **Do not allow force pushes**
- ☑ **Do not allow deletions**

### Regra para `homolog` e `develop`
- **Branch name pattern:** `homolog` e `develop`
- ☑ **Require a pull request before merging**
- ☑ **Require status checks to pass before merging** (`Testes Python`)
- ☑ **Do not allow force pushes**

---

## 📋 5. Guia Rápido: Como Lançar uma Release

Quando as funcionalidades em `homolog` forem testadas e aprovadas para irem a produção:

```bash
# 1. Atualize sua homolog local
git checkout homolog
git pull origin homolog

# 2. Crie a branch de release (ex: v1.0.0)
git checkout -b release/1.0.0

# 3. Se necessário, ajuste números de versão ou changelog estático, commite e envie
git push origin release/1.0.0

# 4. Abra um Pull Request no GitHub: release/1.0.0 -> main
# Aguarde a execução do CI e faça o merge para a main

# 5. Na main atualizada, gere a tag anotada e faça o push:
git checkout main
git pull origin main
git tag -a v1.0.0 -m "Release v1.0.0"
git push origin v1.0.0

# 6. O GitHub Actions executará o release.yml gerando a release no GitHub
# A Vercel fará o deploy automático de produção com a main atualizada.
```
