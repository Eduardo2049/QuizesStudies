# Missão 1 — Plano Consolidado (Fase 2): Redesign de `/app` alinhado a `/`

- **Projeto:** Acely (`Eduardo2049/QuizesStudies`)
- **Branch base verificada:** `develop` (`e8853de`)
- **Branch oficial aprovada (Fase 3+):** `feature/quiz-visual-dashboard` *(alinhamento aprovado pelo usuário antes da Fase 3, substituindo o nome de rascunho `feature/m1-app-redesign`)*
- **Data da consolidação:** `2026-11-18`
- **Status:** **Aprovado para execução das Fases 3–5 na branch `feature/quiz-visual-dashboard`** (com inclusão aprovada do item opcional #9 `Screen Wake Lock` e baseline `before` coletado fora do sandbox). Nenhuma linha de código da aplicação foi modificada nas Fases 1 e 2.
- **Fontes consolidadas:**
  - Fase 1A — Pesquisa técnica e features: [`docs/missoes/m1/features.md`](features.md)
  - Fase 1B — Auditoria de Design e UX: [`docs/missoes/m1/design.md`](design.md)
  - Fase 1C — Arquitetura e contratos: [`docs/missoes/m1/arquitetura.md`](arquitetura.md)
  - Fase 1F — Baseline de QA, A11y e Desempenho: [`docs/missoes/m1/qa-baseline.md`](qa-baseline.md)
  - Normas do projeto: `AGENTS.md`, `docs/DESIGN_SKILLS.md`, `.claude/skills/landing-page-design/SKILL.md`, `docs/DESIGN_UPGRADE.md`, `docs/PLANO_ACELY.md`

---

## 1. Resumo Executivo e Decisões Formais (Pré-Fase 3)

Este plano cruza os quatro relatórios da Fase 1, resolve todas as divergências entre Design (B), Arquitetura (C), Features (A) e QA (F) e estabelece o roteiro fechado e executável para a **Fase 3** na branch `feature/quiz-visual-dashboard` (a partir de `develop`), somente após a aprovação deste documento e a coleta do baseline visual `before` fora do sandbox.

### 1.1 Consolidação das 5 Decisões R2 para `/app`

1. **Tema escuro padrão + claro opcional (Decisão R2.1):**
   - `/app` (`public/web/index.html`) passa a abrir no **tema escuro** quando não houver escolha prévia salva em `localStorage['quiz_theme_preference']`, sinalizado declarativamente por `<html lang="pt-BR" data-default-theme="dark">` e `<meta name="theme-color" content="#000000">`.
   - O seletor `#themeToggle` (`public/web/modules/theme.js`) preserva a chave `quiz_theme_preference` no `localStorage` e mantém os modos `'dark'`, `'light'` e `'system'` disponíveis. O `theme-boot.js` executa sincronamente no `<head>` para garantir zero flash claro (FOUC).
   - Superfícies escuras unificadas com `/`: fundo chapado `#000000`, superfície 1 `#181818`, superfície 2 `#1F1F1F`, bordas `#272727` e `#313131`, texto `#EDEDED` e `#9B9B9B`.
2. **Fundo WebGL `backdrop.js` desligado durante a prova (Decisão R2.2):**
   - `backdrop.js` permanece ativo apenas fora da prova em andamento (estado `'idle'`), com paleta calibrada sobre `#000000` sem azul/roxo genérico.
   - Ao iniciar a prova (estado `'active'`), `app.js` aciona `setBackdropSuspended(true)`: o loop `requestAnimationFrame` para (`0%` de uso de GPU/CPU), o `<canvas class="backdrop">` é ocultado (`opacity: 0` → `hidden`), o botão `#backdropMotionToggle` é ocultado e o fundo de estudo permanece **`#000000` chapado** (ou `#f4f0e8` no tema claro). O mesmo contexto WebGL é reutilizado ao retornar ao estado `'idle'`, sem vazar memória nem esgotar o limite de contextos do navegador.
3. **Acento coral `#FF7A5C` unificado com contraste WCAG AA/AAA (Decisão R2.3):**
   - No tema escuro de `/app`, `--coral` deixa de ser `#4359ff` (azul) e passa para **`#FF7A5C`** (hover `#FF8F75`), com **`--btn-primary-text: #000000`** (`8,19:1` AAA; evita o erro crítico de `#FFFFFF` sobre `#FF7A5C` que daria `2,56:1`).
   - O alias legado `--teal` deixa de ser `#a78bfa` (roxo) no escuro e passa a mapear para `#FF7A5C` (foco, seleção e destaques ativos), enquanto botões secundários (`#btnOpenCatalog`, `#addQuizBtn`) usam contorno neutro limpo, garantindo **1 único CTA principal cheio por tela**.
   - No tema claro opcional (`[data-theme="light"]`), preservam-se `--coral: #c9462a` com `#ffffff` (`4,83:1` AA), `--accent-text: #b23a20` (`5,24:1` AA) e `--teal: #176b67` (`5,63:1` AA).
4. **Navegação em duas camadas (Decisão R2.4):**
   - **Camada 1 — Barra Superior Global Flutuante e Translúcida (`.app-nav-wrap` / `.app-nav`):** fixa no topo (`rgba(24, 24, 24, 0.72)` + `backdrop-filter: blur(16px)` + `border: 1px solid #272727` + `radius: 16px`), contendo retorno à marca `<a href="/" class="app-brand">`, navegação global (`Início`, `Planos` `#plansLink`, `Por que o Acely?` `#btnOpenAboutModal`), utilitários (`#langToggle`, `#themeToggle`, `#backdropMotionToggle`) e conta (`#authControls`).
   - **Camada 2 — Painel de Controle do Simulado (`.exam-panel` dentro de `<header class="hero">`):** superfície `#181818`, borda `#272727`, abrigando título enxuto, seletor de questionário (`#customQuizSelectorWrap`, `#btnOpenCatalog`, `#addQuizBtn`), comando da prova (`#startBtn`, `#btnSetTimer`), progresso (`#progress`, `#percent`, `#progressBar`), barra Foco/Lista (`#examToolbar`, `#btnQuickSubmit`) e paleta (`#questionPalette`).
5. **Movimento nativo e disciplinado (Decisão R2.5):**
   - **Zero `smooth-scroll.js` em `/app`**: rolagem nativa do navegador, protegida por `scroll-padding-top` e `scroll-margin-top` sob a Camada 1 fixa.
   - Animações e transições restritas a `transform` e `opacity` (mais transições de cor de estado), sempre com `--ease-out: cubic-bezier(0.22, 1, 0.36, 1)` e duração `>= 200ms` (`--dur-fast: 200ms`, `--dur-base: 300ms`, `--dur-layout: 500ms`, `--dur-slow: 600ms`), incluindo conversão de `#progressBar` e `.section-progress-fill` de `width` para `transform: scaleX(...)` e respeito estrito a `prefers-reduced-motion: reduce`.

### 1.2 Decisão Formal sobre Tokens Compartilhados em `/` (`inicio.html` / `inicio.css`)

**Decisão (convergência entre B e C):** **Manter `/` (`public/web/inicio.css`, `public/web/modules/inicio.js`, `smooth-scroll.js` e `mural.js` + conteúdo/estrutura de `public/web/inicio.html`) intacta na Missão 1**, consolidando todos os tokens canônicos diretamente em `public/web/styles.css`.

- **Por que não extrair `tokens.css` agora:**
  1. `inicio.html:36-37` já importa `/web/styles.css?v=30` antes de `/web/inicio.css?v=1` e já consome `--font-sans`, `--font-mono`, `--text-xs..md`, `--space-1..6`, `--radius-sm..lg` e `--ease-out` de `styles.css`.
  2. Criar um arquivo `tokens.css` separado adicionaria **+1 requisição CSS bloqueante de renderização** no `<head>` de todas as 9 páginas (prejudicando FCP/LCP) e exigiria reauditar a precedência de cascata em `inicio.css` e `produto.css`.
- **Regras obrigatórias de proteção a `/` e `/produto`:**
  1. **Preservação de nomes em `:root` de `styles.css`:** manter intactos `--font-sans`, `--font-mono`, `--text-xs` (`12px`), `--text-sm` (`14px`), `--text-md` (`16px`), `--space-1..6`, `--radius-sm..lg` e `--ease-out`, apenas adicionando os degraus faltantes (`--space-0`, `--space-05`, `--space-7..11`, `--radius-xl`, `--radius-pill`, `--text-xl..5xl`, `--dur-layout`) e corrigindo `--text-lg` (`19px` → `18px`).
  2. **Escopo estrito:** todas as regras novas de cabeçalho flutuante, drawer mobile, painel do simulado e botões de `/app` devem ser escopadas em `.app-nav*`, `.app-menu*`, `.exam-panel`, `.timer-dock` — nunca alterar seletores globais genéricos (`body`, `header`, `nav`, `h1`, `h2`) sem escopo, para não vazar para `.in-body` ou `produto.css`.
  3. **Regra de `?v=` de `styles.css` em `inicio.html`:** quando `styles.css` subir de `?v=30` para `?v=31`, atualizar **apenas** a query string `<link rel="stylesheet" href="/web/styles.css?v=31">` em **todos os 9 HTMLs** (incluindo `inicio.html`), mantendo o restante de `inicio.html` intocado e validando no baseline `after` (`--only inicio,inicio-menu`) que `/` permanece visualmente idêntica. *(Observação: uma extração futura de `tokens.css` fica registrada como melhoria opcional caso `/` ganhe tema claro em missão própria.)*

### 1.3 Registro Obrigatório do `Dockerfile` (Sem Alterar)

- **Evidência verificada na branch `develop` (`e8853de`):** `Dockerfile`, linhas 3 e 17, utiliza nos dois estágios (`builder` e `runtime`):
  `FROM python:3.16.0a1-slim@sha256:df293ba3b89f458e1aad6051b62ff1c4fad7b3b52b8147ae9cc4b667f9cf2741`
- **Ação na Missão 1:** **Nenhuma alteração** no `Dockerfile` (proibição explícita de R1.C e R3).
- **Recomendação formal:** Abrir tarefa e branch dedicadas fora desta missão (ex.: `chore/dockerfile-python-3.15`) para retornar ambos os estágios do `Dockerfile` para a série estável **`python:3.15-slim`** com digest `@sha256` atualizado, eliminando o risco de versão *alpha* (`3.16.0a1`) em build de extensões C (`psycopg2-binary`), ABI instável e ausência de patches de segurança.

---

## 2. Matriz de Resolução de Conflitos (Design B × Arquitetura C × Features A × QA F)

### Conflito 1 — Hierarquia de `z-index` e Posicionamento de `#timer` vs `timer-drag.js`

| Posições em conflito | Decisão única consolidada |
|---|---|
| **B** listou `--z-timer: 10` e `--z-nav: 50`, sugerindo `.timer-dock` no painel da Camada 2 (ou `top: 84px` no desktop).<br>**C** definiu `--z-global-nav: 40`, `--z-timer: 50`, `--z-timer-handle: 51`, `--z-overlay: 100`, `--z-skip: 101`, mantendo `#timer` `position: fixed` direto em `.timer-wrap` (`display: contents`) abaixo da Camada 1 (`top: ~88px`) para não quebrar `timer-drag.js`. | **Adotar a hierarquia de `z-index` de C + `#timer` `position: fixed` abaixo da Camada 1 (sem `.timer-dock` no fluxo).** |

- **Especificação técnica e justificativa:**
  1. **Escala canônica de `z-index` em `:root`:**
     - `.backdrop`: `-1`
     - `.shell`, `.exam-panel`, `.quiz`, `.question`: `auto` (`0`, proibido `overflow: hidden` ou `transform` permanente em `.exam-panel` para não aprisionar `#customQuizDropdown`)
     - `--z-sticky-nav: 20` (`.focus-navigation`)
     - `--z-dropdown: 30` (`.custom-select-dropdown`)
     - `--z-global-nav: 40` (`.app-nav-wrap` e `.app-nav-drawer` mobile)
     - `--z-timer: 50` (`#timer`, `#timerConfig`)
     - `--z-timer-handle: 51` (`.timer-resize-handle`)
     - `--z-overlay: 100` (`.modal-overlay`)
     - `--z-skip: 101` (`.skip-link`)
  2. **Por que `#timer:not(.timer--custom)` fica `position: fixed` em `top: calc(var(--app-nav-height, 64px) + var(--space-5)); right: var(--space-5);` (em vez de `.timer-dock`):**
     - `timer-drag.js:43` injeta `timer.after(handle)` e `styles.css:3831` depende de `#timer:not(.running):not(.expired) + .timer-resize-handle { display: none; }`.
     - `timer-drag.js:119-124` (`detach()`) lê `getBoundingClientRect()` e passa a gravar `style.left`/`style.top` em coordenadas de viewport, esperando `#timer` com `position: fixed` (sem ancestral com `transform`/`contain`).
     - Com `--z-timer: 50 > --z-global-nav: 40`, quando o usuário arrasta o cronômetro, ele passa acima da barra global em vez de desaparecer atrás dela.
  3. **Ajustes obrigatórios associados:**
     - Remover `body:has(#timer.running) .hero-utils { margin-right: 92px; }` (`styles.css:3581-3584`) e sua exceção `3864-3867`, pois `#timer` não colide mais com a Camada 1.
     - Atualizar `top` de `#timerConfig` (`styles.css:483`) de `56px` para `calc(var(--app-nav-height, 64px) + var(--space-5) + 46px)` para abrir imediatamente abaixo do `#timer` quando não arrastado.
     - No mobile (`<= 768px`), garantir `min-height: 44px; min-width: 72px; display: inline-flex; align-items: center; justify-content: center;` em `#timer` (corrigindo a altura atual de ~28px apontada por B) e manter `.timer-resize-handle` em `z-index: calc(var(--z-timer) + 1)` (`51`, abaixo de `--z-overlay: 100`) com `44×44px`.

---

### Conflito 2 — Menu Mobile, `#authControls` Único (Sem Duplicar IDs) e Alvos de Toque `< 44px`

| Posições em conflito | Decisão única consolidada |
|---|---|
| **B** especificou drawer full-height `.app-menu` no celular (`<= 768px`) com links e `#authControls`, apontando falhas de toque em `.footer-link` (`32px`), `#timer` (`~28px`), `.file-preview-remove` e `.btn-auth-logout`.<br>**C** alertou que `tests/test_ui_contract.py::test_ids_are_unique_per_page` falha se qualquer `id="..."` for duplicado entre barra desktop e menu mobile.<br>**F** detectou que `.visitor-actions .guest-action-link` cai para `36px` na faixa `641px–768px`. | **Usar um único contêiner DOM `#appNavDrawer` com `display: contents` no desktop (`>= 769px`) e drawer expansível no mobile (`<= 768px`), zerando duplicação de IDs e padronizando alvos `>= 44×44px` em `<= 768px`.** |

- **Especificação técnica e justificativa:**
  1. **Estrutura DOM única na Camada 1 (`index.html`):**
     ```html
     <header class="app-nav-wrap">
       <nav class="app-nav" aria-label="Principal">
         <a href="/" class="app-brand" title="Voltar para a página inicial">
           <img src="/web/icons/favicon.svg?v=3" alt="" class="hero-brand-icon" width="22" height="22" aria-hidden="true">
           <span translate="no">Acely</span>
         </a>
         <div class="app-nav-quick">
           <button id="langToggle" ...>...</button>
           <button id="themeToggle" ...>...</button>
           <button type="button" id="appMenuToggle" class="app-menu-toggle" aria-expanded="false" aria-controls="appNavDrawer" aria-label="Abrir menu">...</button>
         </div>
         <div id="appNavDrawer" class="app-nav-drawer">
           <div class="app-nav-links">
             <a href="/" class="app-nav-link">Início</a>
             <a href="/planos" id="plansLink" ...>Planos</a>
             <button id="btnOpenAboutModal" ...>Por que o Acely?</button>
           </div>
           <div class="app-nav-tools">
             <button id="backdropMotionToggle" ... hidden>...</button>
             <div id="authControls" class="auth-controls">...</div>
           </div>
         </div>
       </nav>
     </header>
     ```
  2. **Comportamento por breakpoint (zero clonagem de nós, zero JS de movimentação de DOM):**
     - **Desktop (`>= 981px`) e Tablet largo (`769px–980px`):** `.app-nav-drawer { display: contents; }` (seus filhos participam diretamente do `display: flex; align-items: center;` da `.app-nav`, mantendo `#langToggle` e `#themeToggle` alinhados junto a `#backdropMotionToggle` e `#authControls` via `order` CSS); `#appMenuToggle` fica `display: none`.
     - **Celular (`<= 768px`):** `.app-nav` exibe em linha única `<a href="/" class="app-brand">` à esquerda e `#langToggle` + `#themeToggle` + `#appMenuToggle` à direita (todos `>= 44×44px`). Ao abrir `#appMenuToggle`, `#appNavDrawer` exibe painel translúcido (`var(--nav-menu-bg)` + `blur(24px)`) com `Início`, `Planos`, `Por que o Acely?`, `#backdropMotionToggle` (quando fora de prova) e `#authControls` empilhados com `min-height: 44px`. `Escape`, clique fora ou navegação fecha o drawer e devolve o foco para `#appMenuToggle`; `shortcuts.js` ignora atalhos enquanto `#appNavDrawer.is-open` estiver aberto.
     - *Garantia de contrato:* `#appMenuToggle` aponta `aria-controls="appNavDrawer"` (ID existente em `index.html`, passando `test_accessibility_references_point_to_real_elements`), nenhum ID é repetido (`test_ids_are_unique_per_page`), e `tests/test_pagina_produto.py:181` continua encontrando `<a href="/planos" id="plansLink"` em `index.html`.
  3. **Correção completa de alvos de toque `< 44px` (`@media (max-width: 768px)`):**
     - Corrigir a cascata de `.footer-link` (`styles.css:4178`) aplicando `min-height: 44px; min-width: 44px; display: inline-flex; align-items: center;` em `@media (max-width: 768px)` **após** a declaração base.
     - Corrigir `.visitor-actions .guest-action-link` (`styles.css:4133`) para `min-height: 44px` já em `@media (max-width: 768px)` (cobrindo `641px–768px` e `<= 640px`).
     - Garantir `min-height: 44px; min-width: 44px` em `<= 768px` para: `#timer`, `.file-preview-remove`, `.btn-auth-logout`, `.topic-chip`, `.palette-btn`, `.app-brand`, `.app-menu-toggle`, `#langToggle`, `#themeToggle`, `.app-nav-link`, `.modal-close` e `.catalog-tab-btn`.

---

### Conflito 3 — Gatilho Exato de Suspensão do WebGL (`backdrop.js`)

| Posições em conflito | Decisão única consolidada |
|---|---|
| **B** recomendou manter a prévia imediata de questões no carregamento (`idle`) e suspender o WebGL quando a prova inicia (`startTimer()` ou 1ª resposta), mantendo `--backdrop-calm` contido no lobby.<br>**C** listou os gatilhos concretos no código (`startTimer()`, `FormData(quiz)` não vazio, catálogo) e deixou em aberto na Fase 2 se haveria lobby sem questões visíveis ou disparo na ação de prova. | **Preservar o carregamento imediato das questões sem etapa extra de bloqueio; controlar `backdrop.js` via máquina de estados `examState = 'idle' | 'active' | 'results'` em `app.js` + `setBackdropSuspended(boolean)` sem destruir o contexto WebGL.** |

- **Especificação exata de transições de estado:**
  1. **Estado `'idle'` → `setBackdropSuspended(false)` (WebGL ativo no lobby/repouso):**
     - Ao abrir `/app` (`loadInitialQuiz()`), antes de iniciar o timer e com nenhuma resposta marcada;
     - Ao clicar em `#reset` (`app.js:1205`) ou `#btnRedoQuiz` (`app.js:1216`);
     - Ao trocar de simulado em `#quizSelector` (`change` em `app.js:1466`);
     - Ao carregar o **Caderno de erros** (`#btnTrainMistakes`) ou **Variações IA** (`#btnRemixMistakes`) até que o aluno clique em `Iniciar simulado` ou marque a primeira alternativa;
     - Ao fechar `#resultModal` após conclusão da prova (`!timerInterval && !timer.classList.contains('running')`), permitindo que o lobby respire novamente em repouso.
  2. **Estado `'active'` → `setBackdropSuspended(true)` (WebGL suspenso, fundo `#000000` chapado, `#backdropMotionToggle` oculto):**
     - Clique em `#startBtn` (`app.js:1199`);
     - Marcação da primeira alternativa (`quiz.addEventListener('change', ...)` em `app.js:1454`, que já aciona `startTimer()`);
     - Seleção de simulado no `#catalogList` (`app.js:1444`, que já inicia imediatamente via `startTimer()`);
     - Qualquer chamada a `startTimer()` ou estado em que `timer.classList.contains('running') || timer.classList.contains('expired')` (mantendo o WebGL desligado caso o tempo expire enquanto o aluno ainda lê as questões).
  3. **Estado `'results'` (`handleSubmitQuiz()` abre `#resultModal`):**
     - Mantém `setBackdropSuspended(true)` enquanto o modal de resultado está aberto (evita renderização WebGL desperdiçada atrás do overlay) e retorna a `'idle'` ao fechar o modal ou resetar.
- **Mecanismo interno em `backdrop.js` (anti-leak de WebGL):**
  - Exportar `setBackdropSuspended(suspended: boolean)` (também sincronizando `document.body.dataset.examState`).
  - Quando `suspended === true`: cancelar `rafId` (`stopLoop()`), remover `.is-running`, agendar `canvas.hidden = true` após `transitionend` (ou imediato se `prefers-reduced-motion`; cancelar timeout caso retome antes), pausar processamento de `pointermove`/`resize` e ocultar `[data-backdrop-toggle]`.
  - Quando `suspended === false`: se `instance` ainda não existir (caso o usuário tenha iniciado a prova antes do `requestIdleCallback`), inicializar sob demanda; exibir `canvas.hidden = false`, executar `readPalette()` + `resize()`, reexibir `[data-backdrop-toggle]`, aplicar `.is-running` e retomar `requestAnimationFrame` se `motionEnabled() && !document.hidden`.
  - No `destroy()` definitivo da página, desalocar explicitamente `gl.deleteTexture`, `gl.deleteFramebuffer`, `gl.deleteBuffer` e `gl.deleteProgram`.

---

### Conflito 4 — Tokens Cromáticos, Contraste WCAG AA/AAA e Papel de `--teal` / `--backdrop-*`

| Posições em conflito | Decisão única consolidada |
|---|---|
| **B** propôs `--accent-text: #FF8F75` (7,41:1 em `#1F1F1F`), `--line-interactive: #525252`/`#6B6B6B` (WCAG 1.4.11) e `--backdrop-base: #000000` / `#272727` / `#FF7A5C`.<br>**C** propôs `--accent-text: #FF7A5C` (6,43:1 em `#1F1F1F`) e `--backdrop-a: #7a2e1f` / `--backdrop-b: #2b1f24`. | **Adotar `--accent-text: #FF8F75` (proposta B), `--btn-primary-text: #000000`, `--line-interactive`, remapeamento de `--teal` para coral `#FF7A5C` e `--backdrop-*` coral queimado/grafite sem azul/roxo.** |

- **Tabela canônica de tokens cromáticos de `/app` (`[data-theme="dark"]` padrão vs `[data-theme="light"]` opcional):**

| Token | `[data-theme="dark"]` (Padrão) | `[data-theme="light"]` (Opcional) | Regra de contraste / uso |
|---|---|---|---|
| `--paper` / `--bg-gradient` | `#000000` / `#000000` | `#f4f0e8` / gradiente claro atual | Fundo chapado `#000000` no escuro durante prova e base |
| `--surface` / `--card-solid` | `#181818` | `#ffffff` | Barra flutuante, `.exam-panel`, `.question`, modais |
| `--surface-2` / `--card-bg` | `#1F1F1F` / `rgba(24, 24, 24, 0.90)` | `#ffffff` / `rgba(255, 255, 255, 0.85)` | Sub-cards, dropdowns, opções, estatísticas |
| `--nav-bg` / `--nav-menu-bg` | `rgba(24, 24, 24, 0.72)` / `rgba(0, 0, 0, 0.94)` | `rgba(244, 240, 232, 0.82)` / `rgba(244, 240, 232, 0.96)` | Camada 1 translúcida com fallback sólido `@supports not` |
| `--ink` / `--muted` | `#EDEDED` / `#9B9B9B` | `#182326` / `#5b635e` | `#EDEDED` = 17,9:1 (`#000`) / 15,2:1 (`#181818`); `#9B9B9B` = 7,56:1 / 6,39:1 |
| `--line` / `--line-strong` | `#272727` / `#313131` | `#d8d0c3` / `#c5bbb0` | Bordas estruturais inteiras (sem `border-left` isolado) |
| `--line-interactive` | `#525252` (`#6B6B6B` em inputs isolados) | `#9aa09c` | Discernibilidade WCAG 1.4.11 em inputs e botões contorno |
| `--coral` / `--coral-dark` | `#FF7A5C` / `#FF8F75` | `#c9462a` / `#a8341b` | Acento único da marca (`--coral-rgb: 255, 122, 92`) |
| `--btn-primary-text` | `#000000` (**obrigatório: 8,19:1 AAA**) | `#ffffff` (`4,83:1` AA) | **Proibido `#FFFFFF` sobre `#FF7A5C` (`2,56:1` FAIL)** |
| `--accent-text` | `#FF8F75` (`7,41:1` sobre `#1F1F1F`; `>6,1:1` em pills) | `#b23a20` (`5,24:1`) | Texto pequeno em destaque (ex.: `.results-percent`, links) |
| `--teal` / `--teal-dark` / `--teal-rgb` | `#FF7A5C` / `#FF8F75` / `255, 122, 92` | `#176b67` / `#0f4e4b` / `23, 107, 103` | Elimina roxo `#a78bfa`; `--btn-teal-text: #000000` |
| `--btn-add-*` / `--btn-catalog-*` | Fundo `transparent`, borda `var(--line-interactive)`, texto `var(--ink)`, hover `var(--surface-2)` | Fundo `transparent`, borda `var(--teal)`, texto `var(--teal)`, hover `rgba(23,107,103,0.08)` | Mantém **1 CTA cheio por tela** nos dois temas (`DESIGN_SKILLS.md` §3.1) |
| `--option-bg` / `--option-hover` / `--option-checked` | `#1F1F1F` / `#272727` / `rgba(255, 122, 92, 0.14)` | `rgba(255,255,255,0.75)` / `#ffffff` / `#dcebe5` | Alternativa marcada usa borda inteira `1px solid var(--coral)` |
| `--input-bg` / `--input-border` | `#121212` / `#525252` (foco `--coral`) | `#ffffff` / `#9aa09c` (foco `--teal`) | Inputs com borda visível >= 3:1 |
| `--line-focus` / `--focus-ring` | `#FF7A5C` / `rgba(255, 122, 92, 0.28)` | `#176b67` / `rgba(23, 107, 103, 0.18)` | Foco visível unificado em `:focus-visible` |
| `--orange` / `--btn-orange-text` | `#f2b866` / `#000000` (`11,76:1`) | `#d97706` / `#ffffff` | Botão `.btn-mistakes` com alto contraste |
| `--backdrop-*` | `base: #000000`, `a: #3D1D17`, `b: #8F3724`, `line: #FF7A5C`, `mix: 0.30`, `calm: 0.28`, `calm-b: 0.18` | `base: #f4f0e8`, `a: #8ee8d4`, `b: #ffa647`, `line: #176b67` | WebGL do lobby alinhado ao coral/preto com corredor central AAA |

---

### Conflito 5 — `#progressBar`, `.section-progress-fill`, Escala Tipográfica, `border-left` e Motion

| Posições em conflito | Decisão única consolidada |
|---|---|
| **C** inicialmente tratou `width` em `#progressBar` como exceção possível.<br>**B** exigiu `transform: scaleX()` em `#progressBar` e `.section-progress-fill`, além de correções em `--text-lg` (`19px` → `18px`), `h1` (`<= 72px/48px`), `.comparison-table td` (`>= 12px`), remoção de `border-left` isolados, `authFadeIn` (`180ms` → `200ms`), `scrollIntoView` com `prefers-reduced-motion`, ícones SVG no lugar de símbolos unicode e `translate="no"` em questões/simulados. | **Aprovar todas as correções de B (com o ajuste mínimo em `app.js` para `scaleX()` e `getScrollBehavior()`), cumprindo 100% da regra `B7` (`transform`/`opacity` apenas) e `B1`/`B4`/`B8`.** |

- **Lista fechada de correções consolidadas:**
  1. **`#progressBar` e `.section-progress-fill`:** definir `width: 100%; transform-origin: left center; transform: scaleX(0); transition: transform var(--dur-base) var(--ease-out);` em `styles.css` e atualizar `app.js:981` (`progressBar.style.transform = \`scaleX(\${value / 100})\``) e `app.js:1143` (`el.style.transform = \`scaleX(\${pct / 100})\``). Compatível com CSP `'self'` (CSSOM).
  2. **Escala tipográfica estrita (`B1`):**
     - Corrigir `--text-lg` de `19px` para `18px` (`--leading-lg: 28px`) em `:root`.
     - Completar `--text-xl` (`20px`) até `--text-5xl` (`48px`), ajustando `h1` de `/app` para `36px` (mobile) / `48px` (desktop) — eliminando `90px`.
     - Subir `.comparison-table td` no mobile de `11.5px` para `12px` (`--text-xs`).
     - Remover `text-transform: uppercase` dos rótulos de UI em `styles.css` (linhas `238, 448, 573, 1021, 1414, 2030, 2175, 2307, 2493, 2511`), mantendo `font-style: normal` e peso `<= 700` em toda a interface, e restringindo `DM Mono` a valores numéricos.
  3. **Bordas e superfícies chapadas (`B4`):**
     - Remover `border-left` isolado (e `box-shadow: inset 4px 0 0` unilateral) de `.option:has(input:checked)`, `.result-card`, `.result-card-explanation`, `.confirm-submit-warning`, `.results-badge` e `.comparison-table .highlight-col`, substituindo por borda inteira `1px solid` com tint semântico sutil.
  4. **Motion e `prefers-reduced-motion` (`B7`, `R2.5`):**
     - Elevar `.auth-form-card` (`styles.css:1205`) de `0.18s ease-out` para `200ms var(--ease-out)`.
     - Normalizar `fadeIn`, `slideUp`, `optionPulse`, `fadeInFocus` de `ease` para `var(--ease-out)` (`>= 200ms`).
     - Substituir `.upload-skeleton span` de `background-position` para pulso de `opacity`.
     - Em `@media (prefers-reduced-motion: reduce)`, remover o `transition-duration: 0.01ms !important` global (`styles.css:3495`), anulando apenas deslocamentos (`transform: none !important`, `animation: none`) e mantendo transições suaves de `opacity` (`300ms var(--ease-out)`).
     - Em `app.js`, criar `getScrollBehavior()` (`window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'`) e aplicá-lo nas 7 chamadas de `scrollIntoView` + `window.scrollTo`.
  5. **Ícones SVG inline e `translate="no"`:**
     - Substituir símbolos textuais soltos (`▶`, `↺`, `↻`, `✓`, `✗`, `▾`, `←`, `→` onde aplicável em botões) por SVGs de `icons.js` (mantendo setas textuais apenas onde fazem parte de chave existente de `en.js`, ou atualizando `en.js` em conjunto — ver Seção 3.3).
     - Adicionar `translate="no"` em `renderQuestions()` (`.section`, `.context`, `.question-head h2`, `.option span`), `renderCustomQuizOptions()` / `#customQuizValue` (apenas no `item.label`), `.catalog-card-title` e nos textos da questão/resposta/explicação em `renderResultModal()`, preservando os rótulos de UI traduzíveis.

---

### Conflito 6 — Curadoria dos 12 Itens de `features.md` e Decisão sobre `@layer`

| Posições em conflito | Decisão única consolidada |
|---|---|
| **A** ranqueou 12 features oficiais, incluindo `@layer` (#10), `@container` (#11) e `popover="auto"` (#12).<br>**C** e **B** alertaram que `styles.css` (4.439 linhas) é carregado por `/` (`inicio.css`), `/produto` (`produto.css`) e auth/legais, e que `timer-drag.js` + `app.js` gerenciam `#timerConfig` e `#customQuizDropdown`. | **Adotar 8 itens imediatos (#1 a #8) na Fase 3, incluir #9 (`Wake Lock`) apenas como opcional isolado se aprovado pelo humano, e ADIAR #10 (`@layer`), #11 (`@container`) e #12 (`popover="auto"`) para missão própria pós-M1.** |

- **Classificação consolidada e justificativa técnica:**

| Item (`features.md`) | Decisão na Fase 3 | Justificativa técnica |
|---|---|---|
| **#1 `color-scheme` + `color-mix()`** | **ENTRA** | Baixíssimo risco; alinha `<select>`, `<input>` e derivação de estados tintados a partir de `#FF7A5C`. |
| **#2 `scroll-padding-top` + `scroll-margin-top`** | **ENTRA (Obrigatório)** | Exigido pela WCAG 2.2 SC 2.4.11 para `.skip-link` e `scrollIntoView` sob a Camada 1 fixa. |
| **#3 `dvh` + `overscroll-behavior: contain` + `scrollbar-gutter: stable`** | **ENTRA** | Evita corte de modais no iOS/Android (`100dvh` com fallback `100vh`), scroll chaining e pulo lateral entre Modo Foco e Lista. |
| **#4 `backdrop-filter` só na Camada 1 + `@supports`** | **ENTRA** | Implementa a barra global translúcida da Decisão R2.4 com fallback sólido `#181818` / `#f4f0e8`. |
| **#5 Atributo HTML `inert`** | **ENTRA** | Reforça `trapFocus()` em `<main>`/`<footer>` durante modais e nos cards ocultos do Modo Foco; garante remoção determinística em todos os fechamentos. |
| **#6 `content-visibility: auto` + `contain-intrinsic-size`** | **ENTRA** | Ganho direto de renderização/INP em simulados de 30 questões (`.question`), `#catalogList` e `#resultQuestionsList`, sem tocar no DOM. |
| **#7 Seletor `:has()` declarativo** | **ENTRA** | Estende o padrão já existente em `styles.css:167` para `.option:has(input:checked)` e estados visuais declarativos. |
| **#8 `text-wrap: balance` / `pretty` + alvos `>= 44px`** | **ENTRA** | Cumpre `B1` (`DESIGN_SKILLS.md`) e WCAG 2.2 SC 2.5.8 no mobile (`<= 768px`). |
| **#9 Screen Wake Lock (`navigator.wakeLock`)** | **OPCIONAL (Aprovar)** | Seguro e isolado no controlador `examState === 'active'` (`try/catch` + `visibilitychange`). Entra no Passo 3 somente se aprovado pelo usuário nesta parada. |
| **#10 CSS Cascade Layers (`@layer`)** | **ADIADO** | **Risco alto de cascata cruzada:** em CSS, estilos sem `@layer` (`inicio.css`, `produto.css`) vencem estilos dentro de `@layer`. Refatorar `styles.css` (4.439 linhas) para `@layer` exige reauditar todas as 9 páginas fora do escopo da Missão 1. Escopo próprio com `.app-*`/`.exam-panel` resolve o isolamento com risco zero. |
| **#11 CSS Container Queries (`@container`)** | **ADIADO** | `container-type: inline-size` cria contenção de layout e stacking context que pode prender `#customQuizDropdown` ou alterar largura intrínseca de barras. Media queries existentes atendem todos os breakpoints da M1. |
| **#12 Popover API (`popover="auto"`)** | **ADIADO** | `#timerConfig` depende de posicionamento calculado por `timer-drag.js:72-86` e `#customQuizDropdown` usa gerenciamento próprio de foco/ARIA em `app.js:903-972`. Migrar para Top Layer exige refatoração comportamental fora das 5 decisões R2. |

---

## 3. Especificação Consolidada de Mudanças para a Fase 3

### 3.1 Lista Fechada de Escopo (Permitidos vs Proibidos)

- **Arquivos de código permitidos na Fase 3:**
  1. `public/web/index.html` (Camada 1 + Camada 2, `data-default-theme="dark"`, `theme-color`, título sem travessão, SVGs inline, `?v=`)
  2. `public/web/styles.css` (tokens `:root` / `[data-theme="dark"]` / `[data-theme="light"]`, regras escopadas `.app-*` / `.exam-panel`, features #1–#8, correções WCAG e motion)
  3. `public/web/modules/theme-boot.js` (leitura de `data-default-theme`)
  4. `public/web/modules/theme.js` (leitura de `data-default-theme`, ciclo `['dark', 'light', 'system']` ou transição direta Dark→Light, `theme-color` `#000000`)
  5. `public/web/modules/backdrop.js` (`setBackdropSuspended(boolean)`, ocultação coordenada de `#backdropMotionToggle`, limpeza GPU no `destroy()`)
  6. `public/web/app.js` (`examState` + `setBackdropSuspended`, `inert` em modais/Modo Foco, `transform: scaleX()` nas barras, `getScrollBehavior()`, drawer mobile `aria-expanded`/Esc, `translate="no"` dinâmico, SVGs de `icons.js`, opcional `wakeLock`, imports `?v=`)
  7. `public/web/modules/stats.js` (normalização de caixa normal nos títulos de classificação/ritmo/seção, se aplicada)
  8. `public/web/modules/i18n/en.js` e `public/web/modules/i18n.js` (chaves PT→EN novas/atualizadas e import `?v=` de `en.js`)
  9. **Somente bump sincronizado de `?v=`** (zero alteração visual/funcional): `public/web/inicio.html`, `public/web/login.html`, `public/web/register.html`, `public/web/reset-password.html`, `public/web/produto.html`, `public/web/termos.html`, `public/web/privacidade.html`, `404.html`, `public/web/modules/auth_page.js`, `public/web/modules/inicio.js`, `public/web/modules/produto.js`.
  10. `tests/visual/capture_baseline.py` (apenas se necessário adaptar o clique/preferência de tema claro em `/app`, passando limpo no `ruff`).
- **Arquivos ESTRITAMENTE PROIBIDOS na Fase 3:**
  - `public/web/inicio.css`, `public/web/produto.css`, `public/web/modules/smooth-scroll.js`, `public/web/modules/mural.js`, `public/web/modules/timer-drag.js` (preservar intocado compatibilizando via CSS/HTML)
  - Toda a pasta `api/` (incluindo `api/database/migrations.py`, `handlers`, `services`, `repositories`)
  - `package.json`, `Dockerfile`, `docker-compose.yml`, `Procfile`, `vercel.json`, `.env`

### 3.2 Ordem Passo a Passo de Implementação (1 Agente por Arquivo por Vez)

Executar em branch dedicada `feature/quiz-visual-dashboard` criada a partir de `develop` (`e8853de`), somente após conclusão dos pré-requisitos da Seção 4.2:

1. **Passo 1 — Tema padrão escuro e `theme-color` (`theme-boot.js`, `theme.js`, `index.html`):**
   - Adicionar `data-default-theme="dark"` em `<html>` e `<meta name="theme-color" content="#000000">` em `public/web/index.html`.
   - Atualizar `theme-boot.js` e `theme.js` para usar `document.documentElement.getAttribute('data-default-theme') || 'system'` quando não houver chave em `quiz_theme_preference`, ajustar `theme-color` escuro para `#000000` e ordenar `THEMES = ['dark', 'light', 'system']` para permitir troca imediata Escuro → Claro em 1 clique.
   - *Checkpoint:* `test_ui_contract.py` + conferência sem FOUC com `localStorage` vazio.
2. **Passo 2 — Tokens canônicos, contraste WCAG AA e motion em `public/web/styles.css`:**
   - Atualizar `[data-theme="dark"]` e `:root` com a tabela da Seção 2 (Conflito 4), completar tokens `--space-0/05/7..11`, `--radius-xl/pill`, `--text-xl..5xl`, `--dur-layout`, corrigir `--text-lg: 18px`, `h1`, `.comparison-table td: 12px`, `border-left` isolados, `authFadeIn: 200ms var(--ease-out)` e `prefers-reduced-motion`.
   - Aplicar features #1 (`color-scheme`, `color-mix`), #2 (`scroll-padding-top`, `scroll-margin-top`), #3 (`dvh`, `overscroll-behavior`, `scrollbar-gutter`), #4 (`backdrop-filter` em `.app-nav` + `@supports`), #6 (`content-visibility: auto`), #7 (`:has()`), #8 (`text-wrap`, alvos `>= 44px`).
   - *Checkpoint:* conferir contraste AA/AAA e regressão zero em `/` e `/produto`.
3. **Passo 3 — Ciclo de vida do WebGL (`backdrop.js`) + controlador `examState` em `app.js`:**
   - Implementar `setBackdropSuspended(boolean)` e limpeza completa de recursos GL no `destroy()` de `public/web/modules/backdrop.js`.
   - Integrar `examState` (`idle` / `active` / `results`) em `app.js` nos gatilhos definidos no Conflito 3 (incluindo `#reset`, `#btnRedoQuiz`, `#quizSelector`, `#catalogList`, `quiz` `change`, `handleSubmitQuiz`, `closeResultModal`), além de `Wake Lock` se aprovado.
   - *Checkpoint:* validar pausa efetiva do `requestAnimationFrame` (`rafId === 0`) e fundo `#000000` chapado durante a prova.
4. **Passo 4 — Navegação em 2 camadas, `inert`, `scaleX`, `translate="no"` e i18n (`index.html`, `app.js`, `stats.js`, `en.js`, `i18n.js`):**
   - Reestruturar o topo de `public/web/index.html` com Camada 1 (`.app-nav-wrap` / `.app-nav` / `#appMenuToggle` / `#appNavDrawer`) e Camada 2 (`.exam-panel`), preservando **todos os IDs e `aria-*`** sem duplicação, e reposicionar `#timer` abaixo da Camada 1 conforme Conflito 1.
   - Atualizar `app.js`: `inert` em `<main>`/`<footer>` nos 8 modais (com liberação garantida em `cleanup`/`finally`) e nas questões ocultas do Modo Foco; `scaleX()` em `#progressBar` e `.section-progress-fill`; `getScrollBehavior()`; abertura/fechamento acessível do `#appNavDrawer` (`Esc` + `aria-expanded` + bloqueio em `shortcuts.js`); `translate="no"` nos nós dinâmicos de questão/simulado; ícones SVG em vez de símbolos textuais soltos.
   - Atualizar `public/web/modules/i18n/en.js` com todas as novas chaves e chaves normalizadas (Seção 3.4).
   - *Checkpoint:* `python -m unittest tests/test_ui_contract.py tests/test_modulepreload.py`.
5. **Passo 5 — Sincronia global de `?v=` e Portões de Saída:**
   - Atualizar todos os `?v=` conforme a tabela da Seção 3.3 em todos os 9 HTMLs e imports JS.

### 3.3 Tabela de Sincronismo Obrigatório de `?v=`

Auditoria direta do estado atual → versão alvo na Fase 3 (atenção: `modulepreload`, `<script>` e `import` ES Module **devem** ter o mesmo `?v=` para evitar instância duplicada):

| Arquivo | Versão atual | Versão alvo (Fase 3) | Onde atualizar (todos obrigatórios) |
|---|---:|---:|---|
| `styles.css` | `?v=30` | **`?v=31`** | Todos os **9 HTMLs**: `index.html`, `inicio.html` *(apenas o `?v=` da tag `<link>`)*, `login.html`, `register.html`, `reset-password.html`, `produto.html`, `termos.html`, `privacidade.html`, `404.html` |
| `app.js` | `?v=26` | **`?v=27`** | `index.html` (`modulepreload` linha 40 e `<script type="module">` linha 690) |
| `theme-boot.js` | *(sem `?v=`)* | **`?v=2`** | Todos os **8 HTMLs** que o carregam: `index.html`, `login.html`, `register.html`, `reset-password.html`, `produto.html`, `termos.html`, `privacidade.html`, `404.html` |
| `theme.js` | `?v=9` | **`?v=10`** | `index.html` (`modulepreload`), `app.js:2`, `produto.js:10` |
| `backdrop.js` | `?v=8` *(e **`?v=7` em `404.html:36`**)* | **`?v=9`** | `index.html`, `login.html`, `register.html`, `reset-password.html`, `termos.html`, `privacidade.html` e **`404.html` (corrigindo o `?v=7` defasado)** |
| `i18n.js` e `i18n/en.js` | `?v=10` | **`?v=11`** *(se `en.js` for editado)* | **Regra estrita (`test_single_i18n_version_everywhere`):** `index.html` (`modulepreload` de `i18n.js` e `en.js`), `login.html`, `register.html`, `reset-password.html`, `app.js:6`, `auth_page.js:14`, `inicio.js:12`, `produto.js:9`, `i18n.js:14` |
| `stats.js` | `?v=7` | **`?v=8`** *(se editado)* | `index.html` (`modulepreload`), `app.js:4` |
| `icons.js`, `shortcuts.js`, `timer-drag.js`, `i18n-boot.js` | `?v=6`, `?v=5`, `?v=1`, `?v=1` | Manter *(se não editados)* | Intactos |

### 3.4 Inventário Consolidado PT → EN (`public/web/modules/i18n/en.js`) e Copy

- **Novas chaves obrigatórias para a Camada 1 e Camada 2:**

| Contexto | Chave exata (`pt-BR`, caixa normal, sem `!`) | Valor (`en.js`) |
|---|---|---|
| Marca na Camada 1 (`title`) | `'Voltar para a página inicial'` | `'Back to home page'` |
| Link na Camada 1 | `'Início'` | `'Home'` |
| `aria-label` da Camada 2 | `'Controles do simulado'` | `'Quiz controls'` |
| *(Já existentes em `en.js` — reutilizar exatamente)* | `'Principal'`, `'Abrir menu'`, `'Fechar menu'`, `'Planos'`, `'Por que o Acely?'`, `'Entrar'`, `'Criar conta grátis'` | Já mapeados em `en.js:26-28, 525, 529, 532-533` |

- **Normalização de copy existente (`B1`/`B6`/`B8` — caixa normal e remoção de símbolos unicode soltos):**
  - Se atualizados em `index.html`, `app.js` e `stats.js`, **adicionar as novas chaves abaixo em `en.js`** (mantendo compatibilidade caso algum módulo ainda referencie a chave anterior até o fim da etapa):
    - `'Acely · Treino de raciocínio'`: `'Acely · Reasoning practice'`
    - `'Refazer tudo'`: `'Retake all'` *(já existe em `en.js:230` — basta remover o `↺` do HTML)*
    - `'Gerar novas variações'`: `'Generate new variations'` *(ao trocar `↻` por SVG de `icons.js`)*
    - `'Biblioteca de estudos'`: `'Study library'`
    - `'Opções rápidas:'`: `'Quick options:'`
    - `'Simulado incompleto'`: `'Incomplete quiz'`
    - `'Erro de carregamento'`: `'Loading error'`
    - `'Erro de conexão'`: `'Connection error'`
    - `'Correta'` / `'Errada'`: `'Correct'` / `'Wrong'` *(ao trocar `✓`/`✗` por SVG de `icons.js`)*
    - `'Explicação didática'`: `'Explanation'`
    - *(Em `stats.js`, se normalizado):* `'Bom rendimento'`, `'Desempenho excepcional'`, `'Acima da média'`, `'Regular ou em evolução'`, `'Atenção redobrada'`, `'Ritmo médio:'`, `'Desempenho por disciplina'`.

---

## 4. Baseline de QA, Pré-Requisitos Pré-Fase 3 e Portões de Saída

### 4.1 Números Verificados do Baseline Atual (Fase 1F)

Coletado em `2026-11-18` na branch `develop` (`e8853de`), sem nenhuma alteração de código:

| Verificação | Resultado observado | Observação crítica |
|---|---|---|
| `python -m unittest discover tests` | **390** testes (`38.406s`): **299 OK**, **3 FAILs**, **68 ERRORs**, **20 skips** | **3 FAILs pré-existentes independentes da UI:** `test_banco_credenciais.py:43` (`\` vs `%5C` no Windows), `test_prod_hardening.py:67` e `test_security_fixes.py:194` (presença de `GROQ_API_KEY`/`GEMINI_API_KEY` no `.env` local). **68 ERRORs:** todos por bloqueio de socket loopback no sandbox (`WinError 10013` + porta `8005` em `test_auth_e2e.py`). **20 skips:** aguardando `QUIZ_DB_INTEGRATION=1`. |
| `python -m unittest tests/test_ui_contract.py tests/test_modulepreload.py` | **6 / 6 OK** (exit code `0`) | Contratos de IDs, referências `for`/`aria-*`, unicidade de IDs e `modulepreload` 100% íntegros. |
| `ruff check .` (`ruff 0.16.10`) | **237 violações** em 48 arquivos (`111` auto-fixáveis) | Débito pré-existente concentrado em `api/` e `tests/`. |
| `ruff format --check .` | **56 arquivos** pendentes de formatação (`33` conformes) | Débito pré-existente em `api/`, `scripts/` e `tests/`. |
| `python tests/visual/capture_baseline.py --label before` | **BLOQUEADO_SANDBOX** (`0` PNGs gerados; esperada matriz de **180 PNGs**) | `WinError 10013` no sandbox impediu `quiz_api.py` (Postgres `5433`) e a porta CDP do Edge/Chrome (`127.0.0.1`). |

### 4.2 Pré-Requisito Obrigatório Antes de Iniciar a Fase 3

**A Fase 3 NÃO deve começar** enquanto o operador não executar os dois comandos abaixo **fora do sandbox** (em terminal local normal com sockets liberados) e confirmar os artefatos de referência:

1. **Gerar o baseline visual `before` completo (180 PNGs + auditoria runtime de `overflow-x` e toque `< 44px`):**
   ```powershell
   # Terminal 1
   $env:COOKIE_SECURE = "false"
   python quiz_api.py

   # Terminal 2
   python tests/visual/capture_baseline.py --label before
   python tests/visual/capture_baseline.py --label before --lang en
   ```
2. **Confirmar a suíte completa de testes com sockets liberados:**
   ```powershell
   python -m unittest discover tests
   ```
   *(Validando 0 `ERROR` de conexão nos testes de rota/E2E e apenas os 3 `FAIL`s pré-existentes documentados ou 0 `FAIL`s com `.env` limpo.)*

### 4.3 Portões Objetivos de Aprovação da Fase 3 (Para PR em `develop`)

A implementação da Fase 3 só será considerada aprovada quando **todos** os portões abaixo passarem:

1. **Contratos e suíte completa:**
   - `python -m unittest tests/test_ui_contract.py tests/test_modulepreload.py` → **100% OK** (exit `0`).
   - `python -m unittest discover tests` (fora do sandbox, com `ADMIN_PASSWORD`) → **0 ERRORs**, **0 novas falhas**, `test_single_i18n_version_everywhere`, `test_pagina_produto`, `test_dominio_acely` aprovados.
2. **Baseline visual e responsividade (`before` vs `after`):**
   - `capture_baseline.py --label after` e `--lang en` gerando os **180 PNGs** (Desktop `1440×900`, Tablet `768×1024`, Celular `390×844`, claro e escuro, PT e EN) com **0 falhas `LAYOUT`** (`overflow-x <= 1px`) e **0 avisos `AVISO`** de alvos `< 44×44px` no mobile.
   - Nota: caso `/app` abrindo no escuro por padrão faça o script capturar dois PNGs escuros antes da adaptação de `capture_baseline.py`, atualizar o script (ou validar via toggle de tema) garantindo cobertura real de claro e escuro em `/app` com `0` violações `ruff` no arquivo `.py`.
   - Conferência visual confirmando `/` (`inicio`, `inicio-menu`) e `/produto` pixel-idênticas ao `before`.
3. **Acessibilidade (WCAG 2.1/2.2 AA), WebGL e Console:**
   - Contraste AA/AAA validado nos dois temas (com `--btn-primary-text: #000000` sobre `#FF7A5C` = `8,19:1`).
   - Navegação por teclado (`Tab`, `Esc`, `W A S D`/`← →`, `.skip-link`, `inert` nos modais e foco restaurado).
   - No modo `'active'` da prova: `backdrop.js` com `rafId === 0`, `<canvas class="backdrop">` oculto, `#backdropMotionToggle` oculto e fundo `#000000` chapado.
   - **0 erros** de console/CSP (`'self'` preservada) em todas as rotas.
4. **Lint (`ruff`):** nenhuma nova violação introduzida em relação ao baseline (`<= 237` em `ruff check .`, `0` erros em qualquer `.py` eventualmente tocado).

### 4.4 Procedimento de Rollback

- **Gatilhos:** falha de contrato em produção, regressão visual em `/`, colisão de `#timer` ou dropdown, bloqueio de foco/`inert` preso em modais ou erro JS no console.
- **Execução:** Como a Fase 3 altera exclusivamente camada de apresentação estática (`public/web/`) em branch `feature/quiz-visual-dashboard` (sem migrations em `api/database/migrations.py` nem rotas em `api/`), o rollback em produção é **instantâneo e livre de risco de dados** via **Rollback de Deployment na Vercel** ou `git revert <merge-commit>` via PR na `develop`. Em caso de anomalia restrita ao WebGL, um hotfix de 1 linha forçando `setBackdropSuspended(true)` devolve o fundo `#000000` chapado imediatamente.

---

## 5. Perguntas de Aprovação Humana (Antes de Liberar a Fase 3)

1. Aprovar o **Plano Consolidado** acima (5 decisões R2, manutenção de `/` intacta com bump de `styles.css?v=31`, e os 6 conflitos resolvidos)?
2. Incluir o item **#9 (`Screen Wake Lock` via `navigator.wakeLock`)** em prova ativa no Passo 3 da Fase 3, ou mantê-lo fora deste escopo estritamente visual?
3. Confirmar a execução dos comandos pré-Fase 3 fora do sandbox (`capture_baseline.py --label before` + `unittest discover tests`) antes de criar a branch `feature/quiz-visual-dashboard`.
