# Guia de Localização Rápida no Código (Codebase Lookup Guide)

Este documento foi criado para evitar a varredura completa do repositório a cada tarefa. Consulte este índice para ir diretamente aos arquivos corretos.

---

## 🧭 Fluxo de Dados e Camadas

### 1. Camada de Apresentação (Frontend)
- **`web/index.html`**: Página principal da aplicação. Contém o cabeçalho, barra de ferramentas, seletor de questionário customizado, cronômetro, container do quiz e os modais (`uploadModal`, `resultModal`, `catalogModal`, `aboutModal`, `confirmSubmitModal`, `timerModal`).
- **`web/styles.css`**: Toda a folha de estilos do projeto. Contém tokens de cores (Claro / Dracula Dark), estilos de componentes, e regras responsivas para mobile/tablet (`@media (max-width: 768px)` e `@media (max-width: 380px)`).
- **`web/app.js`**: Orquestrador do frontend. Gerencia renderização de perguntas, seleção de alternativas, envio de respostas para `/api/quiz/submit`, cronômetro, upload de arquivos (`doUpload`), geração por tema (`doGenerateTopic`), e controle de estado do aluno (guest vs logado).
- **`web/modules/theme.js`**: Gerenciador de alternância de tema (Claro / Noturno / Sistema) com persistência em `localStorage` e prevenção de FOUC.
- **`web/modules/shortcuts.js`**: Mapeamento de teclas de atalho (A-D, 1-4, setas para navegação, Ctrl+Enter para finalizar).
- **`web/modules/stats.js`**: Cálculo de métricas pedagógicas, taxa de acerto por disciplina/seção e ritmo de prova (tempo por questão).
- **`web/login.html` & `web/register.html`**: Telas dedicadas de login e cadastro.

### 2. Camada de Roteamento e Handlers (Backend HTTP)
- **`api/handlers/quiz_handler.py`**: O roteador central HTTP (`BaseHTTPRequestHandler`). Trata:
  - `POST /api/auth/login`, `POST /api/auth/register`, `POST /api/auth/logout`, `GET /api/auth/me`
  - `GET /api/quizzes`, `GET /api/quiz/{name}`
  - `POST /api/upload` (processamento de arquivos multipart)
  - `POST /api/quiz/generate` (geração de simulado por tema via IA)
  - `POST /api/quiz/submit` (correção e validação de gabarito)
  - `POST /api/quiz/remix-mistakes` (variação de questões erradas via IA)
- **`api/middleware/http_middleware.py`**: Utilitários para extração de token JWT/sessão dos cookies, parsing de IP do cliente e formatação de respostas JSON padronizadas.

### 3. Camada de Controle e Negócio (Controllers & Services)
- **`api/controllers/quiz_controller.py`**: Recebe chamadas do handler, orquestra serviços e formata respostas de quizzes e uploads.
- **`api/controllers/auth_controller.py`**: Controla operações de autenticação e validação de payload.
- **`api/services/ai_service.py`**: Integração direta com Google Gemini e OpenRouter. Funções principais:
  - `generate_quiz_by_topic(topic, num_questions, difficulty, context, client_ip)`: Cria simulado completo a partir de tema.
  - `parse_and_structure_questions_with_ai(text, num_questions, context, client_ip)`: Estrutura arquivos sem padrão ou transforma material teórico em questões.
  - `generate_answer_key(questions, client_ip)`: Resolve e cria gabarito fundamentado para questões sem resposta.
  - `remix_mistakes_with_ai(questions, client_ip)`: Gera novas questões mutadas com base nos erros do aluno.
- **`api/services/upload_service.py`**: Validação de peso, extração de texto (via `file_parser.py`), detecção de gabarito, corte pela quantidade escolhida (`num_questions`) e persistência.
- **`api/services/auth_service.py`**: Criação de hash seguro de senhas com PBKDF2, geração e validação de tokens JWT de sessão.

### 4. Camada de Dados e Persistência (Repositories & Database)
- **`api/database/migrations.py`**: Migrações do schema PostgreSQL (tabelas `users`, `quizzes`, `sessions`) com fallback em memória SQLite.
- **`api/repositories/quiz_repository.py`**: Operações SQL para salvar, buscar e listar quizzes públicos e privados.
- **`api/repositories/user_repository.py`**: Operações SQL de usuários e sessões ativas.

### 5. Configuração e Ponto de Entrada
- **`quiz_api.py`**: Ponto de entrada que inicializa migrações e sobe o `ThreadingHTTPServer`.
- **`api/utils/config.py`**: Leitura de variáveis de ambiente (`PORT`, `HOST`, `DATABASE_URL`, `GEMINI_API_KEY`, etc.).
