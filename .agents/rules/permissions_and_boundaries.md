# Requisitos, Liberdades e Proibições do Repositório (Boundaries & Permissions)

Este documento define formalmente os limites de acesso, requisitos de engenharia, liberdades concedidas e proibições rígidas para qualquer agente de IA ou desenvolvedor atuando neste projeto.

---

## 📋 1. Requisitos Técnicos do Sistema

1. **Stack Minimalista e Rápida:**
   - **Frontend:** HTML5 semântico, Vanilla JavaScript nativo (sem bundlers pesados, sem Webpack/Vite a menos que expressamente solicitado), Vanilla CSS com variáveis CSS (`--ink`, `--teal`, `--coral`, etc.).
   - **Backend:** Python 3.10+ sem frameworks pesados (FastAPI/Django/Flask). A aplicação usa o servidor nativo `ThreadingHTTPServer` estruturado com MVC limpo.
2. **Qualidade Visual (Aesthetics):**
   - Suporte contínuo a dois temas: Claro (acolhedor e limpo) e Noturno (paleta Dracula enriquecida com roxo claro `#9767f1`).
   - Todos os componentes devem ser responsivos para celulares (a partir de 320px), tablets e desktops.
   - Qualquer novo elemento de interface deve ter foco visível acessível, área de toque confortável (mínimo de 44-48px de altura em mobile) e feedback claro ao usuário.
3. **Integridade de Testes:**
   - O projeto possui suíte automatizada em `tests/`. Toda modificação que afete regras de negócio, parsers ou serviços DEVE passar em `python -m unittest discover tests`.

---

## 🟢 2. Liberdades e Zonas de Autonomia

Você tem total liberdade para agir sem consulta prévia nas seguintes áreas:

1. **Interface e Estilos (`web/`):**
   - Criar, aprimorar ou refatorar classes CSS em `web/styles.css`.
   - Adicionar classes utilitárias ou temas específicos.
   - Melhorar animações, micro-interações, tooltips e acessibilidade ARIA.
   - Criar novos componentes visuais desde que respeitem o Vanilla CSS e ES Modules.
2. **Lógica de Aplicação Frontend (`web/app.js` e `web/modules/`):**
   - Melhorar o tratamento de erros do usuário.
   - Otimizar renderização do DOM, gerenciamento de eventos e manipulação de estado local.
   - Criar novos módulos focados em `web/modules/` (como feito para `theme.js`, `shortcuts.js`, `stats.js`).
3. **Inteligência Artificial e Parsers (`api/services/ai_service.py`, `api/utils/file_parser.py`):**
   - Otimizar prompts de sistema e regras pedagógicas para melhorar a precisão do LLM.
   - Adicionar suporte a novos padrões de formatação de questões ou regex de gabarito.
   - Melhorar a sanitização de alternativas e títulos retornados pela IA.
4. **Testes (`tests/`):**
   - Adicionar novos arquivos de teste e novos métodos `test_*` para cobrir casos de borda.

---

## 🔴 3. Proibições Rígidas e Locais Protegidos

As seguintes regras são restrições inegociáveis:

### 🚫 Localizações Proibidas de Modificar sem Ordem Direta
- **`.env`**: NUNCA altere credenciais existentes nem exponha segredos em logs ou commits. Modificações em variáveis devem ser refletidas apenas em `.env.example`.
- **`.git/`**: NUNCA manipule a pasta `.git` internamente ou force resets destrutivos.
- **`Dockerfile`, `docker-compose.yml`, `Procfile`, `vercel.json`**: Não altere as configurações de deploy e containers a menos que a tarefa seja especificamente de DevOps/deploy.
- **`package.json`, `package-lock.json`**: Não adicione dependências npm desnecessárias. O projeto prioriza web nativa.

### 🚫 Práticas e Ações Proibidas
- **Proibido usar Frameworks CSS Externos:** Não importe Tailwind, Bootstrap ou bibliotecas semelhantes via CDN ou npm.
- **Proibido Destruição de Banco:** NUNCA execute `DROP TABLE`, `TRUNCATE` ou comandos SQL destrutivos em `api/database/migrations.py`. As migrações devem ser sempre incrementais e compatíveis com dados legados.
- **Proibido Remover Rate Limits ou Controles de Autenticação:** A aplicação protege recursos custosos de IA e endpoints com limitadores de requisição (`RateLimiter`) e validação de tokens de sessão (armazenados como hash SHA-256 no banco); eles nunca devem ser desativados.
- **Proibido Quebrar o Protocolo JSON:** Todos os endpoints sob `/api/` devem responder com a estrutura unificada de resposta (`{"status": "success", "data": ...}` ou `{"status": "error", "error": ...}`).
- **Proibido Varreduras Cegas no Repositório:** Não execute `list_dir` de toda a árvore de diretórios ou greps sem filtro quando os arquivos já estiverem mapeados no Guia de Busca.
