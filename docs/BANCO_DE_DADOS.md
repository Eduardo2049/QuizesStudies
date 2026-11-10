# Banco de dados — provedores, credenciais e segurança

O Acely usa PostgreSQL comum (`psycopg2`, sem extensões e sem recursos exclusivos de um
provedor). Qualquer PostgreSQL 14+ serve: Neon, Supabase, Docker local ou outro. Trocar de
provedor é trocar as variáveis abaixo e rodar o primeiro deploy (as migrations criam as tabelas).

## 1. Variáveis

| Variável | Para que serve | Obrigatória |
|---|---|---|
| `DATABASE_URL` | URL usada pela aplicação. Na Vercel, **com pooler**. Tem prioridade sobre as variáveis da integração Neon (`POSTGRES_URL`, `DATABASE_URL_UNPOOLED`, `POSTGRES_PRISMA_URL`), que ficam só como reserva. | Sim |
| `ACELY_DATABASE_URL` | Sua URL, com prioridade sobre todas as outras. Use na Vercel quando a integração Neon trava o nome `DATABASE_URL` (seção 2.1). | Não |
| `ACELY_DATABASE_URL_DIRECT` | Versão sem pooler da anterior (vazio = usa a `ACELY_DATABASE_URL`). | Não |
| `DATABASE_URL_DIRECT` | URL **sem pooler** para migrations e `scripts/reset_database.py`. Vazio = usa a `DATABASE_URL`. | Não |
| `DB_SSLMODE` | Modo TLS quando a URL não traz `sslmode`. Padrão `verify-full`. | Não |
| `DB_SSLROOTCERT` | Certificado da autoridade para `verify-full`: caminho (relativo à raiz do projeto ou absoluto). Vazio = arquivo do `certifi`. | Só no Supabase |
| `DB_SSLROOTCERT_PEM` | Alternativa ao anterior para a Vercel: o conteúdo do `.crt` colado na variável (pode usar `\n` no lugar das quebras de linha). O certificado é público, não é segredo. | Não |
| `AUTO_MIGRATE` | `true` roda as migrations na primeira requisição. | Não |

Regra de segurança importante: se `DATABASE_URL` foi cadastrada à mão, as migrations **nunca**
usam `DATABASE_URL_UNPOOLED` (que pode ter sobrado da integração Neon e apontar para outro
banco). Elas usam `DATABASE_URL_DIRECT` ou a própria `DATABASE_URL`.

### TLS

- Sem `sslmode` na URL, o app usa `verify-full` e, sem certificado configurado, o arquivo de
  autoridades do `certifi` (fixado no `requirements.txt`). `sslrootcert=system` não é usado: o
  OpenSSL do `psycopg2-binary` procura os certificados numa pasta que só existia na máquina
  onde o pacote foi compilado, e a conexão falha com "certificate verify failed".
- Se a URL trouxer `sslmode=require` (as URLs geradas pela integração Neon da Vercel costumam
  trazer), a conexão é cifrada mas **não valida o certificado**. O servidor avisa uma vez no log:
  `[db] Aviso: conexão com ... usa sslmode=require`. Para corrigir, troque por
  `sslmode=verify-full` na URL (Neon: funciona com o `certifi`, sem mais nada; Supabase: veja a seção 3).
- Os logs mostram só host, porta e banco (`describe_database_target`), nunca usuário ou senha.

## 2. Neon com conta própria (recomendado hoje)

Assim as credenciais são suas e não dependem da integração da Vercel.

1. Crie a conta e o projeto em neon.com, na região mais próxima da função da Vercel
   (veja `docs/CICD_E_DEPLOY.md`, seção 8).
2. Crie um branch por ambiente: `main` (produção) e `homolog`/`develop` (Preview). Branches são
   grátis no plano Free.
3. Em **Connect**, copie as duas URLs de cada branch:
   - com pooler (host com `-pooler`) → `DATABASE_URL`;
   - sem pooler → `DATABASE_URL_DIRECT`.
   Troque `sslmode=require` por `sslmode=verify-full` nas duas.
4. Vercel → Settings → Environment Variables: cadastre `DATABASE_URL` e `DATABASE_URL_DIRECT`
   em Production com o branch `main` e em Preview com o branch de homologação.
5. GitHub → Settings → Environments (`production`, `homolog`): atualize o secret `DATABASE_URL`
   usado pelo workflow de limpeza, de preferência com a URL **sem** pooler.
6. Faça um deploy e confira no log que não aparece o aviso de `sslmode`.
7. Só depois de tudo funcionando: remova a integração Neon em Vercel → Storage, se ainda existir
   (ela recria `POSTGRES_URL` e afins). Para levar os dados de um banco ao outro:
   `pg_dump --no-owner --no-acl "$ORIGEM" | psql "$DESTINO"`.

## 2.1 Neon criada pela Vercel (integração) com URL própria

Com a integração, o banco fica na organização `Vercel: <time>` da Neon (entre por Vercel →
Storage → **Open in Neon**) e a integração cria e trava `DATABASE_URL`, `DATABASE_URL_UNPOOLED`,
`POSTGRES_URL` e afins: não dá para editar. Para usar uma URL sua (ex.: com `verify-full`):

1. Neon → **Connect**: branch de produção, banco e role padrão, **Connection pooling ligado**
   (host com `-pooler`). Copie a string direto para a Vercel, sem salvar em arquivo nem colar em chat.
2. Troque `sslmode=require` por `sslmode=verify-full` (pode manter `channel_binding=require`).
   Não acrescente `sslrootcert=system`: o OpenSSL embutido no `psycopg2-binary` não encontra os
   certificados do sistema e a conexão falha com "certificate verify failed". O app usa o
   arquivo de autoridades do `certifi` sozinho (e troca `system` por ele se estiver na URL).
3. Vercel → Settings → Environment Variables → **Add**: nome `ACELY_DATABASE_URL`, cole a URL,
   marque só **Production** e **Sensitive**. Salve.
4. **Redeploy** da produção (variáveis novas só valem em deploys novos).
5. Confira nos logs da função que **não** aparece o aviso `[db] Aviso: ... sslmode=require`.

Preview continua usando as variáveis da integração (um banco/branch separado). Se a senha do
banco for trocada na Neon (**Reset password**), atualize a `ACELY_DATABASE_URL` também:
ela não é atualizada sozinha como as variáveis da integração.

## 3. Supabase

O Acely não usa o login, o armazenamento nem a API REST do Supabase; ele seria só o PostgreSQL.
Atenção ao plano gratuito: projetos sem uso por uma semana são pausados e precisam ser reativados
à mão no painel.

1. Crie o projeto na região mais próxima da função da Vercel.
2. **Connect** → copie:
   - **Transaction pooler** (porta `6543`) → `DATABASE_URL`. Obrigatório na Vercel: a conexão
     direta do Supabase é só IPv6 e a Vercel só sai por IPv4. O `psycopg2` não usa prepared
     statements por padrão, então o modo transação funciona sem ajuste.
   - **Session pooler** (porta `5432` no host `pooler.supabase.com`) → `DATABASE_URL_DIRECT`.
3. Certificado: Project Settings → Database → SSL Configuration → baixe o `.crt`. Use uma das
   duas formas:
   - cole o conteúdo em `DB_SSLROOTCERT_PEM` (mais simples na Vercel); ou
   - salve em `certs/supabase-ca.crt` no repositório e defina `DB_SSLROOTCERT=certs/supabase-ca.crt`.
   Sem isso, `verify-full` falha (o certificado do Supabase não é de uma autoridade pública).
4. Depois do primeiro deploy (tabelas criadas), rode `scripts/sql/supabase_fechar_api_publica.sql`
   no SQL Editor, ou desligue a Data API em Project Settings → Data API. Isso impede que a API
   REST automática exponha as tabelas do esquema `public`.
5. Plano gratuito: 2 projetos ativos. Use um para produção e outro para Preview.

## 4. Docker local

`docker compose up -d` sobe o PostgreSQL em `127.0.0.1:5433` com o banco `quiz_study` (nome
mantido de propósito; trocar aponta o contêiner para um banco vazio). Conexões em `localhost`
não recebem `sslmode`.

## 4.1 Planos e uso mensal (Fase S1 do PLANO_SAAS.md)

| Tabela | O que guarda |
|---|---|
| `plans` | Um registro por plano (`free`, `pro`, `team`, `institution`) com os limites em `limits` (JSONB). |
| `workspaces` | O workspace pessoal de cada conta (`kind = 'personal'`) e, na Fase S2, os de equipe. `plan_id` diz o plano. |
| `workspace_members` | Quem participa de cada workspace e com que papel (`owner`, `manager`, `member`). |
| `usage_counters` | Uso por pessoa, métrica (`ai_generation`, `ai_remix`) e mês (`AAAA-MM`, horário de Brasília). |

- As linhas de `plans` nascem de `api/utils/plans.py` com `ON CONFLICT DO NOTHING`: um ajuste feito
  direto no banco **não** é desfeito no próximo deploy. Para mudar um limite:
  ```sql
  UPDATE plans SET limits = jsonb_set(limits, '{ai_generations_per_month}', '50'), updated_at = NOW()
  WHERE id = 'free';
  ```
- Para pôr uma conta em outro plano (até a cobrança da Fase S4 existir):
  ```sql
  UPDATE workspaces SET plan_id = 'pro'
  WHERE kind = 'personal' AND owner_user_id = (SELECT id FROM users WHERE username = 'fulano');
  ```
- Excluir a conta apaga em cascata o workspace pessoal, os vínculos e os contadores de uso.

## 5. Boas práticas

- Nunca commitar URLs com senha; valores reais só na Vercel, no GitHub Secrets ou no `.env` local.
- Um banco (ou branch) por ambiente: Preview nunca aponta para produção.
- Senha forte e exclusiva por ambiente; ao trocar de provedor, gere senhas novas.
- Espaço: os planos gratuitos têm ~0,5 GB. As tabelas que crescem sem parar se limpam sozinhas, de
  vez em quando, ao gravar: `rate_limits` (24 h), `ai_jobs` (24 h) e `ai_cache` (`AI_CACHE_TTL_DAYS`).

## 6. Desempenho das conexões

**Pool (`api/database/connection.py`).** Na Vercel, a instância da função guarda o pool entre
visitas, e a Neon desliga o banco após 5 minutos sem uso, derrubando as conexões abertas.
- Conexão parada há mais de 30 s (`POOL_CHECK_AFTER_S`) é testada com um `SELECT 1` antes de
  ser reaproveitada; se morreu, é trocada por uma nova sem erro para a pessoa.
- Conexão fechada ou quebrada no meio da requisição é descartada com `putconn(close=True)`,
  liberando a vaga. Antes, cada queda prendia uma das 10 vagas e, esgotado o pool, toda
  requisição abria conexão nova (handshake TLS completo).
- A URL ganha keepalive TCP (`keepalives_idle=30`) para perceber conexões derrubadas.

**Região.** Cada requisição da home faz algumas idas ao banco (limite de requisições,
sessão, consulta). Função e banco em continentes diferentes somam ~120 ms por ida. Confira:
1. Região do banco: Neon → Project settings (ex.: `aws-sa-east-1`); Supabase → Project Settings → General.
2. Vercel → Settings → Functions → Function Region: a mesma região (`gru1` para São Paulo,
   `iad1` para Virgínia). Se preferir no código, `"regions": ["gru1"]` no `vercel.json`.

**Primeira visita depois de uma pausa** soma três esperas: a função "acorda" (cold start),
a Neon religa o banco (algumas centenas de ms) e a conexão TLS é aberta. Isso só some com
banco sempre ligado (plano pago, `scale to zero` desligado).

**Speed Insights.** O Real Experience Score mistura FCP, LCP, CLS e INP medidos no navegador.
Com poucas visitas por dia, o P75 oscila muito e some nos dias sem acesso; compare semanas,
não dias.
