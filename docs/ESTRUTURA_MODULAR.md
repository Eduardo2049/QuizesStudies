# Estrutura Modular do Projeto IFuture_Study

**Versão**: 2.0 (Spring Pattern)  
**Última atualização**: 2026-08-31

---

## 📂 Organização das Pastas (Atual)

```
IFuture_Study/
├── api/                              # Núcleo da aplicação
│   ├── __init__.py
│   ├── main.py                       # Servidor (entry point)
│   ├── handlers/
│   │   ├── __init__.py
│   │   ├── quiz_handler.py           # Requisições HTTP (padrão Spring)
│   │   └── quiz_handler_v2.py        # Nova versão com Middleware
│   ├── controllers/
│   │   ├── __init__.py
│   │   └── quiz_controller.py        # Rotas HTTP → Services
│   ├── services/
│   │   ├── __init__.py
│   │   └── quiz_service.py           # Lógica de negócio
│   ├── repositories/
│   │   ├── __init__.py
│   │   └── quiz_repository.py        # Acesso a dados
│   ├── models/
│   │   ├── __init__.py
│   │   └── dtos.py                   # DTOs (Data Transfer Objects)
│   ├── exceptions/
│   │   ├── __init__.py
│   │   └── quiz_exceptions.py        # Custom exceptions
│   ├── middleware/
│   │   ├── __init__.py
│   │   └── http_middleware.py        # CORS, Headers, ResponseFormatter
│   └── utils/
│       ├── __init__.py
│       ├── config.py                 # Configurações
│       ├── validators.py             # Validadores centralizados
│       ├── markdown_parser.py        # Parse de Markdown
│       └── quiz_logic.py             # Lógica de scoring
├── web/                              # Frontend
│   ├── index.html
│   ├── app.js
│   └── styles.css
├── docs/                             # Documentação
│   ├── INDEX.md                      # Índice de documentação
│   ├── GUIA_RAPIDO.md
│   ├── RESUMO_EXECUTIVO.md
│   ├── PADROES_DESENVOLVIMENTO_MANUS.md
│   ├── COMPONENTES_WATERMELON.md
│   ├── TEMAS_REALTIMECOLORS.md
│   ├── TEMPLATES_GODLY.md
│   ├── CHANGELOG.md
│   └── MELHORIAS_ARQUITETURAIS.md
├── tests/                            # Testes unitários
│   ├── __init__.py
│   └── test_validators.py
├── n8n/                              # Automação n8n (futura)
│   └── workflows/
├── quiz_api.py                       # Wrapper para compatibilidade
├── quiz_api_legacy.py                # Backup (deprecated)
├── requirements.txt
└── README.md
```

---

## 🏗️ Padrão Spring Pattern (Camadas)

### 1️⃣ Handler (HTTP)
```python
class QuizHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Parse requisição
        # Chama Controller
        # Retorna Response
```
**Responsabilidade**: Recepcionar requisições HTTP

---

### 2️⃣ Controller (Rotas)
```python
class QuizController:
    def get_quizzes(self):
        # Chama Service
        # Formata resposta
        # Retorna DTO
```
**Responsabilidade**: Mapear URLs para lógica de negócio

---

### 3️⃣ Service (Lógica de Negócio)
```python
class QuizService:
    def get_quiz(self, source_name):
        # Busca dados via Repository
        # Aplica regras de negócio
        # Retorna DTO
```
**Responsabilidade**: Lógica e orquestração

---

### 4️⃣ Repository (Dados)
```python
class QuizRepository:
    @staticmethod
    def find_by_name(source_name):
        # Acessa arquivo
        # Retorna dados brutos
```
**Responsabilidade**: Acesso a dados

---

### 5️⃣ Models (DTOs)
```python
@dataclass
class QuizDTO:
    title: str
    source: str
    questions: list
```
**Responsabilidade**: Estrutura de dados

---

## 🔄 Fluxo de Requisição

```
GET /api/quiz?source=1%20test
        ↓
Handler.do_GET()
├─ parse_qs(query)
├─ ResponseFormatter.validate()
└─ QuizController.get_quiz(source_name)
        ↓
Controller.get_quiz()
└─ QuizService.get_quiz(source_name)
        ↓
Service.get_quiz()
├─ QuizRepository.find_by_name(source_name)
├─ Aplica lógica (public_questions)
└─ Retorna QuizDTO
        ↓
Controller (recebe DTO)
├─ Formata para dict
└─ Retorna {"status": "success", "data": {...}}
        ↓
Handler (recebe resposta)
├─ ResponseFormatter.success(data)
└─ HTTPMiddleware.send_json_response()
        ↓
HTTP 200 + JSON
```

---

## 🎯 Responsabilidades por Camada

| Camada | Responsabilidade | Exemplo |
|--------|-----------------|---------|
| **Handler** | HTTP parsing | Parse headers, body, URL |
| **Controller** | Roteamento | GET → Service |
| **Service** | Lógica de negócio | Validar, processar, orquestrar |
| **Repository** | Acesso a dados | Ler/escrever arquivos |
| **Model/DTO** | Estrutura | Tipagem de dados |
| **Middleware** | Cross-cutting | CORS, cache, logging |

---

## 📦 Módulos Principais

### `api/utils/config.py`
```python
ROOT = Path(__file__).parent.parent.parent
API_DIR = ROOT / "api"
WEB_DIR = ROOT / "web"
HOST = "127.0.0.1"
PORT = int(os.getenv("QUIZ_PORT", "8000"))
DEBUG = os.getenv("DEBUG", "false").lower() == "true"
```

### `api/utils/validators.py`
```python
class AnswerValidator:
    @staticmethod
    def validate_submit_payload(payload) → (bool, str)

class MarkdownValidator:
    @staticmethod
    def validate_markdown_content(content) → (bool, str)
```

### `api/middleware/http_middleware.py`
```python
class HTTPMiddleware:
    @staticmethod
    def send_json_response(handler, status, data)
    @staticmethod
    def handle_preflight(handler)

class ResponseFormatter:
    @staticmethod
    def success(data, message="OK", status_code=200)
    @staticmethod
    def error(message, error_code, status_code=400)
```

### `api/utils/markdown_parser.py`
```python
def load_questions_from_markdown(path) → list[dict]
```

---

## 🚀 Como Executar

### Opção 1: Script wrapper
```powershell
python quiz_api.py
```

### Opção 2: Módulo direto
```powershell
python -m api.main
```

### Resultado esperado
```
✓ Quiz online em http://localhost:8000
  Arquitetura: Spring Pattern + Middleware
```

---

## 🔧 Variáveis de Ambiente

```powershell
# Porta do servidor (padrão: 8000, tenta 8000-8010)
$env:QUIZ_PORT = "8000"

# Arquivo Markdown a usar (padrão: primeiro encontrado)
$env:QUIZ_MARKDOWN = "C:\caminho\quiz.md"

# Ativa logging detalhado
$env:DEBUG = "true"
```

---

## 📍 Rotas da API

### GET `/api/quizzes`
Lista todos os quizzes disponíveis
```json
{
  "status": "success",
  "message": "OK",
  "data": {
    "quizzes": [
      {"name": "1 test", "label": "1 test"}
    ]
  }
}
```

### GET `/api/quiz?source=1%20test`
Carrega um quiz específico (sem respostas)
```json
{
  "status": "success",
  "message": "OK",
  "data": {
    "title": "Treino de raciocinio",
    "source": "1 test",
    "questions": [
      {
        "id": 1,
        "section": "Geral",
        "question": "Pergunta?",
        "options": ["A", "B", "C", "D"]
      }
    ]
  }
}
```

### POST `/api/quiz/submit`
Submete respostas e retorna score
```json
{
  "answers": {1: 0, 2: 1},
  "source": "1 test"
}
```

Retorna:
```json
{
  "status": "success",
  "message": "OK",
  "data": {
    "score": 2,
    "total": 3,
    "percentage": 66.67,
    "results": [
      {"id": 1, "submitted": 0, "correct": 0, "status": "correct"},
      {"id": 2, "submitted": 1, "correct": 1, "status": "correct"},
      {"id": 3, "submitted": null, "correct": 2, "status": "notAttempted"}
    ]
  }
}
```

---

## ✅ Benefícios da Estrutura

| Aspecto | Benefício |
|---------|-----------|
| **Manutenção** | Cada camada tem responsabilidade única |
| **Testes** | Componentes isolados e testáveis |
| **Reutilização** | Serviços e validadores compartilhados |
| **Escalabilidade** | Fácil adicionar handlers, controllers, etc |
| **Documentação** | Código auto-explicável com camadas |
| **Debug** | Erro em qual camada? Fácil localizar |

---

## 🧪 Testes

```powershell
# Instalar pytest
pip install pytest

# Executar testes
pytest tests/ -v

# Com cobertura
pip install pytest-cov
pytest tests/ --cov=api/
```

---

## 📝 Próximas Melhorias

1. **Frontend** (React + Watermelon Components)
2. **Temas** (RealtimeColors CSS Variables)
3. **Layouts Dinâmicos** (Godly Templates)
4. **Automação** (n8n + Upload de PDFs)

Ver [MELHORIAS_ARQUITETURAIS.md](MELHORIAS_ARQUITETURAIS.md)

---

**Status**: ✅ Production Ready  
**Versão**: 2.0  
**Padrão**: Spring Pattern + Middleware
