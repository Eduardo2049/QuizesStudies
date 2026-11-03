-- Acely — fecha a API REST automática do Supabase (PostgREST) para as tabelas do app.
--
-- Só para Supabase. O Acely fala direto com o PostgreSQL (psycopg2) e não usa a API REST,
-- os papéis `anon`/`authenticated` nem as chaves públicas do Supabase. Sem isto, qualquer
-- pessoa com a URL do projeto e a chave `anon` poderia ler as tabelas do esquema public.
--
-- Como rodar: Supabase → SQL Editor → colar e executar, depois de a aplicação ter criado as
-- tabelas (primeiro deploy com AUTO_MIGRATE=true). Pode rodar de novo a cada tabela nova.
--
-- Por que não quebra o app: o app conecta com o dono das tabelas (usuário `postgres`, pelo
-- pooler), e o dono não é afetado por RLS. Se um dia usar outro usuário, crie as políticas
-- antes ou use FORCE com cuidado.
--
-- Alternativa mais simples: Project Settings → Data API → desligar a Data API.

DO $$
DECLARE
    t record;
BEGIN
    FOR t IN
        SELECT tablename FROM pg_tables WHERE schemaname = 'public'
    LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t.tablename);
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
            EXECUTE format('REVOKE ALL ON public.%I FROM anon', t.tablename);
        END IF;
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
            EXECUTE format('REVOKE ALL ON public.%I FROM authenticated', t.tablename);
        END IF;
    END LOOP;
END $$;

-- Conferência: todas as linhas devem mostrar rowsecurity = true
SELECT tablename, rowsecurity FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;
