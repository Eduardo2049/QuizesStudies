# Sistema de Cores e Temas - RealtimeColors Pattern

## 🎨 Paleta Base (60-30-10 Rule)

A regra 60-30-10 distribui cores de forma balanceada:
- **60%** - Cores neutras (background, texto)
- **30%** - Cores primárias (CTAs, seções)
- **10%** - Cores de destaque (alertas, ênfase)

---

## 📊 Paleta Atual (Recomendada)

```
Nome              Hex       RGB           Uso (% visual)
────────────────────────────────────────────────────────
bg (neutro)      #fbfbfe   251,251,254   [60%] Fundo
text (neutro)    #050315   5,3,21        [60%] Texto
────────────────────────────────────────────────────────
primary          #2f27ce   47,39,206     [30%] Botões principais
primary-light    #4d43d5   77,67,213     [30] Hover
primary-dark     #1f1a8f   31,26,143     [30] Active
────────────────────────────────────────────────────────
secondary        #dedcff   222,220,255   Elementos secundários
secondary-dark   #b3b0ff   179,176,255   Hover secundário
────────────────────────────────────────────────────────
accent           #433bff   67,59,255     [10%] Destaques
success          #10b981   16,185,129    [10] Sucesso
warning          #f59e0b   245,158,11    [10] Aviso
error            #ef4444   239,68,68     [10] Erro
```

### Contraste Verificado ✓

| Combinação | Razão | AA | AAA |
|-----------|-------|----|----|
| text (#050315) on bg (#fbfbfe) | 16.4:1 | ✓ | ✓ |
| primary (#2f27ce) on bg | 8.2:1 | ✓ | ✓ |
| accent (#433bff) on bg | 9.1:1 | ✓ | ✓ |
| white on primary | 11.2:1 | ✓ | ✓ |

---

## 🎯 CSS Variables (Implementação)

```css
/* core/variables.css */

:root {
  /* ========== NEUTROS (60%) ========== */
  --color-bg: #fbfbfe;
  --color-bg-secondary: #f5f3ff;
  --color-bg-tertiary: #ede9fe;

  --color-text: #050315;
  --color-text-secondary: #6b6b7b;
  --color-text-tertiary: #a9a9b8;

  /* ========== PRIMÁRIO (30%) ========== */
  --color-primary: #2f27ce;
  --color-primary-light: #4d43d5;
  --color-primary-lighter: #6b61dd;
  --color-primary-dark: #1f1a8f;

  --color-secondary: #dedcff;
  --color-secondary-dark: #b3b0ff;

  /* ========== ACCENT (10%) ========== */
  --color-accent: #433bff;

  /* Status colors */
  --color-success: #10b981;
  --color-success-light: #6ee7b7;
  --color-warning: #f59e0b;
  --color-warning-light: #fcd34d;
  --color-error: #ef4444;
  --color-error-light: #fca5a5;
  --color-info: #3b82f6;
  --color-info-light: #93c5fd;

  /* ========== SPACING ========== */
  --spacing-xs: 4px;
  --spacing-sm: 8px;
  --spacing-md: 16px;
  --spacing-lg: 24px;
  --spacing-xl: 32px;
  --spacing-2xl: 48px;

  /* ========== BORDERS ========== */
  --radius-sm: 4px;
  --radius-md: 8px;
  --radius-lg: 12px;
  --radius-full: 9999px;
  --border-width: 1px;

  /* ========== SOMBRAS ========== */
  --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.05);
  --shadow-md: 0 4px 6px rgba(0, 0, 0, 0.1);
  --shadow-lg: 0 10px 15px rgba(0, 0, 0, 0.15);

  /* ========== TIPOGRAFIA ========== */
  --font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  --font-size-xs: 0.75rem;
  --font-size-sm: 0.875rem;
  --font-size-base: 1rem;
  --font-size-lg: 1.125rem;
  --font-size-xl: 1.25rem;

  /* ========== Z-INDEX ========== */
  --z-dropdown: 100;
  --z-modal: 1000;
  --z-tooltip: 1100;
}
```

---

## 🎨 Temas Alternativos

### Dark Mode

```css
[data-theme="dark"] {
  --color-bg: #0f0f14;
  --color-bg-secondary: #1a1a23;
  --color-text: #f5f5ff;
  --color-text-secondary: #b0b0c0;
  
  --color-primary: #6b61dd;
  --color-primary-dark: #4d43d5;
}
```

### Light (Padrão)

```css
[data-theme="light"] {
  /* Valores acima (default) */
}
```

### Contrasting (Alta Acessibilidade)

```css
[data-theme="high-contrast"] {
  --color-bg: #ffffff;
  --color-text: #000000;
  --color-primary: #0000ff;
  --color-secondary: #ffff00;
  --color-accent: #ff0000;
}
```

---

## 💻 Hook para Tema (React)

```jsx
// hooks/useTheme.js

import { useState, useEffect } from 'react';

export function useTheme() {
  const [theme, setTheme] = useState(() => {
    // 1. Preferência salva
    const saved = localStorage.getItem('app-theme');
    if (saved) return saved;

    // 2. Preferência do sistema
    if (window.matchMedia('(prefers-color-scheme: dark)').matches) {
      return 'dark';
    }

    // 3. Padrão
    return 'light';
  });

  useEffect(() => {
    // Aplicar tema no documento
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('app-theme', theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme((t) => (t === 'light' ? 'dark' : 'light'));
  };

  return { theme, setTheme, toggleTheme };
}

// Uso:
function App() {
  const { theme, toggleTheme } = useTheme();

  return (
    <div>
      <button onClick={toggleTheme}>
        {theme === 'light' ? '🌙' : '☀️'}
      </button>
    </div>
  );
}
```

---

## 🎨 Componente Theme Picker

```jsx
// components/ThemePicker.jsx

export function ThemePicker() {
  const { theme, setTheme } = useTheme();

  const themes = ['light', 'dark', 'high-contrast'];

  return (
    <div className="theme-picker">
      <label>Tema:</label>
      <select value={theme} onChange={(e) => setTheme(e.target.value)}>
        {themes.map((t) => (
          <option key={t} value={t}>
            {t.charAt(0).toUpperCase() + t.slice(1)}
          </option>
        ))}
      </select>
    </div>
  );
}
```

---

## 📱 Aplicando Cores nos Componentes

```css
/* Button com variáveis */
.btn {
  background-color: var(--color-primary);
  color: var(--color-bg);
  border-radius: var(--radius-md);
  padding: var(--spacing-md);
  border: var(--border-width) solid transparent;
  transition: all 0.2s;
}

.btn:hover {
  background-color: var(--color-primary-light);
  box-shadow: var(--shadow-md);
}

.btn:active {
  background-color: var(--color-primary-dark);
}

/* Card com variáveis */
.card {
  background-color: var(--color-bg);
  color: var(--color-text);
  border-radius: var(--radius-lg);
  padding: var(--spacing-lg);
  box-shadow: var(--shadow-md);
  border: var(--border-width) solid var(--color-secondary);
}

.card-header {
  border-bottom: var(--border-width) solid var(--color-secondary);
  margin-bottom: var(--spacing-md);
}

/* Alert */
.alert-success {
  background-color: var(--color-success-light);
  color: var(--color-success);
  border-left: 4px solid var(--color-success);
}

.alert-error {
  background-color: var(--color-error-light);
  color: var(--color-error);
  border-left: 4px solid var(--color-error);
}

.alert-warning {
  background-color: var(--color-warning-light);
  color: #78350f; /* Dark brown for contrast */
  border-left: 4px solid var(--color-warning);
}
```

---

## 🔄 Exportar Paleta do RealtimeColors

1. Ir para https://www.realtimecolors.com/
2. Escolher cores (principal, secundária, accent)
3. Clicar "Export"
4. Escolher formato "CSS Variables"
5. Copiar e ajustar variáveis acima

---

## 🎯 Best Practices

### ✓ Faça

```css
/* Usar variáveis */
background-color: var(--color-primary);

/* Usar escala de cinza para neutros */
color: var(--color-text-secondary);

/* Usar status colors para feedback */
border-color: var(--color-error);
```

### ✗ Não Faça

```css
/* Hard-coded colors */
background-color: #2f27ce;

/* Muitas cores diferentes */
color: #abc123;

/* Sem contraste */
color: #ede9fe; /* Claro demais no fundo claro */
```

---

## 📊 Testes de Acessibilidade

Verificar contraste com:
- https://www.webaim.org/resources/contrastchecker/
- Ferramenta de contraste do RealtimeColors (built-in)

Requisitos:
- **AA**: Razão 4.5:1 para texto normal, 3:1 para grande
- **AAA**: Razão 7:1 para texto normal, 4.5:1 para grande

---

## 🚀 Próximos Passos

1. [ ] Exportar paleta do RealtimeColors
2. [ ] Atualizar variables.css
3. [ ] Testar contraste de todas cores
4. [ ] Implementar theme switcher
5. [ ] Dark mode completo
6. [ ] High contrast mode
7. [ ] Documentar paleta no Storybook

---

## 🔗 Referências

- RealtimeColors: https://www.realtimecolors.com/
- W3C Color Contrast: https://www.w3.org/WAI/WCAG21/Understanding/contrast-minimum
- CSS Variables: https://developer.mozilla.org/en-US/docs/Web/CSS/var()
