# Acely

Site: [acely.com.br](https://acely.com.br) · Repositório: `Eduardo2049/QuizesStudies` (o nome do repositório é anterior à marca).

Plataforma de simulados com IA. Transforme um material em **PDF**, **DOCX** ou **TXT**, ou só um tema, em um simulado com cronômetro, gabarito comentado, estatísticas e **caderno de erros com variações inéditas geradas por IA**.

> *“Da sua apostila ao simulado ativo, com gabarito comentado.”*

Estado em 24/11/2026: em produção em `acely.com.br` (Vercel, região `gru1`, PostgreSQL na Neon em `sa-east-1`). Próximas fases do produto (equipes, atribuições e cobrança): [`docs/PLANO_SAAS.md`](docs/PLANO_SAAS.md).

---

## O que o Acely faz hoje

- **Simulado por tema**: de 3 a 30 questões, três níveis de dificuldade e instruções extras opcionais. Mais de 5 questões saem em partes de 5 geradas em paralelo, com progresso na tela.
- **Simulado a partir de arquivo** (TXT, PDF, DOCX): o parser reconhece questões e gabaritos em vários formatos (pares "1-B", "GABARITO OFICIAL", tabelas, alternativa marcada). Arquivo que já traz gabarito não gasta IA; sem gabarito, a IA resolve e explica.
- **Qualidade do gabarito**: o servidor reprova questão com gabarito fora do intervalo, alternativas repetidas ou idioma trocado; para quem tem conta, um segundo modelo resolve cada questão sem ver o gabarito e descarta as que discordam.
- **Caderno de erros com variações**: a IA cria questões novas sobre o mesmo conceito das que você errou, para não decorar a letra.
- **Temas de exemplo prontos**: os 4 temas clicáveis da tela respondem na hora, sem IA e sem gastar cota.
- **Prova**: cronômetro arrastável, modo foco, atalhos de teclado, paleta de questões, estatísticas por seção e tela acordada durante a prova (Screen Wake Lock).
- **Pedido que sobrevive ao recarregar**: a geração continua no servidor; ao voltar para a página, o simulado aparece sem gastar outra cota.
- **Interface em português e inglês**, com a IA gerando no idioma escolhido; tema escuro (padrão no app) e claro.
- **Acesso sem muro**: a página inicial e os simulados públicos abrem sem cadastro; o modo convidado dá 3 usos de IA por dia.
- **Conta sem senha**: entrar e criar conta com um código de 6 dígitos enviado ao e-mail, ou com o Google.
- **Planos**: cota mensal decidida no servidor (Grátis: 30 gerações e 10 rodadas de variações por mês, até 30 questões e arquivos de 20 MB). Pro e Equipe aparecem como "em breve" em `/produto`.
- **LGPD**: termos, política de privacidade, cópia dos dados e exclusão da conta em "Minha conta".
- **Diagnóstico da IA para o admin**: em "Minha conta", a ordem real dos provedores, avisos de configuração e um teste de cada provedor.

### Comparação

| Critério | Acely | Quizlet | QConcursos / Gran | Anki |
|---|:---:|:---:|:---:|:---:|
| Simulado a partir do seu material | **Sim (PDF, DOCX, TXT)** | Não (manual ou listas públicas) | Não (banco de provas) | Não (card a card) |
| Simulado por tema com IA | **Sim (OpenAI e provedores gratuitos de reserva)** | Limitado (planos pagos) | Não | Não nativo |
| Caderno de erros com questões novas | **Sim** | Não (repete o card) | Não (filtra questões fixas) | Não (repete o card) |
| Explicação de cada resposta | **Sim (na hora)** | Rara | Sim (comentários e fórum) | Só se o usuário escreveu |
| Tela limpa, sem anúncios | **Sim (modo foco + cronômetro)** | Não | Não | Sim, mas crua |
| Uso sem cadastro | **Sim (convidado com 3 usos de IA por dia)** | Parcial | Não | Sim (local) |

---

## Stack

- **Back-end**: Python puro (`http.server.ThreadingHTTPServer`), em camadas `handlers → controllers → services → repositories`. Dependências: `psycopg2-binary`, `requests`, `pdfplumber`, `python-docx`, `python-dotenv`, `certifi`.
- **Banco**: PostgreSQL (Neon em produção; Supabase ou Docker local também servem). Migrations idempotentes rodam na inicialização.
- **Front-end**: HTML, CSS e JavaScript (ES Modules) sem frameworks, servidos pela CDN da Vercel. CSP só com `'self'`: fontes e ícones ficam no próprio site.
- **IA**: OpenAI, Groq, Gemini, Cerebras e OpenRouter em sequência, todos pelo formato de chat da OpenAI.
- **Infra**: Vercel (produção e previews), Docker Compose e Cloudflare Tunnel (opcional), GitHub Actions (testes com PostgreSQL 16, ruff, Semgrep, gitleaks, pip-audit).

---

## Requisitos

- Python 3.11+ (a imagem Docker usa `python:3.15.2-slim`)
- PostgreSQL 14+

---

## Configuração

```bash
# 1. Instalar dependências
pip install -r requirements.txt

# 2. Criar o arquivo de variáveis de ambiente
cp .env.example .env
```

O `.env.example` explica cada variável. As principais:

### Banco, servidor e segurança

| Variável | Obrigatória | Descrição |
|---|---|---|
| `DATABASE_URL` | ✅ | `postgresql://user:password@host:5432/dbname` (na Vercel, a URL com pooler) |
| `ACELY_DATABASE_URL` | Não | Tem prioridade sobre todas: use quando a integração Neon da Vercel trava o nome `DATABASE_URL` |
| `DATABASE_URL_DIRECT` | Não | URL sem pooler para migrations e scripts (vazio = `DATABASE_URL`). Neon, Supabase e TLS: [`docs/BANCO_DE_DADOS.md`](docs/BANCO_DE_DADOS.md) |
| `DB_SSLMODE` / `DB_SSLROOTCERT` | Não | `verify-full` (padrão recomendado) com o certificado do `certifi`; Supabase precisa do `.crt` próprio |
| `POSTGRES_PASSWORD` | ✅ Docker | Senha do PostgreSQL local |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | ✅ senha | Administrador inicial (entra com senha em `/login?senha=1`) |
| `APP_URL` | ✅ produção | URL pública usada nos e-mails e no login com Google (`https://acely.com.br`) |
| `ALLOWED_ORIGINS` | Não | Origens CORS permitidas, separadas por vírgula |
| `COOKIE_SECURE` | Não | Padrão `true`; `false` só no desenvolvimento em HTTP |
| `TRUST_PROXY` | Não | Confiar em cabeçalhos de proxy (padrão `false`; `true` automático na Vercel) |
| `PORT` / `DEBUG` | Não | Porta (padrão `8000`) e logs detalhados (padrão `false`) |
| `CLOUDFLARE_TUNNEL_TOKEN` | Para o túnel | Token do Cloudflare Zero Trust |

### E-mail e acesso por código

| Variável | Obrigatória | Descrição |
|---|---|---|
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` | ✅ produção | Envio dos códigos de acesso e dos avisos da conta. Sem SMTP, entrar por código responde 503 (em `DEBUG`, o código volta na resposta) |
| `AUTH_CODE_SECRET` | Recomendada | Chave do HMAC que guarda os códigos no banco (sem ela, é derivada de `ADMIN_PASSWORD`) |
| `LOGIN_CODE_TTL_MINUTES`, `LOGIN_CODE_MAX_ATTEMPTS`, `LOGIN_CODE_RESEND_SECONDS`, `LOGIN_CODE_MAX_PER_HOUR` | Não | Validade (10 min), palpites (5), espera para reenviar (60 s) e códigos por hora (5) |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Não | Liga "Entrar com Google". Redirect URI: `<APP_URL>/api/auth/google/callback` |

### IA

| Variável | Obrigatória | Descrição |
|---|---|---|
| `AI_PROVIDERS` | Não | Ordem dos provedores (padrão `openai,groq,gemini,cerebras,openrouter`); provedor sem chave fica de fora. Definida, ela manda: um provedor fora da lista nunca é chamado, mesmo com chave |
| `OPENAI_API_KEY` / `OPENAI_MODELS` | Não | [OpenAI](https://platform.openai.com/api-keys), primeira da fila quando tem chave (precisa de créditos). Padrão `gpt-6-luna,gpt-4o-mini`; os nomes antigos `CODEX_API_KEY`/`CODEX_MODELS` ainda valem |
| `GROQ_API_KEY` / `GROQ_MODELS` | Não (recomendado) | [Groq](https://console.groq.com/keys): o gratuito mais rápido; padrão `openai/gpt-oss-120b,openai/gpt-oss-20b` |
| `GEMINI_API_KEY` / `GEMINI_MODELS` | Não | [Google AI Studio](https://aistudio.google.com/apikey); no plano grátis o Google usa o conteúdo enviado |
| `CEREBRAS_API_KEY` / `CEREBRAS_MODELS` | Não | [Cerebras](https://cloud.cerebras.ai) (teste com cartão, contexto curto) |
| `OPENROUTER_API_KEY` | Não | [OpenRouter](https://openrouter.ai), só modelos gratuitos (`:free`). Libere-os em *Settings → Privacy* e deixe *ZDR Endpoints Only* desligado |
| `OPENROUTER_FREE_MODELS`, `OPENROUTER_DISCOVER_FREE_MODELS`, `OPENROUTER_MAX_ATTEMPTS` | Não | Modelos gratuitos preferidos, descoberta automática de outros (padrão `true`) e tentativas por pedido (padrão `4`) |
| `<PROVEDOR>_DAILY_REQUESTS` / `<PROVEDOR>_DAILY_TOKENS` | Não | Orçamento diário por modelo (`OPENAI_`, `GROQ_`, `GEMINI_`, `CEREBRAS_`); o modelo é pulado antes de levar 429 |
| `AI_DAILY_CALL_LIMIT` | Não | Teto global de chamadas ao provedor a cada 24 h, somando todos (padrão `1000`; `0` desliga). Cada simulado usa de 1 a 5 chamadas. Só com o OpenRouter sem créditos, deixe abaixo de 50 |
| `AI_USER_REQUESTS_PER_MINUTE` | Não | Pedidos de IA por minuto por pessoa (padrão `10`; `0` desliga). A vaga volta quando a IA falha ou o resultado vem pronto |
| `AI_CROSS_CHECK` | Não | Conferência do gabarito por um segundo modelo: `account` (padrão, só contas), `all` ou `off` |
| `AI_ATTEMPT_TIMEOUT` | Não | Segundos que um modelo pode ficar sem mandar nada antes de passar ao próximo (padrão `20`) |
| `AI_CACHE_TTL_DAYS` | Não | Dias que um simulado por tema fica em cache no banco (padrão `7`) |
| `AI_TOKEN_QUOTA_PER_HOUR` | Não | Tokens estimados por hora por IP (padrão `50000`) |

### Convidado

| Variável | Obrigatória | Descrição |
|---|---|---|
| `GUEST_AI_LIMIT` | Não | Usos de IA do convidado por janela (padrão `3`; `0` desliga a IA para convidados) |
| `GUEST_AI_WINDOW_HOURS` | Não | Janela da cota em horas (padrão e máximo `24`) |
| `GUEST_AI_IP_LIMIT` | Não | Teto por IP somando os convidados (padrão `10`), contra quem apaga cookies para renovar a cota |

Variáveis para a Vercel (Production e Preview): [`docs/CICD_E_DEPLOY.md`](docs/CICD_E_DEPLOY.md).

---

## Executar

### Opção A — Docker Compose (recomendado)

Sobe o PostgreSQL e a aplicação:

```bash
docker compose up -d
```

Com o **Cloudflare Tunnel** (HTTPS e proteção contra DDoS sem abrir portas):

```bash
docker compose --profile tunnel up -d
```

### Opção B — Servidor local

```bash
python quiz_api.py
```

O servidor sobe em `http://localhost:8000` (ou na próxima porta livre) e roda as migrations na primeira vez. Sem `DATABASE_URL` ele não sobe: não há banco de reserva.

### Páginas

| Endereço | Página |
|---|---|
| `/` (apelido `/inicio`) | Página inicial |
| `/app` | Simulados (links antigos `/?abrir=`, `/?simulado=` e `/?email=` também abrem o app) |
| `/produto` (`/planos` rola até os planos) | Produto, modelos de IA e planos |
| `/login`, `/register` | Entrar e criar conta com código por e-mail (`/login?senha=1` para o admin) |
| `/termos`, `/privacidade` | Termos de uso e política de privacidade |

---

## IA

- **Ordem**: o servidor tenta os provedores com chave na ordem de `AI_PROVIDERS`. Se um bate no limite, recusa a chave, está sem créditos ou fica `AI_ATTEMPT_TIMEOUT` s sem responder, passa ao próximo sem erro para a pessoa.
- **OpenAI**: modelos de raciocínio vão com esforço baixo e sem `temperature`. Modelo com data de desligamento vencida é pulado sem fazer pedido. Organização sem verificação recebe a resposta inteira, em vez de em partes. Sem créditos, a OpenAI fica de fora por 15 min.
- **Menos chamadas**:
  - cache em dois níveis (memória e tabela `ai_cache`);
  - temas de exemplo prontos;
  - pedidos com `request_id`, que não repetem a chamada ao recarregar a página;
  - arquivos com gabarito, que não chamam a IA.
- **Limites**:
  - cota do convidado e do plano, decidida só no servidor;
  - `AI_USER_REQUESTS_PER_MINUTE` por pessoa;
  - `AI_TOKEN_QUOTA_PER_HOUR` por IP;
  - teto global `AI_DAILY_CALL_LIMIT`;
  - orçamento diário por modelo.
- **Logs**: cada tentativa gera uma linha `[ia]` com o motivo de cada falha, sem a chave. A primeira linha de cada instância mostra a ordem dos provedores e os avisos de configuração.
- **Diagnóstico**: entre como admin e abra **Minha conta → Diagnóstico da IA**. Ali aparecem a ordem real, os avisos (chave fora de `AI_PROVIDERS`, modelo vencendo, teto baixo) e o botão *Testar provedores agora*. As rotas são `GET /api/admin/ia` e `POST /api/admin/ia/teste`, só para o admin e sem devolver chaves.

Detalhes: [`docs/ARQUITETURA.md`](docs/ARQUITETURA.md).

---

## Idiomas (português e inglês)

- A interface tem um botão **PT/EN** no topo. A escolha fica no `localStorage` (`quiz_lang`); na primeira visita segue o idioma do navegador.
- O português escrito no HTML e no JS é o texto-fonte. `public/web/modules/i18n.js` troca textos e atributos pelo dicionário `public/web/modules/i18n/en.js` e observa o que o `app.js` gera depois; `public/web/modules/i18n-boot.js` evita mostrar o português por um instante antes da tradução. Elementos com `translate="no"` não são tocados.
- A IA gera simulados, gabaritos e variações no idioma escolhido: `/api/quiz/generate`, `/api/upload` e `/api/quiz/remix-mistakes` aceitam `language` (`pt-BR` ou `en`; padrão `pt-BR`). Os temas de exemplo prontos existem só em português.
- Para um idioma novo: crie `public/web/modules/i18n/<código>.js`, registre em `LANGUAGES` e `DICTIONARIES` (`i18n.js`), repita a regra em `i18n-boot.js` e acrescente o código em `AI_LANGUAGES` (`api/services/ai_service.py`).

---

## Acesso, conta e segurança

- **Visitante**: a página inicial e os simulados (`/app`) abrem sem cadastro. Dá para resolver os simulados públicos, ver o gabarito comentado e enviar arquivos que já tragam gabarito (o simulado fica só no navegador).
- **Convidado**: ao tentar usar a IA, a pessoa escolhe entre criar conta, entrar ou continuar como convidado. O convidado tem **3 usos de IA a cada 24 horas**, contados no servidor por um cookie HttpOnly (`qs_guest`) e com teto por IP. O upload vai até 5 MB.
- **Conta**: entrar e criar conta com um **código de 6 dígitos** enviado ao e-mail (vale 10 min, 5 palpites), ou com o Google. Os simulados feitos como convidado na mesma aba vão para a conta. As telas de senha estão comentadas no código, não apagadas.
- **Administrador**: entra com usuário e senha em `/login?senha=1` (`ADMIN_USERNAME`/`ADMIN_PASSWORD`), não tem cota de IA e vê o diagnóstico da IA em "Minha conta".
  ```bash
  python scripts/reset_admin.py "NovaSenha123*"   # troca a senha do admin
  python scripts/reset_sessions.py                # derruba todas as sessões
  ```
- **LGPD**: em "Minha conta", a pessoa baixa uma cópia dos dados (`GET /api/account/export`) e exclui a conta com um código enviado ao e-mail.
- **Sessão**: só em cookie HttpOnly (`__Host-acely_session`; o antigo `ifuture_session` ainda é lido). O token não vem no JSON do login, a menos que o cliente peça `"return_token": true`. POSTs vindos de outro site são recusados (`Origin` / `Sec-Fetch-Site`).

### Medidas de proteção
1. **Container sem root**: o `Dockerfile` roda como `appuser` (UID 1000), com a imagem fixada por digest.
2. **Rate limit por janela deslizante** nas rotas de login, código por e-mail, upload, geração e leitura, contado no PostgreSQL (vale entre instâncias). IP do cliente: `CF-Connecting-IP` só fora da Vercel → `X-Forwarded-For` confiável → socket.
3. **Cotas de IA no servidor**: convidado, plano mensal, pedidos por minuto, tokens por hora por IP e teto global diário.
4. **Cabeçalhos HTTP**: HSTS com preload, CSP só `'self'`, `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy` e `Permissions-Policy`.
5. **Validação de entrada**: JSON até 1 MB, upload até 20 MB (5 MB para convidado), só `.txt`, `.pdf` e `.docx`.
6. **Segredos**: códigos de acesso guardados só como HMAC; senhas com PBKDF2; chaves dos provedores nunca vão para o navegador nem para os logs.
7. **Varreduras no CI**: Semgrep (SAST), gitleaks (segredos no histórico) e pip-audit (dependências).

```bash
semgrep scan --config auto .
```

---

## Cloudflare Tunnel (opcional)

Para publicar com domínio próprio, HTTPS e proteção contra DDoS sem abrir portas no roteador:
1. Crie um túnel no [Cloudflare Zero Trust](https://one.dash.cloudflare.com/) (Networks > Tunnels).
2. Aponte o serviço interno do túnel para `http://app:8000`.
3. Cole o token em `CLOUDFLARE_TUNNEL_TOKEN` no `.env`.
4. Suba com `docker compose --profile tunnel up -d`.

---

## Como criar simulados

Em `/app`, use **Novo simulado**.

### Gerar por tema
Digite o tema (ex.: *Raciocínio lógico proposicional*, *Python básico*, *Direito constitucional*), escolha a quantidade (3 a 30, ou personalizada) e a dificuldade, e, se quiser, acrescente instruções. Os temas de exemplo abaixo do campo respondem na hora, sem IA.

### Enviar arquivo
- **`.txt`**: texto estruturado ou livre; o parser e a IA reconhecem perguntas e alternativas mesmo sem numeração ou com quebras irregulares.
- **`.pdf`**: extração de texto com `pdfplumber`.
- **`.docx`**: extração com `python-docx`.

Se o arquivo **não tiver gabarito**, a IA resolve e explica cada questão (gasta um uso de IA). Com gabarito, não gasta. Cada questão pode ter de 2 a N alternativas.

#### Formato aceito

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

Todo endpoint em `/api/` responde `{"status": "success", "data": ...}` ou `{"status": "error", "error": ...}`.

| Método | Rota | Acesso | Descrição |
|---|---|---|---|
| `GET` | `/api/quizzes` | Público | Lista os simulados (cache HTTP com ETag / 304) |
| `GET` | `/api/quiz?source=<name>` | Público | Questões de um simulado (sem gabarito) |
| `POST` | `/api/quiz/submit` | Público | Corrige, salva a tentativa e devolve nota e gabarito |
| `POST` | `/api/quiz/generate` | Convidado / Conta | Gera por tema (aceita `language` e `request_id`) |
| `POST` | `/api/upload` | Convidado (5 MB) / Conta (20 MB) | Upload multipart (TXT, PDF, DOCX); aceita `language` e `request_id` |
| `POST` | `/api/quiz/remix-mistakes` | Convidado / Conta | Variações das questões erradas (aceita `language` e `request_id`) |
| `GET` | `/api/quiz/jobs/<request_id>` | Dono do pedido | Andamento de um pedido de IA (`running` com progresso, `done`, `failed`) |
| `GET` | `/api/user/attempts` | Conta / Convidado | Histórico de tentativas e caderno de erros |
| `POST` | `/api/quizzes/import` | Conta | Salva na conta os simulados criados como convidado |
| `POST` | `/api/auth/email-code` e `/api/auth/email-code/verify` | Público | Envia e confere o código de 6 dígitos (entra ou cria a conta) |
| `POST` | `/api/auth/login` | Público | Entrar com senha (admin e contas antigas) |
| `POST` | `/api/auth/register` | Público | Cadastro com senha (mantido na API) |
| `GET` | `/api/auth/me` · `POST` `/api/auth/logout` | Conta | Usuário da sessão e saída |
| `GET` | `/api/auth/verify-email` · `POST` `/api/auth/resend-verification` | Público / Conta | Confirmação do e-mail |
| `POST` | `/api/auth/forgot-password`, `/api/auth/reset-password` · `GET` `/api/auth/verify-reset-token` | Público | Recuperação de senha |
| `GET` | `/api/auth/providers`, `/api/auth/google/start`, `/api/auth/google/callback` | Público | Login com Google (OAuth, `state` em cookie) |
| `POST` | `/api/guest/start`, `/api/guest/end` · `GET` `/api/guest/status` | Público | Sessão de convidado e cota gratuita |
| `GET` | `/api/me/plan` | Conta | Plano, limites e uso do mês (`PLAN_LIMIT_REACHED` ao passar da cota) |
| `GET` | `/api/account/export` | Conta | Cópia dos dados em JSON (LGPD) |
| `POST` | `/api/account/delete-code` e `/api/account/delete` | Conta | Código de confirmação e exclusão da conta |
| `GET` | `/api/admin/ia` · `POST` `/api/admin/ia/teste` | Admin | Diagnóstico e teste dos provedores de IA |

---

## Testes

```bash
# Suíte completa (o CI roda com PostgreSQL 16 e QUIZ_DB_INTEGRATION=1)
ADMIN_PASSWORD=ci-test-password-123 python -m unittest discover tests

# Lint e formatação (no CI não bloqueiam; há avisos antigos)
ruff check .
ruff format --check .

# Capturas de tela antes/depois (com o app rodando)
python tests/visual/capture_baseline.py --label after --lang en
```

São mais de 450 testes. Sem PostgreSQL local, os que precisam de banco são pulados e os demais usam repositórios em memória.

### Carga e consumo de tokens

Sem custo, com a IA simulada (rate limit, cota por IP, concorrência e anti-spoofing):

```bash
python -m unittest tests/test_load_and_token_usage.py
```

Contra o servidor de verdade (**gasta tokens reais**):

```bash
python scripts/load_test_real_api.py --calls 5 --workers 1 --guest --questions 3          # validação rápida
python scripts/load_test_real_api.py --calls 50 --workers 5 --guest --questions 10 --token-limit 200000
python scripts/load_test_real_api.py --calls 30 --workers 10 --burst --guest              # rajada para ver o 429
```

O script acha a porta do servidor sozinho, mostra cada chamada (`OK`, `429 BLOCKED`, `ERR`) e termina com latência (p50, p95, máx.), tokens e custo estimado.

---

## Estrutura

```
QuizesStudies/
├── api/
│   ├── controllers/        # auth_controller.py, quiz_controller.py
│   ├── database/           # connection.py (URL, pooler, TLS), migrations.py
│   ├── exceptions/         # quiz_exceptions.py
│   ├── handlers/           # quiz_handler.py: rotas, rate limits, cotas
│   ├── middleware/         # http_middleware.py: cookies, CORS, CSRF, respostas JSON
│   ├── models/             # dtos.py
│   ├── repositories/       # ai_job, plan, quiz, rate_limit e user
│   ├── services/
│   │   ├── ai_service.py           # provedores de IA, partes, conferência, diagnóstico
│   │   ├── auth_service.py         # código por e-mail, senha do admin, sessões
│   │   ├── email_service.py        # e-mails de código, confirmação e recuperação
│   │   ├── entitlements_service.py # cota mensal por plano
│   │   ├── google_auth_service.py  # login com Google
│   │   ├── guest_service.py        # modo convidado
│   │   ├── import_service.py       # simulados do convidado para a conta
│   │   ├── quiz_service.py
│   │   └── upload_service.py       # TXT/PDF/DOCX e gabarito
│   ├── utils/              # config.py, plans.py, sample_quizzes.py, file_parser.py, quiz_logic.py, validators.py
│   └── index.py            # entrada da Vercel
├── public/web/             # front-end servido pela CDN em /web/...
│   ├── inicio.html/.css    # página inicial (/)
│   ├── index.html, app.js  # simulados (/app)
│   ├── produto.html/.css   # produto e planos
│   ├── login.html, register.html, reset-password.html, termos.html, privacidade.html
│   ├── styles.css          # tokens e temas
│   └── modules/            # i18n, tema, fundo WebGL, atalhos, estatísticas, diagnóstico da IA...
├── docs/                   # arquitetura, banco, CI/CD e deploy, design, plano SaaS
├── scripts/                # reset_admin, reset_sessions, reset_database, teste de carga
├── tests/                  # suíte unittest (+ tests/visual)
├── 404.html, vercel.json, Dockerfile, docker-compose.yml, Procfile
├── quiz_api.py             # servidor local
└── requirements.txt, pyproject.toml, .env.example
```

---

## Banco de dados

O schema completo está em [`api/database/migrations.py`](api/database/migrations.py). Toda migration é idempotente (`IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS`).

| Tabela | Para quê |
|---|---|
| `users`, `sessions` | Contas (estudante e admin) e sessões (token guardado como hash) |
| `email_codes` | Códigos de 6 dígitos de acesso e de exclusão de conta (só o HMAC) |
| `email_verifications`, `password_resets` | Confirmação de e-mail e recuperação de senha |
| `quizzes`, `questions` | Simulados e questões (alternativas em JSONB, de 2 a N) |
| `quiz_attempts` | Tentativas, notas e questões erradas (caderno de erros) |
| `rate_limits` | Contadores de rate limit, cotas de convidado e orçamento de IA |
| `ai_jobs`, `ai_cache` | Pedidos de IA por `request_id` (24 h) e simulados por tema em cache |
| `plans`, `workspaces`, `workspace_members`, `usage_counters` | Planos, workspace pessoal e uso mensal |

Manutenção: `python scripts/reset_database.py --scope content --dry-run` (ou o workflow *Manutenção — Limpar Banco de Dados* no GitHub Actions).

---

## Documentação

| Documento | Conteúdo |
|---|---|
| [`AGENTS.md`](AGENTS.md) | Regras do projeto, mapa de arquivos e proibições (leia antes de mudar algo) |
| [`docs/ARQUITETURA.md`](docs/ARQUITETURA.md) | Camadas, rotas, IA e decisões de segurança |
| [`docs/BANCO_DE_DADOS.md`](docs/BANCO_DE_DADOS.md) | Neon, Supabase, credenciais e TLS |
| [`docs/CICD_E_DEPLOY.md`](docs/CICD_E_DEPLOY.md) | Fluxo `feature/*` → `develop` → `homolog` → `main`, variáveis da Vercel e domínio |
| [`docs/DESIGN_SKILLS.md`](docs/DESIGN_SKILLS.md) | Regras de design da interface |
| [`docs/PLANO_SAAS.md`](docs/PLANO_SAAS.md) | O que falta para o produto: equipes, atribuições, cobrança e IA paga por plano |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Como contribuir |

---

## Licença

Software proprietário. © 2024–2026 Eduardo Felipe Alves de Sousa. Todos os direitos reservados.
Veja [`LICENSE`](LICENSE).
