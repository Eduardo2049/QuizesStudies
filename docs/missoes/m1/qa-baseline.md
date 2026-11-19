# Baseline de QA, Acessibilidade e Desempenho — Missão 1 (Fase 1F)

- **Projeto:** Acely (`Eduardo2049/QuizesStudies`)
- **Branch base:** `develop` (`e8853de`)
- **Data da coleta:** `2026-11-18` (UTC)
- **Responsável:** Agente F (QA, A11y e Desempenho)
- **Política aplicada:** Somente leitura no código-fonte da aplicação (`public/web/`, `api/`, `tests/`, `package.json`, `Dockerfile`, `docker-compose.yml`, `Procfile`, `vercel.json` preservados intactos).

---

## 1. Resumo Executivo

| Verificação | Comando executado | Exit Code | Resultado resumido |
|---|---|---:|---|
| Suíte automatizada | `python -m unittest discover tests` | `1` | **390** testes em `38.406s` (`299` OK, `3` falhas reais, `68` erros por bloqueio de socket no sandbox `WinError 10013`, `20` skips por ausência de Postgres de integração) |
| Contratos de UI (sem rede) | `python -m unittest tests/test_ui_contract.py tests/test_modulepreload.py` | `0` | **6** testes (`4` em `test_ui_contract.py` + `2` em `test_modulepreload.py`): **100% aprovados** |
| Lint estático | `ruff check .` (`ruff 0.16.10`) | `1` | **237** violações em **48** arquivos (`111` auto-corrigíveis com `--fix`) |
| Formatação | `ruff format --check .` (`ruff 0.16.10`) | `1` | **56** arquivos precisam de reformatação; **33** arquivos já conformes |
| Baseline visual e A11y | `python tests/visual/capture_baseline.py --label before` | `1` | **Bloqueado pelo sandbox** (`WinError 10013` impede abrir servidor local/Postgres e impede conectar na porta CDP do Edge em `127.0.0.1`; `BypassSandbox=true` expirou em 60s sem aprovação interativa) |

> **Nota de ambiente (Windows):** No PowerShell deste ambiente, o alias `python.exe` da Microsoft Store (`WindowsApps`) falhou com erro de acesso ao arquivo. Todas as execuções acima usaram o interpretador real instalado em `C:\Users\eduardo.asousa\AppData\Local\Python\pythoncore-3.14-64\python.exe` (`Python 3.14.5`) e `C:\Users\eduardo.asousa\AppData\Local\Python\pythoncore-3.14-64\Scripts\ruff.exe` (`ruff 0.16.10`).

---

## 2. Testes Automatizados (`unittest`)

### 2.1 Execução completa

- **Comando exato:**
  ```powershell
  & "C:\Users\eduardo.asousa\AppData\Local\Python\pythoncore-3.14-64\python.exe" -m unittest discover tests
  ```
- **Código de saída:** `1`
- **Total executado:** `390` testes (28 arquivos `tests/test_*.py`)
- **Tempo de execução:** `38.406s` no runner (`45.85s` de relógio total)
- **Distribuição:**
  - **Passaram:** `299`
  - **Falhas (`FAIL`):** `3` (falhas reais de asserção, independentes de rede)
  - **Erros (`ERROR`):** `68` (todos decorrentes de bloqueio de socket/loopback no sandbox)
  - **Pulados (`skipped`):** `20` (todos com condição `QUIZ_DB_INTEGRATION=1 com banco local não configurado`)

### 2.2 Diagnóstico das 3 falhas reais (`FAIL`)

| Teste | Arquivo e linha | Erro observado | Causa-raiz verificada |
|---|---|---|---|
| `test_remote_url_gets_verify_full_with_system_ca` | `tests/test_banco_credenciais.py:43` | `AssertionError: 'sslrootcert=C:\\Users\\...\\cacert.pem' not found in 'postgresql://...&sslrootcert=C:%5CUsers%5C...'` | No Windows, `certifi.where()` usa `\`, e `connection.build_database_url()` escapa a URL com `urlencode` (`%5C`), enquanto o teste compara com a string não escapada. |
| `test_missing_key_message_is_generic` | `tests/test_prod_hardening.py:67` | `AssertionError: 'Os modelos gratuitos de IA estão ocupados agora. Tente novamente em alguns instantes.' != 'A geração com IA está indisponível no momento. Tente novamente mais tarde.'` | O `.env` local possui chaves de Groq/Gemini configuradas; o teste só sobrescreve `OPENROUTER_API_KEY=""`, deixando `groq`/`gemini` ativos, que falham na rede e produzem mensagem de indisponibilidade temporária. |
| `test_generate_quiz_by_topic_with_openrouter_free_model` | `tests/test_security_fixes.py:194` | `AssertionError: False is not true` (`sent_model.endswith(":free")`) | Com `GROQ_API_KEY` presente no `.env` local, `AI_PROVIDERS` tenta `groq` antes de `openrouter` e envia o modelo do Groq (sem sufixo `:free`) para a sessão HTTP mockada. |

### 2.3 Diagnóstico dos 68 erros (`ERROR`) e 20 skips

- **67 erros `PermissionError: [WinError 10013]`:** O ambiente sandbox permite `socket.bind('127.0.0.1', 0)`, mas bloqueia `socket.connect` em `127.0.0.1` (`WinError 10013`). Todos os testes que sobem `ThreadingHTTPServer` local e fazem `urllib.request.urlopen` falharam na conexão:
  - `test_guest_access`: 12 erros
  - `test_pagina_inicio`: 11 erros (`TestInicioRoutes`; os outros 10 testes estáticos do mesmo arquivo passaram)
  - `test_prod_hardening`: 9 erros
  - `test_ai_jobs`: 7 erros
  - `test_planos_limites`: 7 erros
  - `test_seguranca`: 7 erros
  - `test_login_codigo_email`: 6 erros
  - `test_dominio_acely`: 3 erros
  - `test_forgot_password_route`: 3 erros
  - `test_pagina_produto`: 2 erros
- **1 erro de timeout de servidor E2E:** `setUpClass (test_auth_e2e.AuthE2ETestCase)` → `RuntimeError: Servidor nao respondeu em 10s na porta 8005.` (mesma causa: conexão local bloqueada no sandbox).
- **20 skips:** `test_db_integration.py`, `test_login_codigo_email.py`, `test_planos_limites.py` e `test_pool_conexoes.py`, todos aguardando `QUIZ_DB_INTEGRATION=1` com PostgreSQL local.
- **Execução fora do sandbox:** Uma tentativa com `BypassSandbox=true` foi disparada e retornou erro de timeout após 60s aguardando confirmação interativa do usuário.
- **Contratos de UI e pré-carregamento (verificação isolada sem rede):**
  - `tests/test_ui_contract.py` (`4/4` OK): todos os IDs buscados por `app.js`, `auth_page.js`, `reset_password_page.js`, `inicio.js` e módulos compartilhados existem nos HTMLs, `for`/`aria-*` apontam para IDs reais e não há IDs duplicados por página.
  - `tests/test_modulepreload.py` (`2/2` OK) e testes estáticos de `tests/test_pagina_inicio.py` (`10/10` OK): versões `?v=` de `i18n.js` sincronizadas, CSP `'self'` respeitada e chaves PT/EN da página inicial alinhadas.

---

## 3. Lint e Formatação (`ruff 0.16.10`)

Configuração ativa em `pyproject.toml`: `target-version = "py311"`, `line-length = 120`, `src = ["api", "tests", "scripts"]`, regras `E, W, F, I, B, C4, UP, S, SIM, TCH, RUF` (ignorando `E501, S101, S311, B008, UP007`; `tests/**` ignora `S101, S106`).

### 3.1 `ruff check .`

- **Comando:** `ruff check .`
- **Código de saída:** `1`
- **Total:** **237 violações** em **48 arquivos** (`111` corrigíveis com `--fix`; `43` ocultas com `--unsafe-fixes`).

**Distribuição por regra (`ruff check . --statistics`):**

| Regra | Ocorrências | Fixável | Descrição |
|---|---:|:---:|---|
| `I001` | 46 | `[*]` | Bloco de imports não ordenado/formatado |
| `RUF059` | 20 | `[ ]` | Variável desempacotada não utilizada |
| `F401` | 19 | `[*]` | Import não utilizado |
| `S310` | 18 | `[ ]` | Uso de `urllib.request.urlopen` sem auditoria de esquema (`# noqa: S310`) |
| `S110` | 18 | `[ ]` | `try-except-pass` sem log |
| `B904` | 16 | `[ ]` | `raise` dentro de `except` sem `from err` / `from None` |
| `SIM105` | 14 | `[ ]` | Substituível por `contextlib.suppress(...)` |
| `RUF100` | 11 | `[*]` | Diretiva `noqa` não utilizada |
| `RUF001` | 7 | `[ ]` | Caractere Unicode ambíguo em string (ex.: travessão/aspa) |
| `F541` | 7 | `[*]` | f-string sem placeholders |
| `SIM117` | 7 | `[-]` | `with` aninhados combináveis |
| `UP012` | 7 | `[*]` | `.encode("utf-8")` redundante |
| `E402` | 6 | `[ ]` | Import no meio do arquivo (fora do topo) |
| `UP045` | 6 | `[*]` | `Optional[X]` em vez de `X | None` |
| `S105` | 5 | `[ ]` | Possível senha hardcoded em string (ex.: `tests/test_validators.py:91`) |
| `W293` | 4 | `[-]` | Linha em branco com espaços |
| `RUF013` | 4 | `[ ]` | `Optional` implícito em argumento com padrão `None` |
| `UP006` | 4 | `[*]` | Anotação genérica antiga (`List`/`Dict`/`Tuple`) |
| `F841` | 4 | `[-]` | Variável local atribuída e não utilizada |
| Outras (`UP035`, `S104`, `RUF012`, `B905`, `UP017`, `S608`, `SIM108`, `W292`, `UP037`, `S603`) | 14 | misto | 1–2 ocorrências cada |

**Top 15 arquivos com mais violações no `ruff check .`:**
1. `api/services/ai_service.py` (25)
2. `scripts/load_test_real_api.py` (17)
3. `api/utils/file_parser.py` (16)
4. `api/handlers/quiz_handler.py` (13)
5. `tests/test_prod_hardening.py` (13)
6. `api/database/connection.py` (11)
7. `api/models/dtos.py` (9)
8. `api/services/upload_service.py` (9)
9. `scripts/reset_admin.py` (7)
10. `tests/test_load_and_token_usage.py` (7)
11. `tests/test_guest_access.py` (6)
12. `tests/test_login_codigo_email.py` (6)
13. `tests/test_password_reset.py` (6)
14. `api/controllers/quiz_controller.py` (5)
15. `api/repositories/ai_job_repository.py` (5)

*(Demais 33 arquivos possuem de 1 a 5 ocorrências cada, incluindo `quiz_api.py` e `tests/visual/capture_baseline.py` com 5 cada.)*

### 3.2 `ruff format --check .`

- **Comando:** `ruff format --check .`
- **Código de saída:** `1`
- **Resultado:** **56 arquivos seriam reformatados**, **33 arquivos já estão formatados** (total de 89 arquivos Python verificados).
- **Distribuição dos 56 arquivos pendentes de formatação:**
  - `quiz_api.py` (1)
  - `api/`: 25 arquivos (`__init__.py`, `index.py`, `controllers/*`, `database/*`, `exceptions/*`, `handlers/*`, `middleware/*`, `models/*`, `repositories/*`, `services/*`, `utils/*`)
  - `scripts/`: 4 arquivos (`load_test_real_api.py`, `reset_admin.py`, `reset_database.py`, `reset_sessions.py`)
  - `tests/`: 26 arquivos (incluindo `tests/test_ui_contract.py`, `tests/test_pagina_inicio.py`, `tests/visual/capture_baseline.py` e demais suítes)

---

## 4. Baseline Visual e A11y (`tests/visual/capture_baseline.py`)

### 4.1 Funcionamento e matriz do script

Conforme inspeção direta de `tests/visual/capture_baseline.py`:
- **Motor:** Não utiliza Playwright; controla `msedge.exe` ou `chrome.exe` diretamente via **Chrome DevTools Protocol (CDP)** por HTTP (`http://127.0.0.1:<port>/json/list`) e `WebSocket` em biblioteca padrão.
- **Viewports emulados:** `desktop` (`1440x900`), `tablet` (`768x1024`), `mobile` (`390x844`, com `mobile=True` e `setTouchEmulationEnabled=True`).
- **Temas emulados:** `light` e `dark` via `Emulation.setEmulatedMedia` (`prefers-color-scheme`), além de `prefers-reduced-motion: reduce`.
- **Idiomas:** `pt-BR` (padrão; sem sufixo no nome do arquivo) e `en` (`--lang en`; sufixo `-en` no PNG), gravado em `localStorage['quiz_lang']`.
- **Telas cobertas (15 telas):** `login`, `register`, `reset-password`, `home-visitor` (`/app`), `home-access` (`/app` + clique `#addQuizBtn`), `home` (`/guest`), `home-catalog`, `home-upload`, `home-about`, `home-timer`, `produto`, `produto-menu`, `inicio` (`/`), `inicio-menu`, `login-codigo`.
- **Saída esperada:** `design-baseline/<label>/<tela>-<dispositivo>-<tema>[-en].png` → **90 PNGs por idioma** (**180 PNGs no total**).
- **Verificações automáticas por captura (`LAYOUT_CHECK`):**
  - `overflow = document.documentElement.scrollWidth - window.innerWidth` (`> 1px` conta como falha `LAYOUT`).
  - Em `vw < 600`, inspeciona `a[href], button, input, select, textarea, [role="button"]` visíveis (exceto `A` inline e checkboxes/radios/file/hidden) e emite `AVISO` para qualquer alvo com largura ou altura `< 44px`.

### 4.2 Execução real no ambiente atual e bloqueio observado

1. **Navegadores detectados na máquina:**
   - Edge: `C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe` (presente)
   - Chrome: `C:\Program Files\Google\Chrome\Application\chrome.exe` (presente)
2. **Tentativa de subir o servidor local (`quiz_api.py` na porta `8765`):**
   - **Exit code do servidor:** `1`
   - **Erro verbatim:**
     ```text
     [db] Erro ao executar migrations: connection to server at "localhost" (::1), port 5433 failed: Permission denied (0x0000271D/10013)
     connection to server at "localhost" (127.0.0.1), port 5433 failed: Permission denied (0x0000271D/10013)
     ```
3. **Tentativa de executar `capture_baseline.py`:**
   - **Comando:**
     ```powershell
     & "C:\Users\eduardo.asousa\AppData\Local\Python\pythoncore-3.14-64\python.exe" tests/visual/capture_baseline.py --label before --only inicio
     ```
   - **Exit code:** `1`
   - **Erro verbatim:**
     ```text
     RuntimeError: O navegador não abriu a porta de depuração a tempo
     ```
   - **Causa-raiz:** O sandbox de comandos bloqueia conexões TCP de saída em `127.0.0.1` (`WinError 10013`), impedindo tanto o `quiz_api.py` de conectar ao PostgreSQL local (`5433`) quanto o `capture_baseline.py` de consultar `http://127.0.0.1:<port>/json/list` e abrir o WebSocket CDP do Edge. Como a tentativa com `BypassSandbox=true` também expirou em 60s sem aprovação do usuário, **nenhuma captura PNG pôde ser gerada dentro deste sandbox**.
   - **Artefato em disco:** Apenas a pasta vazia `design-baseline\before\` criada por `out_dir.mkdir(...)` (ignorada pelo `.gitignore`, sem PNGs).

### 4.3 Tabela de cobertura visual planejada (`before`)

Todas as 180 combinações abaixo ficaram com status **`BLOQUEADO_SANDBOX`** (nenhum screenshot gerado; `overflow-x` e alvos `< 44px` em runtime pendentes de execução fora do sandbox):

| Tela (rota) | PT Desktop (Claro/Escuro) | PT Tablet (Claro/Escuro) | PT Celular (Claro/Escuro) | EN Desktop (Claro/Escuro) | EN Tablet (Claro/Escuro) | EN Celular (Claro/Escuro) | Caminho esperado (`design-baseline/before/`) |
|---|---|---|---|---|---|---|---|
| `login` (`/login`) | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | `login-{vp}-{tema}[-en].png` (12) |
| `register` (`/register`) | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | `register-{vp}-{tema}[-en].png` (12) |
| `reset-password` (`/reset-password`) | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | `reset-password-{vp}-{tema}[-en].png` (12) |
| `home-visitor` (`/app`) | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | `home-visitor-{vp}-{tema}[-en].png` (12) |
| `home-access` (`/app` modal) | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | `home-access-{vp}-{tema}[-en].png` (12) |
| `home` (`/guest`) | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | `home-{vp}-{tema}[-en].png` (12) |
| `home-catalog` (`/guest` modal) | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | `home-catalog-{vp}-{tema}[-en].png` (12) |
| `home-upload` (`/guest` modal) | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | `home-upload-{vp}-{tema}[-en].png` (12) |
| `home-about` (`/guest` modal) | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | `home-about-{vp}-{tema}[-en].png` (12) |
| `home-timer` (`/guest` modal) | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | `home-timer-{vp}-{tema}[-en].png` (12) |
| `produto` (`/produto`) | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | `produto-{vp}-{tema}[-en].png` (12) |
| `produto-menu` (`/produto` menu) | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | `produto-menu-{vp}-{tema}[-en].png` (12) |
| `inicio` (`/`) | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | `inicio-{vp}-{tema}[-en].png` (12) |
| `inicio-menu` (`/` menu) | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | `inicio-menu-{vp}-{tema}[-en].png` (12) |
| `login-codigo` (`/login` etapa 2) | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | BLOQUEADO_SANDBOX | `login-codigo-{vp}-{tema}[-en].png` (12) |

**Comandos para o operador executar fora do sandbox (antes de iniciar a Fase 3):**
```powershell
# Terminal 1 (servidor local)
$env:COOKIE_SECURE = "false"
python quiz_api.py

# Terminal 2 (captura PT e EN — gera 180 PNGs e imprime LAYOUT/AVISO de toque)
python tests/visual/capture_baseline.py --label before
python tests/visual/capture_baseline.py --label before --lang en
```

---

## 5. Auditoria Estática de A11y, Contraste, Layout e Desempenho (Baseline Atual)

Enquanto a captura visual em runtime ficou bloqueada pelo sandbox, a inspeção direta de `public/web/index.html`, `public/web/styles.css`, `public/web/inicio.css`, `public/web/modules/theme.js`, `public/web/modules/backdrop.js` e `public/web/app.js` levantou os seguintes dados objetivos de baseline:

### 5.1 Contraste WCAG 2.1 (tokens atuais vs alvo da Missão 1)

| Cenário / Par | Foreground | Background | Razão | AA Normal (≥ 4.5:1) | AA Grande (≥ 3.0:1) |
|---|---|---|---:|:---:|:---:|
| Claro atual: `--ink` sobre `--paper` | `#182326` | `#f4f0e8` | `14.13:1` | PASS | PASS |
| Claro atual: `--muted` sobre `--paper` | `#5b635e` | `#f4f0e8` | `5.45:1` | PASS | PASS |
| Claro atual: `--accent-text` sobre `--paper` | `#b23a20` | `#f4f0e8` | `5.25:1` | PASS | PASS |
| Claro atual: botão cheio `--coral` | `#ffffff` | `#c9462a` | `4.78:1` | PASS | PASS |
| Claro atual: botão `--teal` | `#ffffff` | `#176b67` | `6.30:1` | PASS | PASS |
| Escuro atual: `--ink` sobre `--paper` | `#d4d4d8` | `#181818` | `12.01:1` | PASS | PASS |
| Escuro atual: `--ink` sobre `--card-solid` | `#d4d4d8` | `#1F1F1F` | `11.15:1` | PASS | PASS |
| Escuro atual: `--muted` sobre `--paper` | `#9d9da8` | `#181818` | `6.61:1` | PASS | PASS |
| Escuro atual: `--accent-text` sobre `#181818` | `#8b93ff` | `#181818` | `6.52:1` | PASS | PASS |
| Escuro atual: botão `--coral` | `#ffffff` | `#4359ff` | `5.11:1` | PASS | PASS |
| Escuro atual: botão `--teal` | `#171717` | `#a78bfa` | `6.59:1` | PASS | PASS |
| **Alvo M1 (risco crítico): texto branco no coral** | `#FFFFFF` | `#FF7A5C` | **`2.56:1`** | **FAIL** | **FAIL** |
| **Alvo M1 (recomendado): texto preto no coral** | `#000000` | `#FF7A5C` | `8.19:1` | PASS | PASS |
| **Alvo M1 (recomendado): `#181818` no coral** | `#181818` | `#FF7A5C` | `6.93:1` | PASS | PASS |
| **Alvo M1: coral sobre superfícies escuras** | `#FF7A5C` | `#000000` / `#181818` / `#1F1F1F` | `8.19` / `6.93` / `6.43:1` | PASS | PASS |

> **Alerta de QA para Fase 2/3:** No tema escuro atual, `--btn-primary-text` é `#ffffff`. Se `--coral` for trocado para `#FF7A5C` sem trocar `--btn-primary-text` para `#000000` (ou `#181818`), **todos** os botões cheios primários (`#startBtn`, `#submit`, `.guest-action-link--primary`, `#accessRegisterLink`, `#confirmSubmitConfirm`) violarão WCAG AA (`2.56:1`).

### 5.2 Acessibilidade, Tema, WebGL e Alvos de Toque

- **Tema padrão atual (`public/web/modules/theme.js` + `theme-boot.js`):** O padrão sem preferência salva no `localStorage` é `'system'` (segue `prefers-color-scheme`), **não** `'dark'`. Além disso, `index.html:18` fixa `<meta name="theme-color" content="#0d3f3d">` no HTML estático antes do `theme.js` atualizar para `#171717` / `#f4f0e8`, e `theme.js` ainda usa `#171717` em vez de `#000000`/`#181818`.
- **Fundo WebGL (`public/web/modules/backdrop.js` + `public/web/app.js`):**
  - `backdrop.js` agenda criação via `requestIdleCallback` (`timeout: 1500`) após `load`, limita a `30 FPS`, `MAX_PIXEL_RATIO = 1.5`, rebaixa qualidade se `slowFrames > 20`, pausa quando `document.hidden` e mostra quadro parado em `prefers-reduced-motion: reduce`.
  - Contudo, `public/web/app.js` possui **0 referências** a `backdrop`: atualmente o WebGL **não é desligado** quando uma prova está em andamento.
- **Overflow e Movimento (`public/web/styles.css`):**
  - `html, body { overflow-x: clip; }` (linha 151) evita rolagem lateral sem quebrar `position: sticky`.
  - Tokens de motion já definidos: `--ease-out: cubic-bezier(0.22, 1, 0.36, 1)`, `--dur-fast: 200ms`, `--dur-base: 300ms`, `--dur-slow: 600ms`.
  - Há 9 blocos `@media (prefers-reduced-motion: ...)`.
  - `smooth-scroll.js` não é importado nem referenciado em `index.html` / `app.js`.
- **Alvos de toque no mobile (`public/web/styles.css`):**
  - Bloco `@media (max-width: 768px)` (linhas 3667–3679) garante `min-height: 44px` para `button`, `.btn-ghost`, `.palette-btn`, `.modal-close`, `.site-footer a`, `.guest-action-link`, etc.
  - **Pontos de atenção identificados:**
    1. `.visitor-actions .guest-action-link` tem `min-height: 36px` no desktop e só sobe para `44px` em `@media (max-width: 640px)` (linha 4133), deixando a faixa `641px–768px` em `36px` caso uma media query tenha precedência sobre a linha 3766.
    2. `.topic-chip` tem `min-height: 32px` no desktop e `44px` em `max-width: 768px` (linha 4253).
    3. `capture_baseline.py` checa alvos em `vw < 600` (viewport mobile `390x844`); cabe validar na Fase 3 se nenhum novo controle na nova barra superior ou sub-cabeçalho de `/app` cai abaixo de `44x44px` em `390px`.
- **Diálogos nativos:** `confirm()` e `prompt()` não são usados em `app.js`; `alert(message)` existe apenas como fallback defensivo caso `#noticeModal` não exista no DOM (`app.js:210`).

### 5.3 Inventário de Tamanho de Bundle (`public/web/`)

| Categoria | Arquivos | Tamanho bruto total | Principais arquivos |
|---|---:|---:|---|
| CSS (`.css`) | 3 | `173.550 bytes` (`169.5 KiB`) | `styles.css` (`122.5 KiB`), `inicio.css` (`27.0 KiB`), `produto.css` (`20.0 KiB`) |
| JS (`.js`) | 18 | `310.774 bytes` (`303.5 KiB`) | `app.js` (`109.4 KiB`), `i18n/en.js` (`60.6 KiB`), `backdrop.js` (`25.4 KiB`) |
| Fontes (`.woff2`) | 6 | `88.932 bytes` (`86.8 KiB`) | Manrope + DM Mono self-hosted |
| HTML (`.html`) | 8 | `139.595 bytes` (`136.3 KiB`) | `index.html` (`44.4 KiB`), `inicio.html` (`26.8 KiB`) |
| Ícones (`.svg`, `.png`) | 7 | `100.997 bytes` (`98.6 KiB`) | `favicon.svg` (`598 B`), PNGs og/icons (`98.0 KiB`) |

*(Versões `?v=` atuais em `index.html`: `styles.css?v=30`, `app.js?v=26`, `theme.js?v=9`, `i18n.js?v=10`, `backdrop.js?v=8`.)*

---

## 6. Estado do Repositório (`git status`)

Verificado após todas as execuções de testes, ruff e tentativa de captura visual:
- Branch: `develop` (alinhada a `origin/develop`)
- Arquivos modificados em código-fonte (`public/web/`, `api/`, `tests/`, `package.json`, `Dockerfile`, `docker-compose.yml`, `Procfile`, `vercel.json`): **0**
- Arquivos não rastreados existentes: `.claude/settings.local.json` e `docs/missoes/` (incluindo este `docs/missoes/m1/qa-baseline.md`). A pasta `design-baseline/` é ignorada pelo `.gitignore`.

---

## 7. Checklist de Critérios de Aceitação de QA para a Fase 2 / Fase 3

A Fase 3 só pode ser considerada concluída e aprovada para PR quando **todos** os portões abaixo forem atendidos e evidenciados:

### 7.1 Testes Automatizados e Contratos
- [ ] `python -m unittest tests/test_ui_contract.py tests/test_modulepreload.py` passando 100% (exit code `0`).
- [ ] `python -m unittest discover tests` executado fora do sandbox (com sockets habilitados): **0** erros de servidor/rotas (`test_pagina_inicio`, `test_guest_access`, `test_planos_limites`, `test_seguranca`, `test_auth_e2e`, etc.) e nenhuma nova falha introduzida em relação às 3 falhas pré-existentes documentadas na seção 2.2.
- [ ] Nenhum ID usado por `app.js` ou atributo `for`/`aria-labelledby`/`aria-describedby`/`aria-controls` quebrado; todos os textos visíveis novos/alterados com tradução idêntica em `public/web/modules/i18n/en.js` e `translate="no"` em nomes de simulados e questões.
- [ ] Versão `?v=` de `styles.css`, `app.js` (e módulos alterados) incrementada nos HTMLs; `?v=` de `i18n.js` mantido idêntico em todos os HTMLs (`test_single_i18n_version_everywhere`).

### 7.2 Lint e Formatação (`ruff`)
- [ ] Se a Fase 3 tocar apenas `public/web/` (e eventualmente `docs/`), **nenhuma nova violação** pode ser introduzida no `ruff check .` (mantendo ou reduzindo a contagem em relação às 237 atuais) nem no `ruff format --check .`.
- [ ] Qualquer arquivo `.py` alterado na Fase 3 (se houver) deve passar limpo com **0 erros** em `ruff check <arquivos>` e `ruff format --check <arquivos>`.

### 7.3 Captura Visual `before` vs `after` e Responsividade
- [ ] Baseline `before` capturado fora do sandbox antes de qualquer alteração visual (`--label before` em `pt-BR` e `--lang en`, totalizando 180 PNGs).
- [ ] Captura `after` executada ao final da Fase 3 (`python tests/visual/capture_baseline.py --label after` e `--lang en`), gerando os 180 PNGs equivalentes.
- [ ] **0 falhas `LAYOUT`** (`overflow-x <= 1px`) em todas as 180 combinações (`desktop 1440`, `tablet 768`, `mobile 390`; modos `light` e `dark`; `pt-BR` e `en`).
- [ ] **0 avisos `AVISO`** de alvos de toque `< 44x44px` no viewport mobile (`390x844`), incluindo barra superior global, sub-cabeçalho do simulado, seletores, paleta de questões e botões de modal.
- [ ] Inspeção visual comparativa `before` vs `after` confirmando: tema escuro padrão em `/app` (`#000000` / `#181818` / `#1F1F1F`), tema claro funcional no seletor, acento coral `#FF7A5C`, barra superior global + sub-cabeçalho legíveis sem sobreposição nem quebra em `390px`/`768px`/`1440px`.

### 7.4 Acessibilidade (WCAG AA) e Movimento
- [ ] **Contraste WCAG 2.1 AA:** ≥ `4.5:1` para texto normal e ≥ `3.0:1` para texto grande e componentes de interface nos temas escuro e claro — garantindo explicitamente **texto escuro (`#000000` ou `#181818`)** sobre fundos `#FF7A5C` (`8.19:1` / `6.93:1`), nunca `#FFFFFF` (`2.56:1`).
- [ ] **Navegação por teclado e foco visível:** Ordem lógica de `Tab` na barra superior global, sub-cabeçalho, opções de questão, paleta e modais; `focus-visible` visível nos dois temas; link "Pular para as questões" funcional; `Esc` fecha modais e devolve foco ao gatilho.
- [ ] **Movimento e `prefers-reduced-motion`:** Sem `smooth-scroll.js` em `/app`; transições com `--ease-out` (`cubic-bezier(0.22, 1, 0.36, 1)`), duração ≥ `200ms`, animando apenas `transform` e `opacity`; com `prefers-reduced-motion: reduce`, transições de movimento degradam para opacidade/estático.

### 7.5 WebGL, Console e Desempenho
- [ ] **Desligamento do WebGL durante a prova:** Com simulado em andamento (após iniciar / durante resolução de questões), o canvas WebGL (`backdrop.js`) deve estar pausado/oculto e o fundo permanecer chapado em `#000000` (no escuro), religando apenas fora da execução da prova (conforme regra da Fase 2).
- [ ] **Zero erros no console:** Nenhuma exceção não tratada (`pageerror`), `console.error` ou falha de rede CSP/404 ao carregar `/app`, `/guest`, `/login`, `/register`, `/produto` e `/` nos modos claro e escuro.
- [ ] **Sem regressão de bundle e Core Web Vitals:** Sem inclusão de bibliotecas externas ou CDNs (CSP `'self'` preservada); tamanho de `styles.css` e `app.js` mantido enxuto sem crescimento injustificado; zero CLS visível na transição de tema no boot (`theme-boot.js` atualizado para o novo padrão escuro sem FOUC claro→escuro).

---

## 8. Pós-Fase 3 — Verificação de QA, Novos Contratos e Baseline Visual (Fase 4)

- **Data da coleta pós-Fase 3:** `2026-11-18` (UTC)
- **Responsável:** Agente F (Fase 4 QA)
- **Arquivos criados/adaptados pelo QA:**
  - `tests/test_app_dashboard_contract.py` (criado e atualizado pós-revisão C): **13** novos testes cobrindo tema padrão escuro (`data-default-theme="dark"`, `#000000`, `THEMES = ['dark', 'light', 'system']`), remoção de `smooth-scroll.js` em `/app` (preservado em `/inicio`), arquitetura em 2 camadas (`.app-nav-wrap`/`.app-nav`/`#appMenuToggle` → `#appNavDrawer` + `.exam-panel` em `.hero` + `#timer` direto em `.timer-wrap`, zero IDs duplicados), barras com `scaleX`, ciclo WebGL (`setBackdropSuspended` + limpeza GL), `navigator.wakeLock` com `try/catch` e `visibilitychange`, `inert` em modais e Modo Foco, `translate="no"`, retorno de `closeResultModal()` para `'idle'` quando `!timerInterval && !running` (sem ficar preso em `'active'` por `.expired`), sincronia completa de `?v=` nos 9 HTMLs e módulos JS, cobertura das 21 chaves novas/normalizadas em `public/web/modules/i18n/en.js` (sem duplicatas nem `!`), tokens escuros (`#000000`, `#181818`, `#1F1F1F`, `#FF7A5C`, `--btn-primary-text: #000000`, `--accent-text: #FF8F75`), regra base `#timer` com `position: fixed;` e `z-index: var(--z-timer);` (compatível com `.timer--custom` de `timer-drag.js`, sem `position:`/`z-index:` em `#timer:not(.timer--custom)`) e alvos mobile `>= 44px` em `@media (max-width: 768px)` (incluindo `.catalog-tab-btn`, `.footer-link`, `.visitor-actions .guest-action-link`, `#timer`, etc.).
  - `tests/visual/capture_baseline.py` (adaptado): grava `localStorage.setItem('quiz_theme_preference', theme)` no início de cada iteração de tema (`light` / `dark`), limpa cookies e `quiz_guest_mode` antes de `/app` (`home-visitor` / `home-access`) e aguarda `#quiz .question` também em `/app`, garantindo captura fiel de claro e escuro com `data-default-theme="dark"` sem afetar `/` (estúdio escuro) nem `/produto`; também sanadas as 5 ocorrências pré-existentes de `ruff` e formatação do arquivo.

### 8.1 Resultados pós-Fase 3 no sandbox

| Verificação | Comando executado | Exit Code | Resultado observado |
|---|---|---:|---|
| Contratos de UI + modulepreload + dashboard `/app` | `& "C:\Users\eduardo.asousa\AppData\Local\Python\pythoncore-3.14-64\python.exe" -m unittest tests/test_ui_contract.py tests/test_modulepreload.py tests/test_app_dashboard_contract.py -v` | `0` | **19 / 19 OK** em `0.076s` (`4` de `test_ui_contract.py`, `2` de `test_modulepreload.py`, `13` de `test_app_dashboard_contract.py`) |
| Suíte completa (`E2E_PORT=8015`) | `$env:E2E_PORT = "8015"; & "C:\Users\eduardo.asousa\AppData\Local\Python\pythoncore-3.14-64\python.exe" -m unittest discover tests` | `1` | **403** testes em `38.484s`: **312 OK** (`+13` novos testes aprovados), **3 FAILs** (mesmos 3 pré-existentes: `test_banco_credenciais.py:43`, `test_prod_hardening.py:67`, `test_security_fixes.py:194`), **68 ERRORs** (mesmo bloqueio de socket loopback `WinError 10013` no sandbox em 67 testes HTTP + `setUpClass (test_auth_e2e.AuthE2ETestCase)`: `RuntimeError: Servidor nao respondeu em 10s na porta 8015.`), **20 skips** (`QUIZ_DB_INTEGRATION=1`) |
| Lint nos arquivos `.py` criados/editados | `& "C:\Users\eduardo.asousa\AppData\Local\Python\pythoncore-3.14-64\python.exe" -m ruff check tests/test_app_dashboard_contract.py tests/visual/capture_baseline.py` | `0` | `All checks passed!` (**0 violações**) |
| Formatação nos arquivos `.py` criados/editados | `& "C:\Users\eduardo.asousa\AppData\Local\Python\pythoncore-3.14-64\python.exe" -m ruff format --check tests/test_app_dashboard_contract.py tests/visual/capture_baseline.py` | `0` | `2 files already formatted` (**0 pendências**) |
| Lint global do repositório | `& "C:\Users\eduardo.asousa\AppData\Local\Python\pythoncore-3.14-64\python.exe" -m ruff check .` | `1` | **232 violações** (redução de `237` → `232` ao zerar os 5 alertas de `capture_baseline.py`; **0 novas violações**) |
| Formatação global do repositório | `& "C:\Users\eduardo.asousa\AppData\Local\Python\pythoncore-3.14-64\python.exe" -m ruff format --check .` | `1` | **55 arquivos** para reformatar, **40 arquivos** conformes (`56` → `55` pendentes; `33` → `40` conformes) |
| Captura visual `after` no sandbox | `& "C:\Users\eduardo.asousa\AppData\Local\Python\pythoncore-3.14-64\python.exe" tests/visual/capture_baseline.py --label after --base-url http://127.0.0.1:8010 --only home-visitor` | `1` | **BLOQUEADO_SANDBOX**: `RuntimeError: O navegador não abriu a porta de depuração a tempo` (sandbox bloqueia conexão TCP loopback ao CDP do Edge em `127.0.0.1`) |

### 8.2 Comandos exatos para execução final pelo operador fora do sandbox

Com o servidor local rodando em `http://127.0.0.1:8010` (ou subindo-o em um terminal separado):

```powershell
# 1. Capturas visuais pós-Fase 3 (PT e EN — 180 PNGs + checagem de overflow e toque < 44px)
& "C:\Users\eduardo.asousa\AppData\Local\Python\pythoncore-3.14-64\python.exe" tests/visual/capture_baseline.py --label after --base-url http://127.0.0.1:8010
& "C:\Users\eduardo.asousa\AppData\Local\Python\pythoncore-3.14-64\python.exe" tests/visual/capture_baseline.py --label after --lang en --base-url http://127.0.0.1:8010

# 2. Suíte completa com sockets liberados (E2E na porta 8015)
$env:E2E_PORT = "8015"
& "C:\Users\eduardo.asousa\AppData\Local\Python\pythoncore-3.14-64\python.exe" -m unittest discover tests
```

