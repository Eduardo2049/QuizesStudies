# IFuture Study

Plataforma de simulados e treino de raciocínio lógico. Faça upload de provas em **PDF**, **DOCX** ou **TXT** e receba quizzes interativos com gabarito automático via IA.

---

## Requisitos

- Python 3.11+
- PostgreSQL 14+

---

## Configuração

```bash
# 1. Instalar dependências
pip install -r requirements.txt

# 2. Criar arquivo de variáveis de ambiente
cp .env.example .env
```

Edite o `.env`:

| Variável | Obrigatória | Descrição |
|---|---|---|
| `DATABASE_URL` | ✅ | `postgresql://user:password@host:5432/dbname` |
| `ADMIN_USERNAME` | Não | Usuário do administrador inicial (padrão: `admin`) |
| `ADMIN_PASSWORD` | Não | Senha do administrador inicial (padrão: `admin_study_2026`) |
| `ALLOWED_ORIGINS` | Não | Origens CORS permitidas (padrão: `*`) |
| `CLOUDFLARE_TUNNEL_TOKEN` | Para Tunnel | Token do Cloudflare Zero Trust para expor via túnel HTTPS |
| `OPENROUTER_API_KEY` | Para IA | Chave do [OpenRouter](https://openrouter.ai) para geração de gabarito |
| `OPENROUTER_MODEL` | Não | Modelo padrão: `openai/gpt-4o-mini` |
| `PORT` | Não | Porta do servidor (padrão: `8000`) |
| `DEBUG` | Não | Logs detalhados (padrão: `false`) |

---

## Executar

### Opção A — Docker Compose (recomendado)

Sobe o PostgreSQL e a aplicação com um único comando:

```bash
docker compose up -d
```

Para subir também o **Cloudflare Tunnel** (expondo com HTTPS e proteção DDoS na Cloudflare):
```bash
docker compose --profile tunnel up -d
```

### Opção B — Servidor local

```bash
python quiz_api.py
```

O servidor inicia em `http://localhost:8000` (ou próxima porta livre) e executa as migrations automaticamente na primeira vez.

---

## Autenticação e Segurança

- **Acesso Público**: Estudantes podem navegar livremente, realizar simulados, selecionar provas e conferir pontuações.
- **Acesso Restrito (Admin)**: O upload de novos simulados e acionamento da IA é restrito a administradores autenticados via Bearer Token.
- **Credenciais Padrão Iniciais**:
  - Usuário: `admin`
  - Senha: `admin_study_2026` (altere no `.env` para produção)

---

## Cloudflare Tunnel (Proxy Reverso Seguro)

Para disponibilizar sua aplicação com domínio próprio, HTTPS automático e proteção contra DDoS sem abrir portas no roteador:
1. Crie um túnel no [Cloudflare Zero Trust Dashboard](https://one.dash.cloudflare.com/) (Networks > Tunnels).
2. Aponte o serviço interno do túnel para `http://app:8000`.
3. Cole o token gerado na variável `CLOUDFLARE_TUNNEL_TOKEN` do seu arquivo `.env`.
4. Inicie o serviço com:
   ```bash
   docker compose --profile tunnel up -d
   ```

---

## Como adicionar quizzes

Clique no botão **"+ Adicionar Quiz"** na interface e envie um arquivo:

- **`.txt`** — texto puro com questões numeradas
- **`.pdf`** — documento PDF (extração automática de texto)
- **`.docx`** — documento Word

Se o arquivo **não contiver gabarito**, ele é gerado automaticamente via `OPENROUTER_API_KEY`. Cada questão pode ter de 2 a N alternativas.

### Formato de questões aceito

```
**1.** Enunciado da questão?
a) Opção A  b) Opção B  c) Opção C  d) Opção D

**2.** Outra questão com alternativas em linhas separadas?
a) Opção A
b) Opção B
c) Opção C

# Gabarito
1. b) Opção B → Explicação da resposta.
2. a) Opção A → Explicação da resposta.
```

---

## Endpoints da API

| Método | Rota | Autenticação | Descrição |
|---|---|---|---|
| `GET` | `/` | Pública | Interface web |
| `GET` | `/api/quizzes` | Pública | Lista quizzes disponíveis |
| `GET` | `/api/quiz?source=<name>` | Pública | Questões de um quiz (sem gabarito) |
| `POST` | `/api/quiz/submit` | Pública | Submete respostas e retorna score |
| `POST` | `/api/auth/login` | Pública | Login (retorna Bearer Token) |
| `POST` | `/api/auth/register` | Pública | Cadastro de estudante |
| `GET` | `/api/auth/me` | Bearer Token | Dados do usuário autenticado |
| `POST` | `/api/auth/logout` | Bearer Token | Encerramento de sessão |
| `POST` | `/api/upload` | **Admin** | Upload de arquivo (multipart/form-data) |

---

## Arquitetura

```
Quizes_Study/
├── api/
│   ├── database/
│   │   ├── connection.py      # Context managers para PostgreSQL
│   │   └── migrations.py      # Schema (executa na inicialização)
│   ├── controllers/
│   │   └── quiz_controller.py # Camada de rotas
│   ├── exceptions/
│   │   └── quiz_exceptions.py # Exceções de domínio
│   ├── handlers/
│   │   └── quiz_handler.py    # Handler HTTP (GET/POST/OPTIONS)
│   ├── middleware/
│   │   └── http_middleware.py # CORS, cache, ResponseFormatter
│   ├── models/
│   │   └── dtos.py            # Data Transfer Objects
│   ├── repositories/
│   │   └── quiz_repository.py # Acesso ao PostgreSQL
│   ├── services/
│   │   ├── ai_service.py      # Geração de gabarito via OpenRouter
│   │   ├── quiz_service.py    # Lógica de negócio
│   │   └── upload_service.py  # Orquestração de upload
│   ├── utils/
│   │   ├── config.py          # Variáveis de ambiente
│   │   ├── file_parser.py     # Extração de texto (TXT/PDF/DOCX) e parse de questões
│   │   ├── quiz_logic.py      # Correção de respostas
│   │   └── validators.py      # Validação de payloads HTTP
│   ├── index.py               # Entrypoint Vercel (serverless)
│   └── main.py                # Inicialização do servidor
├── web/
│   ├── app.js                 # Lógica client-side
│   ├── index.html             # Interface HTML
│   └── styles.css             # Design system
├── .env.example               # Template de variáveis de ambiente
├── docker-compose.yml         # PostgreSQL + app
├── Dockerfile
├── Procfile
├── quiz_api.py                # Entry point
└── requirements.txt
```

---

## Schema do Banco

```sql
-- Quizzes cadastrados
CREATE TABLE quizzes (
    id               SERIAL PRIMARY KEY,
    name             VARCHAR(255) UNIQUE NOT NULL,  -- slug identificador
    label            VARCHAR(255) NOT NULL,          -- nome de exibição
    original_filename VARCHAR(255),
    file_type        VARCHAR(10),                    -- 'txt' | 'pdf' | 'docx'
    has_answer_key   BOOLEAN DEFAULT TRUE,
    ai_generated     BOOLEAN DEFAULT FALSE,
    created_at       TIMESTAMP DEFAULT NOW()
);

-- Questões (options em JSONB suporta 2 a N alternativas)
CREATE TABLE questions (
    id              SERIAL PRIMARY KEY,
    quiz_id         INTEGER REFERENCES quizzes(id) ON DELETE CASCADE,
    question_number INTEGER NOT NULL,
    section         VARCHAR(255) DEFAULT 'Geral',
    context         TEXT DEFAULT '',
    question        TEXT NOT NULL,
    options         JSONB NOT NULL,   -- ["Opção A", "Opção B", ...]
    answer          INTEGER,          -- índice base-0 (0=A, 1=B, ...)
    explanation     TEXT DEFAULT ''
);
```
