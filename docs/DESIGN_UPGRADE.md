# DESIGN_UPGRADE.md — Playbook de evolução de interface (projeto em produção)

> Objetivo: modernizar e diferenciar a interface e o design **sem alterar regras de negócio, rotas, contratos de API nem dados**. Este arquivo é a fonte de instruções para o Claude Code durante o redesign. Copie as seções "Regras de ouro" e "Fluxo de trabalho" para o seu `CLAUDE.md` se preferir que sejam carregadas automaticamente.

---

## 1. Regras de ouro (projeto em produção)

1. **Só camada visual.** Mexer em markup, estilos, tokens, animações e componentes de apresentação. Não alterar lógica de negócio, chamadas de API, autenticação, estado global, rotas ou schema de dados.
2. **Mudança incremental.** Uma tela ou componente por vez, em branch própria (`design/<nome-da-tela>`), com PR pequeno e reversível.
3. **Nada de big-bang.** Se possível, esconder o novo visual atrás de feature flag e liberar gradualmente (ex.: equipe interna → 10% → 100%).
4. **Preservar comportamento.** Mesmos `data-testid`, `id`, `name`, `aria-*`, handlers e props públicas dos componentes. Se precisar mudar algum, avisar antes.
5. **Sem regressão de performance.** Não aumentar o bundle de forma relevante, não adicionar fontes pesadas sem `font-display: swap` e subset, respeitar Core Web Vitals (LCP, CLS, INP).
6. **Acessibilidade é requisito.** Contraste mínimo WCAG AA, foco visível, navegação por teclado, alvos de toque adequados, `prefers-reduced-motion` respeitado.
7. **Sem placeholders.** Nunca deixar `// ...resto do código`, "TODO" ou trechos omitidos. Entregar arquivos completos.
8. **Mostrar antes de aplicar.** Para mudanças grandes, descrever o plano e esperar confirmação.

---

## 2. Stack de ferramentas

### 2.1 Skills de design (regras e gosto)

| Skill | Papel no projeto | Quando usar |
|---|---|---|
| **frontend-design** (oficial Anthropic) | Compromisso com uma direção estética antes de codar | Base de qualquer tela nova ou redesenhada |
| **taste-skill** (Leonxlnx) | Layout, tipografia, espaçamento, motion; 3 dials de intensidade | Montar o esqueleto visual e diferenciar do "visual genérico de IA" |
| **redesign-skill** (parte do taste-skill) | Audita o que já existe e corrige problemas antes de redesenhar | **Primeira passada em telas já em produção** |
| **output-skill** (parte do taste-skill) | Impede código incompleto e placeholders | Sempre ativa |
| **Impeccable** | Comandos de polimento e auditoria (`/audit`, `/critique`, `/polish`, `/typeset`, `/colorize`, `/harden`, `/normalize`) | Manter consistência e identidade da marca |
| **emil-design-eng** (Emil Kowalski) | Movimento, micro-interações, detalhes que dão sensação de qualidade | Etapa final de refinamento |
| **minimalist-skill** / **brutalist-skill** | Estilos específicos (editorial limpo / bruto) | Só se combinar com a identidade escolhida |

### 2.2 MCPs

- **Figma MCP** — fonte da verdade do design: lê frames, tokens, variáveis e componentes.
- **Playwright MCP** — "espelho": abre o app, tira screenshots (desktop/tablet/mobile), testa hover/foco/estados e responsividade, para o Claude *ver* o resultado real e corrigir.
- **(Opcional) Auditoria de acessibilidade via Figma MCP** — para checar contraste, alvos de toque e semântica no design antes de codar.

### 2.3 Instalação

```bash
# Skills
claude plugin install frontend-design@claude-plugins-official
npx skills add https://github.com/Leonxlnx/taste-skill
npx skills@latest add emilkowalski/skills -g -s '*' -a claude-code -y
# Impeccable: siga as instruções do repositório oficial (copiar a pasta .claude do pacote para o projeto ou para ~/.claude)

# Conferir MCPs ativos dentro do Claude Code
/mcp
```

> Os nomes e comandos acima foram levantados em pesquisa; confirme sempre no README de cada repositório antes de instalar, pois podem mudar.

---

## 3. Fluxo de trabalho recomendado (por tela)

**Fase 0 — Baseline (antes de tocar em qualquer coisa)**
1. Criar branch `design/<tela>`.
2. Com Playwright MCP, capturar screenshots "antes" (desktop 1440, tablet 768, mobile 390) de todos os estados relevantes (vazio, carregando, erro, preenchido, hover, foco).
3. Salvar em `design-baseline/<tela>/before/`.
4. Rodar a suíte de testes existente e anotar o resultado (precisa continuar igual no fim).

**Fase 1 — Diagnóstico**
1. Rodar `redesign-skill` / `/audit` na tela: listar problemas de hierarquia, tipografia, espaçamento, cor, consistência e acessibilidade.
2. Entregar relatório priorizado (impacto alto / médio / baixo) **sem alterar código**.

**Fase 2 — Direção de design**
1. Definir (ou revisar) a direção estética do produto: 3 adjetivos, referências, o que evitar.
2. Ler tokens/variáveis do Figma via Figma MCP; se não houver, propor tokens (cor, tipografia, espaçamento, raio, sombra, motion) e centralizá-los em um único lugar.
3. Aprovação do plano antes de implementar.

**Fase 3 — Implementação**
1. Implementar com `frontend-design` + `taste-skill`, reaproveitando componentes e tokens existentes.
2. Respeitar as regras de ouro (seção 1).
3. Manter diffs pequenos e revisáveis.

**Fase 4 — Verificação visual**
1. Playwright: screenshots "depois" nos mesmos breakpoints e estados.
2. Comparar com o Figma e com o baseline; listar diferenças e corrigir.
3. Testar teclado (Tab/Shift+Tab/Enter/Esc), foco visível e `prefers-reduced-motion`.

**Fase 5 — Polimento**
1. `/critique` e `/polish` (Impeccable).
2. `emil-design-eng`: revisar durações, easing, quais interações animam e quais não, estados de press/hover/loading.

**Fase 6 — Portões de qualidade (obrigatórios antes do merge)**
- [ ] Testes existentes passam como no baseline
- [ ] Sem erros novos no console
- [ ] Contraste AA e foco visível OK
- [ ] Responsivo validado (mobile, tablet, desktop)
- [ ] Sem regressão de CLS/LCP (conferir Lighthouse ou equivalente)
- [ ] Bundle não cresceu de forma relevante
- [ ] Feature flag configurada (se aplicável) e plano de rollback descrito no PR

---

## 4. Como se diferenciar (sem cair no visual genérico)

Sinais de "interface genérica de IA" a evitar:
- Gradiente roxo/azul em tudo, cards idênticos em grade, ícones em círculos coloridos, hero centralizado com dois botões.
- Fonte padrão do sistema sem hierarquia clara, espaçamento uniforme demais, sombras iguais em tudo.
- Textos de marketing vazios ("Revolucione seu fluxo de trabalho").

Alavancas de diferenciação:
1. **Tipografia com personalidade**: um par de fontes escolhido de propósito (títulos e corpo), escala tipográfica consistente, entrelinha e tracking ajustados.
2. **Paleta própria**: poucas cores com papéis claros (superfície, texto, destaque, estado), com modo escuro bem resolvido se o produto tiver.
3. **Composição**: quebrar a simetria onde fizer sentido, variar densidade entre seções, usar espaço negativo com intenção.
4. **Detalhes de produto reais**: usar conteúdo, dados e capturas do próprio produto em vez de ilustrações genéricas.
5. **Movimento com propósito**: animar para dar feedback e orientar, não para decorar; interações frequentes devem ser rápidas ou sem animação.
6. **Microcopy com voz**: textos de botões, vazios e erros alinhados ao tom da marca.
7. **Consistência**: um design system pequeno e rigoroso vale mais que muitos efeitos.

Dials sugeridos para começar (ajuste conforme o produto): variação de layout média, movimento baixo a médio, densidade visual média. Para produto já em produção, prefira começar conservador e subir aos poucos.

---

## 5. Prompts prontos (copiar e colar no Claude Code)

**Diagnóstico**
```
Leia DESIGN_UPGRADE.md. Use a redesign-skill para auditar a tela <NOME/ROTA>.
Não altere nenhum arquivo. Entregue um relatório priorizado de problemas visuais,
de consistência e de acessibilidade, com a sugestão de correção para cada item.
```

**Baseline**
```
Com o Playwright MCP, abra <URL local> e capture screenshots da tela <NOME>
em 1440, 768 e 390 de largura, incluindo estados de hover, foco, vazio, erro e loading.
Salve em design-baseline/<tela>/before/.
```

**Implementação**
```
Siga o fluxo da Fase 3 do DESIGN_UPGRADE.md para a tela <NOME>.
Use os tokens do Figma (<LINK DO FRAME>) via Figma MCP e as skills frontend-design e taste-skill.
Só camada visual: não mude lógica, rotas, APIs, ids nem data-testid.
Entregue arquivos completos, sem placeholders.
```

**Verificação**
```
Use o Playwright MCP para capturar os screenshots "depois" nos mesmos breakpoints e estados,
compare com o Figma e com o baseline, liste as diferenças e corrija.
Depois teste navegação por teclado e prefers-reduced-motion.
```

**Polimento**
```
Rode /critique e /polish na tela <NOME>. Em seguida use a emil-design-eng para revisar
durações, easing e quais interações devem ou não animar. Aplique apenas ajustes visuais.
```

**Revisão final**
```
Verifique os portões de qualidade da Fase 6 do DESIGN_UPGRADE.md e me dê um resumo
com o que passou, o que falhou e o plano de rollback para o PR.
```

---

## 6. Plano de rollout sugerido

1. **Semana 1 — Fundação**: tokens centralizados (cor, tipografia, espaçamento, motion) + componentes base (botão, input, card, modal).
2. **Semana 2 — Telas de maior tráfego**: aplicar o novo visual com feature flag.
3. **Semana 3 — Telas secundárias** e estados raros (vazio, erro, loading).
4. **Semana 4 — Polimento e animações**, auditoria de acessibilidade e performance, remoção da flag.

Priorize por **tráfego x impacto na percepção de qualidade** (landing/home, login/cadastro, dashboard principal, fluxo de conversão).

---

## 7. Registro de decisões

Mantenha uma tabela curta no PR ou aqui:

| Data | Tela | Decisão | Motivo | Link do PR |
|---|---|---|---|---|
| | | | | |

---

## 8. Checklist rápido por PR

- [ ] Só alterações visuais (sem lógica)
- [ ] Screenshots antes/depois anexados
- [ ] Testes existentes verdes
- [ ] A11y (contraste, foco, teclado) verificada
- [ ] Responsivo verificado
- [ ] Performance sem regressão
- [ ] Feature flag e rollback descritos
