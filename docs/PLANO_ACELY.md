# PLANO_ACELY.md — Plano de continuação (marca Acely e IA mais rápida e confiável)

Documento de passagem para o agente de IA do editor (VS Code) e para quem continuar o trabalho.
Escrito em 29/10/2026. Antes de qualquer tarefa, leia o `AGENTS.md` (regras e mapa de arquivos)
e siga a ordem das fases abaixo. Cada fase vira **uma branch `feature/*` e um PR para a `develop`**,
pelo fluxo `feature/*` → `develop` → `homolog` → `main` descrito em `docs/CICD_E_DEPLOY.md`.

---

## 0. Estado das branches (atualizado em 23/11/2026)

Em `23/11/2026`, todos os PRs anteriores foram unificados e promovidos: `develop` (`cb33d74`), `homolog` (`2d84dd4`) e `main` (`822f9c8`) estão alinhados e sem branches antigas abertas no remoto.

**Já integradas em `develop` / `main`:**
- Marca Acely + domínio (`feature/rebrand-acely`) e credenciais de banco (`feature/banco-credenciais`).
- **Fase 1** (`feature/ia-tarefas-persistentes`) e **Fase 2** (`feature/ia-multiprovedor`) + provedor OpenAI/Codex e limite por minuto por usuário (`feature/ia-provedor-codex`, PRs #92/#95).
- **Fase S1** (`feature/saas-planos-limites`) e **Fase S6** (`feature/inicio-na-raiz`, PR #85).
- **Missão 1** (`feature/quiz-visual-dashboard`) e **Estúdio `/app` + modais responsivos + tema claro na home `/`** (`feature/app-design-pro`, PR #97).

| Branch | Conteúdo | O que fazer |
|---|---|---|
| `feature/modal-geracao-estudio` | **Seção 6.3 (em andamento):** redesign compacto do modal *Novo simulado* (`#uploadModal` — Enviar arquivo e Gerar por tema) alinhado ao layout estúdio, removendo padrões de template IA e excesso de blocos | Implementar, validar testes de contrato/i18n e abrir PR para `develop`. |
| *(próxima — IA)* `feature/ia-geracao-em-partes` | **Fase 3** (seção 3): geração paralela em lotes de 5 questões com progresso em tempo real | Abrir a partir de `develop` após o PR atual. |
| *(próxima — IA)* `feature/ia-qualidade` | **Fase 4** (seção 3): saída estruturada (`json_schema`), validação no servidor e conferência por segundo modelo | Após Fase 3. |
| *(próxima — Infra)* `chore/dockerfile-python-3.15` | **Seção 7.4:** retorno do `Dockerfile` de `python:3.16.0a1-slim` para série estável `python:3.15-slim` | Tarefa independente a partir de `develop`. |

Para criar a próxima branch: `git checkout develop && git pull && git checkout -b feature/<nome>`.

---

## 1. Marca Acely (acely.com.br)

### 1.1 Já feito na `feature/rebrand-acely`

- Nome "Quiz Study" / "Quizes Study" / "IFuture Study" trocado por **Acely** em telas, títulos,
  e-mails, termos, privacidade, 404, tradução em inglês (`public/web/modules/i18n/en.js`), documentação,
  `pyproject.toml` e `docker-compose.yml` (nomes de contêiner).
- **Logo nova** (`public/web/icons/favicon.svg`): um "A" cuja perna direita vira o sinal de acerto, nas
  cores atuais (fundo `#0d3f3d`, traço `#f4f0e8`, acerto `#ff7a5c`). Gerados a partir do SVG:
  `favicon-16x16.png`, `favicon-32x32.png`, `favicon-192.png`, `favicon.png` (512),
  `apple-touch-icon.png` (180, fundo cheio) e `favicon.ico` (16/32/48).
- **Imagem de compartilhamento** `public/web/icons/og-image.png` (1200×630) e, na home: `og:url`,
  `og:image` absoluto, `canonical`, `twitter:card = summary_large_image`, `theme-color`.
- OpenRouter recebe `HTTP-Referer: https://acely.com.br` e `X-Title: Acely`.
- Remetente padrão `noreply@acely.com.br`; seed do admin com `admin@acely.com.br`;
  exportação de dados baixa `acely-meus-dados.json`.
- `?v=` dos ícones, `i18n.js`, `en.js`, `app.js`, `auth_page.js` e `reset_password_page.js` subidos.

### 1.1.1 Integração com o domínio (também na `feature/rebrand-acely`, 29/10/2026)

- `vercel.json`: `www.acely.com.br` → `https://acely.com.br` (301) e rewrites de `/robots.txt`,
  `/sitemap.xml` e `/site.webmanifest` (arquivos em `public/web/`); o servidor local serve os mesmos
  caminhos (`quiz_handler.py`, tabela `STATIC_CONTENT_TYPES`).
- `public/web/site.webmanifest` (nome Acely, ícones 192/512/SVG, cores do tema) ligado em todas as páginas.
- `canonical`, `og:*` e `theme-color` em login, cadastro, termos e privacidade; `noindex` na
  recuperação de senha (o token vai na URL) e na 404; dados estruturados (`WebSite` + `Organization`
  com a logo) na home.
- E-mail de recuperação: remetente aparece como "Acely" mesmo com `SMTP_FROM` só com o Gmail, logo
  PNG no cabeçalho e link para o domínio no rodapé.
- Testes em `tests/test_dominio_acely.py`.

**Mantidos de propósito (não trocar sem migração):**
- Cookie de sessão `ifuture_session`: trocar o nome desconecta todo mundo. Se quiser trocar, ler os
  dois nomes por 7 dias (o tempo de vida da sessão) e só gravar o novo.
- Chaves `quiz_*` do `localStorage`/`sessionStorage` (idioma, convidado): trocar apaga a escolha
  de idioma e os simulados do convidado.
- Banco `quiz_study` no `docker-compose.yml`: trocar aponta o contêiner para um banco vazio.
- Nome do repositório `Eduardo2049/QuizesStudies` (renomear no GitHub é opcional; o GitHub
  redireciona o endereço antigo).

### 1.2 Passos manuais (fora do código, feitos pelo dono do projeto)

1. **Vercel → Settings → Domains:** adicionar `acely.com.br` e `www.acely.com.br`, com o `www`
   redirecionando para o domínio sem `www` (evita o bloqueio de POST de outro site entre os dois).
   O `vercel.json` já faz esse mesmo redirecionamento; **não** configure o sentido contrário
   (sem `www` → `www`), ou os dois formam um laço.
2. **Registro.br → DNS:** criar os registros que a Vercel pedir (A no domínio raiz e CNAME no `www`).
3. **Vercel → Environment Variables (Production):** `APP_URL=https://acely.com.br`.
   Em Preview, manter a URL da Vercel do ambiente.
4. **Google Cloud → OAuth:** em "Authorized redirect URIs" adicionar
   `https://acely.com.br/api/auth/google/callback`; em "Authorized JavaScript origins",
   `https://acely.com.br`. Na tela de consentimento, nome **Acely**, logo `favicon.png` (512) e
   links `https://acely.com.br/privacidade` e `https://acely.com.br/termos`.
5. **E-mail:** para enviar como `noreply@acely.com.br` é preciso um provedor de e-mail no domínio
   (com SPF e DKIM no DNS); até lá, manter `SMTP_FROM` com o Gmail atual. Opcional: criar
   `contato@acely.com.br` e trocar o e-mail de contato em `public/web/termos.html` e `public/web/privacidade.html`.
6. **Google Search Console:** verificar `acely.com.br` (registro TXT no DNS) e enviar o sitemap
   `https://acely.com.br/sitemap.xml`.
7. Conferir o compartilhamento do link (WhatsApp, LinkedIn) para ver a `og-image.png`.

---

## 2. Problema relatado: geração lenta e perdida ao recarregar

Teste manual no celular e no desktop: a geração por tema demorou demais; ao recarregar a página,
foi preciso fazer a mesma consulta de novo.

**Causas encontradas no código (`api/services/ai_service.py`, `public/web/app.js`):**

1. Os modelos padrão são os Nemotron `:free` do OpenRouter, que ficam em fila compartilhada.
   `_call_openrouter` tenta até `OPENROUTER_MAX_ATTEMPTS` (4) modelos **em sequência** dentro de um
   tempo total de 60–75 s; um modelo travado consome quase todo o tempo antes de passar ao próximo.
2. O simulado inteiro sai em **uma** resposta (até ~3.200 tokens de saída para 10 questões); nada
   aparece até o JSON completo chegar e ser validado.
3. `doGenerateTopic()` em `public/web/app.js` faz um único `fetch` e só guarda o resultado depois da
   resposta. Recarregar abandona o pedido; o convidado perde o simulado e a cota pode ter sido usada.
4. O cache de temas (`_quiz_generation_cache`) fica **na memória** do processo. Na Vercel cada
   instância tem a sua, então quase nunca é reaproveitado.

Observação: não é limite da Vercel (Hobby com Fluid compute permite até 300 s por função).

---

## 3. Fases de implementação

### Fase 1 — Pedido persistente, cache no banco e tempo por tentativa ✅
Branch: `feature/ia-tarefas-persistentes` (concluída em 06/11/2026, aguardando PR)

**Como ficou (diferenças em relação às tarefas abaixo)**
- O "tempo por tentativa" virou tempo **sem resposta**: o pedido ao OpenRouter vai com
  `stream: true`, e um modelo que fica `AI_ATTEMPT_TIMEOUT` s sem mandar nada (os comentários
  `: OPENROUTER PROCESSING` da fila não contam) é abandonado. Um tempo fixo de 20 s para a
  resposta inteira cortaria modelos lentos que estão escrevendo 10 questões.
- A tabela `ai_jobs` guarda também `error_code` e `error_status`; job `running` parado há mais de
  6 min aparece como `failed` e pode ser refeito com o mesmo id. Jobs ficam 24 h.
- O que vem do `ai_cache` devolve o uso ao convidado (a IA não foi chamada).
- `request_id` de outro dono ou com outros dados: 409. Sem `request_id`, tudo como antes.
- No navegador, upload retoma só consultando o andamento (o arquivo não é guardado); variações
  (remix) mandam `request_id`, mas não são retomadas depois de recarregar.
- Não existe SQLite de fallback no código: sem banco, os jobs e o cache ficam na memória.


**Tarefas**
1. Migration idempotente (`api/database/migrations.py`) com duas tabelas:
   - `ai_jobs`: `id` (uuid, vem do cliente), `owner_kind` (`user`/`guest`), `owner_id`, `kind`
     (`generate`/`upload`/`remix`), `params_hash`, `status` (`running`/`done`/`failed`),
     `result` (jsonb), `error` (text), `created_at`, `updated_at`. Índice em `(owner_kind, owner_id, created_at)`.
   - `ai_cache`: `key` (sha256 de tema + quantidade + dificuldade + contexto + idioma), `result`
     (jsonb), `created_at`. Validade de 7 dias (limpeza oportunista na leitura).
   - SQLite de fallback precisa das mesmas tabelas.
2. `POST /api/quiz/generate` (e depois upload/remix) aceita `request_id` (uuid). Se já existe um
   job desse dono com esse id: `done` → devolve o resultado sem chamar a IA nem cobrar cota;
   `running` → `202 {"status":"running"}`. Se não existe: cria `running`, reserva a cota **uma vez**,
   gera, grava `done` + resultado (ou `failed` e devolve a cota).
3. Nova rota `GET /api/quiz/jobs/<id>` (só o dono) com `status`, `result` ou `error`.
4. Trocar o cache em memória por `ai_cache` (pode manter a memória como primeiro nível).
5. Em `_call_openrouter`: tempo máximo **por tentativa** (nova variável `AI_ATTEMPT_TIMEOUT`,
   padrão 20 s) além do tempo total; registrar no log a latência de cada modelo.
6. `public/web/app.js`: gerar `crypto.randomUUID()` antes do `fetch`, salvar
   `{id, payload, startedAt}` em `sessionStorage` (`quiz_pending_job`); ao carregar a página, se houver
   pendente com menos de 10 min, mostrar "Seu simulado ainda está sendo gerado" e consultar
   `/api/quiz/jobs/<id>` a cada 3 s até `done`/`failed`. Limpar a chave no fim. Textos novos com
   tradução em `en.js`.

**Pronto quando**
- Recarregar a página durante a geração não perde o simulado nem gasta outra cota (teste automatizado).
- Repetir o mesmo tema/quantidade/dificuldade/idioma responde do `ai_cache` sem chamar a IA.
- Um modelo que não responde é abandonado em ~20 s.

### Fase 2 — Vários provedores gratuitos em sequência ✅
Branch: `feature/ia-multiprovedor` (concluída em 06/11/2026, aguardando PR; depende da Fase 1)

**Como ficou (diferenças em relação às tarefas abaixo)**
- `_call_openrouter` continua existindo (descoberta de modelos `:free`); `_call_ai` chama ele
  quando chega a vez do OpenRouter e usa `_call_compatible` para Groq, Gemini e Cerebras.
- Padrão: `AI_PROVIDERS=groq,gemini,cerebras,openrouter`; Groq `openai/gpt-oss-120b,openai/gpt-oss-20b`,
  Gemini `gemini-3.5-flash-lite,gemini-flash-lite-latest`, Cerebras `gpt-oss-120b` (conferidos em
  nov/2026). `GEMINI_MODEL` (nome antigo) ainda é aceito.
- O orçamento é **por modelo** (o Groq conta os limites por modelo): `GROQ_DAILY_TOKENS=190000`,
  `GROQ_DAILY_REQUESTS=950`, `GEMINI_DAILY_REQUESTS=450`, `CEREBRAS_DAILY_TOKENS=950000`.
- O Groq não recebe `response_format` (não aceita junto com streaming); a Fase 4 pode usar
  `json_schema` sem streaming onde valer a pena.
- Com um provedor só, nada é pausado (não há para onde ir), como era antes.
- Não testado contra as APIs reais (sem chaves no ambiente de desenvolvimento): conferir os
  logs `[ia] groq ...` depois de cadastrar as chaves em Preview.


**Ideia:** Groq, Google Gemini (AI Studio), Cerebras e OpenRouter aceitam o formato de chat da
OpenAI. `_call_openrouter` vira `_call_ai`, que percorre uma lista de provedores; quando um bate no
limite (429) ou falha, passa ao próximo.

**Configuração (`api/utils/config.py` + `.env.example`)**
```
AI_PROVIDERS=groq,gemini,openrouter        # ordem de tentativa
GROQ_API_KEY=
GROQ_MODELS=openai/gpt-oss-120b,openai/gpt-oss-20b   # confirmar ids em console.groq.com
GEMINI_API_KEY=
GEMINI_MODELS=<flash-lite atual>,<flash atual>        # confirmar ids no AI Studio
CEREBRAS_API_KEY=                          # opcional (teste de 30 dias, exige cartão)
OPENROUTER_API_KEY=                        # já existe
```
Endereços (formato OpenAI):
- Groq: `https://api.groq.com/openai/v1`
- Gemini: `https://generativelanguage.googleapis.com/v1beta/openai/`
- Cerebras: `https://api.cerebras.ai/v1`
- OpenRouter: `https://openrouter.ai/api/v1` (atual)

**Tarefas**
1. Estrutura `Provider(name, base_url, api_key, models, headers, supports_json_schema)`; provedor sem
   chave fica de fora.
2. Generalizar o que hoje é específico do OpenRouter: pausa de modelo que falhou, limite diário
   (429 "per day") pausando **só aquele provedor** até a virada do dia, mensagens amigáveis.
3. Controle de orçamento por provedor no `rate_limit_repository` (pedidos/dia e tokens/dia), para
   pular um provedor antes de levar 429. O Groq limita por **tokens/dia (200 mil por modelo)** e
   8 mil tokens/minuto: um simulado de 10 questões gasta ~5 mil tokens.
4. Reativar o Gemini usando o bloco já comentado em `config.py` e `ai_service.py`, agora pelo
   endereço compatível com OpenAI.
5. Atualizar `public/web/privacidade.html` (lista de provedores que recebem o texto; o plano gratuito do
   Gemini **usa o conteúdo para melhorar os produtos do Google**), `README.md`, `AGENTS.md`,
   `docs/ARQUITETURA.md` e `docs/CICD_E_DEPLOY.md`.
6. Testes no estilo de `tests/test_openrouter_free.py`, com respostas simuladas por provedor.

**Pronto quando**
- Sem chave do Groq/Gemini, o comportamento é igual ao de hoje.
- Com o Groq na frente, um simulado de 10 questões sai em poucos segundos.
- 429 diário de um provedor passa para o próximo sem erro para a pessoa.

**Ganho rápido sem código:** comprar US$ 10 de crédito no OpenRouter uma única vez sobe o limite
dos modelos gratuitos de 50 para 1.000 pedidos/dia (os créditos não são gastos com modelos `:free`).

### Fase 3 — Geração em partes com progresso ✅
Branch: `feature/ia-geracao-em-partes` (concluída em 23/11/2026)

1. Para mais de 5 questões, divide em partes de 5 (`TOPIC_CHUNK_SIZE = 5`) executadas em paralelo
   (`ThreadPoolExecutor`, até `TOPIC_CHUNK_MAX_WORKERS = 3` simultâneas), com índice da parte no
   prompt, remoção de enunciados repetidos no servidor (`_deduplicate_questions`) e resiliência a
   falha parcial de uma parte.
2. Grava o andamento em `ai_jobs.progress` (`{"done": 2, "total": 4}`, coluna idempotente em
   `migrations.py`), devolvido em `GET /api/quiz/jobs/<id>` e exibido no navegador como
   `"Gerando simulado: 2 de 4 partes…"` (com tradução em `en.js`).
3. Testes automatizados em `tests/test_ia_geracao_em_partes.py` (20 questões em 4 partes, limite
   de 3 workers, deduplicação, falha parcial/total e progresso em `AIJobRepository`).

### Fase 4 — Qualidade: menos respostas erradas ou fora do tema ✅
Branch: `feature/ia-qualidade` (concluída em 23/11/2026)

1. **Validação rigorosa no servidor (`validate_question`):** reprova questões com gabarito fora do
   intervalo (`answer_out_of_range`), alternativas repetidas (`duplicate_options`), contagem
   inválida ou idioma trocado (`wrong_language`, `pt-BR` vs `en`).
2. **Conferência por segundo modelo (`cross_check_questions`):** controlada por `AI_CROSS_CHECK`
   (`account` padrão, `all` ou `off`), resolve cada questão sem ver o gabarito em temperatura `0.0`,
   priorizando um provedor diferente via `_call_ai(..., prefer_different_from=...)`. Descarta
   questões em desacordo, marca `verified: True` nas aprovadas e registra `verified_count` no retorno.
3. **Basear no material:** `parse_and_structure_questions_with_ai` exige que questões e explicações
   citem o material enviado e passa pela mesma validação e deduplicação.
4. **Testes:** `tests/test_ia_qualidade.py` cobrindo gabarito fora do intervalo, alternativas
   repetidas, idioma errado, discordância na conferência, troca de provedor e política `AI_CROSS_CHECK`.

### Fase 5 — Menos chamadas por simulado ✅
Branch: `feature/ia-banco-de-questoes` (concluída em 23/11/2026)

1. **Temas de exemplo prontos (`api/utils/sample_quizzes.py`):** os 4 temas clicáveis de
   `.topic-chip` (*Juros simples e compostos*, *Uso da crase na língua portuguesa*, *Lógica
   proposicional e tabela-verdade* e *Direito constitucional: direitos e garantias fundamentais*)
   possuem simulados prontos e validados. Gerar com os parâmetros padrão responde instantaneamente
   sem chamar a IA nem descontar cota (`cached=True`, `sample_preset=True`).
2. **Banco reaproveitável:** `ai_cache` cobre repetições exatas entre instâncias e os presets
   cobrem o primeiro acesso instantâneo mesmo sem chave de IA configurada.
3. **Caminho sem IA mais visível:** quando a cota do modo convidado acaba, o aviso destaca que
   ainda é possível enviar um arquivo que já tem gabarito sem gastar usos de IA (com tradução em
   `en.js`, `app.js?v=29`).
4. **Testes:** `tests/test_ia_banco_de_questoes.py` valida todas as questões prontas com
   `validate_question`, 0 chamadas a `_call_ai` nos presets e chamada normal quando o pedido varia.

---

## 4. Provedores gratuitos (levantamento de outubro de 2026)

Os limites mudam com frequência. Conferir no painel de cada provedor antes de configurar.

| Provedor | Limite grátis | Treina com os dados | Observação |
|---|---|---|---|
| Groq | 1.000 pedidos/dia por modelo, 200 mil tokens/dia, 8 mil tokens/min, 30/min | Não | gpt-oss-120b, gpt-oss-20b, Qwen3.8 27B. Muito rápido |
| Google Gemini (AI Studio) | Sem número oficial; relatos de ~500/dia no Flash-Lite e ~20/dia no Flash | Sim | Sem cartão. Avisar na política de privacidade |
| OpenRouter | 50/dia e 20/min nos `:free`; 1.000/dia após US$ 10 de crédito | Depende do modelo | Atual. Lento nos gratuitos |
| Cerebras | 1 milhão de tokens/dia, 5/min | Não guarda | Só teste: US$ 5, exige cartão, expira em 30 dias |
| Cloudflare Workers AI | 10 mil neurons/dia | Não informado | Modelos melhores só no plano pago |
| NVIDIA NIM | 40/min | Sim | Termos: só teste, não produção |
| Mistral | Cota mensal sem número publicado | Sim (pode desligar) | API só para empresas desde ago/2026 |
| GitHub Models, Hugging Face, Ollama Cloud | — | — | Sem cota grátis hoje |

Capacidade estimada sem pagar nada, somando Groq (~120 simulados de 10 questões), Gemini Flash-Lite
(~500) e OpenRouter (50): **~670 gerações por dia**. Com os US$ 10 no OpenRouter, ~1.600.

Fontes: [OpenRouter — Free LLM APIs compared](https://openrouter.ai/blog/tutorials/free-llm-apis-compared/),
[AgentDeals — Free LLM APIs](https://agentdeals.dev/free-llm-apis),
[AgentDeals — Gemini API](https://agentdeals.dev/gemini-api-pricing-changes),
[BenchLM — Groq](https://benchlm.ai/md/free-tier/groq.md),
[BenchLM — Cerebras](https://benchlm.ai/md/free-tier/cerebras.md),
[Vercel — Functions limits](https://vercel.com/docs/functions/limitations).

---

## 5. Regras para o agente ao executar este plano

- Seguir o `AGENTS.md`: sem frameworks novos, `requests` para HTTP, migrations idempotentes,
  CSP `'self'`, Vanilla JS/CSS, textos novos com tradução em `en.js`, `?v=` subido a cada mudança visual.
- Nunca mover a decisão da cota do convidado para o navegador; o servidor decide.
- Nunca commitar chaves; variáveis novas só no `.env.example`.
- Rodar `python -m unittest discover tests` (com `ADMIN_PASSWORD` definido, como no CI) antes de
  cada PR e, em mudança de tela, `python tests/visual/capture_baseline.py --label after` (e `--lang en`).
- Uma fase por branch e por PR; no PR, citar a fase deste documento e marcar o que ficou pronto.
- Ao terminar uma fase, atualizar a tabela da seção 0 e marcar a fase como concluída aqui.

---

## 6. Missão 1 — Redesign visual de `/app` alinhado a `/` ✅

Implementação e revisão concluídas em `18/11/2026` para a branch `feature/quiz-visual-dashboard`
(criada a partir de `develop` em `e8853de`). Toda a documentação de pesquisa, design, arquitetura,
consolidação e baseline está registrada em `docs/missoes/m1/` (`features.md`, `design.md`,
`arquitetura.md`, `plano-consolidado.md` e `qa-baseline.md`), e a Fase 4 recebeu parecer final
**`APPROVE`** na revisão C.

### 6.1 Resumo do que foi implementado (5 decisões R2 + item #9)

1. **Tema escuro padrão e claro opcional (R2.1):** `/app` (`public/web/index.html`) passa a usar
   `data-default-theme="dark"` e `<meta name="theme-color" content="#000000">`, com `theme-boot.js`
   (zero FOUC) e `theme.js` (`THEMES = ['dark', 'light', 'system']`) mantendo `quiz_theme_preference`
   no `localStorage` e o tema claro completo no seletor. Superfícies escuras unificadas com `/`:
   `#000000` (fundo), `#181818` e `#1F1F1F` (superfícies), `#272727` e `#313131` (bordas).
2. **Fundo WebGL suspenso em prova ativa (R2.2):** `public/web/modules/backdrop.js` exporta
   `setBackdropSuspended(boolean)` e desaloca explicitamente recursos GL no `destroy()`. Em
   `public/web/app.js`, a máquina de estados `examState` (`'idle' | 'active' | 'results'`) suspende
   o loop `requestAnimationFrame` (`0%` de GPU/CPU), oculta `<canvas class="backdrop">` e
   `#backdropMotionToggle` durante a prova e nos resultados — mantendo `#000000` chapado sem vazar
   contexto WebGL — e retoma no repouso (`#reset`, `#btnRedoQuiz`, troca de simulado ou fechamento
   de `#resultModal` quando o timer não estiver mais rodando).
3. **Acento coral `#FF7A5C` e contraste WCAG AA/AAA (R2.3):** no tema escuro de `/app`, `--coral`
   e o alias `--teal` passam para `#FF7A5C` (removendo azul/roxo genéricos), com
   `--btn-primary-text: #000000` (`8,19:1` AAA), `--accent-text: #FF8F75` (`7,41:1` sobre `#1F1F1F`),
   `--line-interactive: #525252` (WCAG 1.4.11) e botões secundários em contorno neutro (1 CTA
   principal cheio por tela). O tema claro opcional mantém contraste AA (`--coral: #c9462a` com
   `#ffffff`, `--teal: #176b67`).
4. **Navegação em 2 camadas (R2.4):**
   - **Camada 1 (`.app-nav-wrap` / `.app-nav`):** barra global flutuante e translúcida
     (`backdrop-filter: blur(16px)` com fallback sólido `@supports not`) reunindo marca (`/`),
     links (`Início`, `Planos` `#plansLink`, `Por que o Acely?` `#btnOpenAboutModal`), utilitários
     (`#langToggle`, `#themeToggle`, `#backdropMotionToggle`) e `#authControls`. No desktop
     (`>= 769px`), `#appNavDrawer` usa `display: contents` (com quebra limpa em `769px–920px`); no
     celular (`<= 768px`), expande como drawer acessível via `#appMenuToggle` sem duplicar IDs.
   - **Camada 2 (`.exam-panel` em `.hero`):** painel do simulado com seletor de questionário, ações,
     progresso e paleta `#questionPalette`. `#timer` permanece direto em `.timer-wrap` com
     `position: fixed` e `z-index: var(--z-timer)` na regra base (e `top`/`right` em
     `#timer:not(.timer--custom)`), preservando compatibilidade com `.timer--custom` de
     `timer-drag.js`.
5. **Movimento nativo, `scaleX`, acessibilidade e item #9 (`Screen Wake Lock`):**
   - Sem `smooth-scroll.js` em `/app`; rolagem nativa com `scroll-padding-top` / `scroll-margin-top`
     (WCAG 2.2 SC 2.4.11) e `getScrollBehavior()` respeitando `prefers-reduced-motion`.
   - `#progressBar` e `.section-progress-fill` convertidos de `width` para `transform: scaleX(...)`
     com `--ease-out` (`>= 200ms`); remoção de `border-left` isolados e de `text-transform: uppercase`
     em rótulos; `inert` em `<main>`/`<footer>` nos 8 modais e nos cards ocultos do Modo Foco.
   - **Item #9 (`navigator.wakeLock`):** integrado ao estado `examState === 'active'` em `app.js`
     com `try/catch`, reaquisição em `visibilitychange` e liberação garantida ao encerrar/sair da prova.
6. **i18n, `translate="no"`, sincronia `?v=` e preservação de `/` e `/produto`:**
   - `translate="no"` aplicado aos conteúdos dinâmicos de questões, alternativas e nomes de simulados;
     21 chaves novas/normalizadas adicionadas em `public/web/modules/i18n/en.js` (e títulos
     normalizados em `stats.js`).
   - Versões `?v=` sincronizadas nos 9 HTMLs e módulos JS (`styles.css?v=31`, `app.js?v=27`,
     `theme-boot.js?v=2`, `theme.js?v=10`, `backdrop.js?v=9`, `i18n.js?v=11` / `en.js?v=11`,
     `stats.js?v=8`), mantendo `inicio.css`, `produto.css`, `smooth-scroll.js`, `mural.js`,
     `timer-drag.js`, `api/`, `Dockerfile` e `vercel.json` intactos.

### 6.2 Testes, baseline e pendências explícitas fora do sandbox

- **Contratos e lint no repositório (aprovados pós-implementação):**
  - `tests/test_app_dashboard_contract.py` criado com **13** novos testes cobrindo tema padrão
    escuro, 2 camadas sem IDs duplicados, `scaleX`, ciclo WebGL, `wakeLock`, `inert`,
    `translate="no"`, retorno de `closeResultModal()` para `'idle'`, sincronia `?v=`, 21 chaves de
    `en.js`, `#timer` compatível com `.timer--custom` e alvos `>= 44px` no mobile (incluindo
    `.catalog-tab-btn`, corrigindo os 2 avisos EN vistos no `before`).
  - `test_ui_contract.py` + `test_modulepreload.py` + `test_app_dashboard_contract.py`: **19/19 OK**.
  - `ruff check` e `ruff format --check` em `tests/test_app_dashboard_contract.py` e
    `tests/visual/capture_baseline.py`: **0 violações** (`ruff check .` caiu de `237` para `232`).
  - `tests/visual/capture_baseline.py` adaptado para testar `light` e `dark` sobre o novo padrão
    escuro de `/app` (gravando `quiz_theme_preference` e limpando cookies/`quiz_guest_mode` antes de `/app`).
- **Pendências operacionais antes de abrir o PR (bloqueadas no sandbox por `WinError 10013`):**
  1. Criar a branch `feature/quiz-visual-dashboard` a partir de `develop` (`e8853de`) e gravar os
     commits organizados (sem `.claude/settings.local.json`, `design-baseline/` ou `.env`).
  2. Executar fora do sandbox (com servidor em `http://127.0.0.1:8010`) `capture_baseline.py --label after`
     (PT e `--lang en`, gerando 180 PNGs com 0 falhas `LAYOUT` e 0 avisos `< 44px`) e
     `python -m unittest discover tests` com `$env:E2E_PORT = "8015"`.
  3. Executar `git push -u origin feature/quiz-visual-dashboard` e abrir o PR para `develop`.

### 6.3 Evolução Estúdio Acely — `/app`, tema claro na home e modal de geração compacto (23/11/2026)

- **Integrado no PR #97 (`feature/app-design-pro`):**
  - Workspace de `/app` em 2 colunas no desktop (painel lateral fixo + área de questão acima da dobra), WebGL mantido no lobby, remoção da pílula duplicada `.user-profile-badge` na barra, escala proporcional de todos os modais para computador (`>= 1440px`) e mobile (`<= 768px`), e tema claro completo na página inicial (`/`, `inicio.css`, `mural.js`, `inicio.html`, `inicio.js`).
- **Em desenvolvimento (`feature/modal-geracao-estudio`):**
  - Compactação editorial do modal *Novo simulado* (`#uploadModal` — abas *Enviar arquivo* e *Gerar por tema*): cabeçalho único com seletor segmentado limpo (sem ícone de estrelinha de IA), remoção de subtítulos redundantes, zona de upload horizontal compacta, linha única de parâmetros e instruções adicionais recolhidas em `<details>` opcional, preservando 100% dos IDs do DOM e traduções em `en.js`.

---

## 7. Backlog priorizado (a partir da Missão 1)

Consolidado da pesquisa técnica em `docs/missoes/m1/features.md` e da auditoria de `docs/missoes/m1/arquitetura.md`:

### 7.1 Implementados na Missão 1 (#1 a #9)

- **#1** `color-scheme` + `color-mix()` para tokens AA/AAA (`#FF7A5C`, tema escuro padrão).
- **#2** `scroll-padding-top` + `scroll-margin-top` (WCAG 2.2 SC 2.4.11 sob cabeçalho em 2 camadas).
- **#3** `100dvh` + `overscroll-behavior: contain` + `scrollbar-gutter: stable`.
- **#4** `backdrop-filter: blur(16px)` restrito à Camada 1 com fallback sólido `@supports not`.
- **#5** Atributo HTML `inert` em `<main>`/`<footer>` nos modais e em cards ocultos do Modo Foco.
- **#6** `content-visibility: auto` + `contain-intrinsic-size` em `.question`, `.result-question-item` e `.catalog-card`.
- **#7** Seletor relacional `:has()` para estados declarativos em opções, questões e painéis.
- **#8** `text-wrap: balance` / `pretty` e alvos de toque `>= 44px` no mobile (WCAG 2.2 SC 2.5.8).
- **#9** Screen Wake Lock API (`navigator.wakeLock`) durante prova ativa.

### 7.2 Adiados para missões futuras (com justificativa técnica)

| Posição | Item | Impacto / Esforço | Motivo do adiamento na M1 e próximo passo |
|---|---|---|---|
| **#10** | **CSS Cascade Layers (`@layer`)** para unificar tokens com `/` | Alto / Médio | `inicio.css` e `produto.css` carregam após `styles.css` sem `@layer` e venceriam estilos em camadas. Exige refatoração e auditoria das 9 páginas em missão dedicada (combinável com eventual extração de `tokens.css` se `/` ganhar tema claro). |
| **#11** | **CSS Container Queries (`@container`)** em painéis e catálogo | Alto / Médio | `container-type: inline-size` cria contenção e *stacking context* que podem prender `#customQuizDropdown` ou alterar larguras intrínsecas da barra de controle. Media queries atuais atendem os breakpoints da M1. |
| **#12** | **Popover API (`popover="auto"`)** na Top Layer | Médio / Médio | `#timerConfig` depende de coordenadas calculadas por `timer-drag.js` e `#customQuizDropdown` possui gestão própria de foco/ARIA em `app.js`; requer refatoração comportamental própria fora do escopo visual R2. |

### 7.3 Itens explicitamente fora das regras (manter descartados)

Conforme `docs/missoes/m1/features.md` (seção 3), continuam vetados em `/app`: `smooth-scroll.js` (R2.5),
WebGL ativo durante prova em andamento (R2.2), `backdrop-filter` em cards/opções/modais (`DESIGN_SKILLS.md` B4),
Cross-Document `@view-transition` e `document.startViewTransition()` na troca de questões, Scroll-Driven
Animations em `/app`, frameworks CSS/JS ou CDNs externas (CSP `'self'`), animações em propriedades de layout
(`width`/`height`) ou abaixo de `200ms`, gradientes de fundo no modo escuro e `border-left` isolado, pesos
`800`/`900`, itálico e `DM Mono` fora de números, CSS Anchor Positioning sem fallback, além de `window.alert()`,
`window.prompt()`, redirecionamento para `/login` ou controle de cota no navegador.

### 7.4 Tarefa de infraestrutura recomendada (fora da Missão 1)

- **Retorno do `Dockerfile` para `python:3.15-slim` (branch sugerida: `chore/dockerfile-python-3.15`):**
  na `develop` (`e8853de`), os dois estágios (`builder` e `runtime`) do `Dockerfile` (linhas 3 e 17) usam
  `python:3.16.0a1-slim@sha256:df293ba3b89f458e1aad6051b62ff1c4fad7b3b52b8147ae9cc4b667f9cf2741`.
  Abrir tarefa própria para voltar ambos os estágios à série estável **`python:3.15-slim`** com digest
  `@sha256` atualizado, evitando versão *alpha* em produção e incompatibilidades de ABI/build em
  extensões C (`psycopg2-binary`).
