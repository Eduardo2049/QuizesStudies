# Auditoria de Design e UX — Missão 1 (Fase 1B): Alinhamento visual entre `/app` e `/`

**Data:** 2026-11-18  
**Escopo:** Frente B (Design e UX) — Somente leitura no código da aplicação (`public/web/`, `api/`, `tests/`).  
**Base de código auditada:** Branch `develop` (`e8853de`), arquivos `public/web/inicio.html`, `public/web/inicio.css`, `public/web/modules/inicio.js`, `public/web/index.html`, `public/web/styles.css`, `public/web/app.js`, `public/web/modules/theme.js`, `public/web/modules/theme-boot.js`, `public/web/modules/icons.js`, `public/web/modules/backdrop.js`, `public/web/modules/timer-drag.js`, `public/web/modules/stats.js`, `public/web/modules/shortcuts.js`, `public/web/modules/i18n.js`, `public/web/modules/i18n/en.js` e `tests/test_ui_contract.py`.  
**Referências normativas:** `AGENTS.md`, `docs/DESIGN_SKILLS.md`, `.claude/skills/landing-page-design/SKILL.md`, `docs/DESIGN_UPGRADE.md` e `docs/PLANO_ACELY.md`.

---

## 1. Resumo Executivo e Alinhamento com as 5 Decisões (R2)

A página inicial `/` (`inicio.html` + `inicio.css`) já implementa integralmente a estética de estúdio escuro da skill `landing-page-design`: fundo preto chapado (`#000000`), superfícies elevadas neutras (`#181818` e `#1F1F1F`), linhas sutis (`#272727` e `#313131`), acento coral da marca (`#FF7A5C`) com texto preto (`#000000`), barra superior flutuante translúcida, tipografia `Manrope` + `DM Mono` exclusivo para números, peso máximo `700`, sem itálico e animações em `--ease-out`.

Em contraste, `/app` (`index.html` + `styles.css`) carrega camadas sobrepostas de quatro fases visuais anteriores (`styles.css:1-4439`):
- O tema padrão resolve para `'system'` (`theme-boot.js:8`, `theme.js:101`), abrindo no **tema claro** (papel `#f4f0e8`, coral `#c9462a`, teal `#176b67`) em sistemas configurados para claro.
- O tema escuro atual (`styles.css:100-146`) usa a paleta **"Frosty Gradient"** (cinza `#181818` com gradiente de fundo, botões primários **azuis** `#4359ff` e destaque **roxo** `#a78bfa`), criando ruptura de identidade visual ao navegar de `/` para `/app`.
- O fundo WebGL (`backdrop.js:657`) roda o tempo todo em `/app` (inclusive durante a resolução de questões), competindo com a leitura do enunciado.
- O cabeçalho de `/app` mistura identidade, navegação global, autenticação, seletor de simulado, status e paleta de questões em um único bloco `<header class="hero">`, enquanto `#timer` flutua em `position: fixed` no canto superior direito colidindo com `.hero-utils` e exigindo compensações de margem (`styles.css:2744`, `styles.css:3581-3584`).

Este documento estabelece a auditoria comparativa, a verificação matemática de contraste WCAG AA, a tabela completa de tokens `:root` (escuro padrão e claro opcional), a especificação **Antes vs Depois** por estado e breakpoint (Desktop, Tablet e Celular) em arquitetura de **duas camadas**, e o contrato integral de IDs, classes, `aria-*` e chaves i18n.

---

## 2. Auditoria Comparativa: `/app` vs `/`

### 2.1 Quadro comparativo direto

| Dimensão | `/` (`inicio.html` + `inicio.css`) | `/app` atual (`index.html` + `styles.css` + `app.js`) | Gap / Ação para alinhamento |
| :--- | :--- | :--- | :--- |
| **Tema padrão** | Sempre escuro (`data-theme="dark"` fixo em `inicio.html:2`) | `'system'` por padrão (`theme-boot.js:8`, `theme.js:101`); abre claro se o SO for claro | **Decisão 1:** tornar `'dark'` o padrão quando não houver escolha salva em `quiz_theme_preference`, mantendo `'light'` e `'system'` no seletor (`theme.js`) |
| **Fundo e gradientes** | `#000000` chapado (`--in-bg`); zero gradiente de fundo (`B4`) | `body` usa `background: var(--bg-gradient)` (`styles.css:175`) com `radial-gradient` + `backdrop.js` WebGL permanente | **Decisão 2:** fundo chapado `#000000` (escuro) / `#f4f0e8` (claro); WebGL (`backdrop.js`) ativo só fora de prova em andamento e desligado ao iniciar/responder |
| **Superfícies e bordas** | `--in-surface: #181818`, `--in-surface-2: #1F1F1F`, `--in-line: #272727`, `--in-line-strong: #313131`, borda inteira (`B4`) | Escuro usa `#181818`, `rgba(23,23,26,.9)`, `#1F1F1F`, `#2e2e35`, `#121214`; vários cartões usam `border-left: 3px/4px` (`result-card`, `confirm-submit-warning`, `results-badge`, `result-card-explanation`) | Adotar `#000000` base + `#181818` / `#1F1F1F` + `#272727` / `#313131` no escuro; substituir `border-left` isolados por borda inteira ou indicador interno (regra `B4` de `SKILL.md`: *"Never apply a border to only one side of a card"*) |
| **Acento da marca** | Coral `#FF7A5C` + texto `#000000` (`--in-accent-ink`) | Escuro usa azul `#4359ff` (`--coral`) + roxo `#a78bfa` (`--teal`) + texto branco `#ffffff` nos botões primários | **Decisão 3:** unificar `#FF7A5C` como acento principal no escuro com texto `#000000` em botões cheios; usar verde `#26A69A` / `#38BDB2` ou neutro claro apenas onde semanticamente distinto, sem roxo/azul genérico |
| **Navegação e cabeçalho** | Barra flutuante translúcida (`.in-nav-wrap` / `.in-nav`, `rgba(24,24,24,0.72)` + `backdrop-filter: blur(16px)` + `border: 1px solid #272727` + `radius: 16px`), painel mobile full-height (`.in-menu`) | Bloco estático único (`.hero-bar` + `.hero-top` + `.hero-actions` + `.status` + `.exam-toolbar` + `.question-palette`) + `#timer` em `position: fixed` sobrepondo utilitários; **sem link de volta para `/`** (`hero-brand` é `<div>`) | **Decisão 4:** arquitetura em **2 camadas**: (1) Barra global flutuante translúcida com `<a href="/">` + Catálogo/Planos/Sobre + PT/EN + Tema + Conta; (2) Sub-cabeçalho/painel de controle do simulado abaixo |
| **Tipografia (`B1`)** | Manrope `400..700`; `DM Mono` só em números (`01`, `18:42`, contadores); zero itálico; escala estrita `12/14/16/18/20/24/30/36/48/60/72/96/128` | `h1` usa `clamp(48px, 8vw, 90px)` (`90px` fora da escala) e `line-height: .92`; `--text-lg: 19px` (`styles.css:3520`, fora da escala); `.comparison-table td` em `11.5px` no mobile (`styles.css:3285`, < 12px); várias classes ainda com `text-transform: uppercase` (`styles.css:238, 448, 573, 1021, 1414, 2030, 2175, 2307, 2493, 2511`) | Ajustar `--text-lg` para `18px`; remover `90px` (usar escala `36/48/60/72px`); garantir mínimo `12px` em toda tabela/rótulo; remover `text-transform: uppercase` de rótulos; manter `DM Mono` **somente** em cronômetro, contadores, numeradores, notas e código de 6 dígitos; manter `font-style: normal` e peso `<= 700` |
| **CTAs por tela (`A4`)** | 1 CTA cheio coral por seção (`Começar grátis` na nav é `--sm`, `Criar meu primeiro simulado` no hero) | Múltiplos botões cheios simultâneos quando visitante (`Criar conta grátis` no topo em coral + `Iniciar simulado` + `Conferir respostas`); no escuro, `#btnOpenCatalog` e `#addQuizBtn` ainda têm fundo colorido (`rgba`) | Garantir **1 CTA principal cheio por estado de tela**: no topo global, links quiet/outline; na área de simulado, `Iniciar simulado` (pré-prova) ou `Conferir respostas` (em prova), e `#btnOpenCatalog` / `#addQuizBtn` em contorno limpo em ambos os temas |
| **Ícones (`B6`)** | SVG inline limpo; zero emojis | Usa `icons.js` na maior parte, mas ainda há caracteres soltos no HTML/JS: `▶` (`index.html:134`, `app.js:1406`), `←` / `→` (`index.html:185,189,198,501`), `▾` (`index.html:117`), `↺` (`index.html:384`), `↻` (`index.html:392`), `✓` / `✗` (`app.js:1170`), `&times;` (`modal-close`) | Padronizar setas, play, fechar (`x`), reload e check com SVGs inline de `icons.js` (estilo Phosphor, `stroke-width: 2` ou `1.5`), mantendo compatibilidade com `i18n/en.js` |
| **Texto e idioma (`B8`, `R3`)** | Caixa normal, sem exclamação, sem travessão como pontuação (`·` no título), `translate="no"` em marca/temas/números | `index.html:6` usa travessão `—`; há Title Case em `'Acely — Treino de Raciocínio'`, `'Opções Rápidas:'`, `'Biblioteca de Estudos'`, `'Simulado Incompleto'`, `'Erro de Carregamento'`, `'Erro de Conexão'`, `'Explicação Didática'`, `'Desempenho Excepcional'`; **falta `translate="no"`** nas questões (`#quiz`), no nome dos simulados (`#customQuizValue`, `#customQuizDropdown`, `#catalogList`) e na revisão (`#resultQuestionsList`) | Aplicar `translate="no"` nos contêineres de conteúdo dinâmico dos simulados (questões, alternativas, explicações, nomes de simulados); padronizar novos textos em caixa normal e sem `!` (e atualizar `en.js` em sincronia caso títulos existentes sejam normalizados) |
| **Foco visível (`B9`)** | `outline: 2px solid var(--in-accent); outline-offset: 3px;` em `:focus-visible` (`inicio.css:60`) | `outline: 2px solid var(--teal) !important; box-shadow: 0 0 0 3px var(--focus-ring) !important;` (`styles.css:162-164`); força `!important` global | Unificar `--line-focus` para `#FF7A5C` (escuro) e `#176b67` (claro) e `--focus-ring` coral suave no escuro; remover necessidade de `!important` onde possível preservando foco nítido em `summary`, `[role="button"]`, radios e opções |
| **Movimento (`B7`, `R2.5`)** | `smooth-scroll.js` próprio + `IntersectionObserver` + `cubic-bezier(0.22, 1, 0.36, 1)` >= 300ms + só `transform`/`opacity` | Usa `ease` padrão em `fadeIn` (`styles.css:679`), `slideUp` (`696`), `optionPulse` (`599`), `fadeInFocus` (`2007`); `authFadeIn` usa `180ms` (`1205`); `#progressBar` anima `width` (`543, 3444`); `prefers-reduced-motion` zera durações para `0.01ms !important` (`3493`) | **Sem `smooth-scroll.js` em `/app`** (rolagem nativa); trocar `ease` / `180ms` por `var(--ease-out)` e `>= 200ms`; trocar `#progressBar` de `width` para `transform: scaleX(...)`; em `prefers-reduced-motion`, trocar deslocamentos por opacidade suave sem `0.01ms` destrutivo |
| **Alvos de toque mobile** | `44px` em `.in-logo`, `.in-icon-btn`, `.in-menu-toggle`, `.in-switch-btn`, `.in-footer-links a` (`inicio.css:685-710`) | Maioria em `44px`, porém **falhas reais detectadas**: `.footer-link` sobrescrito por `min-height: 32px` na linha `4178` após a `@media` da linha `3668`; `#timer` no mobile (`3850`) fica com ~28px de altura; `.file-preview-remove` (`895`) e `.btn-auth-logout` (`1040`) sem `min-width: 44px` no mobile | Corrigir cascata de `.footer-link`, garantir `min-height: 44px; min-width: 44px` em todos os controles interativos no mobile (`#timer`, fechar arquivo, `Sair`, `Conta`, links de rodapé, paleta) |

### 2.2 Verificação de Contraste WCAG 2.1 (AA / AAA)

Cálculo exato pela fórmula oficial de luminância relativa da W3C WCAG 2.1 ($L = 0.2126 R + 0.7152 G + 0.0722 B$ e razão $CR = (L_1 + 0.05)/(L_2 + 0.05)$). Critérios: **texto normal ≥ 4,5:1 (AA)** / **≥ 7,0:1 (AAA)**; **texto grande (≥ 18pt ou ≥ 14pt bold) e componentes de UI/foco (WCAG 1.4.11) ≥ 3,0:1**.

#### Tema Escuro Proposto (Padrão em `/app` — alinhado a `/`)

| Par de cores (Frente vs Fundo) | Uso na interface | Razão WCAG 2.1 | Resultado | Observação de design |
| :--- | :--- | :---: | :---: | :--- |
| `#000000` sobre `#FF7A5C` | Texto de botões primários cheios (`--in-accent-ink` / `--btn-primary-text` sobre `--coral`) | **8,19 : 1** | **AAA** (≥ 7:1) | Nota: `inicio.css:32` comenta `8,9:1`; o cálculo exato W3C sRGB é `8,19:1` — ambos aprovados com folga AAA |
| `#111111` sobre `#FF7A5C` | Alternativa de tinta escura em botão cheio coral | **7,36 : 1** | **AAA** (≥ 7:1) | Válido, porém `#000000` mantém paridade exata com `inicio.css:32` |
| `#000000` sobre `#FF8F75` | Hover de botão primário cheio (`--coral-hover`) | **9,44 : 1** | **AAA** (≥ 7:1) | Igual ao `.in-btn--primary:hover` (`inicio.css:109`) |
| `#FFFFFF` sobre `#FF7A5C` | **Anti-padrão atual se mantido `#ffffff` de `styles.css:121`** | **2,56 : 1** | **REPROVADO** | Proibido usar texto branco sobre `#FF7A5C`; obrigatório trocar `--btn-primary-text` para `#000000` |
| `#FF7A5C` sobre `#000000` | Acento, ícones, bordas ativas e foco sobre fundo base | **8,19 : 1** | **AAA** | Aprovado para texto normal, ícones e foco 1.4.11 |
| `#FF7A5C` sobre `#181818` | Texto/ícone/borda ativa sobre superfície 1 (cards, barra flutuante, modais) | **6,93 : 1** | **AA** (quase AAA) | Aprovado com ampla margem para texto normal e UI |
| `#FF7A5C` sobre `#1F1F1F` | Texto/ícone/borda ativa sobre superfície 2 (sub-cards, opções, abas) | **6,43 : 1** | **AA** | Aprovado para texto normal (≥ 4,5:1) e UI (≥ 3,0:1) |
| `#FF7A5C` sobre `#272727` | Texto/ícone sobre superfície 3 ou hover elevado | **5,83 : 1** | **AA** | Aprovado para texto normal |
| `#FF8F75` sobre `#1F1F1F` (ou pill `14%` coral) | `--accent-text` em texto pequeno sobre fundos tintados de coral | **7,41 : 1** (s/ `#1F1F1F`) / **~6,1 : 1** (s/ pill) | **AA / AAA** | Garante AA mesmo dentro de `.coral-glow` / `.results-badge.practice` |
| `#EDEDED` sobre `#000000` | Texto principal sobre fundo da página | **17,94 : 1** | **AAA** | Igual a `inicio.css:29` |
| `#EDEDED` sobre `#181818` | Texto principal em cards e modais | **15,17 : 1** | **AAA** | Excelente legibilidade em estudo prolongado |
| `#EDEDED` sobre `#1F1F1F` | Texto principal em alternativas, inputs e dropdowns | **14,08 : 1** | **AAA** | Excelente |
| `#9B9B9B` sobre `#000000` | Texto secundário (`--muted`) sobre fundo | **7,56 : 1** | **AAA** | (`inicio.css:30` cita `7,4:1`; cálculo exato `7,56:1`) |
| `#9B9B9B` sobre `#181818` | Texto secundário em cards e barra superior | **6,39 : 1** | **AA** | Aprovado para 12px/14px |
| `#9B9B9B` sobre `#1F1F1F` | Texto secundário em sub-cards e abas | **5,93 : 1** | **AA** | Aprovado para 12px/14px |
| `#6FDC9A` sobre `#181818` / `#1F1F1F` | `--success` (acerto / confirmação) | **10,61 : 1** / **9,84 : 1** | **AAA** | Mantido |
| `#FF8A7A` sobre `#181818` / `#1F1F1F` | `--error` (erro / alerta crítico) | **7,59 : 1** / **7,04 : 1** | **AAA** | Mantido |
| `#F2B866` sobre `#181818` / `#000000` | `--orange` (aviso / caderno de erros; tinta `#000000` sobre `#F2B866` = `11,76:1`) | **9,94 : 1** | **AAA** | Botão `.btn-mistakes` com texto `#000000` |
| `#272727` / `#313131` sobre `#181818` | Linhas divisórias e bordas de cards | `1,19:1` / `1,36:1` | **Divisória estrutural** | **Atenção WCAG 1.4.11:** válido para divisórias e cards com contraste de fundo (`#181818` vs `#000000`), porém inputs, checkboxes/radios e botões contorno interativos devem usar `--line-interactive` (`#525252` = `2,33:1` no `#181818`, ou `#6B6B6B` = `3,64:1` no `#181818` e `4,01:1` no `#000000`) ou preencher fundo distinto (`#1F1F1F` sobre `#000000`) |

#### Tema Claro Opcional (Mantido via `theme.js`)

| Par de cores | Uso | Razão WCAG 2.1 | Resultado |
| :--- | :--- | :---: | :---: |
| `#FFFFFF` sobre `#C9462A` | Botão primário claro (`--coral` + `--btn-primary-text`) | **4,83 : 1** | **AA** (comentário `styles.css:63` cita `4,78:1`) |
| `#B23A20` sobre `#F4F0E8` | `--accent-text` sobre papel | **5,24 : 1** | **AA** |
| `#176B67` sobre `#F4F0E8` | `--teal` (foco, bordas ativas, links secundários) sobre papel | **5,63 : 1** | **AA** |
| `#182326` sobre `#F4F0E8` | `--ink` sobre papel | **13,86 : 1** | **AAA** |
| `#5B635E` sobre `#F4F0E8` | `--muted` sobre papel | **5,41 : 1** | **AA** |

---

## 3. Mapeamento Completo de Tokens (`:root`)

### 3.1 Inventário lado a lado (Atual: `inicio.css` vs `styles.css`)

| Categoria | Token em `inicio.css` (`.in-html`) | Token atual em `styles.css` (`:root` claro) | Token atual em `styles.css` (`[data-theme="dark"]`) | Diagnóstico |
| :--- | :--- | :--- | :--- | :--- |
| **Fundo página** | `--in-bg: #000000` | `--paper: #f4f0e8` + `--bg-gradient` | `--paper: #181818` + `--bg-gradient` (azul radial) | Escuro de `/app` usa `#181818` + gradiente em vez de `#000000` chapado |
| **Superfície 1** | `--in-surface: #181818` | `--card-bg: rgba(255,255,255,0.85)` | `--card-bg: rgba(23,23,26,0.90)` | Tom azulado `23,23,26` destoa do `#181818` neutro de `/` |
| **Superfície 2** | `--in-surface-2: #1F1F1F` | `--card-solid: #ffffff` | `--card-solid: #1F1F1F` | Alinhar `#181818` (cards) e `#1F1F1F` (elementos elevados/inputs/dropdowns) |
| **Nav translúcida** | `--in-nav-bg: rgba(24,24,24,0.72)` | *(não existe)* | *(não existe)* | Novo token `--nav-bg` necessário para a Camada 1 |
| **Bordas** | `--in-line: #272727`<br>`--in-line-strong: #313131` | `--line: #d8d0c3`<br>`--input-border: #d8d0c3` | `--line: #2e2e35`<br>`--input-border: #2e2e35` | `#2e2e35` tem matiz arroxeada; alinhar a `#272727` / `#313131` + `--line-interactive` para WCAG 1.4.11 |
| **Texto** | `--in-text: #EDEDED`<br>`--in-muted: #9B9B9B` | `--ink: #182326`<br>`--muted: #5b635e` | `--ink: #d4d4d8`<br>`--muted: #9d9da8` | Alinhar escuro para `#EDEDED` e `#9B9B9B` |
| **Acento primário** | `--in-accent: #FF7A5C`<br>`--in-accent-ink: #000000` | `--coral: #c9462a`<br>`--coral-dark: #a8341b`<br>`--btn-primary-text: #ffffff` | `--coral: #4359ff`<br>`--coral-dark: #3446e6`<br>`--btn-primary-text: #ffffff` | Trocar azul `#4359ff` por `#FF7A5C` (`--coral-dark` hover `#FF8F75`), `--coral-rgb: 255, 122, 92` e `--btn-primary-text: #000000` |
| **Acento secundário / UI** | *(não usa azul/roxo; usa `#FF7A5C` e neutro)* | `--teal: #176b67`<br>`--teal-dark: #0f4e4b` | `--teal: #a78bfa`<br>`--teal-dark: #c4b5fd` | No escuro, `--teal` hoje pinta h1 `em`, foco, abas ativas, opções selecionadas, ícones e botões contorno de roxo! Deve migrar para coral `#FF7A5C` (foco, ativo, seleção) e neutro `#EDEDED`/`#9B9B9B` (contorno secundário) ou teal discreto só onde semântico |
| **Espaçamento** | `--space-7: 40px` .. `--space-11: 96px` (herda `1..6` de `styles.css`) | `--space-1: 4px` .. `--space-6: 32px` | *(herda)* | Faltam `--space-0` (`0`), `--space-05` (`2px`), `--space-7` (`40px`) a `--space-11` (`96px`) em `styles.css` |
| **Tipografia** | Usa `--font-sans`, `--font-mono`, `--text-xs..md` de `styles.css` + valores em `px` da escala | `--text-xs: 12px`, `--text-sm: 14px`, `--text-md: 16px`, `--text-lg: 19px` | *(herda)* | `--text-lg: 19px` viola escala (`18px`); faltam `--text-xl` (`20px`) a `--text-7xl` (`72px`) |
| **Raios** | `--radius-xl: 24px` (herda `sm..lg` de `styles.css`) | `--radius-sm: 8px`, `--radius-md: 12px`, `--radius-lg: 16px` | *(herda)* | Falta `--radius-xl: 24px` e `--radius-pill: 999px`; muitos seletores em `styles.css` ainda usam `2px`, `4px`, `6px`, `10px` soltos |
| **Movimento** | Usa `--ease-out` de `styles.css` | `--ease-out: cubic-bezier(0.22, 1, 0.36, 1)`, `--ease-in-out`, `--dur-fast: 200ms`, `--dur-base: 300ms`, `--dur-slow: 600ms` | *(herda)* | Faltam `--dur-layout: 500ms`; `styles.css` ainda tem `ease` e `180ms` soltos |
| **WebGL Backdrop** | Não usa `backdrop.js` (usa `mural.js` no hero) | `--backdrop-base: #f4f0e8`, `a: #8ee8d4`, `b: #ffa647`, `line: #176b67` | `--backdrop-base: #181818`, `a: #3a4bd9`, `b: #7c5cf0`, `line: #8f9bff` | No escuro padrão, alinhar `--backdrop-base` para `#000000` e ajustar manchas para estúdio escuro sutil (coral/grafite ou Frosty contido) apenas no lobby |

### 3.2 Tabela de Tokens Proposta para `/app` (Zero Valores Soltos)

> **Regra de implementação:** Todos os tokens estruturais vivem em `:root`; os tokens cromáticos são definidos em `[data-theme="dark"]` (padrão inicial) e `:root` / `[data-theme="light"]` (opcional via `theme.js`). Nenhum componente de `/app` deve declarar hex, `px` de espaçamento, raio ou curva fora desta tabela.

#### A. Tokens de Escala Global (`:root`)

| Token | Valor | Uso obrigatório |
| :--- | :--- | :--- |
| `--font-sans` | `'Manrope', system-ui, sans-serif` | Toda a interface (`font-style: normal`, peso `400/500/600/700`) |
| `--font-mono` | `'DM Mono', ui-monospace, monospace` | **Somente** dados numéricos (`#timer`, contadores, percentuais, `.number`, `.palette-btn`, `.code-digit`, `.usage-meter-count`) |
| `--text-xs` / `--leading-xs` | `12px` / `16px` | Rótulos mínimos, badges, hints, footer meta |
| `--text-sm` / `--leading-sm` | `14px` / `20px` | Botões da barra global, links, textos secundários, inputs |
| `--text-md` / `--leading-md` | `16px` / `24px` | Corpo padrão, alternativas, botão principal |
| `--text-lg` / `--leading-lg` | `18px` / `28px` | **Corrigido de 19px → 18px.** Enunciado de questão (`.question h2`), subtítulos |
| `--text-xl` / `--leading-xl` | `20px` / `28px` | Títulos de modais (`.modal-title`), `h3` de cards |
| `--text-2xl` / `--leading-2xl` | `24px` / `32px` | Cabeçalhos de resultado, `.access-title`, `.code-digit` |
| `--text-3xl` / `--leading-3xl` | `30px` / `36px` | Títulos de página no mobile, menu mobile |
| `--text-4xl` / `--leading-4xl` | `36px` / `40px` | Título `/app` mobile (`h1` compacto) e seções |
| `--text-5xl` / `--leading-5xl` | `48px` / `1` | Título `/app` desktop (`h1` enxuto no painel do simulado) |
| `--space-0` / `--space-05` | `0` / `2px` | Zeros explícitos e micro-ajustes |
| `--space-1` .. `--space-6` | `4px`, `8px`, `12px`, `16px`, `24px`, `32px` | Gaps, paddings de cards, botões e modais |
| `--space-7` .. `--space-11` | `40px`, `48px`, `64px`, `80px`, `96px` | Margem superior da `.shell` sob barra fixa (`--space-11`), seções |
| `--radius-sm` / `--radius-md` / `--radius-lg` / `--radius-xl` / `--radius-pill` | `8px`, `12px`, `16px`, `24px`, `999px` | Fiel a `B3` (regra `interno = externo - gap`). Substituir todos os `2px/4px/6px/10px/20px` soltos |
| `--ease-out` | `cubic-bezier(0.22, 1, 0.36, 1)` | Curva única de transição e animação |
| `--dur-fast` / `--dur-base` / `--dur-layout` / `--dur-slow` | `200ms`, `300ms`, `500ms`, `600ms` | Nunca `< 200ms`. `300ms` para cor/opacidade; `500ms` para `transform`/layout |
| `--z-timer` / `--z-sticky-nav` / `--z-nav` / `--z-timer-mobile` / `--z-overlay` | `10`, `20`, `50`, `95`, `100` | `--z-nav: 50` alinha com `.in-nav-wrap` de `/` (`inicio.css:133`), sempre abaixo de `--z-overlay: 100` |

#### B. Tokens Cromáticos — Escuro Padrão (`[data-theme="dark"]`) vs Claro Opcional (`[data-theme="light"]`)

| Token semântico | `[data-theme="dark"]` (Padrão) | `[data-theme="light"]` (Opcional via `theme.js`) | Papel na interface |
| :--- | :--- | :--- | :--- |
| `--paper` | `#000000` | `#f4f0e8` | Fundo chapado da página (`body { background: var(--paper); }`) |
| `--surface` / `--card-solid` | `#181818` | `#ffffff` | Superfície primária: barra flutuante (translúcida), cards de questão, modais |
| `--surface-2` / `--card-bg` | `#1F1F1F` (ou `rgba(24, 24, 24, 0.88)` onde translúcido sobre WebGL no lobby) | `#ffffff` / `rgba(255, 255, 255, 0.88)` | Superfície elevada secundária: sub-cards, dropdowns, barra de controle, opções |
| `--nav-bg` | `rgba(24, 24, 24, 0.72)` | `rgba(244, 240, 232, 0.82)` | Fundo da barra global flutuante (Camada 1) com `backdrop-filter: blur(16px)` |
| `--nav-menu-bg` | `rgba(0, 0, 0, 0.94)` | `rgba(244, 240, 232, 0.96)` | Painel mobile full-height (`.app-menu`) com `blur(24px)` |
| `--ink` | `#EDEDED` | `#182326` | Texto principal |
| `--muted` | `#9B9B9B` | `#5b635e` | Texto secundário e rótulos quietos |
| `--line` | `#272727` | `#d8d0c3` | Borda estrutural de cards, barra flutuante e divisórias |
| `--line-strong` | `#313131` | `#c5bbb0` | Hover de borda estrutural |
| `--line-interactive` | `#525252` (ou `#6B6B6B` em inputs isolados) | `#9aa09c` | Borda de inputs/botões secundários garantindo discernibilidade WCAG 1.4.11 |
| `--coral` | `#FF7A5C` | `#c9462a` | Acento principal da marca (botão cheio, indicador ativo, barra de progresso) |
| `--coral-dark` (hover) | `#FF8F75` | `#a8341b` | Hover de botão cheio coral |
| `--coral-rgb` | `255, 122, 92` | `201, 70, 42` | Brilhos, seleção suave e badges |
| `--coral-glow` | `rgba(255, 122, 92, 0.16)` | `rgba(201, 70, 42, 0.16)` | Fundo translúcido de estado ativo/coral |
| `--btn-primary-text` | `#000000` | `#ffffff` | Texto sobre `--coral` (`8,19:1` no escuro; `4,83:1` no claro) |
| `--accent-text` | `#FF8F75` | `#b23a20` | Texto em cor de destaque sobre `--surface`/`--surface-2` (`>= 7,4:1` escuro) |
| `--teal` | `#FF7A5C` *(ou neutro/coral unificado)* | `#176b67` | **Atenção:** para compatibilidade dos seletores de `styles.css` sem manter roxo no escuro, `--teal` no tema escuro mapeia para `#FF7A5C` (foco, seleção ativa, ícone em destaque) e `--teal-rgb: 255, 122, 92`; botões secundários (`Explorar`, `Criar`) usam contorno neutro (`--line-strong` + `--ink`) |
| `--option-bg` / `--option-hover` / `--option-checked` | `#1F1F1F` / `#272727` / `rgba(255, 122, 92, 0.14)` | `rgba(255,255,255,0.75)` / `#ffffff` / `#dcebe5` | Estados das alternativas |
| `--input-bg` / `--input-border` | `#121212` / `#313131` | `#ffffff` / `#d8d0c3` | Campos de texto e selects |
| `--line-focus` / `--focus-ring` | `#FF7A5C` / `rgba(255, 122, 92, 0.28)` | `#176b67` / `rgba(23, 107, 103, 0.18)` | Foco visível por teclado |
| `--success` / `--error` / `--orange` | `#6fdc9a` / `#ff8a7a` / `#f2b866` | `#1d7a4e` / `#a33b2b` / `#d97706` | Estados semânticos (com `--btn-orange-text: #000000` no escuro) |
| `--backdrop-base` / `a` / `b` / `line` | `#000000` / `#272727` / `#FF7A5C` / `#FF7A5C` *(mix `0.25`, calm `0.28`, calm-b `0.18`)* | `#f4f0e8` / `#8ee8d4` / `#ffa647` / `#176b67` | **WebGL do lobby** alinhado à identidade coral/preto no escuro (sutil, sem azul/roxo genérico; desligado automaticamente ao iniciar prova) |
| `--shadow-card` / `--shadow-lift` | `none` (estúdio usa borda `#272727`, sem sombra pesada) / `0 16px 40px rgba(0, 0, 0, 0.65)` | `0 4px 16px rgba(24, 35, 38, 0.06)` / `0 10px 28px rgba(24, 35, 38, 0.10)` | No escuro estúdio, superfícies se distinguem por degrau (`#000000` → `#181818` → `#1F1F1F`) + borda `#272727`; sombras ficam só em overlays/flutuantes |

### 3.3 Avaliação de UX: Extrair tokens compartilhados para `/` vs manter `/` intacta

**Situação observada no código:**
1. `public/web/inicio.html:36-37` já importa `/web/styles.css?v=30` **antes** de `/web/inicio.css?v=1`, e `inicio.css` consome diretamente `--font-sans`, `--font-mono`, `--text-xs`, `--text-sm`, `--text-md`, `--space-1..6`, `--radius-sm..lg` e `--ease-out` de `styles.css`.
2. Além disso, `inicio.css:15-21` define localmente `--space-7..11` e `--radius-xl`, e `inicio.css:24-35` define os tokens escuros `--in-bg`, `--in-surface`, `--in-surface-2`, `--in-line`, `--in-line-strong`, `--in-text`, `--in-muted`, `--in-accent`, `--in-accent-ink`, `--in-nav-bg`.
3. `public/web/produto.html` / `produto.css` (citado no mapa de `AGENTS.md`) também compõe o ecossistema público.

**Análise de prós e contras (para decisão conjunta com Arquitetura C na Fase 2):**
- **Opção 1 — Manter `/` (`inicio.html` e `inicio.css`) 100% intacta e consolidar os tokens em `styles.css`:**
  - *Prós:* Zero risco de regressão visual ou de regressão em `tests/test_pagina_inicio.py` / `tests/visual/capture_baseline.py` na página principal (`/`). Como `styles.css` já é carregado por `inicio.html`, adicionar `--space-0`, `--space-7..11`, `--radius-xl` e `--text-xl..5xl` em `:root` de `styles.css` é totalmente retrocompatível com `inicio.css`.
  - *Contras:* Os valores hex (`#000000`, `#181818`, `#1F1F1F`, `#272727`, `#313131`, `#EDEDED`, `#9B9B9B`, `#FF7A5C`) continuam duplicados entre `[data-theme="dark"]` de `styles.css` e `.in-html` de `inicio.css`.
- **Opção 2 — Extrair `public/web/tokens.css` (ou bloco compartilhado em `styles.css`) consumido por `/` e `/app`:**
  - *Prós:* Fonte única de verdade para paleta escura, escala tipográfica, espaçamentos e raios; evita divergência futura.
  - *Contras:* Exige mexer em `inicio.html` (mais um link bloqueante de CSS se for arquivo separado, impactando LCP/FCP de `/`, ou revisão de cascata em `inicio.css`) e retestar o baseline visual completo de `/`.

**Recomendação de UX (Frente B):** **Manter `inicio.html` e `inicio.css` intactas na Missão 1 (Opção 1)** — salvo se C comprovar ganho técnico claro ao extrair `tokens.css` sem adicionar requisição extra bloqueante. Como `inicio.html` já carrega `styles.css`, basta completar a escala (`--space-7..11`, `--radius-xl`, `--text-xl..5xl`, `--dur-layout`) no `:root` de `styles.css` e alinhar o `[data-theme="dark"]` de `styles.css` aos valores exatos de `inicio.css`. O visual percebido pelo usuário entre `/` e `/app` ficará idêntico sem tocar em `/`.

---

## 4. Especificação Antes / Depois por Tela, Estado e Breakpoint

### 4.1 Breakpoints considerados

| Breakpoint | Largura de referência | Regra estrutural principal |
| :--- | :--- | :--- |
| **Desktop** | `≥ 981px` (baseline `1440×900`) | Barra global flutuante em linha única; painel do simulado centralizado (`max-width: 980px`); alternativas em 2 colunas (`grid-template-columns: repeat(2, 1fr)`). |
| **Tablet** | `769px – 980px` (baseline `768×1024`) | Links secundários da barra global compactados (ou drawer se `< 900px`); seletor de questionário ocupa 100% da linha; alternativas em 2 colunas (em `768px` exato já cai na regra `<= 768px` de 1 coluna, evitando aperto). |
| **Celular** | `≤ 768px` e compacto `≤ 380px` (baseline `390×844`) | Barra global compacta com botão de menu full-height (padrão `.in-menu` de `/`); todos os alvos de toque `>= 44×44px`; alternativas em 1 coluna; `overflow-x: clip`; zero colisão com `#timer`. |

---

### 4.2 Arquitetura em Duas Camadas (Cabeçalho Global + Painel de Controle)

#### Antes (Estado atual)
- `.hero-bar` (`index.html:60-102`) mistura marca (sem link para `/`), 5 botões utilitários (`themeToggle`, `langToggle`, `backdropMotionToggle`, `plansLink`, `btnOpenAboutModal`) e `#authControls` dentro do mesmo `<header class="hero">` onde ficam `<h1>`, `.intro`, `.hero-top` (seletor + Explorar + Criar), `.hero-actions` (`Iniciar simulado` + `Tempo`), `.status`, `.exam-toolbar` e `#questionPalette`.
- `#timer` (`styles.css:451`) usa `position: fixed; top: 16px; right: 20px;` e colide visualmente com `.hero-utils` (exigindo `margin-right: 92px` abaixo de `1100px` e `padding-right: 78px` no mobile).

#### Depois (Duas camadas limpas)

**Camada 1 — Barra Superior Global Flutuante e Translúcida (`.app-nav-wrap` / `.app-nav`)**
- **Geometria e visual (alinhado a `.in-nav-wrap` / `.in-nav` de `inicio.css:128-192`):**
  - `position: fixed; top: var(--space-4); left: 0; right: 0; z-index: var(--z-nav);` com container flex centralizado (`padding: 0 var(--space-4)`).
  - `.app-nav`: `background: var(--nav-bg)` (`rgba(24, 24, 24, 0.72)` no escuro), `-webkit-backdrop-filter: blur(16px); backdrop-filter: blur(16px);`, `border: 1px solid var(--line)` (`#272727`), `border-radius: var(--radius-lg)` (`16px`), `padding: var(--space-2) var(--space-2) var(--space-2) var(--space-4)`, `gap: var(--space-3)`.
  - `.shell` ganha `padding-top: var(--space-11)` (`96px` no desktop) e `padding-top: var(--space-10)` (`80px` no mobile) para nunca ficar sob a barra fixa.
- **Conteúdo da Camada 1 (esquerda → direita):**
  1. **Marca com link de retorno (`<a href="/" class="app-brand">`):** `favicon.svg` + `Acely` (`translate="no"`, Manrope `700`, `--text-md`). Restabelece o caminho de volta exigido por `B10`.
  2. **Links de navegação global (desktop `≥ 901px`):**
     - `Explorar simulados` (`#btnOpenCatalog` estilizado como link/botão quiet de navegação ou atalho direto) *ou* manter `#btnOpenCatalog` na Camada 2 e colocar na Camada 1: `Início` (`/`), `Planos` (`#plansLink`, `/planos`), `Por que o Acely` (`#btnOpenAboutModal`). **Nota para C:** Manter `#btnOpenCatalog` na Camada 2 (ao lado do seletor e `Criar simulado`) evita duplicidade e mantém o contrato de `hero-top-buttons`, enquanto a Camada 1 agrupa navegação institucional/global (`Início`, `Planos`, `Por que o Acely`) + utilitários + conta! Alternativamente, um atalho `Catálogo` pode abrir `#catalogModal` — manter `#btnOpenCatalog` único evita IDs duplicados (`test_ui_contract.py:121`).
  3. **Utilitários compactos:**
     - `#langToggle` (`PT` / `EN`, `40×40px` desktop, `44×44px` mobile, borda `--line`, raio `--radius-sm` — respeitando `16 - 8 = 8` da regra `B3`).
     - `#themeToggle` (`40×40px` desktop, `44×44px` mobile, ícone + `.theme-label` `.sr-only` em barra compacta, tooltip completo).
     - `#backdropMotionToggle` (`40×40px` desktop, `44×44px` mobile; visível **somente** quando não há prova em andamento e WebGL está ativo).
  4. **Conta (`#authControls`):**
     - Visitante: `#visitorActions` com `Entrar` (`.guest-action-link` quiet) e `Criar conta` / `Criar conta grátis` (em contorno `--line-strong`, **não** coral cheio para não competir com o CTA principal da tela!).
     - Convidado / Conta: `#userProfile` em pílula compacta (`#userRoleBadge`, `#userName`, `#guestAiChip` em `DM Mono`, `#accountBtn`, `#logoutBtn`, `#guestActions`).
- **Comportamento por breakpoint da Camada 1:**
  - **Desktop (`≥ 981px`):** Barra centrada dimensionada ao conteúdo (`max-width: min(1240px, 100%)`), todos os itens em uma linha.
  - **Tablet (`769px – 980px`):** Links `Planos` e `Por que o Acely` recolhem ou compactam; barra continua em 1 linha sem quebra desordenada.
  - **Celular (`≤ 768px`):** Barra ocupa `width: 100%`, `justify-content: space-between`. Mostra **Marca** à esquerda e **Idioma (`44×44`) + Tema (`44×44`) + Botão Menu (`44×44`)** à direita. Ao tocar no botão Menu (2 linhas que animam em `X` com `--ease-out` `500ms`, idêntico a `.in-menu-toggle` de `/`), abre o painel full-height translúcido (`.app-menu`, `rgba(0,0,0,0.94)` + `blur(24px)`) contendo `Planos`, `Por que o Acely`, `#backdropMotionToggle` e todos os controles de `#authControls` com alvos `>= 44px` e entrada escalonada em `transform`/`opacity`. *Obs. técnica:* `#authControls` deve permanecer em um único nó do DOM ou ser movido/exibido no painel sem duplicar IDs (`test_ui_contract.py`).

**Camada 2 — Sub-cabeçalho / Painel de Controle do Simulado (`.exam-panel` dentro de `<header class="hero">`)**
- **Estrutura visual:** Cartão de superfície `#181818` (`--surface`), borda `1px solid var(--line)` (`#272727`), `border-radius: var(--radius-lg)` (`16px`), `padding: var(--space-5)` (`24px` desktop) / `var(--space-4)` (`16px` mobile).
- **Elementos organizados em grade clara (de cima para baixo):**
  1. **Linha de seleção de questionário (`.hero-top`):** `#customQuizSelectorWrap` (com `#customQuizTrigger` min-height `44px`, fundo `--surface-2` `#1F1F1F`, borda `--line-strong` `#313131`, raio `--radius-sm` `8px`) + `#btnOpenCatalog` (contorno) + `#addQuizBtn` (contorno).
  2. **Linha de comando da prova (`.hero-actions`):**
     - **Antes de iniciar:** `#startBtn` (`Iniciar simulado`, único botão cheio coral `#FF7A5C` com texto `#000000`, altura `48px`, `16px` semibold) + `#btnSetTimer` (contorno secundário, altura `48px`).
     - **Em andamento:** `#startBtn` oculto; barra compacta exibe modo de visualização (`#btnToggleFocus` / `#btnToggleList` em interruptor estilizado como `.in-switch` de `/`: fundo `--paper` `#000000`, ativo em coral `#FF7A5C` texto `#000000` ou `--surface-2` texto `#EDEDED`), **#timer em DM Mono** (ancorado/docked na barra de controle por padrão, mantendo o suporte arrastável de `timer-drag.js` sem colidir com a Camada 1!) e `#btnQuickSubmit` (`Finalizar simulado` em contorno coral `--coral` com texto `--accent-text`, altura `44px`).
  3. **Linha de progresso (`.status` + `.progress-track`):** `#progress` (`0 de 10 respondidas`), `#percent` (em `DM Mono`), barra `.progress-track` (`#272727`, altura `8px`, preenchimento `#progressBar` em `--coral` animado via `transform: scaleX(...)`).
  4. **Paleta de questões (`#questionPalette`):** Chips `38×38px` (desktop) / `44×44px` (mobile) em `DM Mono`: padrão `#1F1F1F` borda `#272727`; respondida fundo `rgba(255, 122, 92, 0.16)` borda `#FF7A5C` texto `#FF8F75`; ativa borda `2px solid #EDEDED` (ou `#FF7A5C` sólido se atual não respondida).

---

### 4.3 Especificação por Estado / Tela e Breakpoint

#### Estado 1 — Lobby / Estado Inicial (Sem prova em andamento → `backdrop.js` ATIVO)

| Aspecto | Antes | Depois |
| :--- | :--- | :--- |
| **Fundo WebGL** | `backdrop.js` ativo com manchas azul/roxo sobre `#181818` (`--backdrop-*`) | `backdrop.js` **ativo** com paleta escura sutil (`#000000` base, acento coral suave `#FF7A5C` e grafite `#272727` no escuro; papel/teal/laranja no claro). Botão `#backdropMotionToggle` visível na Camada 1 |
| **Cabeçalho & Título** | `<h1>Treino de<br><em>raciocínio</em></h1>` até `90px` (com `em` roxo no escuro) + `.intro` | Título compacto em escala (`48px` desktop, `36px` tablet/mobile, peso `600`, `line-height: 1.05`, `text-wrap: balance`) com gradiente sutil `#FFFFFF → #9B9B9B` ou coral discreto sem itálico; `.intro` limitada a `max-width: 680px` (`text-wrap: pretty`) |
| **Visibilidade da prova** | Questões e paleta já aparecem inteiras desde o segundo 0, antes do usuário clicar em `Iniciar simulado` | **Desktop / Tablet / Celular:** O painel de controle (Camada 2) ganha protagonismo limpo acima da dobra com o simulado selecionado em destaque, duração estimada, `#startBtn` (1 CTA cheio coral) e opções `Explorar simulados` / `Criar simulado`. As questões (`#quiz`) ou prévia do simulado ficam logo abaixo em repouso; ao clicar em `#startBtn` **ou** marcar qualquer alternativa (`quiz.addEventListener('change')`), a página entra em estado de **prova ativa** |
| **Breakpoints** | Mobile: `.hero-top-buttons` em 2 colunas apertadas, `#authControls` cai fora do alinhamento, timer fixo reserva `78px` | **Desktop:** Camada 1 flutuante no topo + Painel Camada 2 em `max-width: 980px`.<br>**Tablet (`769–980px`):** Seletor 100%, `Explorar` e `Criar` lado a lado (`50%/50%`), `#startBtn` à esquerda.<br>**Celular (`≤ 768px`):** `padding: 80px var(--space-4) var(--space-9)`; `#customQuizTrigger`, `#btnOpenCatalog`, `#addQuizBtn`, `#startBtn` e `#btnSetTimer` com `min-height: 44px`–`48px` em largura total ou grade `1fr 1fr` (em `<= 380px`, `1fr`), zero overflow lateral |

#### Estado 2 — Execução de Simulado: Modo Foco e Modo Lista (`exam-active` → `backdrop.js` DESLIGADO)

| Aspecto | Antes | Depois |
| :--- | :--- | :--- |
| **Fundo WebGL** | Continua rodando em 30fps WebGL atrás dos cards, causando ruído visual na leitura | **Desligado automaticamente** quando `startTimer()` / estado `exam-active` entra: canvas `.backdrop` recebe `opacity: 0` e para o loop `requestAnimationFrame` (`backdrop.pause()` / `destroy()`), mantendo **fundo `#000000` chapado** (escuro) ou `#f4f0e8` (claro). `#backdropMotionToggle` oculta-se durante a prova para não distrair |
| **Cartão da Questão (`.question`)** | Fundo `rgba(23,23,26,0.90)` com `backdrop` aparecendo nas bordas; `.number` em pílula roxa/coral; `.section` em `DM Mono` uppercase | Superfície sólida `#181818` (`--surface`), borda inteira `1px solid #272727`, `border-radius: 16px` (`--radius-lg`), `padding: 32px` (desktop) / `24px` (tablet) / `16px` (mobile). `.section` em `Manrope` `12px` sem uppercase. `.number` em `DM Mono` (`#FF8F75` sobre `rgba(255,122,92,0.14)`) |
| **Alternativas (`.option`)** | 2 colunas no desktop (`options`), `border-radius: 4px/8px`, marcada com `box-shadow: inset 4px 0 0 var(--teal)` (borda lateral roxa que lembra "single-sided border") | Fundo `#1F1F1F` (`--surface-2`), borda inteira `1px solid #313131`, `border-radius: 8px` (`--radius-sm` via `B3`), `min-height: 52px`. Hover: `#272727`. Selecionada (`:has(input:checked)`): fundo `rgba(255, 122, 92, 0.14)` e **borda inteira** `1px solid #FF7A5C` (substitui o `inset 4px` roxo). `.option-kbd` em `DM Mono` (`1–5`) oculto em `hover: none` / mobile |
| **Timer (`#timer`)** | `position: fixed; top: 16px; right: 20px;` (colide com barra global!); `28px` de altura no mobile (`< 44px`) | **Posição padrão:** ancorado à esquerda/direita dentro do painel de prova (Camada 2) ou logo abaixo da Camada 1 (`top: calc(var(--space-4) + 64px)` se flutuante ao rolar no modo Lista), com **min-height `44px`** no mobile e fonte `DM Mono` `14px`–`16px`. Preserva 100% o comportamento arrastável e redimensionável de `timer-drag.js` |
| **Modo Foco (`#focusNavigation`)** | Desktop: estático abaixo da questão; Mobile: `position: sticky; bottom: 12px;` com `backdrop-filter: blur(10px)` | Mantém comportamento: **Desktop/Tablet** no fluxo abaixo da questão (`#181818`, borda `#272727`, `radius-md`); **Celular** sticky no rodapé (`bottom: var(--space-3)`), botões `Anterior` (contorno) e `Próxima` (ou `Finalizar simulado` na última) com `min-height: 44px`, `#focusIndicator` em `DM Mono` |
| **Modo Lista (`#quiz:not(.quiz--focus)`)** | Todas as questões empilhadas, botão `#submit` (`Conferir respostas`) cheio ao final e `#reset` (`Resetar quiz`) em contorno | Mesma estética limpa sobre `#000000` chapado; `#submit` em coral cheio `#FF7A5C` (texto `#000000`, `48px`), `#reset` em contorno `#313131` |
| **Breakpoints (Foco & Lista)** | Mobile: `question h2` cai para `14px` (`styles.css:2927`), um pouco pequeno para enunciado longo | **Desktop:** opções em 2 colunas (`gap: 12px`), enunciado `18px`.<br>**Tablet:** opções em 2 colunas se `≥ 769px`, `1fr` em `≤ 768px`, enunciado `18px`.<br>**Celular (`≤ 768px`):** opções em 1 coluna (`1fr`), enunciado `16px` (`--text-md`, mais legível que `14px`), `padding` `16px`, `.palette-btn` `44×44px` com scroll horizontal ou máximo 3 linhas |

#### Estado 3 — Resultados, Estatísticas Pedagógicas e Conta / Histórico

| Aspecto | Antes | Depois |
| :--- | :--- | :--- |
| **Modal de Resultado (`#resultModal` / `.modal--results`)** | Fundo `#1F1F1F`, bordas `#2e2e35`, `.results-badge` e `.result-card` com `border-left: 3px/4px` isolado, `.results-percent` em roxo `#a78bfa`, `.stats-overview-card::before` barra no topo, `.btn-remix` em `#4359ff` azul | Fundo `#181818`, borda inteira `1px solid #272727`, `border-radius: 16px` (desktop/tablet) e bottom-sheet `16px 16px 0 0` (mobile). `.results-score` (`30px` `DM Mono`) + `.results-percent` (`16px` `DM Mono` `#FF8F75`). **Cartões `.result-card` e `.result-card-explanation`:** remover `border-left: 4px` isolado e usar borda inteira `1px solid` com tint semântico sutil + selo superior de status (`Correta` / `Errada` com SVG inline em vez de `✓`/`✗`). **Botões do rodapé (`.results-footer`):** `Refazer tudo` e `Fechar` em contorno; `Caderno de erros` em `--orange` (`#f2b866` com texto `#000000`); `Gerar novas variações` (`.btn-remix`) como **único botão cheio coral `#FF7A5C`** (texto `#000000`) quando visível |
| **Estatísticas (`stats.js` / `#resultStatsContainer`)** | `.stats-pill` em `#1F1F1F`; `.pill-time` roxo; `.stats-pill .pill-label` e `.sections-breakdown-title` em `uppercase`; barras `.section-progress-fill` animam `width` (`styles.css:2568`) | Cards `.stats-overview-card` e `.sections-breakdown-card` em `#1F1F1F` borda `#272727` (`radius-md`); `.pill-label` e títulos em caixa normal Manrope; números em `DM Mono`; `.pill-time .pill-number` em `#EDEDED` ou `#FF8F75`; barras de seção animando `transform: scaleX(...)` |
| **Minha Conta e Histórico (`#accountModal`)** | `.modal--access-compact` em `#1F1F1F`, barras de uso `.usage-meter-track span` em roxo (`--teal`) | Fundo `#181818`, seções separadas por `border-top: 1px solid #272727`; medidores de cota (`.usage-meter-track span`) em `#FF7A5C` (coral quando normal e `--error` quando esgotado); `Baixar meus dados` e `Ver planos` em contorno `44px`; exclusão com `.btn-danger` em contorno `--error` |
| **Breakpoints** | Mobile `<= 380px`: `.stats-pills-row` 1 coluna; `.results-footer` empilhado em `position: static` | **Desktop (`≥ 981px`):** modal `max-width: 820px`, 4 pílulas em linha, `.results-footer` `position: sticky; bottom: 0; background: #181818`.<br>**Tablet:** modal `max-width: min(820px, 100%)`, 4 pílulas em `2×2` ou `4×1`.<br>**Celular (`≤ 768px`):** modal full-width `max-height: 94dvh`, 2 colunas de pílulas (`1fr` em `≤ 380px`), botões do rodapé em largura `100%` e `48px` de altura |

#### Estado 4 — Modais Principais (`#accessModal`, `#uploadModal`, `#catalogModal`, `#confirmSubmitModal`, `#customTimerModal`, `#aboutModal`, `#noticeModal`)

| Modal | Antes | Depois | Breakpoints (Desktop / Tablet / Celular) |
| :--- | :--- | :--- | :--- |
| **`#accessModal`** (`/app` nunca redireciona para `/login`) | Card `#1F1F1F`; `.access-option--account` em `#272727` com borda roxa; `.access-option-tag` roxo; `.access-perks li::before` check roxo; botão `Criar conta grátis` azul | Card `#181818` borda `#272727`; `.access-option` em `#1F1F1F` borda `#272727` (`radius-md`); `.access-option--account` com borda `#FF7A5C` e tag `Recomendado` em coral suave; checkmarks em `#FF7A5C`; **único CTA cheio coral `#FF7A5C` texto `#000000`** (`Criar conta grátis`); `Continuar como convidado` em contorno (`44px`) | **Desktop/Tablet:** 2 colunas (`1fr 1fr`, `max-width: 680px`), ou 1 coluna quando `limit`.<br>**Celular:** 1 coluna, `access-login-link` `>= 44px`, CTA `48px` |
| **`#uploadModal`** (Arquivo / Gerar por tema) | Abas com `border-bottom: 2px solid` roxo e fundo roxo; `.drop-zone` borda tracejada `#2e2e35`; `.upload-skeleton` gradiente roxo `background-position`; botão `Gerar simulado` / `Enviar arquivo` azul `#4359ff` | Abas estilo pílula segmentada (igual `.in-switch` de `/`) ou sublinhado coral `#FF7A5C`; `.drop-zone` `#1F1F1F` borda tracejada `#313131` (hover `#FF7A5C` em fundo `rgba(255,122,92,0.08)`); `.upload-skeleton` em pulso de `opacity` neutro (`#272727` / `#313131`); **CTA cheio coral `#FF7A5C` texto `#000000`**; `.topic-chip` hover coral, `min-height: 44px` no mobile; `.file-preview-remove` `44×44px` no mobile | **Desktop/Tablet:** `max-width: 560px`, linhas de formulário em 2 colunas (`.modal-form-row`).<br>**Celular:** bottom-sheet, `.modal-form-row` em 1 coluna, `font-size: 16px` nos inputs (evita zoom iOS), botões empilhados `48px` |
| **`#catalogModal`** | `.catalog-tab-btn.active` fundo roxo texto `#171717`; `.catalog-card` `#1F1F1F` borda `#2e2e35` hover roxo; `.catalog-card-btn` em azul `#4359ff` em todos os cards (múltiplos botões cheios!) | `.catalog-tab-btn.active` em coral `#FF7A5C` texto `#000000` (ou `#EDEDED` sobre `#272727`); `.catalog-card` `#181818` / `#1F1F1F` borda `#272727` hover `#313131`; **`.catalog-card-btn` em contorno neutro/coral** (hover preenche coral `#FF7A5C` texto `#000000`), evitando 12 botões cheios competindo na mesma grade | **Desktop:** grid 3 colunas (`minmax(240px, 1fr)`).<br>**Tablet:** 2 colunas.<br>**Celular:** 1 coluna, tabs `min-height: 44px` com scroll horizontal seguro ou wrap limpo |
| **`#confirmSubmitModal`** | `.confirm-submit-warning` com `border-left: 3px solid var(--orange)`; `.btn-confirm-finish` azul | `.confirm-submit-warning` com borda inteira `1px solid rgba(242,184,102,0.35)`; `Voltar e revisar` em contorno; `Confirmar e ver gabarito` em **coral cheio `#FF7A5C` texto `#000000`** | **Desktop/Tablet:** `max-width: 440px`, botões lado a lado.<br>**Celular:** botões empilhados `48px` |
| **`#customTimerModal`** | `.timer-chip` hover/active coral com `--coral` azul no escuro | `.timer-chip` `#1F1F1F` borda `#313131`, ativo `#FF7A5C` texto `#000000` (ou borda `#FF7A5C` + fundo `rgba(255,122,92,0.16)`); `Definir tempo` em **coral cheio `#FF7A5C` texto `#000000`** | **Desktop/Tablet:** grid `3×3` de chips.<br>**Celular:** grid `3×3` (`2×5` em `<= 380px`), chips `>= 44px` |
| **`#aboutModal` & `#noticeModal`** | `.pillar-card h3` roxo; `.comparison-table .highlight-col` borda lateral roxa; `.comparison-table td` `11.5px` mobile | `.pillar-icon` e `.highlight-col` em coral `#FF7A5C` / `#FF8F75`; `.comparison-table td` mínimo **`12px`** em todos os breakpoints; CTA único `Entendi, vamos treinar` / `Entendi` em coral `#FF7A5C` texto `#000000` | **Desktop/Tablet:** 3 pilares.<br>**Celular:** 1 coluna de pilares; tabela com `overflow-x: auto` interno ao wrapper, nunca vazando o viewport |

---

### 4.4 Política de Movimento em `/app` (R2.5 + B7)

1. **Sem `smooth-scroll.js` em `/app`:** A rolagem inercial customizada permanece exclusiva de `/`. Em `/app`, usa-se rolagem nativa do navegador (`scroll-behavior: auto` global ou `smooth` apenas pontual em `scrollIntoView` respeitando `prefers-reduced-motion`).
2. **Propriedades permitidas:** Apenas `transform` e `opacity` (e `background-color` / `border-color` / `color` para feedback de estado em `300ms`). **Correções obrigatórias em `styles.css`:**
   - `#progressBar` (`styles.css:543, 3444`): trocar `width: ${value}%` + `transition: width` por `transform: scaleX(${value / 100})` com `transform-origin: left center` + `transition: transform var(--dur-base) var(--ease-out)` (nota para C: exige ajustar 1 linha em `app.js:981`).
   - `.section-progress-fill` (`styles.css:2568`, `app.js:1143`): idem, usar `transform: scaleX(${pct / 100})` com `transform-origin: left center`.
   - `fadeIn` (`679`), `slideUp` (`696`), `optionPulse` (`599`), `fadeInFocus` (`2007`): substituir `ease` por `var(--ease-out)` (`cubic-bezier(0.22, 1, 0.36, 1)`) e duração `>= 200ms` (ex.: `240ms` / `300ms`).
   - `authFadeIn` (`1205`): subir de `0.18s ease-out` para `200ms var(--ease-out)`.
   - `.upload-skeleton span` (`4298-4306`): substituir animação de `background-position` por pulso de `opacity` (`0.45 ↔ 0.9`, `1200ms var(--ease-out)`).
3. **`prefers-reduced-motion: reduce`:** Remover `transition-duration: 0.01ms !important` global (`styles.css:3495`) que corta feedbacks de opacidade; em vez disso, zerar `transform` (`transform: none !important`) em hover/active/entradas e manter apenas transições suaves de `opacity` (`300ms var(--ease-out)`).

---

## 5. Contrato de Classes, IDs, `aria-*` e Novos Textos i18n

### 5.1 Elementos Protegidos por `tests/test_ui_contract.py` e `app.js` (NÃO QUEBRAR)

Abaixo está o inventário completo extraído de `public/web/index.html`, `public/web/app.js`, `public/web/modules/*.js` e validado pelo parser de `tests/test_ui_contract.py`. Todos estes **IDs**, **classes consultadas por JS** e **atributos `aria-*` / `for`** devem ser preservados integralmente na Fase 3:

#### A. IDs estáticos obrigatórios em `index.html`

- **Navegação / Cabeçalho / Barra Global & Utilitários:**
  `themeToggle`, `langToggle`, `backdropMotionToggle`, `plansLink`, `btnOpenAboutModal`, `authControls`, `visitorActions`, `userProfile`, `userRoleBadge`, `userName`, `guestAiChip`, `accountBtn`, `logoutBtn`, `guestActions`
- **Painel de Controle do Simulado & Status:**
  `introGuestAiLimit`, `quizSelector`, `customQuizSelectorWrap`, `customQuizTrigger`, `customQuizValue`, `customQuizDropdown`, `btnOpenCatalog`, `addQuizBtn`, `startBtn`, `btnSetTimer`, `progress`, `percent`, `timer`, `timerConfig`, `timerPreset`, `progressBar`, `examToolbar`, `btnToggleFocus`, `btnToggleList`, `btnQuickSubmit`, `questionPalette`
- **Área do Quiz & Navegação Foco:**
  `quiz`, `focusNavigation`, `btnPrevQuestion`, `btnNextQuestion`, `focusIndicator`, `shortcutsHint`, `submit`, `reset`, `footerAccountBtn`
- **Modal Upload / Tema (`#uploadModal`):**
  `uploadModal`, `closeModal`, `modalTitle`, `guestAiNotice`, `guestAiNoticeText`, `tabUploadFile`, `tabGenerateTopic`, `panelUpload`, `panelTopic`, `dropZone`, `uploadSizeLimit`, `fileInput`, `filePreview`, `filePreviewName`, `removeFile`, `uploadNumQuestions`, `uploadCustomQtyWrap`, `uploadCustomQty`, `uploadContext`, `topicInput`, `topicNumQuestions`, `topicCustomQtyWrap`, `topicCustomQty`, `topicDifficulty`, `topicContext`, `uploadStatus`, `uploadStatusText`, `uploadStatusHint`, `uploadError`, `uploadSuccess`, `uploadVisibilityOption`, `isPublicQuiz`, `cancelUpload`, `confirmUpload`, `confirmGenerateTopic`
- **Modal Resultado (`#resultModal`):**
  `resultModal`, `closeResultModal`, `resultScoreBadge`, `resultModalTitle`, `resultScoreNumber`, `resultScorePercent`, `resultSummaryText`, `resultStatsContainer`, `resultQuestionsList`, `btnRedoQuiz`, `btnTrainMistakes`, `mistakesCount`, `btnRemixMistakes`, `btnCloseResultModal`
- **Modal Sobre (`#aboutModal`):**
  `aboutModal`, `closeAboutModal`, `aboutModalTitle`, `btnCloseAbout`
- **Modal Confirmar Finalização (`#confirmSubmitModal`):**
  `confirmSubmitModal`, `confirmSubmitTitle`, `confirmSubmitMsg`, `confirmSubmitAnswered`, `confirmSubmitTotal`, `confirmSubmitWarning`, `confirmSubmitMissing`, `confirmSubmitCancel`, `confirmSubmitConfirm`
- **Modal Catálogo (`#catalogModal`):**
  `catalogModal`, `closeCatalogModal`, `catalogModalTitle`, `catalogSearchInput`, `catalogList`
- **Modal Acesso (`#accessModal`):**
  `accessModal`, `closeAccessModal`, `accessModalBadge`, `accessModalTitle`, `accessModalText`, `accessOptions`, `accessAccountTitle`, `accessRegisterLink`, `accessLoginLink`, `accessGuestOption`, `accessGuestTitle`, `accessGuestLimit`, `accessGuestWindow`, `accessGuestBtn`, `accessFeedback`
- **Modal Minha Conta (`#accountModal`):**
  `accountModal`, `closeAccountModal`, `accountModalTitle`, `accountUsername`, `accountEmailTitle`, `accountEmailAddress`, `accountEmailStatus`, `accountEmailFeedback`, `accountResendVerification`, `accountPlanTitle`, `accountPlanSummary`, `accountUsageGeneration`, `accountUsageGenerationLabel`, `accountUsageGenerationCount`, `accountUsageGenerationBar`, `accountUsageRemix`, `accountUsageRemixLabel`, `accountUsageRemixCount`, `accountUsageRemixBar`, `accountPlanRenews`, `accountPlansLink`, `accountDataTitle`, `accountExportLink`, `accountDeleteTitle`, `deleteAccountForm`, `deleteAccountSendCode`, `deleteAccountCodeGroup`, `deleteAccountCode`, `deleteAccountFeedback`, `deleteAccountBtn`
- **Modais Aviso e Tempo (`#noticeModal`, `#customTimerModal`):**
  `noticeModal`, `noticeIcon`, `noticeModalTitle`, `noticeModalMessage`, `btnNoticeClose`, `customTimerModal`, `closeCustomTimerModal`, `customTimerTitle`, `timerPresetsGrid`, `customTimerForm`, `customTimerMinutesInput`, `customTimerFeedback`, `cancelCustomTimer`, `applyCustomTimer`

#### B. Classes e atributos `data-*` consultados ou alternados via JavaScript (`app.js`, `theme.js`, `backdrop.js`, `i18n.js`, `stats.js`)

- **Temas / Backdrop / i18n:** `.theme-icon`, `.theme-label`, `.lang-code`, `[data-lang-toggle]`, `[data-backdrop-toggle]`, `.backdrop`, `.is-running`, `html.i18n-pending`, `[translate="no"]`
- **Sessão / Links:** `[data-show-for]`, `[data-auth-link]`, `.guest-ai-chip--empty`, `.guest-ai-notice--empty`, `.user-role-badge`, `.role-admin`, `.role-student`, `.role-guest`, `.usage-meter-track--full`
- **Quiz / Toolbar / Timer:** `.question`, `.question--active`, `.quiz--focus`, `.option`, `.option--hotkey-pulse`, `.palette-btn`, `.answered`, `.active`, `.is-final`, `.timer-config-label`, `.timer-config--visible`, `.timer-chip`, `.timer-resize-handle`, `.timer--custom`, `.is-dragging`, `.is-resizing`, `.running`, `.expired`, `.hidden`
- **Seletor customizado & Catálogo & Modais:** `.custom-select-option`, `.custom-select-empty`, `.is-selected`, `.custom-select-option-check`, `.catalog-tab-btn`, `.catalog-card`, `.modal-overlay`, `.modal--access`, `.access-options--single`, `.modal--access-compact`, `.access-badge--warning`, `.drop-zone--active`, `.drop-zone--error`, `.topic-chip`, `.results-badge` (`.excellent`, `.good`, `.practice`), `.section-progress-fill[data-percentage]`

#### C. Referências ARIA obrigatórias (`tests/test_ui_contract.py`)

- Todos os `for="..."` apontando para os `<input>`/`<select>` acima (`quizSelector`, `timerPreset`, `uploadNumQuestions`, `uploadCustomQty`, `uploadContext`, `topicInput`, `topicNumQuestions`, `topicCustomQty`, `topicDifficulty`, `topicContext`, `deleteAccountCode`, `customTimerMinutesInput`).
- Todos os `aria-labelledby`, `aria-describedby` e `aria-controls` apontando para IDs reais na página (inclusive em eventuais novos menus mobile como `aria-controls="appNavMenu"`).
- `role="dialog"` / `role="alertdialog"` e `aria-modal="true"` em todos os `.modal-overlay`.
- `role="listbox"` / `role="option"` + `aria-haspopup="listbox"` + `aria-expanded` em `#customQuizTrigger` / `#customQuizDropdown`.
- `role="status"` + `aria-live="polite"` em `#uploadStatusText`, `#guestAiChip`, `#guestAiNotice`, `#accountPlanSummary`, `#timer`.
- `role="progressbar"` + `aria-valuemin`/`aria-valuemax`/`aria-valuenow`/`aria-valuetext` nas barras de uso.

---

### 5.2 Novas Classes e Modificadores Propostos (Sem conflito com `app.js` ou `.in-*`)

Usar prefixo `.app-*` (e `data-exam-state` no `body`) para isolar completamente de `.in-*` (`inicio.css`) e não colidir com seletores de `app.js`:

| Classe / Atributo proposto | Elemento alvo | Função visual / comportamental |
| :--- | :--- | :--- |
| `body[data-exam-state="idle" \| "active" \| "results"]` *(ou `.is-exam-active`)* | `<body>` | Controla estado global da prova: em `"active"`, oculta/pausa `.backdrop` e `#backdropMotionToggle`, destaca o painel de execução e ajusta o foco de leitura sobre `#000000` chapado |
| `.app-nav-wrap`, `.app-nav` | `<header>` / `<nav>` (Camada 1) | Barra global flutuante translúcida (`rgba(24,24,24,0.72)` + `blur(16px)` + `border: 1px solid #272727` + `radius-lg`) |
| `.app-brand` | `<a href="/">` dentro de `.app-nav` | Link de marca retornando para `/` com ícone + `Acely` (`translate="no"`), alvo `>= 44px` no mobile |
| `.app-nav-links`, `.app-nav-tools` | Grupos dentro de `.app-nav` | Links institucionais/globais (`Início`, `Planos`, `Por que o Acely`) separados das ferramentas (`PT/EN`, `Tema`, `Fundo`, `Conta`) |
| `.app-menu-toggle`, `.app-menu`, `.app-menu.is-open`, `.app-menu-line` | Drawer mobile (`≤ 768px`) | Alterna painel full-height translúcido no celular sem duplicar IDs protegidos (`#authControls` pode ser realocado via media/slot ou espelhado com links `<a>` sem IDs duplicados — **ponto de atenção para C!**) |
| `.exam-panel` | Bloco da Camada 2 dentro de `<header class="hero">` | Envelopa seletor, ações de simulado, status, barra de progresso, toolbar foco/lista e paleta em superfície `#181818` borda `#272727` `radius-lg` |
| `.exam-header-intro` | Wrapper de `<h1>` + `.intro` | Compacta título e subtítulo acima do `.exam-panel` (ou dentro dele) sem empurrar a primeira questão para fora da dobra |
| `.timer-dock` | Contêiner de referência para `#timer` quando não arrastado (`:not(.timer--custom)`) | Evita colisão fixa no canto superior direito com a Camada 1; quando `timer-drag.js` move `#timer`, `.timer--custom` volta a `position: fixed` livremente |
| `.btn-outline` | Modificador opcional para `#btnOpenCatalog`, `#addQuizBtn`, `#visitorActions .guest-action-link--primary` | Garante visual de contorno limpo no tema escuro e claro, reservando o coral cheio apenas para o CTA principal da tela |

---

### 5.3 Novos Textos Visíveis, Normalizações de Copy e Contrato i18n (`en.js`)

Todos os textos novos ou ajustados devem seguir `B8` (`AGENTS.md` §5 e `R3`): **pt-BR em caixa normal, sem ponto de exclamação, sem travessão pontuando frase** e com **chave idêntica** em `public/web/modules/i18n/en.js`, além de `translate="no"` no conteúdo dos simulados.

#### A. Novos textos visíveis sugeridos pela arquitetura em 2 camadas

| Contexto / Atributo | Texto pt-BR proposto (chave exata) | Tradução proposta para `en.js` |
| :--- | :--- | :--- |
| `<nav class="app-nav" aria-label="...">` | `Navegação global` *(ou `Principal`, já existe em `en.js:525`!)* | `'Main'` *(já existe)* |
| Link na marca `<a href="/" class="app-brand" title="...">` | `Voltar para a página inicial` | `'Back to home page'` |
| Botão hambúrguer mobile `aria-label` (fechado / aberto) | `Abrir menu` / `Fechar menu` *(já existem em `en.js:532-533`!)* | `'Open menu'` / `'Close menu'` *(já existem)* |
| Link opcional de navegação na Camada 1 | `Início` | `'Home'` |
| `aria-label` da barra de controle (Camada 2) | `Controles do simulado` | `'Quiz controls'` |

#### B. Ajustes de Copy (Caixa normal / Pontuação) + Impacto em `en.js`

Os textos abaixo já existem no HTML/JS e violam levemente `B1`/`B8` (Title Case ou travessão). Se atualizados na Fase 3, **é obrigatório atualizar ou manter aliases** das chaves em `public/web/modules/i18n/en.js`:

| Arquivo atual | Texto atual | Ajuste recomendado (`B1`/`B8`) | Chave correspondente em `en.js` |
| :--- | :--- | :--- | :--- |
| `index.html:6` | `Acely — Treino de Raciocínio` | `Acely · Treino de raciocínio` | `'Acely · Treino de raciocínio': 'Acely · Reasoning practice'` |
| `index.html:134`, `app.js:1406` | `Iniciar simulado <span>▶</span>` / `Iniciar Simulado ▶` | `Iniciar simulado` (+ ícone SVG `play` de `icons.js`) | `'Iniciar simulado'` já existe (`en.js:63`); remover `▶` |
| `index.html:384, 392`, `app.js:1257` | `↺ Refazer tudo` / `↻ Gerar novas variações` | Usar ícones SVG inline (`icons.js`) + texto limpo `Refazer tudo` / `Gerar novas variações` | Adicionar chaves sem símbolo unicode em `en.js` |
| `index.html:513` | `Biblioteca de Estudos` | `Biblioteca de estudos` | `'Biblioteca de estudos': 'Study library'` |
| `index.html:659` | `Opções Rápidas:` | `Opções rápidas:` | `'Opções rápidas:': 'Quick options:'` |
| `app.js:1006, 1070, 1450` | `Simulado Incompleto` / `Erro de Conexão` / `Erro de Carregamento` | `Simulado incompleto` / `Erro de conexão` / `Erro de carregamento` | Atualizar chaves correspondentes em `en.js` |
| `app.js:1170, 1184` | `✓ Correta` / `✗ Errada` / `Explicação Didática` | Ícone SVG + `Correta` / `Errada` / `Explicação didática` | Atualizar chaves correspondentes em `en.js` |
| `stats.js:65-82, 146, 175` | `Bom Rendimento`, `Desempenho Excepcional`, `Acima da Média`, `Regular / Em Evolução`, `Atenção Redobrada`, `Ritmo Médio:`, `Desempenho por Disciplina / Matéria` | `Bom rendimento`, `Desempenho excepcional`, `Acima da média`, `Regular ou em evolução`, `Atenção redobrada`, `Ritmo médio:`, `Desempenho por disciplina` | Atualizar chaves correspondentes em `en.js` |

#### C. Blindagem `translate="no"` (obrigatório em `R3`)

Adicionar `translate="no"` em todos os elementos que exibem **conteúdo gerado ou nomes de simulados**, impedindo o `i18n.js` (`MutationObserver`) de alterar acidentalmente enunciados, alternativas, explicações ou títulos de provas ao alternar para `EN`:
1. `#quiz` (ou cada `.question` / `.section` / `.context` / `.question-head h2` / `.option span`) — *Nota:* manter rótulos de interface como `.empty-state` fora de `translate="no"` (aplicar `translate="no"` diretamente em `.question` gerada em `renderQuestions()`, `app.js:694`!).
2. `#customQuizValue` (`app.js:897`) e `.custom-select-option-label` (apenas no `item.label` em `app.js:874, 886`, mantendo `Quizzes da Plataforma` traduzível).
3. `.catalog-card-title` (`app.js:1399`).
4. `#resultQuestionsList` — aplicar `translate="no"` apenas em `.result-card-question`, `.result-user-answer strong`, `.result-correct-answer strong` e no texto da explicação (`app.js:1172-1185`), preservando `Correta`, `Errada`, `Sua resposta:`, `Gabarito correto:` e `Explicação didática` traduzíveis pelo `i18n.js`!

---

## 6. Pontos de Atenção para Cruzamento na Fase 2 (Design B × Arquitetura C)

1. **Disparo exato do desligamento de `backdrop.js` (`exam-active`):**
   - Hoje `app.js` já renderiza as questões de um simulado padrão na carga inicial (`loadInitialQuiz`), mesmo antes de o usuário clicar em `#startBtn`.
   - **Pergunta para C resolver na Fase 2:** O `backdrop.js` deve desligar (a) assim que `startTimer()` roda (clique em `Iniciar simulado` ou seleção da 1ª alternativa — ou seja, quando `#timer` está `.running`), **ou** (b) sempre que houver questões visíveis na tela (exigindo um estado de Lobby sem a lista de questões expandida até clicar em `Iniciar simulado`)?
   - *Posição recomendada por Design (B):* Opção (a) preserva o comportamento imediato atual de `/app` (o usuário já vê o simulado pronto sem etapa extra), mantendo o WebGL rodando em suavidade apenas no estado pré-prova (`idle`) e desligando instantaneamente (`opacity: 0` + pausa do loop WebGL) no momento em que o estudo começa (`startTimer()` ou foco na prova). Se desejar ainda menos ruído visual, reduzir `--backdrop-calm` para `0.28` no escuro para que o corredor central de leitura fique quase preto puro `#000000`.
2. **Alocação de `#authControls` entre Barra Desktop e Menu Mobile (`.app-menu`):**
   - `test_ui_contract.py:121` proíbe IDs duplicados na página (`#visitorActions`, `#userProfile`, `#accountBtn`, `#logoutBtn`, etc.).
   - Portanto, no mobile, o menu full-height não pode clonar `#authControls`; o CSS ou JS deve posicionar o mesmo container `#authControls` dentro do drawer mobile (ou exibi-lo como bloco dentro da barra expandida / realocação responsiva via CSS Grid/Flex sem duplicar DOM).
3. **Posição de `#timer` e compatibilidade com `timer-drag.js`:**
   - `timer-drag.js` lê `timer.getBoundingClientRect()` no `detach()` e alterna `.timer--custom` quando movido/redimensionado.
   - Se `#timer:not(.timer--custom)` passar de `position: fixed; top: 16px; right: 20px` (onde hoje colide com a Camada 1!) para dentro de `.timer-dock` na Camada 2 (ou `top: 84px; right: 20px` no desktop se mantiver `fixed`), `timer-drag.js` continua funcionando perfeitamente — mas precisa ser validado por C quanto ao `ResizeObserver` e comportamento ao rolar longas listas no Modo Lista.
4. **Atualização síncrona de `?v=`:**
   - Qualquer alteração futura em `styles.css`, `app.js`, `theme.js`, `backdrop.js` ou `i18n/en.js` exigirá incrementar `?v=` em **todos** os HTMLs que os importam (`index.html`, `inicio.html`, `login.html`, `register.html`, `reset-password.html`, `produto.html`, `termos.html`, `privacidade.html`, `404.html`), especialmente mantendo a mesma versão `?v=` de `i18n.js` em todos (`R3`).
5. **`theme-boot.js` e `<meta name="theme-color">`:**
   - Para que `/app` abra no tema escuro por padrão sem FOUC, `theme-boot.js:8` e `theme.js:101` precisam mudar o fallback sem chave salva de `'system'` para `'dark'`, e `index.html:18` + `theme.js:38` precisam atualizar `theme-color` de `#0d3f3d` / `#171717` para `#000000` no tema escuro.
