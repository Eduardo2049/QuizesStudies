# PLANO_ACELY.md — Plano de continuação (marca Acely e IA mais rápida e confiável)

Documento de passagem para o agente de IA do editor (VS Code) e para quem continuar o trabalho.
Escrito em 29/10/2026. Antes de qualquer tarefa, leia o `AGENTS.md` (regras e mapa de arquivos)
e siga a ordem das fases abaixo. Cada fase vira **uma branch `feature/*` e um PR para a `develop`**,
pelo fluxo `feature/*` → `develop` → `homolog` → `main` descrito em `docs/CICD_E_DEPLOY.md`.

---

## 0. Estado das branches (em 29/10/2026)

| Branch | Conteúdo | O que fazer |
|---|---|---|
| `feature/docs-contexto` | Documentação atualizada (idiomas, OpenRouter gratuito, LGPD, rotas) + merge de `fix/openrouter-modelos-gratuitos` | **Já está dentro de `feature/rebrand-acely`.** Não precisa de PR próprio; pode ser apagada depois do merge da rebrand. |
| `feature/rebrand-acely` | Tudo da linha acima + `develop` atualizada + troca de marca para Acely + este plano | Abrir PR para a `develop`. É a base de todas as fases seguintes. |

Para criar a próxima branch: `git checkout develop && git pull && git checkout -b feature/<nome>`
(depois que a rebrand estiver na `develop`).

---

## 1. Marca Acely (acely.com.br)

### 1.1 Já feito na `feature/rebrand-acely`

- Nome "Quiz Study" / "Quizes Study" / "IFuture Study" trocado por **Acely** em telas, títulos,
  e-mails, termos, privacidade, 404, tradução em inglês (`web/modules/i18n/en.js`), documentação,
  `pyproject.toml` e `docker-compose.yml` (nomes de contêiner).
- **Logo nova** (`web/icons/favicon.svg`): um "A" cuja perna direita vira o sinal de acerto, nas
  cores atuais (fundo `#0d3f3d`, traço `#f4f0e8`, acerto `#ff7a5c`). Gerados a partir do SVG:
  `favicon-16x16.png`, `favicon-32x32.png`, `favicon-192.png`, `favicon.png` (512),
  `apple-touch-icon.png` (180, fundo cheio) e `favicon.ico` (16/32/48).
- **Imagem de compartilhamento** `web/icons/og-image.png` (1200×630) e, na home: `og:url`,
  `og:image` absoluto, `canonical`, `twitter:card = summary_large_image`, `theme-color`.
- OpenRouter recebe `HTTP-Referer: https://acely.com.br` e `X-Title: Acely`.
- Remetente padrão `noreply@acely.com.br`; seed do admin com `admin@acely.com.br`;
  exportação de dados baixa `acely-meus-dados.json`.
- `?v=` dos ícones, `i18n.js`, `en.js`, `app.js`, `auth_page.js` e `reset_password_page.js` subidos.

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
2. **Registro.br → DNS:** criar os registros que a Vercel pedir (A no domínio raiz e CNAME no `www`).
3. **Vercel → Environment Variables (Production):** `APP_URL=https://acely.com.br`.
   Em Preview, manter a URL da Vercel do ambiente.
4. **Google Cloud → OAuth:** em "Authorized redirect URIs" adicionar
   `https://acely.com.br/api/auth/google/callback`; em "Authorized JavaScript origins",
   `https://acely.com.br`. Na tela de consentimento, nome **Acely**, logo `favicon.png` (512) e
   links `https://acely.com.br/privacidade` e `https://acely.com.br/termos`.
5. **E-mail:** para enviar como `noreply@acely.com.br` é preciso um provedor de e-mail no domínio
   (com SPF e DKIM no DNS); até lá, manter `SMTP_FROM` com o Gmail atual. Opcional: criar
   `contato@acely.com.br` e trocar o e-mail de contato em `web/termos.html` e `web/privacidade.html`.
6. **Google Search Console:** verificar `acely.com.br` e enviar a home.
7. Conferir o compartilhamento do link (WhatsApp, LinkedIn) para ver a `og-image.png`.

---

## 2. Problema relatado: geração lenta e perdida ao recarregar

Teste manual no celular e no desktop: a geração por tema demorou demais; ao recarregar a página,
foi preciso fazer a mesma consulta de novo.

**Causas encontradas no código (`api/services/ai_service.py`, `web/app.js`):**

1. Os modelos padrão são os Nemotron `:free` do OpenRouter, que ficam em fila compartilhada.
   `_call_openrouter` tenta até `OPENROUTER_MAX_ATTEMPTS` (4) modelos **em sequência** dentro de um
   tempo total de 60–75 s; um modelo travado consome quase todo o tempo antes de passar ao próximo.
2. O simulado inteiro sai em **uma** resposta (até ~3.200 tokens de saída para 10 questões); nada
   aparece até o JSON completo chegar e ser validado.
3. `doGenerateTopic()` em `web/app.js` faz um único `fetch` e só guarda o resultado depois da
   resposta. Recarregar abandona o pedido; o convidado perde o simulado e a cota pode ter sido usada.
4. O cache de temas (`_quiz_generation_cache`) fica **na memória** do processo. Na Vercel cada
   instância tem a sua, então quase nunca é reaproveitado.

Observação: não é limite da Vercel (Hobby com Fluid compute permite até 300 s por função).

---

## 3. Fases de implementação

### Fase 1 — Pedido persistente, cache no banco e tempo por tentativa
Branch sugerida: `feature/ia-tarefas-persistentes`

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
6. `web/app.js`: gerar `crypto.randomUUID()` antes do `fetch`, salvar
   `{id, payload, startedAt}` em `sessionStorage` (`quiz_pending_job`); ao carregar a página, se houver
   pendente com menos de 10 min, mostrar "Seu simulado ainda está sendo gerado" e consultar
   `/api/quiz/jobs/<id>` a cada 3 s até `done`/`failed`. Limpar a chave no fim. Textos novos com
   tradução em `en.js`.

**Pronto quando**
- Recarregar a página durante a geração não perde o simulado nem gasta outra cota (teste automatizado).
- Repetir o mesmo tema/quantidade/dificuldade/idioma responde do `ai_cache` sem chamar a IA.
- Um modelo que não responde é abandonado em ~20 s.

### Fase 2 — Vários provedores gratuitos em sequência
Branch sugerida: `feature/ia-multiprovedor`

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
5. Atualizar `web/privacidade.html` (lista de provedores que recebem o texto; o plano gratuito do
   Gemini **usa o conteúdo para melhorar os produtos do Google**), `README.md`, `AGENTS.md`,
   `.agents/rules/codebase_lookup_guide.md` e `docs/CICD_E_DEPLOY.md`.
6. Testes no estilo de `tests/test_openrouter_free.py`, com respostas simuladas por provedor.

**Pronto quando**
- Sem chave do Groq/Gemini, o comportamento é igual ao de hoje.
- Com o Groq na frente, um simulado de 10 questões sai em poucos segundos.
- 429 diário de um provedor passa para o próximo sem erro para a pessoa.

**Ganho rápido sem código:** comprar US$ 10 de crédito no OpenRouter uma única vez sobe o limite
dos modelos gratuitos de 50 para 1.000 pedidos/dia (os créditos não são gastos com modelos `:free`).

### Fase 3 — Geração em partes com progresso
Branch sugerida: `feature/ia-geracao-em-partes`

1. Para mais de 5 questões, dividir em partes de 5 e gerar em paralelo
   (`concurrent.futures.ThreadPoolExecutor`, no máximo 3 ao mesmo tempo), cada parte com um foco
   diferente do tema (índice da parte no prompt) e remoção de enunciados repetidos no servidor.
2. Gravar o andamento no job (`progress: {done: 2, total: 4}`); a tela mostra "2 de 4 partes".
3. Mostrar as questões da primeira parte assim que chegarem (opcional, depois do progresso).

**Pronto quando** um simulado de 20 questões mostra progresso e não depende de uma única resposta.

### Fase 4 — Qualidade: menos respostas erradas ou fora do tema
Branch sugerida: `feature/ia-qualidade`

1. **Saída estruturada:** usar `response_format` com `json_schema` onde o provedor aceita
   (gpt-oss no Groq, Gemini); manter a validação atual para os demais.
2. **Validação no servidor** de cada questão: número de alternativas, índice da resposta dentro do
   intervalo, alternativas sem repetição, idioma pedido, explicação presente e coerente com a letra
   correta, menção ao tema. A questão reprovada é refeita uma vez; se falhar de novo, sai do simulado.
3. **Conferência por um segundo modelo** (de preferência outro provedor): responde cada questão
   **sem ver o gabarito**, com temperatura 0. Se discordar do gabarito, a questão é refeita ou
   descartada. Dobra as chamadas: ligar por variável (`AI_CROSS_CHECK=account|all|off`, padrão
   `account`, só para quem tem conta).
4. **Temperatura** 0.2–0.4 para gabarito e conferência; um pouco mais alta só para enunciados.
5. **Basear no material:** quando houver arquivo, o prompt exige que a questão saia do texto
   enviado e a explicação cite o trecho; questões sem apoio no texto são descartadas.
6. Registrar no resultado quantas questões foram conferidas (para mostrar um selo "conferida").

**Pronto quando** testes com respostas simuladas cobrem: gabarito fora do intervalo, alternativas
repetidas, idioma errado e discordância na conferência.

### Fase 5 — Menos chamadas por simulado
Branch sugerida: `feature/ia-banco-de-questoes`

1. **Temas de exemplo prontos:** os temas clicáveis da home (`.topic-chip`) passam a ter simulados
   já gerados e salvos (script em `scripts/` que gera uma vez); clicar não gasta IA.
2. **Banco reaproveitável:** simulados públicos gerados ficam disponíveis para o mesmo tema
   (o `ai_cache` da Fase 1 já cobre a repetição exata).
3. **Caminho sem IA mais visível:** quando a cota acaba, destacar "Enviar um quiz que já tem
   gabarito" (não usa IA).
4. **Opcional: chave própria** (o usuário cola a chave grátis dele do Groq ou Gemini nas
   configurações da conta; guardar criptografada; nunca devolver a chave para o navegador).

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
