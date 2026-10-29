# Guia de Localização Rápida no Código (Codebase Lookup Guide)

Este documento foi criado para evitar a varredura completa do repositório a cada tarefa. Consulte este índice para ir diretamente aos arquivos corretos.

---

## 🧭 Fluxo de Dados e Camadas

### 1. Camada de Apresentação (Frontend)
- **`web/index.html`**: Página principal da aplicação. Contém o cabeçalho, barra de ferramentas, seletor de questionário customizado, cronômetro, container do quiz e os modais (`uploadModal`, `resultModal`, `catalogModal`, `aboutModal`, `confirmSubmitModal`, `timerModal`).
- **`web/styles.css`**: Toda a folha de estilos do projeto. Contém tokens de cores (Claro / Noturno grafite neutro), estilos de componentes, e regras responsivas para mobile/tablet (`@media (max-width: 768px)` e `@media (max-width: 380px)`).
- **`web/app.js`**: Orquestrador do frontend. Gerencia renderização de perguntas, seleção de alternativas, envio de respostas para `/api/quiz/submit`, cronômetro, upload de arquivos (`doUpload`), geração por tema (`doGenerateTopic`), e controle de estado do aluno (guest vs logado).
- **`web/modules/theme.js`**: Gerenciador de alternância de tema (Claro / Noturno / Sistema) com persistência em `localStorage` e prevenção de FOUC.
- **`web/modules/shortcuts.js`**: Mapeamento de teclas de atalho (A-D, 1-4, setas para navegação, Ctrl+Enter para finalizar).
- **`web/modules/stats.js`**: Cálculo de métricas pedagógicas, taxa de acerto por disciplina/seção e ritmo de prova (tempo por questão).
- **`web/modules/i18n.js`, `web/modules/i18n-boot.js`, `web/modules/i18n/en.js`**: Tradução da interface (PT/EN). O português do HTML/JS é o texto-fonte; o dicionário traduz textos e atributos e um `MutationObserver` cobre o que o `app.js` gera depois. Escolha salva em `localStorage` (`quiz_lang`).
- **`web/termos.html`, `web/privacidade.html`, `404.html` (raiz)**: Páginas legais (LGPD) e 404 própria.
- **`web/login.html` & `web/register.html`**: Telas de login e cadastro. Aceitam `?next=` (só caminhos internos) para devolver a pessoa ao ponto onde estava.
- **Home aberta**: `/` é servida a qualquer visitante. `web/app.js` distingue visitante, convidado e conta (`sessionKind()`), mostra o modal de acesso (`#accessModal`) quando o visitante tenta criar um simulado ou usar a IA, e exibe a cota de IA do convidado (`#guestAiChip`).

### 2. Camada de Roteamento e Handlers (Backend HTTP)
- **`api/handlers/quiz_handler.py`**: O roteador central HTTP (`BaseHTTPRequestHandler`). Trata:
  - `POST /api/auth/login`, `POST /api/auth/register`, `POST /api/auth/logout`, `GET /api/auth/me`
  - `POST /api/auth/forgot-password`, `POST /api/auth/reset-password`, `GET /api/auth/verify-reset-token`
  - `GET /api/auth/providers`, `GET /api/auth/google/start`, `GET /api/auth/google/callback` (login com Google)
  - `GET /api/account/export`, `POST /api/account/delete` (LGPD), `POST /api/quizzes/import` (simulados do convidado)
  - `GET /api/user/attempts` (histórico e caderno de erros)
  - `POST /api/guest/start`, `POST /api/guest/end`, `GET /api/guest/status` (sessão de convidado e cota de IA)
  - `GET /api/quizzes`, `GET /api/quiz/{name}`
  - `POST /api/upload` (processamento de arquivos multipart)
  - `POST /api/quiz/generate` (geração de simulado por tema via IA; aceita `language`)
  - `POST /api/quiz/submit` (correção e validação de gabarito)
  - `POST /api/quiz/remix-mistakes` (variação de questões erradas via IA; aceita `language`)
- **`api/middleware/http_middleware.py`**: Utilitários para extração de token de sessão dos cookies, parsing de IP do cliente, formatação de respostas JSON padronizadas e recusa de POST vindo de outro site (`Origin` / `Sec-Fetch-Site`).

### 3. Camada de Controle e Negócio (Controllers & Services)
- **`api/controllers/quiz_controller.py`**: Recebe chamadas do handler, orquestra serviços e formata respostas de quizzes e uploads.
- **`api/controllers/auth_controller.py`**: Controla operações de autenticação e validação de payload.
- **`api/services/ai_service.py`**: Integração com o OpenRouter usando só modelos gratuitos (`:free`): os preferidos de `OPENROUTER_FREE_MODELS` e, como reserva, os descobertos na lista pública (cache de 6 h). Se um modelo falha, tenta o próximo e pausa o que falhou. Os modelos gratuitos raciocinam antes de responder e o raciocínio gasta o mesmo `max_tokens`, então o raciocínio vai desligado (effort `none`); se o modelo recusar, repete com effort `low` e 50% de folga no limite. Conta com "ZDR Endpoints Only" ligado bloqueia todos os gratuitos (404 "ZDR violation"): o serviço para na hora e registra no log onde mudar. Teto global diário (`AI_DAILY_CALL_LIMIT`). O Google AI Studio (Gemini) está desativado, com o código comentado aqui e em `config.py`. Funções principais:
  - `generate_quiz_by_topic(topic, num_questions, difficulty, context, client_ip, language)`: Cria simulado completo a partir de tema.
  - `parse_and_structure_questions_with_ai(text, max_chars, client_ip, num_questions, context, language)`: Estrutura arquivos sem padrão ou transforma material teórico em questões.
  - `generate_answer_key(questions, client_ip)`: Resolve e cria gabarito fundamentado para questões sem resposta.
  - `remix_questions_by_ai(questions, client_ip, language)`: Gera novas questões mutadas com base nos erros do aluno.
  - `normalize_language(value)`: Converte o idioma pedido pelo cliente (`pt-BR` ou `en`; padrão `pt-BR`).
- **`api/services/upload_service.py`**: Validação de peso, extração de texto (via `file_parser.py`), detecção de gabarito, corte pela quantidade escolhida (`num_questions`) e persistência.
- **`api/services/guest_service.py`**: Modo convidado. Gera o id do cookie `qs_guest` e controla a cota gratuita de IA (`GUEST_AI_LIMIT` usos por `GUEST_AI_WINDOW_HOURS`, com teto por IP `GUEST_AI_IP_LIMIT`). A reserva é atômica e é devolvida se a geração falhar.
- **`api/services/google_auth_service.py`**: Login com Google (OAuth com `state` em cookie); fica desligado sem `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`.
- **`api/services/import_service.py`**: Salva na conta os simulados criados como convidado, ao entrar ou se cadastrar.
- **`api/services/email_service.py`**: Envio do e-mail de redefinição de senha.
- **`api/services/auth_service.py`**: Criação de hash seguro de senhas com PBKDF2 (600k iterações), geração e validação de tokens de sessão opacos (armazenados como hash SHA-256 no banco).

### 4. Camada de Dados e Persistência (Repositories & Database)
- **`api/database/migrations.py`**: Migrações do schema PostgreSQL (tabelas `users`, `quizzes`, `sessions`) com fallback em memória SQLite.
- **`api/repositories/quiz_repository.py`**: Operações SQL para salvar, buscar e listar quizzes públicos e privados.
- **`api/repositories/user_repository.py`**: Operações SQL de usuários e sessões ativas, exportação (`export_user_data`) e exclusão de conta (`delete_user_and_data`).
- **`api/repositories/rate_limit_repository.py`**: Contadores persistentes de rate limit e cotas de IA.

### 5. Configuração e Ponto de Entrada
- **`quiz_api.py`**: Ponto de entrada que inicializa migrações e sobe o `ThreadingHTTPServer`.
- **`api/utils/config.py`**: Leitura de variáveis de ambiente (`PORT`, `HOST`, `DATABASE_URL`, `OPENROUTER_API_KEY`, `OPENROUTER_FREE_MODELS`, `AI_DAILY_CALL_LIMIT`, `GUEST_AI_LIMIT`, `GOOGLE_CLIENT_ID`, `APP_URL`, etc.).
