# PLANO_SAAS.md: Acely como produto (SaaS individual e para equipes)

Documento de passagem para quem continuar o trabalho (pessoa ou agente). Escrito em 09/11/2026.
Antes de qualquer fase, leia o `AGENTS.md` e o `docs/PLANO_ACELY.md` (as fases de IA de lá continuam
valendo e se encaixam nas fases deste plano). Cada fase vira **uma branch `feature/*` e um PR para a
`develop`**, pelo fluxo `feature/*` → `develop` → `homolog` → `main`.

---

## 0. Decisões já tomadas (09/11/2026)

| Tema | Decisão |
|---|---|
| Código | Repositório passa a **privado**; licença MIT trocada por **proprietária** (`LICENSE`). |
| Público | **Individual** (estudante) e **coletivo**: turmas de ensino (professor, cursinho, escola) **e** empresas (treinamento, certificações). Um único modelo de *workspace* com papéis atende os dois. |
| Cobrança | **Provedor a decidir.** Planos, limites e telas são feitos agora; o pagamento entra numa fase própria (seção 5, Fase S4). Até lá, os planos pagos aparecem como "em breve". |
| Primeira entrega | Página de produto `/produto` (alias `/planos`) com o produto, os planos, os modelos de IA e equipes. |

---

## 1. O que muda ao virar produto

### 1.1 Itens que hoje impedem cobrar

| Item | Situação | O que fazer |
|---|---|---|
| **Hospedagem** | Vercel Hobby, que é só para uso pessoal e não comercial (Fair Use Guidelines). | Migrar o time da Vercel para o **Pro** antes do primeiro pagamento (US$ 20/mês por membro do time). |
| **IA gratuita** | Groq, Gemini, Cerebras e OpenRouter nos planos grátis. O grátis do Gemini usa o conteúdo para melhorar os produtos do Google; o do Groq é voltado a protótipo, com limite baixo por minuto. | Plano **Grátis** do Acely pode seguir nos provedores grátis (com aviso na privacidade). Planos **pagos** usam a API paga (Groq Developer ou Gemini com faturamento), sem uso dos dados para treino. |
| **Licença MIT** | Quem já copiou o código mantém o direito de usar a versão MIT. Não dá para revogar. | A nova licença vale para o código daqui para frente; o diferencial passa a ser o serviço (dados, IA, equipes), não o código. |
| **E-mail** | Remetente pelo Gmail. | Provedor transacional no domínio (SPF, DKIM, DMARC) para convites de equipe e recibos. |
| **Termos** | Escritos para um serviço gratuito. | Termos com planos, renovação, cancelamento, reembolso (CDC: 7 dias de arrependimento na compra on-line), e um contrato de tratamento de dados (DPA) para empresas e escolas. |

### 1.2 Custo de IA por simulado (referência para o preço)

Simulado de 10 questões ≈ 1,5 mil tokens de entrada e 3,5 mil de saída. No Groq pago, o
`gpt-oss-120b` custa US$ 0,15 por milhão de tokens de entrada e US$ 0,60 por milhão de saída:
**≈ US$ 0,0023 por simulado** (≈ US$ 0,005 com a conferência por um segundo modelo da Fase 4 do
`PLANO_ACELY.md`). 300 simulados por mês de um assinante custam ≈ US$ 1,50 de IA.
Conferir os preços no painel do provedor antes de fechar os valores.

---

## 2. Planos propostos

Valores sugeridos para validar (referência: Quizlet Plus no Brasil ≈ R$ 49,90/mês na App Store).
Os limites ficam em uma tabela no banco (Fase S1) para mudar sem deploy.

| | **Grátis** | **Pro** (individual) | **Equipe** (turmas e empresas) | **Instituição** |
|---|---|---|---|---|
| Preço sugerido | R$ 0 | R$ 19,90/mês ou R$ 179/ano | R$ 14,90 por membro/mês (mín. 3) | Sob consulta |
| Gerações com IA | 20 por mês | 300 por mês | 300 por membro/mês, somadas no time | Contrato |
| Questões por simulado | até 10 | até 30 | até 30 | até 50 |
| Arquivo enviado | até 5 MB | até 20 MB | até 20 MB | até 50 MB |
| Modelos de IA | Rápido (provedores gratuitos) | Preciso (API paga, sem treino com seus dados) | Preciso | Preciso, com região e retenção definidas |
| Conferência do gabarito por um segundo modelo | Não | Sim | Sim | Sim |
| Caderno de erros com variações | 3 por mês | Ilimitado (dentro da cota) | Ilimitado (dentro da cota) | Ilimitado |
| Workspace, papéis e convites | Não | Não | Sim | Sim + SSO |
| Atribuir simulado com prazo e ver resultados | Não | Não | Sim | Sim |
| Banco de questões compartilhado | Não | Não | Sim | Sim |
| Relatórios e exportação (CSV) | Básico | Completo | Por membro e por turma | API |
| Suporte | Comunidade | E-mail | E-mail prioritário | Dedicado, DPA LGPD |

O convidado (sem conta) continua com a cota atual (`GUEST_AI_LIMIT`) e é a porta de entrada do Grátis.

**Na página `/produto` hoje:** o Grátis lista só o que já existe (até 30 questões, arquivos de
até 20 MB); Pro e Equipe aparecem como "em breve", sem preço e com o botão desativado; Instituição
abre um e-mail. Ao implementar a Fase S1, trocar os limites do Grátis na página pelos da tabela
`plans` e, na S4, pôr os preços e o checkout nos cartões (o teste `tests/test_pagina_produto.py`
confere que nenhum plano pago tem compra ativa: atualizá-lo junto).

---

## 3. Modelo de dados (multi-inquilino)

Tudo novo, com migrations idempotentes (`IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS`). Nenhuma
coluna existente muda de tipo.

```
plans            (id 'free'|'pro'|'team'|'institution', nome, limites jsonb, ativo)
workspaces       (id uuid, nome, slug, kind 'personal'|'class'|'company', plan_id,
                  seats, owner_user_id, created_at)
workspace_members(workspace_id, user_id, role 'owner'|'manager'|'member', status, joined_at)
workspace_invites(id, workspace_id, email, role, token_hash, expires_at, accepted_at)
subscriptions    (id, workspace_id, provider, provider_ref, status 'trialing'|'active'|
                  'past_due'|'canceled', current_period_end, cancel_at)
usage_counters   (workspace_id, user_id, metric 'ai_generation'|'ai_remix'|'upload_mb',
                  period 'YYYY-MM', amount)        -- substitui contagens soltas por usuário
assignments      (id, workspace_id, quiz_id, title, due_at, created_by)
assignment_results(assignment_id, user_id, attempt_id, score, finished_at)
audit_log        (id, workspace_id, actor_user_id, action, target, created_at)
```

- Todo usuário ganha um workspace `personal` na primeira entrada (migration preenche os atuais).
- `quizzes` ganha `workspace_id` (nulo = legado/pessoal) e `visibility` ('private'|'workspace'|'public').
- **Regra de ouro:** toda consulta de dados de equipe filtra por `workspace_id` vindo da sessão e
  do vínculo em `workspace_members`, nunca do corpo da requisição. Testes de isolamento entre
  workspaces são obrigatórios em cada PR que tocar repositórios.
- `role` atual em `users` ('student'/'admin') continua para o admin da plataforma; os papéis de
  equipe ficam em `workspace_members`.

---

## 4. Arquitetura que se mantém

- Backend Python puro em camadas, PostgreSQL, Vanilla JS/CSS, CSP `'self'`. Nada disso muda.
- Novo serviço `api/services/entitlements_service.py`: responde "este usuário, neste workspace,
  pode fazer X?" e "quanto resta da cota?". `quiz_handler.py` chama esse serviço antes de toda
  ação de IA, no mesmo lugar onde hoje chama o `GuestService`. O navegador só mostra a cota.
- Novo `api/services/billing_service.py` com uma interface única (`create_checkout`,
  `handle_webhook`, `portal_url`, `cancel`) e um adaptador por provedor. Webhooks com assinatura
  verificada e idempotência por id do evento.
- A ordem de provedores de IA passa a depender do plano: `AI_PROVIDERS_FREE` e
  `AI_PROVIDERS_PAID` (mesma lógica de `_call_ai` da Fase 2 do `PLANO_ACELY.md`).

---

## 5. Fases

### Fase S0: Privatização e base legal (dono do projeto + PR de licença)
Branch: `feature/saas-produto-e-planos` (licença) · resto é manual.

**Checklist manual (fora do código)**
1. GitHub → `Eduardo2049/QuizesStudies` → Settings → General → Danger Zone → **Change visibility → Private**.
   Antes: conferir se algum serviço usa o repositório público (badge do README, GitHub Pages, links
   no portfólio e no LinkedIn).
2. GitHub → Settings → Actions: conferir os minutos do plano gratuito para repositório privado
   (2.000 min/mês no Free); os workflows de `ci.yml` e `tests.yml` passam a consumir essa cota.
3. GitHub → Settings → Code security: o Dependabot continua funcionando em privado; o *secret
   scanning* e o *code scanning* passam a depender do plano.
4. GitHub Projects ligados ao repositório: mudar a visibilidade de cada projeto para privado
   (Project → Settings → Visibility).
5. Vercel → Project → Settings → **Git**: confirmar que a integração continua com acesso ao
   repositório privado (a Vercel pede permissão de novo se o app do GitHub tiver acesso só a
   repositórios públicos).
6. Vercel → Settings → **Deployment Protection**: ativar proteção nos *Preview Deployments* (as
   URLs de preview são públicas por padrão).
7. Procurar cópias públicas: forks (hoje 0), o repositório do portfólio, gists, o `GEMINI.md` e o
   `.github/copilot-instructions.md` (não expõem segredos, mas descrevem a arquitetura).
8. Rodar uma busca por segredos no histórico (`gitleaks detect` localmente). Qualquer chave que
   já tenha aparecido em commit deve ser **trocada**, porque o histórico público já pode ter sido copiado.
9. Registrar a marca **Acely** no INPI (classes 9, 41 e 42) e conferir o domínio `.com`.

**No código (este PR):** `LICENSE` proprietária, `license` no `pyproject.toml`/`package.json`,
seção de licença no `README.md`.

### Fase S1: Planos e limites no servidor
Branch sugerida: `feature/saas-planos-limites`
1. Tabelas `plans`, `workspaces`, `workspace_members`, `usage_counters` + migration que cria o
   workspace pessoal de cada usuário e o põe no plano `free`.
2. `entitlements_service.py` com testes: cota mensal, tamanho de arquivo, questões por simulado,
   recursos liga/desliga.
3. Trocar as checagens soltas de limite por chamadas ao serviço (geração, upload, remix).
4. `GET /api/me/plan` → plano, limites e uso do mês. Chip de cota no topo usa essa rota.
5. Tela "Minha conta" ganha a aba **Plano e uso** (barra de uso do mês, data da renovação).

**Pronto quando** um usuário Grátis recebe erro claro ao passar da cota e um usuário marcado como
Pro no banco (manualmente) não recebe.

### Fase S2: Workspaces de equipe
Branch sugerida: `feature/saas-equipes`
1. Criar equipe (nome, tipo `class` ou `company`), seletor de workspace no topo.
2. Convites por e-mail e por link com validade; aceitar exige conta; papéis dono/gestor/membro.
3. Simulados com visibilidade `workspace`; banco de questões compartilhado.
4. Testes de isolamento: membro de A nunca lê, altera ou lista nada de B.
5. Textos adaptados por tipo: "Turma/Aluno/Professor" em `class`, "Equipe/Colaborador/Gestor" em `company`.

### Fase S3: Atribuições e painel do gestor
Branch sugerida: `feature/saas-atribuicoes`
1. Gestor atribui simulado com prazo; membro vê "Para fazer" na home.
2. Painel do gestor: quem fez, nota, tempo, questões mais erradas, evolução por tema
   (reaproveita `modules/stats.js`).
3. Exportar CSV por atribuição. Registrar ações no `audit_log`.

### Fase S4: Cobrança (depois de escolher o provedor)
Branch sugerida: `feature/saas-cobranca`
1. Escolher o provedor. Critérios: Pix Automático e cartão recorrente, boleto para escolas,
   nota fiscal de serviço, cobrança por assento, portal do cliente, taxas e repasse.
   Candidatos: Stripe (cartão e Pix, bom para cobrar fora do Brasil), Mercado Pago, Asaas, Pagar.me, Vindi.
2. `billing_service.py` + adaptador do escolhido; webhooks → `subscriptions` → plano do workspace.
3. Checkout a partir da página `/produto#planos` e de "Minha conta"; teste grátis de 7 dias no Pro.
4. Atualizar termos (renovação, cancelamento, reembolso) e privacidade (o provedor de pagamento
   como operador de dados).
5. Abrir CNPJ (MEI não cobre "desenvolvimento de software" com tranquilidade; avaliar ME no
   Simples, Anexo III com Fator R) antes do primeiro pagamento.

### Fase S5: IA paga por plano
Junto com as Fases 3 e 4 do `PLANO_ACELY.md`.
1. `AI_PROVIDERS_FREE` e `AI_PROVIDERS_PAID`; chaves pagas só em produção.
2. Conferência por segundo modelo ligada para planos pagos (`AI_CROSS_CHECK=paid`).
3. Selo "gabarito conferido" nas questões; métricas de custo por workspace no admin.

### Fase S6: Promoção da página de produto para a raiz
Branch sugerida: `feature/saas-raiz`
Quando a página de produto estiver validada: `/` vira a página de produto para quem não tem
sessão e o app passa para `/app`. Tocar com cuidado: `safe_next` (padrão `/`), redirecionamentos
da confirmação de e-mail e do login com Google, `vercel.json`, `sitemap.xml`, testes que acessam `/`
e as capturas em `tests/visual/capture_baseline.py`.

---

## 6. Primeira entrega deste plano (09/11/2026)

Branch `feature/saas-produto-e-planos`:
- Página `/produto` (e `/planos`, que rola até os planos) em `public/web/produto.html`, com estilo
  em `public/web/produto.css` e comportamento em `public/web/modules/produto.js`.
  Seções: hero, como funciona, tagline com revelação palavra por palavra, modelos de IA,
  para quem (individual, turmas, empresas), planos, perguntas frequentes e chamada final.
- Link "Planos" no topo da home e "Produto e planos" no rodapé de todas as páginas.
- Rotas no `vercel.json` e no `quiz_handler.py`; `sitemap.xml` atualizado.
- Tradução em `en.js`; testes do domínio cobrem a rota nova.
- Licença proprietária.

---

## 7. Regras para quem executar este plano

- Tudo do `AGENTS.md` continua: sem frameworks novos, CSP `'self'`, migrations idempotentes,
  textos novos com tradução, `?v=` subido, testes antes do PR.
- Nunca decidir plano ou cota no navegador. O servidor decide; o cliente só mostra.
- Nunca confiar em `workspace_id` vindo do cliente sem conferir o vínculo do usuário.
- Preços e limites mudam pela tabela `plans`, não por constantes espalhadas no código.
- Ao terminar uma fase, marcar aqui o que ficou pronto e o que mudou em relação ao plano.
