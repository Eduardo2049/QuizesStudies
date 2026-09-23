# Quizes Study

Plataforma de simulados de alto rendimento e treino de raciocínio lógico. Transforme qualquer material em **PDF**, **DOCX** ou **TXT** (ou gere tópicos do zero) em simulados interativos com gabarito pedagógico e **Caderno de Erros inteligente com mutações por IA**.

> **Proposta de Valor Central:** *“Da sua apostila ao simulado ativo em 5 segundos.”*  
> Menos tempo formatando flashcards, zero distração com fóruns poluídos e foco total na retenção de raciocínio.

---

## Por que o Quiz Study existe? (Diferenciais de Mercado)

Estudantes para concursos, certificações e vestibulares enfrentam três grandes problemas no mercado atual:
1. **Criação Lenta de Questões:** Plataformas como o Anki exigem digitação e formatação manual card por card.
2. **Bancos Estáticos e Rígidos:** Grandes sites (como QConcursos e Gran) dependem exclusivamente de provas antigas de bancas, sem permitir que o aluno pratique sobre suas próprias anotações, resumos ou livros de faculdade.
3. **Decoreba de Gabarito:** Ao refazer uma questão errada, o cérebro tende a lembrar da letra correta (*"na 3 era a C"*), gerando uma falsa ilusão de aprendizado.

O **Quiz Study** resolve isso unindo a extração instantânea de conteúdo à **Mutação de Questões por IA**: a IA identifica onde você errou e pode gerar variações inéditas mantendo o mesmo conceito teórico e nível de dificuldade, forçando a aplicação real do raciocínio.

### 📊 Benchmarking Competitivo

| Critério / Ferramenta | Quiz Study | Quizlet | QConcursos / Gran Cursos | Anki |
|---|:---:|:---:|:---:|:---:|
| **Geração Instantânea por Material Próprio** | **Sim (PDF, DOCX, TXT)** | Não (Manual ou listas públicas) | Não (Apenas banco próprio de bancas) | Não (Manual card a card) |
| **Geração de Simulado por Tema via IA** | **Sim (Google Gemini / OpenRouter)** | Limitado (em planos pagos) | Não | Não nativo |
| **Caderno de Erros com Mutação IA** | **Sim (Gera variações inéditas)** | Não (Apenas repete o card) | Não (Filtra questões estáticas) | Não (Repete o mesmo card) |
| **Explicação Didática Passo a Passo** | **Sim (Imediata via IA)** | Raras (Geralmente apenas definição) | Sim (Fórum / Comentários de profs) | Apenas se o usuário tiver escrito |
| **Experiência Limpa e Sem Fricção** | **Sim (Modo foco + cronômetro)** | Não (Gameficado/Anúncios) | Não (Poluído de propagandas e fórum) | Interface crua e curva alta |
| **Acesso Convidado sem Cadastro** | **Sim (Guest Mode completo)** | Não | Não | Sim (Local) |

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
| `POSTGRES_PASSWORD` | ✅ Docker | Senha forte do PostgreSQL local |
| `ADMIN_USERNAME` | Não | Usuário do administrador inicial (padrão: `admin`) |
| `ADMIN_PASSWORD` | ✅ | Senha forte do administrador inicial |
| `ALLOWED_ORIGINS` | Não | Lista separada por vírgulas de origens CORS permitidas |
| `COOKIE_SECURE` | Não | Padrão `true`; use `false` apenas no desenvolvimento HTTP |
| `CLOUDFLARE_TUNNEL_TOKEN` | Para Tunnel | Token do Cloudflare Zero Trust para expor via túnel HTTPS |
| `GEMINI_API_KEY` | Opção 1 IA (Recomendado) | Chave gratuita direta do [Google AI Studio](https://aistudio.google.com) (1.500 req/dia) |
| `GEMINI_MODEL` | Não | Modelo Google Gemini (padrão: `gemini-2.5-flash`) |
| `OPENROUTER_API_KEY` | Opção 2 IA | Chave do [OpenRouter](https://openrouter.ai) para geração multi-provedor |
| `OPENROUTER_MODEL` | Não | Modelo OpenRouter (padrão: `google/gemini-2.5-flash`) |
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

- **Acesso Convidado / Público**: Qualquer usuário pode navegar livremente, selecionar quizzes públicos da plataforma, responder simulados, conferir pontuações com gabarito explicativo e **gerar simulados inéditos por tema com IA** salvos localmente no navegador.
- **Acesso de Estudantes**: Cadastro via `/register` e autenticação via `/login`.
- **Acesso de Administrador**:
  - Usuário: `admin`
  - Senha: definida pela variável de ambiente `ADMIN_PASSWORD` no seu `.env` (obrigatório antes de iniciar).
  - **Redefinição rápida de senha do admin**:
    ```bash
    python scripts/reset_admin.py "NovaSenha123*"
    ```
  - **Invalidar todas as sessões ativas (forçar reautenticação geral)**:
    ```bash
    python scripts/reset_sessions.py
    ```

---

## Auditoria de Segurança e Hardening (Semgrep SAST)

A base de código é submetida a auditorias estáticas contínuas (SAST) com **Semgrep** utilizando o conjunto oficial de regras para OWASP Top 10, Python, Dockerfile e Web:

```bash
# Executar varredura estática de segurança
semgrep scan --config auto .
```

### Medidas de Hardening Implementadas:
1. **Container Seguro (Non-Root User)**:
   - O `Dockerfile` cria e executa o processo sob um usuário sem privilégios (`appuser`, UID 1000), prevenindo ataques de escape de container e execução indevida como `root` (`dockerfile.security.missing-user.missing-user`).
2. **Prevenção de SSRF e Protocolos Arbitrários**:
   - A integração com a API do OpenRouter em `api/services/ai_service.py` utiliza a biblioteca `requests` com timeout explícito e validação estrita de protocolo HTTP/HTTPS, eliminando riscos de leitura local de arquivos via esquemas como `file://` (`python.lang.security.audit.dynamic-urllib-use-detected`).
3. **Proteção contra Ataques de Rajada e DDoS (Rate Limiting por Janela Deslizante)**:
   - Implementação de `RateLimiter` genérico em [`api/handlers/quiz_handler.py`](file:///c:/Users/eduardo.asousa/Projetos/Pessoal/QuizesStudies/api/handlers/quiz_handler.py) protegendo rotas críticas (`/api/auth/*`, `/api/upload`, `/api/quiz/generate`).
   - Resolução confiável do IP de origem seguindo a cadeia segura: `CF-Connecting-IP` → primeiro IP confiável de `X-Forwarded-For` → endereço de socket (`client_address`).
4. **Cota de Proteção de Tokens de IA por IP (`AI_TOKEN_QUOTA_PER_HOUR`)**:
   - Limite configurável de tokens consumidos por hora por IP (padrão: **200.000 tokens/hora**, ajustável no `.env`), impedindo o esgotamento malicioso de cotas do Gemini / OpenRouter.
5. **Cabeçalhos de Segurança HTTP e HSTS**:
   - Aplicação de `Strict-Transport-Security` (HSTS com `max-age=63072000; includeSubDomains; preload`), `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Content-Security-Policy` e `Referrer-Policy`.
6. **Validação Rigorosa de Payloads**:
   - Limite estrito de tamanho para JSONs (`MAX_JSON_BYTES = 1 MB`), upload com teto de 20 MB e whitelist de formatos (`.txt`, `.pdf`, `.docx`).
7. **Status do Scan SAST**:
   - ✅ **0 vulnerabilidades / 0 achados bloqueantes** em mais de 490 regras aplicadas.

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

Clique no botão **"+ Adicionar Quiz"** na interface. Você pode escolher entre duas formas:

### Opção 1: ✨ Gerar por Tema com IA (Sem Arquivo)
Se você não tiver um documento pronto, digite o **tema ou assunto** desejado (ex: *Raciocínio Lógico Proposicional*, *Python Básico*, *História do Brasil*, *Direito Constitucional*), escolha o número de questões (3, 5 ou 10) e o nível de dificuldade. A IA elaborará todo o simulado com alternativas e explicações detalhadas!

### Opção 2: 📄 Enviar Arquivo (com Parsing Heurístico e IA)
Envie um arquivo nos formatos suportados:
- **`.txt`** — texto estruturado ou em formato livre. O sistema conta com **parser heurístico inteligente e adaptação via IA** capaz de reconhecer perguntas e alternativas mesmo sem números de separação (`1.`, `2.`), marcadores padronizados ou com quebras de linha irregulares (respeitando o limite de peso de 20 MB).
- **`.pdf`** — documento PDF (extração automática de texto via `pdfplumber`)
- **`.docx`** — documento Word (via `python-docx`)

Se o arquivo **não contiver gabarito**, as respostas e justificativas são geradas automaticamente via IA (`OPENROUTER_API_KEY` ou Gemini). Cada questão pode ter de 2 a N alternativas.

#### Formato de questões aceito em arquivos

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
| `GET` | `/` ou `/index.html` | Pública | Interface principal de simulados |
| `GET` | `/login` ou `/login.html` | Pública | Página de autenticação |
| `GET` | `/register` ou `/register.html` | Pública | Página de cadastro de estudante |
| `GET` | `/api/quizzes` | Pública | Lista quizzes disponíveis |
| `GET` | `/api/quiz?source=<name>` | Pública | Questões de um quiz (sem gabarito) |
| `POST` | `/api/quiz/submit` | Pública | Submete respostas, salva tentativa e retorna score/gabarito |
| `GET` | `/api/user/attempts` | Autenticado / Convidado | Histórico de tentativas e caderno de erros |
| `POST` | `/api/quiz/remix-mistakes` | Pública | Cria variações inéditas com IA para questões erradas |
| `POST` | `/api/quiz/generate` | Pública / Convidado / Autenticado | Gera questões por tema via IA |
| `POST` | `/api/auth/login` | Pública | Login (retorna Bearer Token) |
| `POST` | `/api/auth/register` | Pública | Cadastro de estudante |
| `GET` | `/api/auth/me` | Bearer Token | Dados do usuário autenticado |
| `POST` | `/api/auth/logout` | Bearer Token | Encerramento de sessão |
| `POST` | `/api/upload` | Autenticado / Convidado (`?guest=1`) | Upload de arquivo (multipart/form-data) |

---

## Testes de Carga, Segurança e Consumo de Tokens

O projeto conta com suítes completas tanto para **auditoria em ambiente isolado (sem custo de tokens)** quanto para **testes reais de carga contra o servidor ativo**.

### 1. Testes Automatizados de Segurança e Carga (Mock — Sem Custo)
Valida a integridade do `RateLimiter`, cotas de tokens por IP e concorrência massiva:
```bash
python -m unittest tests/test_load_and_token_usage.py
```
- **Cobertura (23 testes passando)**:
  - **Limite exato de 200k tokens**: Validação do corte determinístico em 200.000 tokens com retorno HTTP `429 Too Many Requests`.
  - **Alta concorrência**: 500 chamadas simultâneas com 50 threads (latência p99 < 10ms).
  - **Simulação DDoS**: 50 IPs diferentes concorrentes sem bypass de cota individual.
  - **Resistência Anti-Spoofing**: Proteção contra manipulação de cabeçalhos `X-Forwarded-For`.

### 2. Teste Real de Carga contra a API (Consome Tokens Reais)
Para testar a infraestrutura com geração real de questões via IA (`POST /api/quiz/generate`):
```bash
# Nível 1: Teste rápido de validação (5 chamadas, 1 worker, ~7k tokens)
python tests/test_real_api_load.py --calls 5 --workers 1 --guest --questions 3

# Nível 2: Carga moderada (10 chamadas, 3 workers, ~15k tokens)
python tests/test_real_api_load.py --calls 10 --workers 3 --guest --questions 5

# Nível 3: Teste de estresse com teto de 200k tokens
python tests/test_real_api_load.py --calls 50 --workers 5 --guest --questions 10 --token-limit 200000

# Nível 4: Rajada imediata para testar bloqueio 429 pelo Rate Limiter
python tests/test_real_api_load.py --calls 30 --workers 10 --burst --guest
```
- **Recursos do script**:
  - **Auto-detecção inteligente de porta**: Identifica se o servidor está na porta `8001`, `8002`, etc., evitando conflitos com serviços nativos do Windows (como IIS/HTTP.sys na porta 8000).
  - **Monitoramento em tempo real**: Exibe status individual (`OK`, `429 BLOCKED`, `ERR`), latência e barra de progresso do consumo acumulado de tokens.
  - **Contabilidade precisa e custos**: Tokens só são contabilizados em caso de sucesso real, gerando ao final relatório com latência percentilar (p50, p95, max) e estimativa de custo em USD.

---

## Arquitetura

```
Quizes_Study/
├── api/
│   ├── database/
│   │   ├── connection.py      # Context managers para PostgreSQL
│   │   └── migrations.py      # Schema (executa na inicialização)
│   ├── controllers/
│   │   ├── auth_controller.py # Endpoints de login, registro e sessão
│   │   └── quiz_controller.py # Endpoints de quizzes e upload
│   ├── exceptions/
│   │   └── quiz_exceptions.py # Exceções de domínio
│   ├── handlers/
│   │   └── quiz_handler.py    # Handler HTTP (GET/POST/OPTIONS)
│   ├── middleware/
│   │   └── http_middleware.py # CORS, cache, ResponseFormatter
│   ├── models/
│   │   └── dtos.py            # Data Transfer Objects
│   ├── repositories/
│   │   ├── auth_repository.py # Persistência de usuários e sessões
│   │   └── quiz_repository.py # Persistência de quizzes e questões
│   ├── services/
│   │   ├── ai_service.py      # Geração de gabarito via OpenRouter (requests)
│   │   ├── auth_service.py    # Regras de hash e autenticação
│   │   ├── quiz_service.py    # Lógica de negócio de simulados
│   │   └── upload_service.py  # Orquestração de upload TXT/PDF/DOCX
│   ├── utils/
│   │   ├── config.py          # Variáveis de ambiente
│   │   ├── file_parser.py     # Extração de texto (TXT/PDF/DOCX) e parse de questões
│   │   ├── quiz_logic.py      # Correção e pontuação de respostas
│   │   └── validators.py      # Validação de payloads HTTP
│   ├── index.py               # Entrypoint Vercel (serverless)
│   └── main.py                # Inicialização do servidor
├── web/
│   ├── app.js                 # Lógica client-side (SPA)
│   ├── index.html             # Interface principal
│   ├── login.html             # Tela de login moderna
│   ├── register.html          # Tela de cadastro moderna
│   └── styles.css             # Design system completo
├── .env.example               # Template de variáveis de ambiente
├── docker-compose.yml         # PostgreSQL + app + tunnel
├── Dockerfile                 # Multi-stage com usuário non-root
├── Procfile
├── quiz_api.py                # Entry point local
└── requirements.txt           # Dependências (psycopg2, pdfplumber, requests, etc.)
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

-- Tentativas e Histórico de Desempenho (Caderno de Erros)
CREATE TABLE quiz_attempts (
    id                 SERIAL PRIMARY KEY,
    user_id            INTEGER REFERENCES users(id) ON DELETE CASCADE,
    quiz_id            INTEGER REFERENCES quizzes(id) ON DELETE CASCADE,
    score              INTEGER NOT NULL,
    total              INTEGER NOT NULL,
    percentage         INTEGER NOT NULL,
    wrong_question_ids JSONB DEFAULT '[]'::jsonb,
    created_at         TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_quiz_attempts_user ON quiz_attempts(user_id);
CREATE INDEX idx_quiz_attempts_quiz ON quiz_attempts(quiz_id);
```
