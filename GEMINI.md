# Diretrizes do Projeto & Guia Rápido de Pesquisa (Quiz Study)

Este documento é a referência primária e fixa de arquitetura, permissões, liberdades e proibições deste repositório.
**REGRA DE OURO:** NÃO analise nem varra todo o projeto a cada interação. Consulte diretamente a tabela de busca rápida abaixo e abra apenas os arquivos responsáveis pela demanda.

---

## 🗺️ 1. Mapa de Busca Rápida (Onde procurar sem varrer o projeto)

| Se a demanda for sobre... | Arquivos EXATOS a consultar | O que NÃO precisa olhar |
| :--- | :--- | :--- |
| **Estilos, cores, temas, responsividade, CSS** | `web/styles.css`<br>`web/modules/theme.js` | Toda a pasta `api/`<br>`web/app.js` (exceto se criar classes dinâmicas) |
| **Interface HTML, modais, marcação, textos estáticos** | `web/index.html`<br>`web/login.html`<br>`web/register.html` | Pasta `api/`<br>Pastas de testes |
| **Comportamento da tela, eventos, estado local, timer** | `web/app.js` | Backend `api/services/`<br>`api/repositories/` |
| **Atalhos de teclado (hotkeys)** | `web/modules/shortcuts.js`<br>`web/app.js` | Arquivos Python da `api/` |
| **Estatísticas e análise pedagógica do aluno** | `web/modules/stats.js` | Arquivos de upload ou banco |
| **IA (Google Gemini / OpenRouter, prompts, limites)** | `api/services/ai_service.py` | `web/styles.css`<br>`api/repositories/` |
| **Upload e leitura de arquivos (TXT, PDF, DOCX)** | `api/services/upload_service.py`<br>`api/utils/file_parser.py` | `api/services/auth_service.py`<br>`web/modules/` |
| **Rotas da API, endpoints, cookies, rate limits** | `api/handlers/quiz_handler.py`<br>`api/middleware/http_middleware.py` | Frontend `web/styles.css`<br>Migrations |
| **Autenticação, login, cadastro, senhas, tokens de sessão** | `api/services/auth_service.py`<br>`api/controllers/auth_controller.py`<br>`api/repositories/user_repository.py` | `api/utils/file_parser.py`<br>`api/services/ai_service.py` |
| **Banco de dados, tabelas, consultas SQL, migrations** | `api/database/migrations.py`<br>`api/repositories/quiz_repository.py`<br>`api/repositories/user_repository.py` | Toda a pasta `web/` |
| **Configuração de ambiente, portas, chaves de API** | `api/utils/config.py`<br>`.env.example` | Código de regras de negócio |
| **Pipelines CI/CD, deploy e Gitflow** | `.github/workflows/`<br>`vercel.json`<br>`docs/CICD_E_DEPLOY.md` | Código de backend `api/` |
| **Testes unitários e de integração** | `tests/` (execute o teste específico ou a suíte) | `web/` |

---

## 🟢 2. Liberdades (Zonas Seguras para Criação e Refatoração)

O agente tem total liberdade para:
1. **Frontend UI/UX (`web/styles.css`, `web/index.html`, `web/modules/`):**
   - Melhorar responsividade mobile, tablet e desktop.
   - Refinar contraste, tipografia, micro-animações, estados de foco e acessibilidade (ARIA).
   - Componentizar JavaScript em módulos reutilizáveis dentro de `web/modules/`.
2. **Serviços de Negócio (`api/services/`):**
   - Aprimorar prompts de IA, tratamento de respostas JSON e heurísticas de extração de texto.
   - Otimizar sanitização e validação de dados de entrada.
3. **Novos Testes (`tests/`):**
   - Criar novos cenários de testes unitários ou de integração sem restrições.
4. **Documentação e Guias (`docs/` ou `.agents/`):**
   - Criar e atualizar documentos de arquitetura, referências e runbooks.

---

## 🔴 3. Proibições e Restrições Críticas (Zonas Proibidas)

É **ESTRITAMENTE PROIBIDO** realizar as seguintes ações:
1. **Segredos e Credenciais (`.env`):**
   - **NUNCA** commitar, expor em logs ou sobrescrever o arquivo `.env` com valores fictícios se já contiver chaves reais.
   - Ao adicionar novas variáveis, registre apenas o modelo em `.env.example`.
2. **Histórico e Git (`.git/`):**
   - Proibido executar comandos destrutivos como `git reset --hard`, `git clean -fd` ou `git push --force` sem autorização explícita do usuário.
3. **Destruição de Dados em Produção (`api/database/migrations.py`):**
   - **NUNCA** adicionar comandos `DROP TABLE`, `TRUNCATE` ou alterar tipos de colunas existentes sem migração compatível retroativa. As migrations devem ser sempre idempotentes (`IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS`).
4. **Dependências Externas Desnecessárias:**
   - **NÃO** instalar frameworks CSS pesados (ex: Tailwind, Bootstrap). O projeto é intencionalmente construído em **Vanilla CSS** moderno com CSS Variables.
   - **NÃO** instalar frameworks frontend pesados (ex: React, Angular, Vue) a menos que solicitado explicitamente. A stack do cliente é **Vanilla JavaScript**.
   - No Python, utilize a biblioteca padrão sempre que possível antes de sugerir novos pacotes no `requirements.txt`.
5. **Bypass de Segurança:**
   - **NUNCA** desativar rate limits (`RateLimiter`), hashing seguro de senhas (PBKDF2), verificação de permissões de administrador (`role == 'admin'`) ou proteção contra CSRF/CORS.
6. **Varreduras Globais Inúteis:**
   - Não execute comandos como `list_dir` recursivo na raiz inteira ou buscas genéricas que consumam contexto quando o problema apontar para um arquivo específico.

---

## ⚙️ 4. Padrões Arquiteturais Obrigatórios

- **Backend:** Python 3.10+ sem frameworks pesados; utiliza `http.server.ThreadingHTTPServer` com arquitetura em camadas (`handlers` -> `controllers` -> `services` -> `repositories`).
- **Banco de Dados:** PostgreSQL com fallback automático para SQLite em memória caso o PostgreSQL não esteja acessível.
- **Frontend:** HTML5 semântico, Vanilla CSS com suporte a temas Claro e Noturno (Dracula), JavaScript modular nativo ES Modules.
- **Validação de Testes:** Execute sempre `python -m unittest discover tests` para assegurar que todas as suítes permaneçam 100% aprovadas.
