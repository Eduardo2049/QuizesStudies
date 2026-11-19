# Missão 1 — Fase 1A: Pesquisa Técnica e Features Recomendadas para `/app`

> **Escopo:** Pesquisa baseada exclusivamente em fontes oficiais (**MDN Web Docs**, **web.dev**, **Can I Use** e **W3C / WCAG 2.2**) para orientar o redesign da interface de estudos e simulados (`/app` — `public/web/index.html`, `public/web/styles.css`, `public/web/app.js` e módulos associados) no projeto **Acely**.
> **Restrições respeitadas:** Decisões R2 (1 a 5) e premissas R3 (`AGENTS.md`, `docs/DESIGN_SKILLS.md`, `.claude/skills/landing-page-design/SKILL.md`, `docs/DESIGN_UPGRADE.md`). Nenhum código-fonte da aplicação foi alterado nesta etapa.

---

## 1. Resumo Executivo e Critérios de Ranqueamento

A interface de `/app` combina fluxos densos de leitura e resposta cronometrada (Modo Foco e Modo Lista com até 30 questões, paleta de navegação rápida, cronômetro em `DM Mono`, seletor customizado de questionários e 8 modais interativos) com requisitos estritos de engenharia: **Vanilla CSS e Vanilla JS (ES Modules)**, **CSP `'self'`**, **tema escuro padrão** (`#000000` / `#181818` / `#1F1F1F`, acento `#FF7A5C` com texto escuro `#000000` nos botões cheios), **tema claro opcional**, **WebGL `backdrop.js` desligado durante prova ativa**, **cabeçalho em duas camadas** (barra global flutuante translúcida + painel de controle do simulado), **sem `smooth-scroll.js`**, movimento restrito a `transform` e `opacity` com `--ease-out` (`>= 200ms`) e `prefers-reduced-motion`, **alvos de toque >= 44px no mobile**, e **preservação integral de IDs e atributos `aria-*`** validados por `tests/test_ui_contract.py`.

### Critérios de Avaliação (Impacto × Esforço)

- **Impacto (Alto / Médio / Baixo):**
  - **Alto:** Resolve problemas estruturais das 5 decisões R2 (contraste WCAG AA do novo tema escuro padrão + `#FF7A5C`, foco não encoberto pelo cabeçalho flutuante em duas camadas, estabilidade de layout em mobile/modais, isolamento acessível de modais, performance de renderização em provas longas, eliminação de conflitos de cascata CSS).
  - **Médio:** Melhora ergonomia, responsividade por componente, clareza tipográfica ou robustez de estado com baixo acoplamento.
  - **Baixo:** Ganho estético marginal (nenhum item de baixo impacto foi incluído no top 12).
- **Esforço (Baixo / Médio / Alto):**
  - **Baixo:** Aplicação declarativa em CSS/HTML ou poucas linhas de JS, sem alterar contrato de IDs nem fluxo de eventos em `app.js`.
  - **Médio:** Exige refatoração localizada de regras CSS (ex.: camadas `@layer`, container queries) ou adaptação controlada de atributos/API em `app.js` preservando `tests/test_ui_contract.py`.
  - **Alto:** Reestruturação ampla de markup/JS.

Os **12 itens** abaixo foram ordenados priorizando **maior Impacto e menor Esforço** no topo.

---

## 2. Features Recomendadas (12 itens ranqueados)

### Visão Geral do Ranqueamento

| Posição | Feature / Web API | Impacto | Esforço | Alvo principal em `/app` |
|---|---|---|---|---|
| **#1** | `color-scheme` + `color-mix()` para tokens de contraste AA | Alto | Baixo | `:root` e `[data-theme="dark"]` (`styles.css`, `theme.js`, `theme-boot.js`) |
| **#2** | `scroll-padding-top` + `scroll-margin-top` (WCAG 2.2 SC 2.4.11) | Alto | Baixo | `html`, `#quiz`, `.question` sob cabeçalho em 2 camadas |
| **#3** | `dvh` + `overscroll-behavior: contain` + `scrollbar-gutter: stable` | Alto | Baixo | Shell, modais (`.modal`), `#customQuizDropdown` e alternância Foco/Lista |
| **#4** | `backdrop-filter` restrito à barra global flutuante (com fallback sólido) | Alto | Baixo | Barra global flutuante (camada 1 do cabeçalho, R2.4) |
| **#5** | Atributo HTML `inert` em modais e questões ocultas | Alto | Baixo | `<main>`, `<footer>` e cards inativos do Modo Foco |
| **#6** | `content-visibility: auto` + `contain-intrinsic-size` | Alto | Baixo | `.question` (Modo Lista), `.catalog-card` e `.result-question-item` |
| **#7** | Seletor relacional `:has()` para estados declarativos | Médio | Baixo | `.question`, `.option`, `.hero-bar`, painéis de modal |
| **#8** | `text-wrap: balance` / `pretty` + alvos de toque `>= 44px` (WCAG 2.2 SC 2.5.8) | Médio | Baixo | Títulos de modais/painéis, explicações, paleta `#questionPalette` e mobile |
| **#9** | Screen Wake Lock API (`navigator.wakeLock`) em prova ativa | Médio | Baixo | Ciclo de prova ativa em `app.js` (pareado ao desligamento de `backdrop.js`) |
| **#10** | CSS Cascade Layers (`@layer`) para unificar tokens com `/` | Alto | Médio | Organização de `styles.css` e tokens compartilhados com `inicio.css` |
| **#11** | CSS Container Queries (`@container`) | Alto | Médio | `.exam-toolbar`, `#catalogList`, `#accessOptions`, `#resultStatsContainer` |
| **#12** | Popover API (`popover="auto"`) na Top Layer | Médio | Médio | `#customQuizDropdown` e `#timerConfig` sem conflito de `z-index` |

---

### Detalhamento Técnico e Fontes Oficiais (1 a 12)

#### #1 — `color-scheme` + `color-mix()` para tema escuro padrão e acento `#FF7A5C`
- **Impacto:** Alto | **Esforço:** Baixo
- **Descrição técnica e aplicação concreta em `/app`:**
  - Declarar `color-scheme: dark` no tema escuro padrão (`#000000` / `#181818` / `#1F1F1F`) e `color-scheme: light` quando `[data-theme="light"]` estiver ativo. Isso alinha automaticamente barras de rolagem nativas, `<select id="topicDifficulty">`, `<input type="number">` e controles do navegador ao tema sem CSS proprietário de scrollbar.
  - Em `theme-boot.js` e `theme.js`, alterar o padrão inicial (quando não há preferência salva em `quiz_theme_preference`) de `'system'` para `'dark'`, mantendo `'light'` e `'system'` selecionáveis via `#themeToggle` (Decisão R2.1).
  - Usar `color-mix(in srgb, var(--accent) 16%, transparent)` (e variações de 8% a 28%) para derivar estados hover, foco e badges translúcidos a partir do coral `#FF7A5C` (Decisão R2.3) sem duplicar variáveis `*-rgb`, mantendo botões cheios em `#FF7A5C` com texto `#000000` (contraste ~8,9:1, WCAG AA/AAA).
- **Fontes oficiais e compatibilidade:**
  - MDN (`color-scheme`): https://developer.mozilla.org/en-US/docs/Web/CSS/color-scheme
  - MDN (`color-mix()`): https://developer.mozilla.org/en-US/docs/Web/CSS/color_value/color-mix
  - web.dev (`color-scheme` + `light-dark()`): https://web.dev/articles/color-scheme-dependent-colors-with-light-dark
  - Can I Use (`color-scheme` / `color-mix()`): https://caniuse.com/color-scheme e https://caniuse.com/css-color-mix
  - **Suporte:** `color-scheme` — **Baseline Widely Available** (Chrome/Edge 81+, Firefox 96+, Safari 13+). `color-mix()` — **Baseline Widely Available** desde mai/2023 (Chrome/Edge 111+, Firefox 113+, Safari 16.2+). *(Nota: manter `[data-theme="dark"]` / `[data-theme="light"]` nos tokens principais evita dependência estrita de `light-dark()`, que só entrou no Safari 17.5+).*

#### #2 — `scroll-padding-top` + `scroll-margin-top` para cabeçalho em duas camadas (WCAG 2.2 SC 2.4.11)
- **Impacto:** Alto | **Esforço:** Baixo
- **Descrição técnica e aplicação concreta em `/app`:**
  - Com a arquitetura em duas camadas (Decisão R2.4: barra global flutuante no topo + painel de controle do simulado), saltar para `#quiz` pelo `.skip-link`, navegar pela `#questionPalette` ou avançar com `Tab` pode posicionar o elemento focado ou o enunciado parcialmente atrás da barra fixa.
  - Definir `scroll-padding-top` em `html` (calibrado por token CSS para a altura da barra flutuante + `--space-4`) e `scroll-margin-top` em `#quiz` e `.question` garante que o foco do teclado e a rolagem por âncora mantenham o elemento visível, cumprindo **WCAG 2.2 SC 2.4.11 (Focus Not Obscured — Minimum, Level AA)** sem necessidade de scripts de rolagem.
- **Fontes oficiais e compatibilidade:**
  - MDN (`scroll-padding-top`): https://developer.mozilla.org/en-US/docs/Web/CSS/scroll-padding-top
  - MDN (`scroll-margin-top`): https://developer.mozilla.org/en-US/docs/Web/CSS/scroll-margin-top
  - W3C WCAG 2.2 (SC 2.4.11): https://www.w3.org/TR/WCAG22/#focus-not-obscured-minimum e https://www.w3.org/WAI/WCAG22/Understanding/focus-not-obscured-minimum
  - **Suporte:** **Baseline Widely Available** (Chrome 69+, Firefox 68+, Safari 14.1+/15+).

#### #3 — `dvh` + `overscroll-behavior: contain` + `scrollbar-gutter: stable`
- **Impacto:** Alto | **Esforço:** Baixo
- **Descrição técnica e aplicação concreta em `/app`:**
  - Substituir `100vh` / `92vh` por `100dvh` / `calc(100dvh - ...)` (com fallback `vh` antes da linha) em `body`, `.modal` e `.modal--access-compact` para evitar que barras de endereço móveis cortem o rodapé dos modais (`#uploadModal`, `#resultModal`, `#catalogModal`, `#accountModal`).
  - Aplicar `overscroll-behavior: contain` nos contêineres roláveis (`.modal`, `#catalogList`, `#customQuizDropdown`) para evitar *scroll chaining* para o fundo da prova e impedir *pull-to-refresh* acidental durante uma tentativa em celular.
  - Aplicar `scrollbar-gutter: stable` em `html` (e painéis com rolagem condicional) para eliminar o deslocamento lateral de 15–17px ao alternar entre **Modo Foco** (1 questão, sem barra vertical) e **Modo Lista** (até 30 questões, com barra vertical) ou ao abrir modais.
- **Fontes oficiais e compatibilidade:**
  - MDN (`dvh` / `<length>`): https://developer.mozilla.org/en-US/docs/Web/CSS/length
  - Can I Use (`dvh`): https://caniuse.com/viewport-unit-variants
  - MDN (`overscroll-behavior`): https://developer.mozilla.org/en-US/docs/Web/CSS/overscroll-behavior
  - Can I Use (`overscroll-behavior`): https://caniuse.com/css-overscroll-behavior
  - MDN (`scrollbar-gutter`): https://developer.mozilla.org/en-US/docs/Web/CSS/scrollbar-gutter
  - Can I Use (`scrollbar-gutter`): https://caniuse.com/mdn-css_properties_scrollbar-gutter
  - **Suporte:** `dvh` — **Baseline Widely Available** (Chrome 108+, Firefox 101+, Safari 15.4+). `overscroll-behavior` — amplamente suportado (Chrome 63+, Firefox 59+, Safari 16.0+). `scrollbar-gutter` — **Baseline Newly Available** (Chrome 94+, Firefox 97+, Safari 18.2+; ignorado com segurança em Safari anterior).

#### #4 — `backdrop-filter` isolado na barra global flutuante (com fallback opaco)
- **Impacto:** Alto | **Esforço:** Baixo
- **Descrição técnica e aplicação concreta em `/app`:**
  - Implementar a camada 1 do cabeçalho de `/app` no mesmo padrão da barra flutuante de `/` (`.in-nav`): superfície translúcida `rgba(24, 24, 24, 0.72)` (e equivalente claro no tema claro), borda completa `1px solid #272727` e `-webkit-backdrop-filter: blur(16px); backdrop-filter: blur(16px);`, acompanhada de `@supports not ((backdrop-filter: blur(16px)) or (-webkit-backdrop-filter: blur(16px)))` com fundo sólido `#181818`.
  - Manter o efeito restrito **apenas** a essa barra única de navegação para preservar fluidez de rolagem (especialmente no mobile) e respeitar a regra B4 de `DESIGN_SKILLS.md` nos cards e no painel da prova (fundos chapados `#181818` / `#1F1F1F`).
- **Fontes oficiais e compatibilidade:**
  - MDN (`backdrop-filter`): https://developer.mozilla.org/en-US/docs/Web/CSS/backdrop-filter
  - Can I Use (`backdrop-filter`): https://caniuse.com/css-backdrop-filter
  - **Suporte:** **Baseline Widely Available** (Chrome 76+, Firefox 103+, Safari 9+ com prefixo `-webkit-` e unprefixed em Safari 18+).

#### #5 — Atributo HTML `inert` para isolamento de modais e questões inativas
- **Impacto:** Alto | **Esforço:** Baixo
- **Descrição técnica e aplicação concreta em `/app`:**
  - Atualmente `app.js` usa `trapFocus()` nos 8 modais (`#uploadModal`, `#resultModal`, `#catalogModal`, `#accessModal`, `#accountModal`, `#confirmSubmitModal`, `#noticeModal`, `#customTimerModal`). Ao aplicar `inert = true` em `<main class="shell">` e `<footer class="site-footer">` enquanto qualquer `.modal-overlay` estiver aberto, o navegador bloqueia nativamente foco via `Tab`, cliques, seleção e exposição na árvore de acessibilidade para leitores de tela, sem alterar os IDs dos modais nem quebrar `tests/test_ui_contract.py`.
  - No **Modo Foco**, aplicar `inert` às questões ocultas (`.question[hidden]` ou inativas) reforça que atalhos e leitores de tela interajam exclusivamente com a questão atual.
- **Fontes oficiais e compatibilidade:**
  - MDN (`inert`): https://developer.mozilla.org/en-US/docs/Web/HTML/Global_attributes/inert
  - web.dev (`The inert attribute`): https://web.dev/articles/the-inert-attribute
  - Can I Use (`inert`): https://caniuse.com/inert
  - **Suporte:** **Baseline Widely Available** (Chrome/Edge 102+, Firefox 112+, Safari 15.5+).

#### #6 — `content-visibility: auto` + `contain-intrinsic-size` em listas longas de questões e catálogo
- **Impacto:** Alto | **Esforço:** Baixo
- **Descrição técnica e aplicação concreta em `/app`:**
  - Simulados no **Modo Lista** (até 30 questões), a revisão detalhada em `#resultQuestionsList` e a grade de simulados em `#catalogList` criam dezenas de cards com rádio inputs, badges e textos de explicação.
  - Aplicar `content-visibility: auto; contain-intrinsic-size: auto 260px;` em `.question`, `.result-question-item` e `.catalog-card` permite que o navegador pule layout e pintura dos itens fora da tela, acelerando abertura de simulados extensos e reduzindo latência de interação (INP), sem remover os nós do DOM (preservando `Ctrl+F`, contagem de respostas e acessibilidade).
- **Fontes oficiais e compatibilidade:**
  - MDN (`content-visibility`): https://developer.mozilla.org/en-US/docs/Web/CSS/content-visibility
  - web.dev (`content-visibility`): https://web.dev/articles/content-visibility
  - Can I Use (`content-visibility`): https://caniuse.com/css-content-visibility
  - **Suporte:** **Baseline Newly Available** desde set/2024 (Chrome/Edge 85+, Firefox 125+, Safari 18.0+; navegadores mais antigos ignoram a propriedade sem impacto funcional).

#### #7 — Seletor relacional `:has()` para estados declarativos sem JS extra
- **Impacto:** Médio | **Esforço:** Baixo
- **Descrição técnica e aplicação concreta em `/app`:**
  - `styles.css` já usa `.option:has(input:focus-visible)` na linha 167. Estender o mesmo padrão para `.option:has(input:checked)` (borda `#FF7A5C` ou superfície `#272727` no tema escuro), `.question:has(input:checked)` (marcador discreto de questão respondida sem esperar manipulação de classe em `app.js`), `.hero-bar:has(.visitor-actions:not([hidden]))` e `.modal-panel:has(.upload-error:not([hidden]))`.
  - Mantém o contrato de markup e IDs intacto e reduz a chance de dessincronia visual após ações como `#reset` ou retomada de estado.
- **Fontes oficiais e compatibilidade:**
  - MDN (`:has()`): https://developer.mozilla.org/en-US/docs/Web/CSS/:has
  - Can I Use (`:has()`): https://caniuse.com/css-has
  - web.dev (`5 CSS snippets`): https://web.dev/articles/5-css-snippets-every-front-end-developer-should-know-in-2024
  - **Suporte:** **Baseline Widely Available** desde dez/2023 (Chrome/Edge 105+, Safari 15.4+, Firefox 121+).

#### #8 — `text-wrap: balance` / `pretty` e conformidade WCAG 2.2 SC 2.5.8 (`>= 44px` no mobile)
- **Impacto:** Médio | **Esforço:** Baixo
- **Descrição técnica e aplicação concreta em `/app`:**
  - Cumprir a regra B1 de `docs/DESIGN_SKILLS.md` em todo `/app`: aplicar `text-wrap: balance` nos títulos (`h1`, `.modal-title`, `.results-title`, `.catalog-title`, `.access-title`, `.confirm-submit-title`) e `text-wrap: pretty` (como aprimoramento progressivo) nas introduções, subtítulos de modais e explicações de gabarito para evitar palavras órfãs na última linha.
  - Em conjunto, padronizar alvos de toque `min-height: 44px; min-width: 44px;` no mobile (`<= 768px`) para chips da `#questionPalette`, botões da barra global flutuante, `.modal-close`, `.topic-chip` e links do rodapé — superando o requisito mínimo de **24×24px da WCAG 2.2 SC 2.5.8 (Target Size Minimum)** e atendendo ao script `tests/visual/capture_baseline.py`.
- **Fontes oficiais e compatibilidade:**
  - MDN (`text-wrap`): https://developer.mozilla.org/en-US/docs/Web/CSS/text-wrap
  - Can I Use (`text-wrap: pretty`): https://caniuse.com/mdn-css_properties_text-wrap_pretty
  - W3C WCAG 2.2 (SC 2.5.8): https://www.w3.org/TR/WCAG22/#target-size-minimum e https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum
  - **Suporte:** `text-wrap: balance` — **Baseline 2024** (Chrome 114+, Firefox 121+, Safari 17.5+). `text-wrap: pretty` — Chrome/Edge 117+, Safari 26+, Firefox sem suporte (degradação limpa para quebra padrão).

#### #9 — Screen Wake Lock API (`navigator.wakeLock`) durante simulado ativo
- **Impacto:** Médio | **Esforço:** Baixo
- **Descrição técnica e aplicação concreta em `/app`:**
  - Ao iniciar um simulado (`#startBtn`) no celular ou tablet, estudantes costumam ler enunciados longos sem tocar na tela, fazendo o sistema apagar ou bloquear o visor durante a contagem do cronômetro.
  - Integrar `navigator.wakeLock?.request('screen')` (com `try/catch` silencioso, verificação de suporte e reaquisição no evento `visibilitychange` quando a aba volta a ficar visível) no mesmo controlador de estado "prova ativa" que desativa `backdrop.js` (Decisão R2.2), liberando o lock (`sentinel.release()`) ao finalizar, pausar ou resetar (`#reset`). Zero impacto na CSP `'self'` e degradação transparente se negado por economia de bateria.
- **Fontes oficiais e compatibilidade:**
  - MDN (`Navigator.wakeLock`): https://developer.mozilla.org/en-US/docs/Web/API/Navigator/wakeLock
  - MDN (`WakeLock`): https://developer.mozilla.org/en-US/docs/Web/API/WakeLock
  - web.dev (`Screen Wake Lock supported in all browsers`): https://web.dev/blog/screen-wake-lock-supported-in-all-browsers
  - Can I Use (`wake-lock`): https://caniuse.com/wake-lock
  - **Suporte:** **Baseline Newly Available** (Chrome/Edge 84+, Safari 16.4+, Firefox 126+; requer contexto seguro HTTPS).

#### #10 — CSS Cascade Layers (`@layer`) para organizar `styles.css` e tokens compartilhados
- **Impacto:** Alto | **Esforço:** Médio
- **Descrição técnica e aplicação concreta em `/app`:**
  - `public/web/styles.css` possui atualmente ~4.439 linhas com múltiplas passadas de sobrescrita ao final do arquivo (linhas 4260+) e usos de `!important` em estados de foco e responsividade.
  - Declarar uma ordem explícita no topo (`@layer reset, tokens, base, components, states, overrides;`) permite isolar a camada `tokens` (inclusive facilitando extrair ou compartilhar os tokens `:root` `#000000` / `#181818` / `#1F1F1F` / `#FF7A5C` / `--space-*` / `--text-*` / `--radius-*` / `--ease-out` com `inicio.css`, se aprovado na Fase 2) e garantir previsibilidade de cascata entre o tema escuro padrão e o tema claro opcional sem aumentar especificidade.
- **Fontes oficiais e compatibilidade:**
  - MDN (`@layer`): https://developer.mozilla.org/en-US/docs/Web/CSS/@layer
  - Can I Use (`css-cascade-layers`): https://caniuse.com/css-cascade-layers
  - **Suporte:** **Baseline Widely Available** (Chrome/Edge 99+, Firefox 97+, Safari 15.4+).

#### #11 — CSS Container Queries (`@container`) para componentes adaptativos de `/app`
- **Impacto:** Alto | **Esforço:** Médio
- **Descrição técnica e aplicação concreta em `/app`:**
  - Configurar `container-type: inline-size` nos wrappers do painel de controle do simulado (`.exam-toolbar`, `.quiz-picker`), no grid de catálogo (`#catalogList`), nos cartões de acesso (`#accessOptions`) e no container de estatísticas (`#resultStatsContainer`).
  - Dessa forma, os componentes (como cartões de simulado, métricas de `stats.js` e controles do painel) reorganizam suas colunas e espaçamentos conforme a largura real do contêiner/modal, e não apenas por breakpoints globais da viewport — simplificando a transição desktop/tablet/celular e mantendo todos os seletores e IDs existentes.
- **Fontes oficiais e compatibilidade:**
  - MDN (`CSS container queries`): https://developer.mozilla.org/en-US/docs/Web/CSS/CSS_container_queries
  - web.dev (`Container queries`): https://web.dev/articles/container-queries-and-units-in-action
  - Can I Use (`css-container-queries`): https://caniuse.com/css-container-queries
  - **Suporte:** **Baseline Widely Available** desde fev/2023 (Chrome/Edge 105+, Firefox 110+, Safari 16.0+).

#### #12 — Popover API (`popover="auto"`) na Top Layer para seletor e presets de tempo
- **Impacto:** Médio | **Esforço:** Médio
- **Descrição técnica e aplicação concreta em `/app`:**
  - Migrar painéis flutuantes leves de `/app` — como `#customQuizDropdown` (lista de questionários) e o painel de presets `#timerConfig` — para a **Popover API** (`popover="auto"`), removendo conflitos de `z-index` e `overflow: hidden`/`clip` com a nova barra global flutuante (Decisão R2.4) e herdando fechamento leve (*light dismiss* ao clicar fora ou pressionar `Esc`) diretamente do navegador.
  - A transição de entrada/saída deve continuar usando apenas `opacity` e `transform` com `--ease-out` (`>= 200ms`) e respeitar `@media (prefers-reduced-motion: reduce)`. Requer atenção em `app.js` para manter os IDs `#customQuizTrigger`, `#customQuizDropdown` e `#timerConfig` exigidos por `tests/test_ui_contract.py`.
- **Fontes oficiais e compatibilidade:**
  - MDN (`popover` attribute): https://developer.mozilla.org/en-US/docs/Web/HTML/Global_attributes/popover
  - web.dev (`Popover API lands in Baseline`): https://web.dev/blog/popover-api-lands-in-baseline
  - Can I Use (`popover`): https://caniuse.com/popover
  - **Suporte:** **Baseline Newly Available** (Chrome/Edge 114+, Firefox 125+, Safari 17.0+, com refinamentos de *light-dismiss* no Safari 18.3).

---

## 3. Itens "Fora das Regras" (Descartados)

Os recursos abaixo foram avaliados durante a pesquisa e **devem ser explicitamente evitados** no redesign de `/app` por violarem decisões da Missão 1 (R2), restrições de arquitetura (`AGENTS.md`, R3) ou regras da skill de design (`docs/DESIGN_SKILLS.md`):

| Recurso / Técnica Descartada | Regra Violada | Motivo Técnico do Descarte |
|---|---|---|
| **1. `smooth-scroll.js` (rolagem com inércia em JS, estilo Lenis)** | **R2 — Decisão 5** | Proibido explicitamente em `/app`. Interceptar `wheel` cria latência artificial durante leitura de enunciados extensos, prejudica rolagem com `Ctrl+F` e entra em atrito com tecnologia assistiva. `/app` deve usar rolagem nativa + `scroll-padding-top`. |
| **2. Fundo WebGL (`backdrop.js`) ativo durante o simulado** | **R2 — Decisão 2** | Proibido durante prova em andamento. Manter o shader Perlin/Flow Field rodando a 30fps atrás das questões consome GPU/bateria no mobile e reduz o conforto de leitura no fundo `#000000` chapado. |
| **3. `backdrop-filter` em cards de questão, opções ou overlay de modais** | **`DESIGN_SKILLS.md` B4 + Performance** | Permitido apenas na barra global flutuante (R2.4). Aplicá-lo em 10–30 `.question` ou `.modal-overlay` causa múltiplas passadas de desfoque em GPU, queda de FPS no mobile e viola "fundos chapados". |
| **4. Cross-Document View Transitions (`@view-transition { navigation: auto; }`)** | **Compatibilidade Baseline + R3 / Movimento** | Segundo MDN (`https://developer.mozilla.org/en-US/docs/Web/CSS/@view-transition`) e Can I Use, cross-document view transitions ainda têm suporte parcial/atrás de flag no Firefox estável; além disso, transições entre rotas `/` e `/app` com temas diferentes e WebGL exigem controle rigoroso de `prefers-reduced-motion` e `--ease-out`. |
| **5. `document.startViewTransition()` na troca de questões do Modo Foco** | **R2.5 + `DESIGN_UPGRADE.md` §4.5** | Embora same-document View Transitions seja Baseline recente (MDN `https://developer.mozilla.org/en-US/docs/Web/API/Document/startViewTransition`), capturar snapshots de tela inteira a cada clique em "Próxima" adiciona latência perceptível para interações frequentes de teclado (`W A S D` / `← →`), violando `DESIGN_UPGRADE.md` ("interações frequentes devem ser rápidas"). |
| **6. Scroll-Driven Animations (`animation-timeline: scroll()` / `view()`) em `/app`** | **`DESIGN_SKILLS.md` B7 + R2.5 + Escopo de `/app`** | Embora recém-chegado a Baseline 2026 (`animation-timeline` no Firefox 159+ / Safari 26+), `/app` é ferramenta de estudo e prova cronometrada, não landing page editorial. Animações presas ao scroll em questões distraem e conflitam com o modo de foco. |
| **7. Frameworks CSS/JS e CDNs externas (Tailwind, Bootstrap, React, Vue, GSAP, Google Fonts CDN, ícones via CDN)** | **R3 (`AGENTS.md` §3.4 e §5) + CSP `'self'`** | A CSP em `vercel.json` e `api/middleware/http_middleware.py` bloqueia scripts/estilos/fontes externos (`'self'` apenas). Fontes ficam em `public/web/fonts/` e ícones SVG inline em `public/web/modules/icons.js`. |
| **8. Animar propriedades de layout (`width`, `height`, `top`, `left`) ou durações `< 200ms` / curvas padrão (`ease`, `linear`)** | **`DESIGN_SKILLS.md` B7 + R2.5** | Proibido animar `width` na `#progressBar` ou altura de painéis; apenas `transform` e `opacity` com `--ease-out` (`cubic-bezier(0.22, 1, 0.36, 1)`) e duração `>= 200ms` (e fallback em `prefers-reduced-motion`). |
| **9. Gradientes de fundo (`--bg-gradient` no tema escuro) e bordas unilaterais** | **R2.1 + `DESIGN_SKILLS.md` B4** | O modo escuro de `/app` deve usar superfícies chapadas `#000000`, `#181818`, `#1F1F1F` e linhas completas `#272727`/`#313131` (sem `border-left` isolado nem halo radial de fundo quando em prova). |
| **10. Pesos `800`/`900`, `font-style: italic` e `DM Mono` em rótulos/textos** | **R3 + `DESIGN_SKILLS.md` B1** | Peso máximo 700, zero itálico (inclusive em `<h1>Treino de <em>raciocínio</em></h1>`, onde `em` só pode mudar cor), e `DM Mono` exclusivo para dados numéricos (cronômetro, contadores, pontuação, chip de cota). |
| **11. CSS Anchor Positioning complexo (`anchor-name` / `position-try`) sem fallback** | **Compatibilidade recente (2026) + Complexidade** | Embora Firefox 147 (jan/2026) tenha completado o suporte básico segundo relatórios de compatibilidade, usuários em navegadores com defasagem de alguns meses (iOS/macOS e Linux ESR) ficariam com menus mal posicionados. Melhor usar Popover API + posicionamento CSS previsível junto ao elemento pai ou modal centralizado. |
| **12. `window.alert()`, `window.prompt()`, redirecionamento forçado para `/login` ou controle de cota no cliente** | **R3 + `AGENTS.md` §3.5 e §5** | Proibidos pela arquitetura aberta de `/app` (`#accessModal`, `#noticeModal`, `#customTimerModal` e decisão server-side de cota em `GuestService` / `EntitlementsService`). |

---

## 4. Riscos e Cuidados para a Fase 2 (Consolidação)

1. **Preservação estrita de IDs e seletores (`tests/test_ui_contract.py`):**
   - Ao introduzir a arquitetura de cabeçalho em duas camadas (R2.4) ou evoluir `#customQuizDropdown`/`#timerConfig` para Popover API (#12), **todos os IDs** consultados por `app.js`, `theme.js`, `backdrop.js`, `shortcuts.js`, `stats.js`, `timer-drag.js` e `i18n.js` devem permanecer únicos e presentes no DOM, assim como todos os `for`, `aria-labelledby`, `aria-describedby` e `aria-controls`.
2. **Contraste de `#FF7A5C` nos dois temas (claro e escuro):**
   - No tema escuro (`#000000` / `#181818` / `#1F1F1F`), `#FF7A5C` sobre preto tem contraste alto (~7,4:1 para texto/ícones grandes ou ~8,9:1 com texto `#000000` dentro de botões cheios), **porém** no tema claro opcional (`#f4f0e8` / `#ffffff`) o `#FF7A5C` puro **não** atinge 4,5:1 para texto ou texto branco em botão cheio! A Fase 2 deve garantir que no `[data-theme="light"]` os tokens semânticos (`--accent`, `--accent-text`, `--btn-primary-text`) mantenham contraste WCAG AA (ex.: `#c9462a` com `#ffffff` no claro, ou `#FF7A5C` com `#000000` onde aplicável).
3. **Sincronização entre desligamento de `backdrop.js` e `navigator.wakeLock` (R2.2 + Item #9):**
   - Definir um único estado claro no ciclo de vida da prova em `app.js` (ex.: atributo `data-exam-active="true|false"` em `<body>` ou `document.documentElement` e chamada explícita à API do módulo `backdrop.js`) para pausar/destruir o loop WebGL quando a prova inicia e reativá-lo ao sair/finalizar — evitando `MutationObserver` frágil ou vazamento de contexto WebGL.
4. **Refatoração segura de `styles.css` com `@layer` (Item #10) e tokens de `/`:**
   - Como `inicio.html` carrega **tanto** `styles.css?v=30` quanto `inicio.css?v=1` (ver `public/web/inicio.html:36-37`), qualquer alteração de tokens `:root` ou introdução de `@layer` em `styles.css` precisa ser testada contra `/` (`inicio.html`) e todas as páginas secundárias (`login.html`, `register.html`, `reset-password.html`, `produto.html`, `termos.html`, `privacidade.html`), além de incrementar `?v=` em todos os HTMLs.
5. **Regressão de foco com `inert` e `trapFocus` (Item #5):**
   - Garantir que `releaseFocus()` e a remoção de `inert` rodem **em todos os caminhos de fechamento de modal** (`Esc`, clique no backdrop, botão fechar, submissão assíncrona e troca de modal como `#accessModal` → `#uploadModal`), evitando que `<main>` fique permanentemente `inert`.
6. **Cache-busting e i18n (R3):**
   - Qualquer texto novo introduzido pelos ajustes de acessibilidade ou controles da barra global (inclusive `title`, `aria-label`, `placeholder`) exige chave idêntica em `public/web/modules/i18n/en.js`, mesma versão `?v=` de `i18n.js` em todos os HTMLs e incremento de `?v=` de `styles.css` e `app.js`.
