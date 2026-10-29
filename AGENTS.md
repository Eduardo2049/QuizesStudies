# Diretrizes do Projeto & Guia Rápido de Pesquisa (Acely)

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
| **IA (OpenRouter com modelos gratuitos, prompts, limites; Gemini comentado para o futuro)** | `api/services/ai_service.py` | `web/styles.css`<br>`api/repositories/` |
| **Upload e leitura de arquivos (TXT, PDF, DOCX)** | `api/services/upload_service.py`<br>`api/utils/file_parser.py` | `api/services/auth_service.py`<br>`web/modules/` |
| **Rotas da API, endpoints, cookies, rate limits** | `api/handlers/quiz_handler.py`<br>`api/middleware/http_middleware.py` | Frontend `web/styles.css`<br>Migrations |
| **Autenticação, login, cadastro, senhas, tokens de sessão** | `api/services/auth_service.py`<br>`api/controllers/auth_controller.py`<br>`api/repositories/user_repository.py` | `api/utils/file_parser.py`<br>`api/services/ai_service.py` |
| **Acesso sem login, modo convidado e cota gratuita de IA** | `api/services/guest_service.py`<br>`api/handlers/quiz_handler.py` (rotas `/api/guest/*`)<br>`web/app.js` (`checkAuth`, `openAccessModal`, `requireAiAccess`) | `api/repositories/quiz_repository.py`<br>`web/styles.css` |
| **Domínio acely.com.br, SEO, manifesto, redirecionamento www** | `vercel.json` (`redirects`, `rewrites`)<br>`web/robots.txt`<br>`web/sitemap.xml`<br>`web/site.webmanifest`<br>`<head>` dos HTMLs (`canonical`, `og:*`) | `api/services/`<br>`api/repositories/` |
| **Termos, privacidade, 404, Minha conta (LGPD)** | `web/termos.html`<br>`web/privacidade.html`<br>`404.html` (na raiz, servido pela Vercel e pelo servidor)<br>`api/repositories/user_repository.py` (`export_user_data`, `delete_user_and_data`) | `api/services/ai_service.py` |
| **Entrar com Google e importar simulados do convidado** | `api/services/google_auth_service.py`<br>`api/services/import_service.py`<br>`web/modules/auth_page.js` | `web/styles.css` |
| **Idiomas da interface (PT/EN) e idioma da IA** | `web/modules/i18n.js`<br>`web/modules/i18n/en.js` (dicionário)<br>`web/modules/i18n-boot.js`<br>`api/services/ai_service.py` (`normalize_language`, campo `language`) | `api/repositories/`<br>`api/database/` |
| **Regras de design (skill adotada)** | `.claude/skills/landing-page-design/SKILL.md`<br>`docs/DESIGN_SKILLS.md` | Pasta `api/` |
| **Banco de dados, tabelas, consultas SQL, migrations** | `api/database/migrations.py`<br>`api/repositories/quiz_repository.py`<br>`api/repositories/user_repository.py` | Toda a pasta `web/` |
| **Configuração de ambiente, portas, chaves de API** | `api/utils/config.py`<br>`.env.example` | Código de regras de negócio |
| **Pipelines CI/CD, deploy e Gitflow** | `.github/workflows/`<br>`vercel.json`<br>`docs/CICD_E_DEPLOY.md` | Código de backend `api/` |
| **Plano em andamento (marca Acely, IA mais rápida e multiprovedor)** | `docs/PLANO_ACELY.md` (ler antes de começar uma fase) | Código fora da fase em execução |
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
   - **NUNCA** liberar endpoints de IA para quem não tem conta nem sessão de convidado, nem mover a contagem da cota do convidado (`GuestService`) para o navegador. O cliente só exibe a cota; quem decide é o servidor.
6. **Varreduras Globais Inúteis:**
   - Não execute comandos como `list_dir` recursivo na raiz inteira ou buscas genéricas que consumam contexto quando o problema apontar para um arquivo específico.

---

## ⚙️ 4. Padrões Arquiteturais Obrigatórios

- **Backend:** Python 3.10+ sem frameworks pesados; utiliza `http.server.ThreadingHTTPServer` com arquitetura em camadas (`handlers` -> `controllers` -> `services` -> `repositories`).
- **Banco de Dados:** PostgreSQL com fallback automático para SQLite em memória caso o PostgreSQL não esteja acessível.
- **Frontend:** HTML5 semântico, Vanilla CSS com suporte a temas Claro (papel/coral/teal) e Noturno (cinza-preto neutro com acentos azul/roxo da cena "Frosty Gradient" do Unicorn Studio; no escuro, os tokens `--coral`/`--teal` guardam o azul e o roxo e mantêm o nome por compatibilidade). Os dois temas têm o fundo animado em WebGL (`web/modules/backdrop.js`, cores nos tokens `--backdrop-*`). JavaScript modular nativo ES Modules.
- **Validação de Testes:** Execute sempre `python -m unittest discover tests` para assegurar que todas as suítes permaneçam 100% aprovadas.

---

## 🎨 5. Regras para Redesign de Interface (`web/`)

Referência completa: `docs/DESIGN_UPGRADE.md` e a skill de design adotada, traduzida para este projeto em `docs/DESIGN_SKILLS.md` (cópia original em `.claude/skills/landing-page-design/`). Resumo obrigatório:

- Seguir a skill `landing-page-design` pela tabela de tradução de `docs/DESIGN_SKILLS.md`: um CTA principal por tela, textos em caixa normal e sem exclamação, só Manrope (mono só em números), sem itálico, peso máximo 700, transições com `--ease-out` e nunca abaixo de 200ms.
- A home é aberta: nada de redirecionar visitantes para `/login`. Ações que exigem identidade abrem o modal de acesso (`#accessModal`).
- Somente Vanilla CSS/JS. Proibido Tailwind, Bootstrap, React/Vue, GSAP e ícones/fontes via CDN.
- A CSP (`vercel.json` e `api/middleware/http_middleware.py`) só permite `'self'`: fontes ficam em `web/fonts/` (woff2 + `font-display: swap`) e ícones são SVG inline via `web/modules/icons.js`. Não usar emojis como ícones de interface.
- Não alterar `package.json`, `Dockerfile`, `migrations.py` nem regras de negócio em `api/` por causa de mudanças visuais. Servir novos tipos estáticos exige apenas o mapeamento de `Content-Type` em `quiz_handler.py`.
- Manter IDs, classes usadas por `app.js` e atributos `aria-*` existentes (`tests/test_ui_contract.py` confere que os IDs usados pelo JS e as referências `for`/`aria-*` existem).
- Idiomas: o português escrito no HTML e no JS é o texto-fonte. Todo texto visível novo (inclusive `title`, `placeholder`, `aria-label`, `alt`) precisa da tradução em `web/modules/i18n/en.js`, com a chave idêntica ao texto em português; trechos dinâmicos usam `{0}`, `{1}`. Conteúdo que não deve ser traduzido (questões, nomes de simulados) leva `translate="no"`. As rotas de geração, upload e remix recebem `language` (padrão `pt-BR`).
- Contraste mínimo WCAG AA; respeitar `prefers-reduced-motion`; alvos de toque ≥ 44px no mobile; texto de rótulo ≥ 12px.
- Usar os tokens de `:root` (cor, `--space-*`, `--text-*`, `--radius-*`, `--dur-*`) em vez de valores soltos.
- Subir o `?v=` de `styles.css` e `app.js` nos HTMLs a cada mudança visual (cache de 1 dia).
- Antes de concluir: `python -m unittest discover tests` e, se possível, `python tests/visual/capture_baseline.py --label after` (e `--lang en` para o inglês; requer Playwright instalado). O script também acusa rolagem lateral e alvos de toque menores que 44px.
