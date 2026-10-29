# DESIGN_SKILLS.md — Skill de design adotada e como ela se aplica ao Acely

A interface segue a skill **`landing-page-design`** do repositório
[elayadesign/ai-design-skills](https://github.com/elayadesign/ai-design-skills) (licença MIT).

- Cópia fiel da skill: [`.claude/skills/landing-page-design/SKILL.md`](../.claude/skills/landing-page-design/SKILL.md)
  (licença ao lado, em `LICENSE`). O Claude Code carrega a skill automaticamente desta pasta.
- Este arquivo **traduz a skill para a stack do projeto** (Vanilla CSS, CSP `'self'`, pt-BR) e
  registra onde ela conflita com decisões já documentadas. Quando houver conflito, vale a ordem
  da própria skill: *pedido explícito do dono do projeto > regra da skill > padrão de framework*.

Para atualizar a skill: copie de novo o `SKILL.md` do repositório original, mantenha a `LICENSE`
e revise a seção 3 deste arquivo.

---

## 1. Como usar no dia a dia

1. Antes de criar ou mudar qualquer tela, leia a skill (Parte A para textos e estrutura,
   Parte B para valores visuais) e a tabela de tradução abaixo.
2. Todo valor visual novo sai dos tokens de `web/styles.css`. Se a skill pedir um valor que não
   existe como token, crie o token em `:root` (e no tema escuro) em vez de escrever o número solto.
3. No PR, marque o checklist da seção 4.

---

## 2. Tradução das regras da skill para este projeto

A skill fala em classes do Tailwind; aqui o Tailwind é proibido (`AGENTS.md`). Usamos apenas a
**escala de valores** dele, em variáveis CSS.

| Regra da skill | Como fica no Acely |
|---|---|
| **B1 Fonte única** (Geist, Manrope…) | Manrope (`--font-sans`), self-hosted em `web/fonts/`. DM Mono (`--font-mono`) só para dado numérico: cronômetro, contadores, chip de cota de IA. |
| **B1 Sem itálico, peso máx. bold** | `font-style: normal` em toda a interface (inclusive `em` de destaque, que só muda a cor). Pesos 400, 500, 600 e 700; 800/900 proibidos. |
| **B1 Escala tipográfica** | `--text-xs` 12/16, `--text-sm` 14/20, `--text-md` 16/24, 18/28, 20/28, 24/32, 30/36, 36/40, 48, 60, 72. Valores fora da escala descem para o degrau abaixo. |
| **B1 Botões** | Principal: 16px semibold. Botões pequenos do cabeçalho: 14px semibold. Altura mínima 44px no mobile. |
| **B1 Texto** | Títulos com `text-wrap: balance`; parágrafos com `text-wrap: pretty`. Sem hífen ou travessão como pontuação; **palavras compostas do português mantêm o hífen** (e-mail, boas-vindas), pois é ortografia. |
| **B2 Espaçamento** | `--space-1` 4, `--space-2` 8, `--space-3` 12, `--space-4` 16, `--space-5` 24, `--space-6` 32; para 2, 40, 48, 64, 80 e 96 crie tokens antes de usar. |
| **B3 Raio** | `--radius-sm` 8, `--radius-md` 12, `--radius-lg` 16. Raio interno = externo menos o espaçamento, quando o espaçamento for menor que 32px e o resultado maior que 2. |
| **B4 Bordas e fundos** | Borda em volta toda ou nenhuma. Fundos chapados. Escuro: preferir #000000, #181818, #1F1F1F, #272727, #313131. |
| **B5 Hero** | Título e subtítulo com no máximo 680px e quebras de linha onde a ideia quebra. |
| **B6 Ícones** | SVG inline em `web/modules/icons.js` (a CSP não permite CDN). Ícones novos: copiar o SVG do Phosphor (MIT) para o módulo. |
| **B7 Movimento** | Curva base `--ease-out` = `cubic-bezier(0.22, 1, 0.36, 1)`. Posição/layout 500ms; cor e opacidade 300ms (nunca abaixo de 200ms: `--dur-fast` = 200ms). Animar só `transform` e `opacity`. Em `prefers-reduced-motion`, trocar movimento por opacidade. |
| **B8 Conteúdo** | Frases em caixa normal ("Criar simulado", não "Criar Simulado"). Mensagens de sistema calmas e específicas, sem ponto de exclamação: o que falhou e o que fazer. Sem promessas que não dá para comprovar (ex.: "em 5 segundos"). A mesma regra vale para a tradução em inglês (`web/modules/i18n/en.js`). |
| **B9 Estados** | Hover, active (`scale(0.98)`), foco visível, carregando (skeleton), vazio (orientação de próximo passo) e erro inline. Nunca `alert()`. |
| **B10 Itens de entrega** | Link "pular para o conteúdo", `<title>`, meta description, `og:*`, alt text, HTML semântico, caminho de volta em toda página. Termos, privacidade (LGPD) e 404 própria já entregues. |
| **A4 Conversão** | Um CTA principal por tela, verbo + o que a pessoa recebe ("Criar conta grátis"), redução de risco visível ("Grátis · sem cartão"). |

---

## 3. Conflitos com decisões existentes (aguardando decisão do dono do projeto)

| Regra | Situação atual | Recomendação |
|---|---|---|
| B4 "nunca usar gradiente no fundo" | O fundo animado em WebGL (`web/modules/backdrop.js`) e `--bg-gradient` são parte da identidade documentada em `AGENTS.md`. | Manter por enquanto (decisão anterior do projeto vence). Se adotar a skill à risca, trocar por fundo chapado (`--paper`) e deixar a animação só na futura landing page. |
| B11 seção de tagline obrigatória | Vale para landing pages; a home é uma ferramenta. | Criar uma landing page própria (ex.: `/sobre`) com hero, benefícios, como funciona, FAQ e a seção de tagline. |

---

## 3.1 Já aplicado em todo o CSS

- Tamanhos de fonte em px ajustados para o degrau da escala logo abaixo (77 valores; `clamp()` e tamanhos abaixo de 12px de ícones ficaram).
- Todas as transições com a curva `--ease-out` e duração mínima de 200ms.
- Rótulos, abas e selos em Manrope e caixa normal; DM Mono só em números (cronômetro, contadores, paleta de questões, notas).
- Fundos do tema escuro na paleta da skill (#181818 e #1F1F1F).
- Um botão cheio por tela: "Explorar simulados", "Criar simulado" e "Finalizar simulado" (barra) em contorno.
- Esqueleto no formato das questões no lugar do spinner de geração.
- Páginas de termos, privacidade e 404 próprias; rodapé com links legais.
- Regras do Hallmark sem mudar o tema: textos sem exclamação, modal "Por que o Acely?" enxuto, `overflow-x: clip` em `html`/`body`, foco visível em `summary` e `[role=button]`, alvos de 44px no celular (ícones do topo, rodapé, abas e links de login).
- Modal de resultado rola inteiro (placar, estatísticas e questões); rodapé fixo no desktop.
- Interface em português e inglês (botão PT/EN no topo).

## 4. Checklist de PR (resumo da skill para este projeto)

- [ ] Um CTA principal por tela; verbo + o que a pessoa recebe
- [ ] Textos em caixa normal, específicos, sem exclamação e sem palavras de enchimento
- [ ] Só Manrope (mono apenas em números), sem itálico, peso máximo 700
- [ ] Tamanhos, espaçamentos e raios vindos dos tokens da seção 2
- [ ] Transições com `--ease-out`, ≥ 200ms, animando só `transform`/`opacity`, com fallback de `prefers-reduced-motion`
- [ ] Estados completos: hover, active, foco visível, carregando, vazio e erro inline
- [ ] Contraste AA nos dois temas e alvo de toque ≥ 44px no mobile
- [ ] Textos novos com tradução em `web/modules/i18n/en.js`
- [ ] `python -m unittest discover tests` passando (inclui `test_ui_contract.py`)
- [ ] `?v=` de `styles.css`/`app.js` incrementado nos HTMLs
