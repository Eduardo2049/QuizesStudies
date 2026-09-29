# Quiz Study — Documento de Arquitetura, Busca Rápida e Governança

Este documento consolida a arquitetura completa do **Quiz Study**, funcionando como guia fixo para desenvolvedores humanos e agentes de IA localizarem instantaneamente qualquer parte do sistema sem necessidade de reanalisar o repositório inteiro a cada alteração.

---

## 🏗️ 1. Diagrama de Arquitetura

```mermaid
graph TD
    Client[Cliente / Navegador Web] -->|HTTP / REST| Handler[api/handlers/quiz_handler.py]
    Handler --> Middleware[api/middleware/http_middleware.py]
    Handler --> AuthController[api/controllers/auth_controller.py]
    Handler --> QuizController[api/controllers/quiz_controller.py]

    AuthController --> AuthService[api/services/auth_service.py]
    AuthService --> UserRepo[api/repositories/user_repository.py]

    QuizController --> UploadService[api/services/upload_service.py]
    QuizController --> AIService[api/services/ai_service.py]
    QuizController --> QuizRepo[api/repositories/quiz_repository.py]

    UploadService --> FileParser[api/utils/file_parser.py]
    UploadService --> AIService
    UploadService --> QuizRepo

    AIService -->|API| GoogleGemini[Google AI Studio / Gemini]
    AIService -->|API| OpenRouter[OpenRouter API]

    UserRepo --> DB[(PostgreSQL / SQLite)]
    QuizRepo --> DB
```

---

## 📍 2. Índice Fixo de Onde Procurar

Ao receber uma demanda, consulte esta tabela para abrir diretamente os arquivos envolvidos:

### 🎨 Frontend & Design System
| Objetivo | Arquivo Principal | Arquivos Secundários |
| :--- | :--- | :--- |
| **Estilos, cores, temas, responsividade mobile/desktop** | `web/styles.css` | `web/modules/theme.js` |
| **Estrutura visual HTML, modais, cabeçalho, textos** | `web/index.html` | `web/login.html`, `web/register.html` |
| **Eventos de tela, ciclo de prova, envio, estado local** | `web/app.js` | — |
| **Mapeamento de atalhos de teclado (A-D, 1-4, etc.)** | `web/modules/shortcuts.js` | `web/app.js` |
| **Analytics e métricas pedagógicas de desempenho** | `web/modules/stats.js` | `web/app.js` |

### 🧠 Backend, Serviços & IA
| Objetivo | Arquivo Principal | Arquivos Secundários |
| :--- | :--- | :--- |
| **IA: Geração por tema, estruturação de arquivo, gabaritos** | `api/services/ai_service.py` | `api/utils/config.py` |
| **Upload: Extração de texto de TXT, PDF, DOCX e corte** | `api/services/upload_service.py` | `api/utils/file_parser.py` |
| **Roteamento de URLs, endpoints da API, rate limit** | `api/handlers/quiz_handler.py` | `api/middleware/http_middleware.py` |
| **Autenticação, hash de senhas PBKDF2, JWT de sessão** | `api/services/auth_service.py` | `api/controllers/auth_controller.py` |
| **Banco de dados, tabelas, migrações e persistência** | `api/database/migrations.py` | `api/repositories/quiz_repository.py` |
| **Servidor HTTP nativo e inicialização** | `quiz_api.py` | `api/utils/config.py` |

---

## 🔒 3. Governança: Liberdades e Proibições

### 🟢 O que é PERMITIDO (Liberdade total de evolução)
- Aperfeiçoar o design visual em `web/styles.css` (cores, animações, acessibilidade, breakpoints de tela).
- Criar novos componentes visuais ou refatorar o JavaScript em `web/modules/`.
- Ajustar heurísticas de regex em `api/utils/file_parser.py` para suportar novos formatos de questões.
- Otimizar prompts de IA em `api/services/ai_service.py` para respostas mais precisas e didáticas.
- Adicionar novos testes automatizados em `tests/`.

### 🔴 O que é PROIBIDO (Zonas restritas de segurança)
1. **Credenciais:** Jamais commitar ou alterar dados reais do arquivo `.env`. Atualizações de chaves devem ser registradas apenas em `.env.example`.
2. **Dependências:** Não instalar frameworks CSS (Bootstrap, Tailwind) nem frameworks JS pesados (React, Vue). O projeto é intencionalmente **Vanilla**.
3. **Destruição de Dados:** Não adicionar `DROP TABLE` ou comandos destrutivos em `api/database/migrations.py`. Todas as migrações devem ser seguras e idempotentes.
4. **Segurança:** Não desativar limitadores de taxa (`RateLimiter`), hashing de senha ou validação de permissões de administrador.
5. **Git:** Não executar comandos de reescrita de histórico (`git reset --hard`, `git push --force`).
6. **Varredura Cega:** Evitar listar pastas inteiras quando o alvo da alteração já estiver mapeado.

---

## 🧪 4. Como Executar e Validar

- **Rodar o servidor localmente:**
  ```bash
  python quiz_api.py
  ```
- **Rodar a suíte completa de testes:**
  ```bash
  python -m unittest discover tests
  ```
- **Rodar um teste específico:**
  ```bash
  python -m unittest tests/test_file_parser_extended.py
  ```
