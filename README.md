# IFuture Study — Treino de Raciocínio & Mindsight

Plataforma interativa para prática guiada e avaliação de raciocínio lógico, sequências numéricas, dedução proposicional e interpretação de dados com gabarito inteligente e temporizador.

---

## 🚀 Como Executar Localmente

O projeto utiliza **exclusivamente a biblioteca padrão do Python** (zero dependências externas obrigatórias).

### 1. Iniciar o Servidor
```bash
python quiz_api.py
```
*Ou usando o módulo:*
```bash
python -m api.main
```

### 2. Acessar a Aplicação
Abra no seu navegador:
```
http://localhost:8000
```

---

## 🧪 Como Rodar os Testes

Execute a suíte de testes unitários com o executor integrado da biblioteca padrão:

```bash
python -m unittest discover tests
```

---

## ☁️ Instruções de Deploy

A aplicação está configurada para deploy simplificado em diversas plataformas:

### 1. Vercel
- **Configuração**: Roteamento gerenciado via `vercel.json` e Serverless Function em `api/index.py`.
- **Deploy**: Basta conectar seu repositório no dashboard da Vercel ou rodar `vercel` via CLI.

### 2. Render / Railway / Heroku
- **Configuração**: Utiliza o arquivo `Procfile` (`web: python quiz_api.py`).
- O servidor detecta automaticamente as variáveis de ambiente `PORT` e `HOST` (`0.0.0.0`).

### 3. Docker / Containers
```bash
# Construir a imagem
docker build -t ifuture-study .

# Executar o container
docker run -d -p 8000:8000 --name ifuture-quiz ifuture-study
```

---

## 🏗️ Arquitetura do Projeto (Spring Pattern)

O backend segue a arquitetura em camadas inspirada no ecossistema Spring:

```
IFuture_Study/
├── api/
│   ├── controllers/      # Camada de controle de rotas (@RestController)
│   │   └── quiz_controller.py
│   ├── exceptions/       # Exceções personalizadas (@ExceptionHandler)
│   │   └── quiz_exceptions.py
│   ├── handlers/         # Handler HTTP principal
│   │   └── quiz_handler.py
│   ├── middleware/       # CORS, headers de cache e ResponseFormatter
│   │   └── http_middleware.py
│   ├── models/           # DTOs (Data Transfer Objects)
│   │   └── dtos.py
│   ├── repositories/     # Acesso e descoberta de questionários (@Repository)
│   │   └── quiz_repository.py
│   ├── services/         # Regras de negócio e correção (@Service)
│   │   └── quiz_service.py
│   ├── utils/            # Parsers, validadores e configurações
│   │   ├── config.py
│   │   ├── markdown_parser.py
│   │   ├── quiz_logic.py
│   │   └── validators.py
│   ├── index.py          # Entrypoint para Vercel Serverless
│   └── main.py           # Ponto de inicialização do servidor HTTP
├── tests/
│   └── test_validators.py # Suíte de testes (unittest)
├── web/
│   ├── app.js            # Lógica client-side (tema, timer, progresso, filtros)
│   ├── index.html        # Estrutura HTML5 acessível e semântica
│   └── styles.css        # Design System moderno (Dark/Light)
├── 1 test                # Questionário 1 (Treino Mindsight)
├── 2 test                # Questionário 2 (Com Pegadinhas)
├── 3 test                # Questionário 3 (Desafios Rápidos)
├── Dockerfile            # Containerização
├── Procfile              # Deploy Render/Heroku/Railway
├── quiz_api.py           # Entry point rápido da aplicação
└── vercel.json           # Configuração de rotas Vercel
```

---

## 📡 Endpoints da API

| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/` | Serve a interface web (`index.html`) |
| `GET` | `/web/*` | Serve os arquivos estáticos (`styles.css`, `app.js`) |
| `GET` | `/api/quizzes` | Retorna a lista de questionários disponíveis |
| `GET` | `/api/quiz?source=1 test` | Retorna as questões do questionário (sem gabarito) |
| `POST` | `/api/quiz/submit` | Envia respostas para correção e retorna score detalhado |
| `POST` | `/api/upload` | Envia novo questionário em Markdown (validação automática) |

---

## 📝 Como Adicionar Novos Questionários

Basta criar um arquivo com nome `X test` ou `nome.quiz.md` na raiz do projeto seguindo a estrutura:

```markdown
# Título do Questionário

## Bloco 1 — Nome da Seção

**1.** Enunciado da primeira questão?
a) Opção A  b) Opção B  c) Opção C  d) Opção D

**2.** Enunciado da segunda questão?
a) Opção A
b) Opção B
c) Opção C
d) Opção D

# Gabarito
1. b) Opção B → Explicação detalhada da resposta.
2. a) Opção A → Explicação detalhada da resposta.
```
