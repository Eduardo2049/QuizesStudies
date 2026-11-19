# Arquitetura e Revisão Técnica — Missão 1 (Fase 1C)

**Projeto:** Acely (`Eduardo2049/QuizesStudies`)
**Branch base verificada:** `develop` (`e8853de`)
**Escopo:** Fase 1C — Arquitetura das 5 decisões para `/app`, análise de contratos (IDs, classes, acessibilidade, i18n, `?v=`, CSP), decisão sobre tokens compartilhados em `/`, registro do `Dockerfile`, plano de riscos, ordem de implementação segura e critérios de verificação/rollback.
**Regra de execução:** Documento produzido em modo **somente leitura** sobre o código da aplicação (`public/web/`, `api/`, `tests/`, `Dockerfile`, `vercel.json`).

---

## 1. Arquitetura das 5 Decisões para `/app`

### 1.1 Decisão 1 — Tema escuro padrão em `/app`, `theme.js` e `localStorage`

#### Diagnóstico do estado atual
1. **Boot anti-FOUC (`public/web/modules/theme-boot.js`, linhas 6–15):**
   - Lê `localStorage.getItem('quiz_theme_preference') || 'system'`.
   - Quando o valor é `'system'`, resolve via `window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'`.
   - Define `data-theme` (`'dark'` ou `'light'`) e `data-theme-mode` (`'system'`, `'dark'` ou `'light'`) no elemento `<html>` de forma síncrona no `<head>`.
   - **Lacuna de cache:** Em `index.html:49`, `login.html:24`, `register.html:24`, `reset-password.html:19`, `termos.html:21`, `privacidade.html:21`, `produto.html:43` e `404.html:16`, o script é carregado como `/web/modules/theme-boot.js` **sem parâmetro `?v=`**, sujeito ao cache HTTP de 1 dia (`max-age=86400` no `vercel.json:71-75`).
2. **Gerenciador de tema (`public/web/modules/theme.js`, linhas 7–131):**
   - Usa `THEME_STORAGE_KEY = 'quiz_theme_preference'` e `THEMES = ['system', 'dark', 'light']`, iniciando com `currentTheme = 'system'`.
   - Atualiza `<meta name="theme-color">` na linha 38 com `#171717` (escuro) ou `#f4f0e8` (claro).
   - Conecta-se ao botão `#themeToggle` e atualiza `.theme-icon` e `.theme-label`.
3. **Comportamento nas demais páginas:**
   - `/` (`public/web/inicio.html:2,15`): fixa `data-theme="dark"` e `class="in-html"` diretamente no `<html>`, com `meta[name="theme-color" content="#000000"]`. Não carrega `theme-boot.js` nem `theme.js`.
   - `/produto` e `/planos` (`public/web/produto.html:43`, `public/web/modules/produto.js:15`): usam `theme-boot.js` + `initTheme()`, mantendo claro/sistema/escuro conforme preferência.
   - `/login`, `/register`, `/reset-password`, `/termos`, `/privacidade`, `404.html`: carregam `theme-boot.js` sem `#themeToggle`, herdando a preferência salva ou `'system'`.

#### Arquitetura proposta (escuro padrão apenas em `/app` sem quebrar outras páginas)
1. **Preservar a chave `quiz_theme_preference` no `localStorage`:** conforme `docs/PLANO_ACELY.md` §1.1.1, chaves `quiz_*` não devem ser renomeadas para não invalidar preferências salvas dos usuários.
2. **Sinalização declarativa de padrão por página no `<html>`:**
   - Em `public/web/index.html`, adicionar `data-default-theme="dark"` na tag `<html>` (e ajustar `<meta name="theme-color" content="#000000">`).
   - Em `theme-boot.js` e `theme.js`:
     - Ler `var fallback = document.documentElement.getAttribute('data-default-theme') || 'system';`
     - Se `localStorage.getItem('quiz_theme_preference')` não existir (ou não estiver em `['system', 'dark', 'light']`), usar `fallback` (`'dark'` em `/app`; `'system'` nas demais páginas).
     - Se o usuário já salvou explicitamente `'light'`, `'dark'` ou `'system'` em `localStorage`, a escolha salva prevalece em todas as páginas que usam `theme.js`/`theme-boot.js`.
3. **Ciclo de alternância no `#themeToggle` (`theme.js`):**
   - Manter `THEMES = ['dark', 'light', 'system']` (ou `['system', 'dark', 'light']`), garantindo que ao clicar pela primeira vez em `/app` (partindo de `'dark'`), o usuário consiga ir diretamente para `'light'` sem passar por um passo intermediário que possa resolver novamente para escuro se o SO estiver em dark mode. A ordem `['dark', 'light', 'system']` torna a transição Dark → Light imediata em 1 clique.
   - Atualizar `meta[name="theme-color"]` em `theme.js:38` para `resolved === 'dark' ? '#000000' : '#f4f0e8'`, alinhando ao fundo `#000000` chapado.
4. **Preventivo de cache e FOUC:**
   - Ao modificar `theme-boot.js`, adicionar `?v=2` em todos os HTMLs que o importam (`index.html`, `login.html`, `register.html`, `reset-password.html`, `termos.html`, `privacidade.html`, `produto.html`, `404.html`).
   - Como `theme-boot.js` executa de forma síncrona no `<head>` antes do CSS pintar o `<body>`, `data-theme="dark"` estará aplicado antes do primeiro frame em `/app`, garantindo zero flash claro (FOUC).
5. **Nota de impacto em `tests/visual/capture_baseline.py`:**
   - Atualmente `capture_baseline.py` alterna o tema emulando `prefers-color-scheme` via CDP. Como `/app` terá padrão `'dark'` independente do SO quando `localStorage` estiver vazio, na Fase 3/QA será necessário atualizar a captura de `/app` no modo claro (ex.: clicando em `#themeToggle` ou populando `quiz_theme_preference = 'light'` antes da captura), mantendo `prefers-color-scheme` para as demais páginas.

---

### 1.2 Decisão 2 — Ciclo de vida do WebGL (`backdrop.js`) durante e fora da prova

#### Diagnóstico do estado atual (`public/web/modules/backdrop.js`)
1. **Auto-inicialização incondicional:** `scheduleBackdrop()` (linhas 647–657) agenda `initBackdrop()` no evento `load` + `requestIdleCallback` (timeout 1500 ms).
2. **Recursos WebGL alocados em `createBackdrop()` (linhas 336–613):**
   - 2 programas (`field`, `display`) + shaders compilados;
   - 1 VBO (`buffer`) com o triângulo fullscreen;
   - 1 `fieldTexture` (`RGBA`) + 1 `framebuffer` redimensionados em `resize()`;
   - Loop contínuo `requestAnimationFrame(frame)` a até `MAX_FPS = 30` (linha 28);
   - Listeners globais: `visibilitychange`, `resize`, `pointermove`, `pointerout`, `prefers-reduced-motion`, `MutationObserver` em `data-theme`, `webglcontextlost`/`restored`, e clique em `[data-backdrop-toggle]` (`#backdropMotionToggle` em `index.html:73`).
3. **Problema na arquitetura de `destroy()` atual (linhas 597–611):**
   - `destroy()` cancela o `rafId` e remove o `<canvas>` do DOM, mas não libera explicitamente `fieldTexture`, `framebuffer`, `buffer` e `program` na GPU antes de descartar o canvas. Além disso, destruir e recriar contextos WebGL repetidamente numa mesma aba (ao iniciar/resetar vários simulados) pode consumir o limite de contextos WebGL do navegador (~8–16 contextos simultâneos) até a coleta de lixo.

#### Arquitetura proposta para o ciclo de vida em `/app`
1. **Contrato de estado entre `app.js` e `backdrop.js`:**
   - Exportar em `backdrop.js` uma função de controle explícito: `setBackdropExamActive(active: boolean)` (ou `setBackdropSuspended(suspended: boolean)`), além de permitir configurar `backdrop.js` sem auto-start em prova caso o estado inicial já seja ativo.
   - Alternativamente (acoplamento zero por atributo DOM + API explícita), `app.js` marca `document.body.dataset.examState = 'idle' | 'active' | 'finished'` e chama `setBackdropSuspended(isExamActive)`.
2. **Definição inequívoca de "prova em andamento" (`active`) vs "sem prova em andamento" (`idle` / `finished`):**
   - **Sem prova em andamento (`suspended = false`, WebGL permitido):**
     - Ao abrir `/app` antes de iniciar o simulado (sem cronômetro rodando, sem questão respondida, ou em estado vazio / pós-submissão com modal de resultado / reset).
     - Observação de UX para validação na Fase 2: ao carregar `/app`, `loadInitialQuiz()` (`app.js:629`) já renderiza o primeiro simulado no `#quiz`. Recomenda-se considerar a prova **em andamento** a partir de qualquer um dos seguintes gatilhos em `app.js`:
       1. `startTimer()` é acionado (botão `#startBtn`, clique em card do `#catalogList`, ou marcação da primeira alternativa em `quiz.addEventListener('change', ...)` — `app.js:1199, 1444, 1454`);
       2. Existe pelo menos 1 alternativa marcada no formulário (`new FormData(quiz)` não vazio);
       3. `timer` está com classe `.running` ou `.expired` (até que `#reset` ou carregamento de novo simulado sem auto-start ocorra);
       4. Link direto de início imediato ou estado em que o aluno já esteja interagindo com as questões (ex.: navegação de foco/paleta após iniciar).
     - Ao acionar `#reset` (`app.js:1205`), `#btnRedoQuiz` ou concluir/fechar após revisão, ou trocar de questionário sem iniciar (`quizSelector` change — `app.js:1466`), o estado retorna a `idle` (`setBackdropSuspended(false)`), salvo se o fluxo iniciar o cronômetro imediatamente (como ocorre ao escolher no catálogo na linha 1444, onde deve permanecer `suspended = true`).
   - *Nota para Fase 2:* Caso Design (B) opte por manter o WebGL desligado sempre que houver qualquer `.question` visível na tela (mesmo antes de clicar "Iniciar"), a função `setBackdropSuspended(Boolean)` continua idêntica — muda apenas o predicado que a invoca em `app.js`. Arquiteturalmente, o mecanismo de suspensão é o mesmo.
3. **Mecanismo interno de suspensão limpa (sem leak de memória/GPU e sem esgotar contextos):**
   - Quando `setBackdropSuspended(true)` for chamado:
     1. Cancelar imediatamente o loop (`stopLoop()` -> `cancelAnimationFrame(rafId)`, `rafId = 0`, 0% de uso de GPU/CPU).
     2. Remover a classe `.is-running` do `<canvas class="backdrop">` (`opacity` vai a `0` com `--dur-slow` ou imediato em `prefers-reduced-motion`) e, ao concluir a transição (ou imediatamente via atributo `hidden` após fade-out de 300–600 ms, garantindo cancelamento se resumir antes), retirar o canvas da composição (`canvas.hidden = true`).
     3. Liberar a textura de campo (`gl.deleteTexture` / desalocar com `texImage2D(..., 1, 1, ...)` ou manter apenas quando ativo) e remover listeners de `pointermove`/`resize` enquanto suspenso (ou fazê-los retornar cedo quando `suspended === true`) para eliminar processamento por evento do mouse durante a prova.
     4. Ocultar `[data-backdrop-toggle]` (`#backdropMotionToggle`) durante `suspended === true` para que o aluno não veja um controle de animação do fundo enquanto o fundo está desligado pela regra da prova.
     5. Como a instância e o contexto `gl` único da página são preservados em memória ociosa (ou liberados apenas no `pagehide`/destroy definitivo), alternar entre `idle` e `active` múltiplas vezes **nunca** cria múltiplos contextos WebGL nem gera leak.
   - Quando `setBackdropSuspended(false)` for chamado:
     1. Se `scheduleBackdrop()` ainda não tiver criado a instância (ex.: o usuário iniciou a prova antes do `requestIdleCallback`), não há nada pendente; ao voltar para `idle`, inicializa sob demanda se ainda não existir.
     2. Reanexa `canvas.hidden = false`, relê paleta (`readPalette()`), chama `resize()` se a janela mudou durante a prova, adiciona `.is-running`, reexibe `#backdropMotionToggle`, e retoma `requestAnimationFrame(frame)` se `motionEnabled() && !document.hidden`.
4. **Fundo chapado `#000000` garantido durante a prova:**
   - Em `[data-theme="dark"]` (`public/web/styles.css`), substituir `--paper: #181818` e `--bg-gradient: radial-gradient(...)` por `--paper: #000000` e `background: #000000` (ou `--bg-gradient: #000000`). Assim, quando `.backdrop` fica invisível/suspenso durante a prova, o fundo é **100% `#000000` chapado**, sem brilho azul/roxo residual.

---

### 1.3 Decisão 3 — Acento Coral `#FF7A5C` unificado

#### Diagnóstico do estado atual
- Em `/` (`public/web/inicio.css:31-32`): `--in-accent: #FF7A5C`, `--in-accent-ink: #000000` (contraste 8,9:1), hover `#FF8F75`.
- Em `/app` escuro (`public/web/styles.css:100-131`): `--coral: #4359ff` (azul), `--teal: #a78bfa` (roxo), `--paper: #181818`, `--card-solid: #1F1F1F`, `--line: #2e2e35`, `--btn-primary-text: #ffffff`.
- Em `/app` claro (`public/web/styles.css:52-97`): `--coral: #c9462a`, `--btn-primary-text: #ffffff` (4,78:1), `--teal: #176b67`, `--paper: #f4f0e8`.
- Em `styles.css:3887-3896`, os tokens `--backdrop-*` do tema escuro ainda apontam para azul/roxo (`#181818`, `#3a4bd9`, `#7c5cf0`, `#8f9bff`).

#### Arquitetura de tokens e contraste WCAG AA
1. **Tema escuro (`[data-theme="dark"]` em `styles.css`):**
   - Superfícies alinhadas a `/`:
     - `--paper: #000000` (fundo chapado)
     - `--bg-gradient: #000000`
     - `--card-solid: #181818` / `--card-bg: rgba(24, 24, 24, 0.92)` (ou `#181818` chapado) e superfície elevada `#1F1F1F` (`--input-bg: #121214` ou `#181818`, `--option-bg: #181818`, `--option-hover: #1F1F1F`).
     - `--line: #272727`, `--line-strong: #313131` (novo token ou uso de `#313131` em bordas de foco/hover).
     - `--ink: #EDEDED`, `--muted: #9B9B9B` (7,4:1 sobre `#000000`, alinhado a `inicio.css:30`).
   - Acento principal unificado:
     - `--coral: #FF7A5C`
     - `--coral-dark: #FF8F75` (hover sobre escuro, seguindo `inicio.css:109`)
     - `--coral-rgb: 255, 122, 92`
     - `--coral-glow: rgba(255, 122, 92, 0.22)`
     - `--accent-text: #FF7A5C` (texto coral sobre `#000000` = 8,9:1; sobre `#181818` = 7,2:1; sobre `#1F1F1F` = 6,5:1 — AA/AAA).
     - `--btn-primary-text: #000000` (**obrigatório:** texto branco sobre `#FF7A5C` daria apenas ~2,6:1 e violaria WCAG AA; texto `#000000` garante 8,9:1 em `.primary`, `.btn-confirm-finish`, `.btn-remix`, `.guest-action-link--primary`, `a.access-cta.primary`).
   - Papel secundário / `--teal` e `--line-focus` no tema escuro:
     - `--line-focus: #FF7A5C` e `--focus-ring: rgba(255, 122, 92, 0.28)` (alinhado ao `:focus-visible` de `inicio.css:60`).
     - `--teal` no tema escuro era um alias legado para roxo (`#a78bfa`). Para eliminar o visual "roxo/azul genérico" (`DESIGN_UPGRADE.md` §4) sem quebrar seletores que referenciam `--teal`, definir no escuro `--teal: #FF7A5C` (ou `#EDEDED` nos contornos neutros e `--coral`/`#FF7A5C` nos destaques ativos, com `--btn-teal-text: #000000` e `--option-checked: rgba(255, 122, 92, 0.14)`). Validar na Fase 2 entre Design (B) e Arquitetura (C) todos os usos de `--teal` em estados ativos (`.toggle-btn.active`, `.palette-btn.answered`, `.catalog-tab-btn.active`, `.option:has(input:checked)`).
2. **Impacto em `backdrop.js` (`--backdrop-*`):**
   - `backdrop.js` não possui cores hardcoded no GLSL; lê tudo de `:root` / `[data-theme="dark"]` em `readPalette()` (linhas 291–308).
   - No `[data-theme="dark"]` de `styles.css`, atualizar os tokens `--backdrop-*` para harmonizar com `#000000` + `#FF7A5C` quando fora de prova:
     - `--backdrop-base: #000000`
     - `--backdrop-a`: tom coral escuro/queimado controlado (ex.: `#7a2e1f` ou `#9e3c28`) e `--backdrop-b`: grafite quente/âmbar sutil (ex.: `#2b1f24` ou `#52271e`), `--backdrop-line: #FF7A5C` (em baixa opacidade no shader: `bar * 0.5`), mantendo `--backdrop-calm` calibrado para garantir contraste AA ≥ 4,5:1 para `#EDEDED` e `#9B9B9B` sobre o corredor central!
3. **Preservação do tema claro (`:root`):**
   - No tema claro (`#f4f0e8`), **não** usar `#FF7A5C` como fundo com texto branco nem como texto sobre papel claro (pois `#FF7A5C` sobre `#f4f0e8` tem ~2,3:1, falhando AA). Manter `--coral: #c9462a` (com `#ffffff` = 4,78:1) e `--accent-text: #b23a20` (> 5:1) no modo claro, ou aplicar `#FF7A5C` com `#000000` apenas onde o contraste AA for matematicamente verificado.

---

### 1.4 Decisão 4 — Navegação em duas camadas

#### Estrutura DOM semântica proposta para `index.html`
Atualmente, `index.html` coloca toda a barra superior (`.hero-bar`), título `<h1>`, seletor de questionário (`.hero-top`), CTA (`#startBtn`), status/timer (`.status`), barra de progresso (`.progress-track`), `#examToolbar` e `#questionPalette` dentro de `<main class="shell"><header class="hero">`.

A nova arquitetura separa **duas camadas com responsabilidades e contextos de empilhamento distintos**:

1. **Camada 1 — Barra Superior Global Flutuante e Translúcida (fora de `.shell`, logo após `<a href="#quiz" class="skip-link">`)**
   - `<header class="app-nav-wrap">` contendo `<nav class="app-nav" aria-label="Principal">`:
     - **Esquerda (Marca):** `<a href="/" class="app-logo">` (ou `div.hero-brand` mantendo `.hero-brand-icon` e `<span translate="no">Acely</span>`, ligando à raiz `/`).
     - **Centro/Links principais:** `<a href="/planos" id="plansLink" ...>`, `<button id="btnOpenAboutModal" ...>` ("Por que o Acely?"), e opcionalmente atalho direto para catálogo (`#btnOpenCatalog` ou manter catálogo no painel do simulado conforme distribuição de ações). Nota: `tests/test_pagina_produto.py:181` exige exatamente `<a href="/planos" id="plansLink"` no HTML de `index.html`!
     - **Direita (Utilitários + Conta):** `#langToggle`, `#themeToggle`, `#backdropMotionToggle` (oculto durante prova), `#authControls` (`#visitorActions`, `#userProfile` com `#userRoleBadge`, `#userName`, `#guestAiChip`, `#accountBtn`, `#logoutBtn`, `#guestActions`).
     - **Mobile (`<= 768px` / `640px`):** Gaveta ou linha responsiva sem `overflow-x` (todos os itens com `min-height: 44px; min-width: 44px`, mantendo todos os IDs únicos e sem duplicar IDs entre barra desktop e menu mobile!). *Atenção crítica:* `test_ui_contract.py::test_ids_are_unique_per_page` proíbe IDs duplicados na mesma página. Portanto, os elementos com ID (`#themeToggle`, `#langToggle`, `#plansLink`, `#authControls`, etc.) devem permanecer em um único contêiner DOM responsivo (sem clonar no HTML como ocorre em `inicio.html` onde `#inNavAccount` e `#inMenuAccount` têm IDs distintos), evitando duplicação de IDs e mantendo todos os listeners de `app.js` / `theme.js` / `i18n.js` intactos.
   - **Estilo visual da Camada 1 (padrão `/`):**
     - `position: fixed; top: var(--space-4); left: 0; right: 0; z-index: var(--z-global-nav);`
     - Cartão interno: `background: rgba(24, 24, 24, 0.72)` (no claro: `rgba(244, 240, 232, 0.82)`), `border: 1px solid var(--line)` (`#272727` no escuro), `border-radius: var(--radius-lg)` (16px), `backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px);`.
     - Compensação no `.shell`: aumentar `padding-top` do `.shell` para `calc(var(--nav-height, 64px) + var(--space-6))` (ex.: `96px` no desktop e proporcional no mobile) para que o conteúdo nunca nasça escondido atrás da barra flutuante.

2. **Camada 2 — Sub-cabeçalho / Painel de Controle do Simulado (dentro de `<main class="shell">`)**
   - `<section class="exam-panel" aria-label="Controle do simulado">` (ou `<header class="hero exam-panel">` preservando classes onde necessário):
     - Título enxuto e introdução (`<h1>`, `.intro`, `.intro--visitor`).
     - `.hero-top`: `.quiz-picker` (`#customQuizSelectorWrap`, `#customQuizTrigger`, `#customQuizDropdown`, `<select id="quizSelector" class="sr-only">`) + `.hero-top-buttons` (`#btnOpenCatalog`, `#addQuizBtn`).
     - `.hero-actions`: `#startBtn` (CTA principal cheio, coral `#FF7A5C` com texto `#000000`) + `#btnSetTimer`.
     - `.status` + `.progress-track`: `#progress`, `#percent`, `.timer-wrap` (`#timer` em `DM Mono`, `#timerConfig` / `#timerPreset`), `#progressBar`.
     - `#examToolbar`: `.view-mode-toggle` (`#btnToggleFocus`, `#btnToggleList`) + `#btnQuickSubmit`.
     - `<nav id="questionPalette" class="question-palette" aria-label="Navegação rápida de questões"></nav>`.

#### Hierarquia de `z-index` (Stacking Context) e resolução de colisões
Estado atual em `styles.css:3623-3626`:
- `--z-timer: 10`, `--z-sticky-nav: 20`, `--z-timer-mobile: 95`, `--z-overlay: 100`.
- `backdrop.js`: `.backdrop` usa `z-index: -1`.
- **Conflito atual identificado:** Com a Camada 1 fixa no topo (`z-index` ~40–50), o `#timer` (`position: fixed; top: 16px; right: 20px; z-index: 10`) ficaria **por baixo** da Camada 1 no canto superior direito ou sobreporia os utilitários da conta!

**Nova tabela canônica de camadas (`z-index`) proposta:**

| Token | Valor | Elementos | Regra |
|---|---|---|---|
| `--z-backdrop` | `-1` | `.backdrop` (canvas WebGL) | Sempre atrás do `body` |
| `auto` | `0` | `.shell`, `.exam-panel`, `.quiz`, `.question` | **Proibido** aplicar `transform`/`overflow: hidden` permanente em `.exam-panel` para não prender `.custom-select-dropdown` |
| `--z-sticky-nav` | `20` | `.focus-navigation` (sticky bottom no mobile) | Acima das questões em scroll |
| `--z-dropdown` | `30` | `.custom-select-dropdown` (quando dentro do fluxo) — ou `100` se fora de stacking context restritivo | Deve abrir acima de `#examToolbar`, `#questionPalette` e `.question` |
| `--z-global-nav` | `40` | `.app-nav-wrap` (Camada 1 flutuante) | Acima do conteúdo, painel do simulado e `.focus-navigation`; abaixo do timer arrastável e de modais |
| `--z-timer` | `50` | `#timer`, `#timerConfig` | Acima da Camada 1 caso o usuário arraste (`timer-drag.js`) sobre a barra; **posição inicial padrão** deslocada abaixo da Camada 1 (`top: calc(var(--nav-height, 64px) + var(--space-5))`, ex.: `88px`, `right: 20px`) para nunca colidir com `#authControls`! |
| `--z-timer-handle` | `51` | `.timer-resize-handle` (`calc(var(--z-timer) + 1)`) | Sempre 1 acima do `#timer` |
| `--z-overlay` | `100` | `.modal-overlay` (`#uploadModal`, `#resultModal`, `#aboutModal`, `#confirmSubmitModal`, `#catalogModal`, `#accessModal`, `#accountModal`, `#noticeModal`, `#customTimerModal`) | Cobre toda a interface incluindo Camada 1 e `#timer` |
| `--z-skip` | `101` | `.skip-link` (`calc(var(--z-overlay) + 1)`) | Sempre acessível ao Tab inicial |

*Nota sobre `body:has(#timer.running) .hero-utils { margin-right: 92px; }` (`styles.css:3581-3584`):* Ao posicionar o `#timer` inicial abaixo da Camada 1 (`top: ~88px`) ou integrado visualmente à altura da Camada 2 antes de ser arrastado, essa regra de `margin-right: 92px` torna-se obsoleta e pode ser removida com segurança, liberando largura preciosa na Camada 1 em viewports <= 1100 px e mobile!

#### Impacto em `app.js`, `shortcuts.js` e `stats.js`
- **`app.js`:**
  - Todas as referências aos controles de topo e barra são feitas por `#id` (nenhuma usa seletor ancestral `.hero > .hero-bar`), logo a reorganização estrutural em duas camadas não quebra os bindings de eventos.
  - **Ponto crítico de scroll:** `app.js` chama `.scrollIntoView({ behavior: 'smooth', block: 'start' })` em 7 pontos (linhas 761, 767, 1202, 1223, 1240, 1292, 1447). Com a Camada 1 fixa no topo, rolar uma `.question` para `block: 'start'` fará com que o topo do cartão fique coberto pela barra flutuante **a menos que** `.question` tenha `scroll-margin-top: calc(var(--nav-height, 64px) + var(--space-6))` no `styles.css`! Essa regra CSS é **obrigatória** na Fase 3.
  - **`timer-drag.js`:** O módulo chama `timer.after(handle)` (linha 43) e CSS usa `#timer:not(.running):not(.expired) + .timer-resize-handle { display: none; }` (`styles.css:3831`). Manter `#timer` como elemento `position: fixed` direto dentro de `.timer-wrap` (`display: contents`), sem inserir novos elementos entre `#timer` e `#timerConfig`.
- **`shortcuts.js`:**
  - Escuta `window` `keydown` (linha 37), ignora quando `isInputActive(e)` (linhas 9–21) ou quando existe `.modal-overlay:not([hidden])` (linha 62). Se houver um menu/drawer mobile na Camada 1 aberto com foco dentro, garantir que `Escape` feche o menu antes de qualquer ação e que os atalhos de questão não disparem enquanto o menu mobile estiver aberto.
- **`stats.js`:**
  - Opera 100% dentro de `#resultStatsContainer` no `#resultModal` (`app.js:1136-1144`). Nenhum impacto estrutural.

---

### 1.5 Decisão 5 — Movimento

1. **Ausência de `smooth-scroll.js` em `/app`:**
   - Confirmado: `public/web/index.html` importa apenas `theme-boot.js`, `i18n-boot.js`, `analytics-boot.js`, `backdrop.js` e `app.js`. O módulo `public/web/modules/smooth-scroll.js` é importado exclusivamente por `public/web/modules/inicio.js:13` (página `/`).
   - `/app` deve manter rolagem nativa do navegador (`scroll-behavior: auto` no `html` para não interferir com foco/arrasto/atalhos).
2. **Transições, easing e propriedades animáveis (`DESIGN_SKILLS.md` B7 e R2.5):**
   - Curva única obrigatória: `--ease-out: cubic-bezier(0.22, 1, 0.36, 1)`.
   - Duração mínima: **>= 200 ms** (`--dur-fast: 200ms`, `--dur-base: 300ms`, `--dur-slow: 600ms`).
   - **Débito identificado no `styles.css` atual:**
     - Linha 1205: `.auth-form-card { animation: authFadeIn 0.18s ease-out; }` (abaixo de 200 ms e sem `--ease-out`);
     - Diversas regras usam `transition: background .2s ...` ou `color .2s ...` (200 ms é o limite mínimo válido, mas idealmente normalizar `ease` / `ease-out` para `var(--ease-out)` em `.modal-overlay`, `.modal`, `.option--hotkey-pulse`, `.quiz--focus .question--active`).
   - Animar exclusivamente `transform` e `opacity` em entradas e movimentações (evitar animar `width`, `height`, `top`, `left` em hover/transição; exceção legítima: `#progressBar` ou trocar `#progressBar` para `transform: scaleX()` no futuro se desejado, mantendo compatibilidade com `app.js:981`).
3. **Respeito a `prefers-reduced-motion: reduce`:**
   - CSS (`styles.css:3491-3498`) já zera animações e transições em `reduce`.
   - **Melhoria recomendada em `app.js`:** substituir chamadas diretas de `{ behavior: 'smooth', block: 'start' }` (7 ocorrências) por um helper `scrollBehavior()` que retorne `'auto'` quando `window.matchMedia('(prefers-reduced-motion: reduce)').matches` for `true`, pois o `scrollIntoView({ behavior: 'smooth' })` via JS em alguns navegadores não é suprimido apenas pela regra CSS `scroll-behavior: auto !important`.

---

## 2. Análise Profunda do Contrato de Classes, IDs, Acessibilidade, i18n, `?v=` e CSP

### 2.1 Contrato estático HTML ↔ JS (`tests/test_ui_contract.py`)
O teste `tests/test_ui_contract.py` falha automaticamente se:
1. Qualquer ID consultado via `getElementById('...')` ou `querySelector('#...')` em `app.js`, `theme.js`, `backdrop.js`, `shortcuts.js`, `stats.js`, `timer-drag.js` ou `i18n.js` for removido ou renomeado de `public/web/index.html` (salvo se criado dinamicamente no JS via `id="..."` ou `.id = '...'`).
2. Qualquer atributo `for`, `aria-labelledby`, `aria-describedby` ou `aria-controls` apontar para um ID inexistente na página.
3. Houver qualquer `id="..."` duplicado na mesma página HTML (fora comentários `<!-- ... -->`).

#### Inventário de IDs obrigatórios em `public/web/index.html`
- **Cabeçalho / Utilitários / Sessão (Camada 1):**
  `themeToggle`, `langToggle`, `backdropMotionToggle`, `plansLink`, `btnOpenAboutModal`, `authControls`, `visitorActions`, `userProfile`, `userRoleBadge`, `userName`, `guestAiChip`, `accountBtn`, `logoutBtn`, `guestActions`.
- **Painel do Simulado / Controles (Camada 2):**
  `introGuestAiLimit`, `quizSelector`, `customQuizSelectorWrap`, `customQuizTrigger`, `customQuizValue`, `customQuizDropdown`, `btnOpenCatalog`, `addQuizBtn`, `startBtn`, `btnSetTimer`, `progress`, `percent`, `timer`, `timerConfig`, `timerPreset`, `progressBar`, `examToolbar`, `btnToggleFocus`, `btnToggleList`, `btnQuickSubmit`, `questionPalette`.
- **Área do Quiz, Navegação Foco e Rodapé:**
  `quiz`, `focusNavigation`, `btnPrevQuestion`, `focusIndicator`, `btnNextQuestion`, `shortcutsHint`, `submit`, `reset`, `footerAccountBtn`.
- **Modais (todos preservando estrutura e IDs):**
  - `#uploadModal`: `closeModal`, `modalTitle`, `guestAiNotice`, `guestAiNoticeText`, `tabUploadFile`, `tabGenerateTopic`, `panelUpload`, `panelTopic`, `dropZone`, `uploadSizeLimit`, `fileInput`, `filePreview`, `filePreviewName`, `removeFile`, `uploadNumQuestions`, `uploadCustomQtyWrap`, `uploadCustomQty`, `uploadContext`, `topicInput`, `topicNumQuestions`, `topicCustomQtyWrap`, `topicCustomQty`, `topicDifficulty`, `topicContext`, `uploadStatus`, `uploadStatusText`, `uploadStatusHint`, `uploadError`, `uploadSuccess`, `uploadVisibilityOption`, `isPublicQuiz`, `cancelUpload`, `confirmUpload`, `confirmGenerateTopic`.
  - `#resultModal`: `closeResultModal`, `resultScoreBadge`, `resultModalTitle`, `resultScoreNumber`, `resultScorePercent`, `resultSummaryText`, `resultStatsContainer`, `resultQuestionsList`, `btnRedoQuiz`, `btnTrainMistakes`, `mistakesCount`, `btnRemixMistakes`, `btnCloseResultModal`.
  - `#aboutModal`: `closeAboutModal`, `aboutModalTitle`, `btnCloseAbout`.
  - `#confirmSubmitModal`: `confirmSubmitTitle`, `confirmSubmitMsg`, `confirmSubmitAnswered`, `confirmSubmitTotal`, `confirmSubmitWarning`, `confirmSubmitMissing`, `confirmSubmitCancel`, `confirmSubmitConfirm`.
  - `#catalogModal`: `closeCatalogModal`, `catalogModalTitle`, `catalogSearchInput`, `catalogList`.
  - `#accessModal`: `closeAccessModal`, `accessModalBadge`, `accessModalTitle`, `accessModalText`, `accessOptions`, `accessRegisterLink`, `accessLoginLink`, `accessGuestOption`, `accessGuestLimit`, `accessGuestWindow`, `accessGuestBtn`, `accessFeedback`.
  - `#accountModal`: `closeAccountModal`, `accountModalTitle`, `accountUsername`, `accountEmailTitle`, `accountEmailAddress`, `accountEmailStatus`, `accountEmailFeedback`, `accountResendVerification`, `accountPlanTitle`, `accountPlanSummary`, `accountUsageGeneration`, `accountUsageGenerationLabel`, `accountUsageGenerationCount`, `accountUsageGenerationBar`, `accountUsageRemix`, `accountUsageRemixLabel`, `accountUsageRemixCount`, `accountUsageRemixBar`, `accountPlanRenews`, `accountPlansLink`, `accountDataTitle`, `accountExportLink`, `accountDeleteTitle`, `deleteAccountForm`, `deleteAccountSendCode`, `deleteAccountCodeGroup`, `deleteAccountCode`, `deleteAccountFeedback`, `deleteAccountBtn`.
  - `#noticeModal`: `noticeIcon`, `noticeModalTitle`, `noticeModalMessage`, `btnNoticeClose`.
  - `#customTimerModal`: `closeCustomTimerModal`, `customTimerTitle`, `timerPresetsGrid`, `customTimerForm`, `customTimerMinutesInput`, `customTimerFeedback`, `cancelCustomTimer`, `applyCustomTimer`.
- **IDs gerados dinamicamente por `app.js` (não colocar estaticamente, mas preservar padrão):** `question-card-${index}` e `option-${index}-${i}`.

#### Inventário de seletores de classes e `data-*` usados pelo JS
- **`app.js`:** `.modal-overlay`, `.modal--access`, `.modal--access-compact`, `.access-badge--warning`, `.access-options--single`, `.catalog-tab-btn`, `.catalog-card`, `.catalog-card-btn`, `.catalog-card-header`, `.catalog-card-title`, `.catalog-card-badge`, `.catalog-card-meta`, `.catalog-empty`, `.timer-chip`, `.timer-config-label`, `.timer-config--visible`, `.section-progress-fill[data-percentage]`, `.question`, `.question--active`, `.quiz--focus`, `.palette-btn`, `.answered`, `.active`, `.custom-select-option`, `.custom-select-empty`, `.custom-select-option.is-selected`, `.custom-select-option-check`, `.option`, `.option--hotkey-pulse`, `.topic-chip`, `.drop-zone--active`, `.drop-zone--error`, `.empty-state`, `.results-badge`, `.excellent`, `.good`, `.practice`, `.result-card`, `.is-correct`, `.is-wrong`, `.is-final`, `.hidden`, `.primary`, `.secondary`, `.inline-ai`, `[data-show-for]`, `[data-auth-link]`.
- **`theme.js`:** `.theme-icon`, `.theme-label`.
- **`backdrop.js`:** `[data-backdrop-toggle]`, `.theme-icon`, `.backdrop`, `.is-running`.
- **`shortcuts.js`:** `.modal-overlay:not([hidden])`, `.option-kbd`.
- **`i18n.js`:** `[data-lang-toggle]`, `.lang-code`, `[translate="no"]`.
- **`timer-drag.js`:** `.timer-resize-handle`, `.timer--custom`, `.is-dragging`, `.is-resizing`, `.timer-config--visible`.
- **`tests/test_pagina_produto.py:175,181`:** exige em `index.html` exatamente `<a href="/planos" id="plansLink"` e `<a href="/produto">Produto e planos</a>` no rodapé.
- **`tests/test_dominio_acely.py:101-126`:** exige `<link rel="manifest" href="/site.webmanifest">`, `<link rel="canonical" href="https://acely.com.br/app">`, `og:url`, `og:image`, e JSON-LD válido em `index.html`.

### 2.2 Acessibilidade e Responsividade Mobile
1. **Alvos de toque (`capture_baseline.py` `LAYOUT_CHECK` linhas 68–82):**
   - Em viewports `< 600 px` (ex.: celular `390x844`), todo elemento interativo visível (`a[href]`, `button`, `input`, `select`, `textarea`, `[role="button"]`, exceto `a` inline dentro de texto) deve medir **no mínimo `44x44` px**.
   - **Atenção na nova Camada 1:** botões de ícone/idioma/tema/conta no cabeçalho mobile devem manter `min-width: 44px; min-height: 44px` em `@media (max-width: 768px)` (e `guest-action-link` `min-height: 44px`).
2. **Proibição de `overflow-x` (`capture_baseline.py:66`):**
   - `document.documentElement.scrollWidth - window.innerWidth` deve ser `0` em desktop (`1440x900`), tablet (`768x1024`) e celular (`390x844`).
   - Manter `html, body { overflow-x: clip; }` (`styles.css:151`), pois `overflow-x: hidden` quebraria `position: sticky` de `.focus-navigation` / `.results-footer`.
3. **Foco visível e teclado:**
   - Todos os elementos interativos mantêm `:focus-visible` com `outline: 2px solid` + `outline-offset` (no escuro, `#FF7A5C` com `--focus-ring`).
   - Preservar `trapFocus()` nos modais (`app.js:53`), `aria-modal="true"`, `role="dialog"` / `role="alertdialog"` e `aria-labelledby`.
   - Manter `.skip-link` funcional apontando para `#quiz` (com `scroll-margin-top` suficiente para não ficar atrás da barra fixa).

### 2.3 Regras de i18n (`i18n.js` e `en.js`)
1. **Texto-fonte:** O português escrito no HTML/JS é a chave do dicionário em `public/web/modules/i18n/en.js`.
2. **Todo texto visível novo** (incluindo `title`, `placeholder`, `aria-label`, `alt`, `label`, `data-topic` — ver `ATTRIBUTES` em `i18n.js:19`) deve possuir chave **idêntica** em `en.js`, respeitando R3: caixa normal, sem ponto de exclamação, mensagens calmas e específicas.
3. **`translate="no"` (R3):**
   - Já presente em `#langToggle`, `#accountEmailAddress`, marca `Acely` em `inicio.html` e `produto.html`.
   - **Verificação pendente/recomendada para Fase 3 em `/app`:** R3 determina `translate="no"` em questões e nomes de simulados (além da marca `Acely` na barra superior, se aplicável). Atualmente `renderQuestions()` (`app.js:693`), `renderCustomQuizOptions()` (`app.js:872`) e `renderCatalogList()` (`app.js:1397`) **não** aplicam `translate="no"` no título/enunciado dinâmico da questão ou nome do simulado (apenas os simulados gerados pela IA já vêm no idioma escolhido via parâmetro `language`, mas nomes de simulados públicos da plataforma poderiam ser alterados pelo `MutationObserver` caso coincidam com chaves). Garantir `translate="no"` onde o conteúdo não deve ser traduzido pelo dicionário de UI (e manter os rótulos de UI como "Questão {0}" traduzíveis!).

### 2.4 Auditoria Completa de Versionamento `?v=` (Estado Atual)

Levantamento direto de todos os HTMLs (`public/web/*.html` e `404.html`) e módulos JS (`public/web/*.js` e `public/web/modules/*.js`):

| Recurso | Versão atual | Onde aparece | Situação / Regra |
|---|---|---|---|
| `styles.css` | `?v=30` | Todos os 8 HTMLs em `public/web/` + `404.html` | **Sincronizado.** Subir para `?v=31` em **todos** os HTMLs a cada mudança visual. |
| `app.js` | `?v=26` | `index.html:40` (`modulepreload`) e `index.html:690` (`script`) | **Sincronizado.** Subir ambos juntos para `?v=27` ao alterar `app.js`. |
| `i18n.js` e `en.js` | `?v=10` | `index.html`, `inicio.html`, `login.html`, `register.html`, `reset-password.html`, `produto.html`, `app.js`, `auth_page.js`, `inicio.js`, `produto.js`, `i18n.js` | **Sincronizado.** `test_pagina_inicio.py::test_single_i18n_version_everywhere` **exige** versão única em todo o projeto! |
| `theme.js` | `?v=9` | `index.html:42`, `app.js:2`, `produto.js:10` | **Sincronizado.** Se alterado na Fase 3, subir em todos os 3 lugares! |
| `backdrop.js` | `?v=8` (e **`?v=7` em `404.html:36`**) | `index.html`, `login.html`, `register.html`, `reset-password.html`, `termos.html`, `privacidade.html`, `404.html` | **Dessincronia detectada:** `404.html:36` ainda está em `?v=7`. Ao alterar `backdrop.js` na Fase 3, subir para `?v=9` em todos os 7 arquivos (corrigindo `404.html`). |
| `theme-boot.js` | **Sem `?v=`** | `index.html`, `login.html`, `register.html`, `reset-password.html`, `termos.html`, `privacidade.html`, `produto.html`, `404.html` | **Risco de cache (1 dia):** Ao alterar `theme-boot.js` na Fase 3, adicionar `?v=2` em todos esses 8 arquivos. |
| `icons.js` | `?v=6` | `index.html`, `app.js`, `theme.js`, `backdrop.js`, `stats.js` | Sincronizado. |
| `shortcuts.js` | `?v=5` | `index.html`, `app.js` | Sincronizado. |
| `stats.js` | `?v=7` | `index.html`, `app.js` | Sincronizado. |
| `timer-drag.js` | `?v=1` | `index.html`, `app.js` | Sincronizado. |
| `i18n-boot.js` | `?v=1` | `index.html`, `inicio.html`, `login.html`, `register.html`, `reset-password.html`, `produto.html` | Sincronizado. |
| `inicio.css` / `inicio.js` | `?v=1` / `?v=2` | `inicio.html` | Intactos na Missão 1. |

**Regra operacional:** Em módulos ES (`<script type="module">` e `<link rel="modulepreload">`), uma diferença de `?v=` entre o HTML e o `import` dentro de outro `.js` faz o navegador **baixar e instanciar o módulo duas vezes** (quebrando singletons como `instance` de `backdrop.js`, `currentTheme` de `theme.js` e tradução duplicada em `i18n.js`). Sempre atualizar `modulepreload` + `<script>` + `import` com o mesmo `?v=`.

### 2.5 CSP e Mapeamento de Estáticos
1. **CSP (`vercel.json:66` e `api/middleware/http_middleware.py:60`):**
   - `default-src 'self'; script-src 'self' https://va.vercel-scripts.com; style-src 'self'; img-src 'self' data:; connect-src 'self' https://vitals.vercel-insights.com; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'`
   - **Proibições absolutas:** atributo `style="..."` inline no HTML, tags `<style>` inline, `<script>` executável inline (exceto `application/ld+json`), CDNs de fontes/ícones/CSS/JS.
   - Alterações dinâmicas de layout (como largura de barras ou posição do `#timer`) continuam via CSSOM (`el.style.width = ...`, `el.style.setProperty(...)`) em `.js`, que **não** violam `style-src 'self'` (conforme já documentado em `app.js:1139-1140`).
2. **Servidor local (`api/handlers/quiz_handler.py:43-54`):**
   - `STATIC_CONTENT_TYPES` já contempla `.css`, `.js`, `.html`, `.svg`, `.png`, `.ico`, `.woff2`, `.txt`, `.xml`, `.webmanifest`.
   - Toda rota sob `/web/*` lê de `public/web/*` (linhas 690–714), e os HTMLs são servidos em `/`, `/inicio`, `/app`, `/guest`, `/login`, `/register`, `/reset-password`, `/termos`, `/privacidade`, `/produto`, `/planos`. Não há necessidade de alterar `quiz_handler.py` nem `vercel.json`.

---

## 3. Decisão Arquitetural sobre Tokens Compartilhados em `/` (`inicio.html` / `inicio.css`)

### Análise comparativa das opções

| Critério | Opção 1: Extrair `public/web/tokens.css` compartilhado por `/` e `/app` | Opção 2: Manter `/` 100% intacta e alinhar tokens canônicos em `styles.css` |
|---|---|---|
| **Impacto em `/` (`inicio.html` / `inicio.css`)** | Exige alterar `inicio.html` (adicionar `<link rel="stylesheet" href="/web/tokens.css?v=1">`), `inicio.css` (remover/substituir tokens locais) e demais 7 HTMLs para evitar duplicação. | **Zero alteração** em `inicio.css` e `inicio.js`; `/` permanece preservada tal como entregue no PR #85 (`e8853de`). |
| **Impacto em performance / LCP** | Adiciona **+1 requisição CSS bloqueante** de renderização no `<head>` de todas as páginas (ou `@import`, que cria cascata sequencial prejudicial ao FCP/LCP). | Mantém exatamente a cadeia atual (`styles.css` + `inicio.css` em `/`; apenas `styles.css` em `/app`). |
| **Risco de regressão visual em `/`** | Médio: extrair `:root` pode alterar precedência de cascata em `.in-html` / `produto.css` / `login.html`. | **Mínimo**, desde que `styles.css` preserve intactos os tokens consumidos por `inicio.css` (`--font-sans`, `--font-mono`, `--text-xs/sm/md`, `--space-1..6`, `--radius-sm/md/lg`, `--ease-out`) e não altere regras globais não escopadas que afetem `.in-body`. |
| **Manutenibilidade de tokens** | Fonte única formal em `tokens.css`. | Fonte única prática para **todo o app** (`index.html`, `produto.html`, `login.html`, `register.html`, `termos.html`, `privacidade.html`, `404.html`), enquanto `inicio.css` mantém seus 10 tokens `--in-*` já consolidados. |
| **Reversibilidade (Rollback)** | Exige reverter múltiplos HTMLs e criação de novo arquivo. | Trivial: mudanças restritas a `styles.css`, `index.html`, módulos JS de `/app` e bump de `?v=`. |

### Recomendação Técnica para a Fase 2 e Fase 3
**Recomenda-se formalmente a Opção 2: manter `/` (`inicio.html`, `inicio.css`, `inicio.js`, `smooth-scroll.js`, `mural.js`) intacta na Missão 1 e consolidar os tokens canônicos diretamente em `public/web/styles.css`.**

**Condições de segurança obrigatórias ao aplicar a Opção 2 em `styles.css`:**
1. **Não remover nem renomear** em `:root` de `styles.css` os tokens já consumidos por `inicio.css` e `produto.css`: `--font-sans`, `--font-mono`, `--text-xs` (`12px`), `--text-sm` (`14px`), `--text-md` (`16px`), `--space-1` (`4px`) a `--space-6` (`32px`), `--radius-sm` (`8px`), `--radius-md` (`12px`), `--radius-lg` (`16px`), `--ease-out` (`cubic-bezier(0.22, 1, 0.36, 1)`).
2. **Isolamento de estilos da Camada 1 e `/app`:** Toda nova regra visual para a barra flutuante e o painel do simulado de `/app` deve ser escopada por classes próprias (ex.: `.app-nav-wrap`, `.app-nav`, `.exam-panel`) em vez de alterar seletores genéricos (`body`, `header`, `nav`, `h1`, `h2`, `button`), pois `inicio.html` e `produto.html` carregam `styles.css` antes de `inicio.css` e `produto.css`.
3. **Atualização de `?v=` de `styles.css` em `inicio.html`:** Se `styles.css` for atualizado para `?v=31`, decidir na Fase 2 entre atualizar `?v=31` também em `inicio.html` (mantendo o conteúdo funcional/visual de `/` 100% intacto e validando com `capture_baseline.py --only inicio,inicio-menu`) ou manter `inicio.html` sem edição. Pela regra de manter consistência de cache em todo o site (`styles.css?v=30` hoje é igual nos 9 HTMLs), recomenda-se subir `?v=31` de `styles.css` em todos os HTMLs (incluindo `inicio.html`, **apenas** o `?v=` da tag `<link>`) ou verificar no baseline visual de pós-implementação que `/` permanece pixel-idêntica.
4. *Evolução futura:* Caso futuramente `/` receba tema claro ou novo redesign, a extração de `tokens.css` poderá ser feita em missão dedicada à landing page.

---

## 4. Registro Obrigatório do `Dockerfile` (Sem Alterar)

### Evidência verificada no repositório (`develop`, commit `e8853de`)
Arquivo `Dockerfile`, linhas 3 e 17:
- **Linha 3 (Stage 1 — Builder):**
  `FROM python:3.16.0a1-slim@sha256:df293ba3b89f458e1aad6051b62ff1c4fad7b3b52b8147ae9cc4b667f9cf2741 AS builder`
- **Linha 17 (Stage 2 — Runtime):**
  `FROM python:3.16.0a1-slim@sha256:df293ba3b89f458e1aad6051b62ff1c4fad7b3b52b8147ae9cc4b667f9cf2741`

### Análise de risco técnico
1. **Versão Alpha em produção (`3.16.0a1`):** `3.16.0a1` é uma build *alpha* inicial de pré-lançamento, não destinada a workloads de produção.
2. **Quebra de ABI e compilação de extensões nativas:** Durante a fase alpha, a C-API do CPython sofre alterações sem garantia de compatibilidade, podendo causar falhas na compilação ou execução de pacotes com extensões C (como `psycopg2-binary` no Stage 1, ou futuras dependências). Pacotes no PyPI frequentemente não publicam *wheels* binários para versões `cp316` alpha, forçando compilação do zero ou falhando.
3. **Imutabilidade por digest (`@sha256:...`) em imagem alpha:** A imagem fica congelada numa snapshot alpha sem correções de segurança (CVEs) ou bugfixes da série estável.
4. **Divergência de ambiente:** Pode gerar comportamento diferente entre o container Docker local/staging e os ambientes de CI/Vercel.

### Recomendação formal
- **Ação na Missão 1:** **Nenhuma alteração** no `Dockerfile` (conforme R1.C e R3).
- **Ação recomendada fora da Missão 1:** Criar uma **tarefa própria e branch dedicada** (ex.: `chore/dockerfile-python-3.15`) para reverter a imagem base dos dois estágios (`builder` e `runtime`) para **`python:3.15-slim`** (preferencialmente versão patch estável mais recente de 3.15 com digest `@sha256` atualizado e validado contra `requirements.txt`, build Docker e suíte `unittest`).

---

## 5. Plano de Riscos, Ordem de Implementação Segura (Fase 3) e Critérios de Rollback

### 5.1 Matriz de Riscos Arquiteturais

| ID | Risco | Impacto | Mitigação obrigatória |
|---|---|---|---|
| **R-01** | **Contraste WCAG AA em `#FF7A5C`:** texto branco sobre `#FF7A5C` dá ~2,6:1 (reprova AA); `#FF7A5C` sobre papel claro `#f4f0e8` dá ~2,3:1. | Alto (A11y) | Usar `--btn-primary-text: #000000` sobre `#FF7A5C` (8,9:1) no escuro; manter `#c9462a` + `#ffffff` no modo claro. Validar todos os estados (`hover`, `active`, badges, `.btn-quick-submit`). |
| **R-02** | **Vazamento de estilos / regressão em `/`, `/produto` e `/login`:** `styles.css` é compartilhado por todas as páginas. | Alto | Escopar novos estilos da navegação/painel de `/app` (`.app-nav*`, `.exam-panel`); manter tokens de `inicio.css` e `produto.css` intactos; rodar baseline visual também em `inicio`, `produto`, `login`, `register`. |
| **R-03** | **Colisão de `z-index` entre Camada 1 fixa, `#timer` e `.custom-select-dropdown`:** barra fixa cobrindo `#timer` ou dropdown cortado atrás dos cards. | Alto | Adotar a hierarquia canônica de `z-index` (Seção 1.4); posicionar `#timer` padrão abaixo da Camada 1 (`top: ~88px`); proibir `overflow: hidden` / `transform` permanente no `.exam-panel`. |
| **R-04** | **`scrollIntoView` encoberto pela Camada 1 fixa:** `app.js` usa `scrollIntoView({ block: 'start' })` em 7 pontos. | Médio | Definir `scroll-margin-top` nas `.question` e `#quiz` igual à altura da Camada 1 + folga; criar helper de scroll em `app.js` que respeite `prefers-reduced-motion`. |
| **R-05** | **Vazamento de memória / limite de contextos WebGL (`backdrop.js`):** criar/destruir contextos WebGL a cada prova pode atingir limite do browser. | Médio | Usar suspensão limpa (`stopLoop()` + ocultar canvas + pausar listeners de ponteiro) reutilizando o mesmo contexto único da página, e só chamar `destroy()` + `loseContext()` se necessário no encerramento. |
| **R-06** | **Cache obsoleto ou módulo JS duplicado:** `theme-boot.js` não tem `?v=`; `404.html` tem `backdrop.js?v=7`; `i18n.js` exige versão única. | Alto (Testes/Prod) | Adicionar `?v=2` em `theme-boot.js`, alinhar `backdrop.js?v=9` (inclusive em `404.html`), manter `i18n.js?v=10` (ou bump unificado) e `styles.css`/`app.js` sincronizados entre `modulepreload`, `<script>` e `import`. |
| **R-07** | **Quebra do contrato de IDs ou i18n no CI:** remoção/duplicação de ID no menu responsivo ou texto novo sem chave em `en.js`. | Alto (CI) | Manter 1 único conjunto de IDs no HTML (sem clonar botões no DOM mobile); adicionar traduções exatas em `en.js` antes de finalizar; executar `unittest discover tests`. |
| **R-08** | **Estouro horizontal ou alvo < 44 px no mobile (390 px):** barra global com muitos botões em uma linha. | Médio (Visual/A11y) | Testar layout mobile em 390×844 com `capture_baseline.py`, garantindo `min-height: 44px; min-width: 44px` e `overflow-x: 0`. |

### 5.2 Ordem de Implementação Segura (para a Fase 3 futura)

Executar em pequenos passos verificáveis na branch `feature/m1-app-redesign` (criada a partir de `develop`), **um agente por arquivo por vez**:

1. **Passo 1 — Tema padrão escuro e `theme-color` (`theme-boot.js`, `theme.js`, `index.html`):**
   - Adicionar `data-default-theme="dark"` em `index.html` e `meta[name="theme-color" content="#000000"]`.
   - Atualizar `theme-boot.js` e `theme.js` para ler `data-default-theme` quando `localStorage` estiver vazio, ajustar `theme-color` escuro para `#000000` e ajustar ciclo de `THEMES`.
   - Atualizar `?v=` de `theme-boot.js` e `theme.js` nos HTMLs/JS afetados.
   - *Verificação:* `test_ui_contract.py` + inspeção de FOUC com `localStorage` limpo.
2. **Passo 2 — Tokens de cor `#000000` + `#FF7A5C` e tokens de movimento em `styles.css`:**
   - Atualizar `[data-theme="dark"]` em `styles.css` (`#000000`, `#181818`, `#1F1F1F`, `#272727`, `#313131`, `#EDEDED`, `#9B9B9B`, `#FF7A5C`, `--btn-primary-text: #000000`, `--backdrop-*` compatíveis).
   - Adicionar os tokens de escala faltantes e normalizar transições `< 200ms` / curvas diferentes de `--ease-out`.
   - *Verificação:* conferir contraste AA nos dois temas e que `/` (`inicio.html`) e `/produto` não sofreram alteração visual.
3. **Passo 3 — Ciclo de vida do WebGL em `backdrop.js` e integração de estado em `app.js`:**
   - Implementar `setBackdropSuspended(boolean)` (pausa rAF, oculta canvas, oculta `#backdropMotionToggle`, pausa listeners de mouse) em `backdrop.js`.
   - Integrar em `app.js` nos pontos de início de prova (`startTimer`, 1ª resposta, catálogo), finalização (`handleSubmitQuiz`) e reset/troca (`#reset`, `#btnRedoQuiz`, `#quizSelector`).
   - *Verificação:* confirmar no DevTools/Performance que `requestAnimationFrame` para 100% durante a prova e `#000000` fica chapado.
4. **Passo 4 — Navegação em duas camadas (`index.html`, `styles.css`, ajustes de scroll/i18n em `app.js` e `en.js`):**
   - Reestruturar o topo de `index.html` em Camada 1 (`.app-nav-wrap` / `.app-nav`) + Camada 2 (`.exam-panel`), preservando **todos** os IDs obrigatórios e `aria-*` sem duplicação.
   - Aplicar a tabela de `z-index`, reposicionar `#timer` padrão abaixo da Camada 1, adicionar `scroll-margin-top` nas `.question` e helper de `scrollIntoView` respeitando `prefers-reduced-motion` em `app.js`.
   - Adicionar `translate="no"` em nomes de simulados/questões dinâmicas onde cabível e novas chaves PT → EN em `en.js`.
5. **Passo 5 — Sincronia final de `?v=` e Portões de Qualidade:**
   - Subir `?v=` de `styles.css`, `app.js`, `backdrop.js`, `theme.js`, `theme-boot.js` (e `i18n.js`/`en.js` se alterados) em **todos** os HTMLs e imports JS (incluindo `404.html`).
   - Rodar suíte completa e captura visual de verificação.

### 5.3 Critérios de Verificação e Rollback

#### Portões obrigatórios antes de concluir a Fase 3 (PR para `develop`)
1. `python -m unittest discover tests` (com `ADMIN_PASSWORD` configurado) — **100% aprovado**, cobrindo `test_ui_contract.py`, `test_pagina_inicio.py` (`test_single_i18n_version_everywhere`), `test_pagina_produto.py`, `test_dominio_acely.py`, `test_seguranca.py`.
2. `ruff check .` e `ruff format --check .` — **0 erros** (se código Python for tocado; para frontend, garantir ausência de regressão).
3. `python tests/visual/capture_baseline.py --label after` e `--lang en` (desktop `1440×900`, tablet `768×1024`, celular `390×844`, claro e escuro):
   - Zero falhas de `LAYOUT` (`scrollWidth <= innerWidth`);
   - Zero avisos novos de alvo `< 44 px` no celular;
   - Comparação visual antes/depois confirmando `/`, `/produto` e `/login` íntegras e `/app` com as 5 decisões aplicadas.
4. Verificação manual/DevTools de WebGL: durante prova ativa, `rafId === 0` e `<canvas class="backdrop">` oculto/inativo; fora de prova, animação rodando em até 30 FPS e pausando com `prefers-reduced-motion` ou aba oculta.

#### Critérios e Procedimento de Rollback
- **Gatilhos de rollback:** falha de contrato em produção, regressão de contraste/legibilidade, bloqueio de interação no `#timer` ou dropdown, erro de JS no console em `/app` ou regressão visual em `/`.
- **Rollback imediato (Git/Vercel):**
  1. Como o redesign ocorre isoladamente em branch `feature/*` e arquivos estáticos (`public/web/`), sem migrations de banco (`migrations.py`) nem alterações de API (`api/`), o rollback em produção é **instantâneo e sem risco de dados** via **Rollback de Deployment na Vercel** ou `git revert <merge-commit>` na `develop` (via PR de revert, respeitando o fluxo sem force-push).
  2. Caso ocorra problema específico apenas no WebGL em produção, basta acionar um hotfix de 1 linha definindo `setBackdropSuspended(true)` por padrão em `/app`, devolvendo imediatamente o fundo `#000000` chapado sem afetar o restante da interface.
