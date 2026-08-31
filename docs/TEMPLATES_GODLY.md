# Templates e Layouts - Godly Pattern

## 📐 Sistema de Layouts

Godly oferece templates modulares e ajustáveis. Implementaremos um sistema JSON para:
- Diferentes layouts de quiz
- Componentes em diferentes posições
- Configurações por usuário
- Persistência em localStorage

---

## 🎨 Layouts Base

### Layout 1: Classic (Padrão Atual)

```
┌────────────────────────────────┐
│         HEADER/TITLE           │
├────────────────────────────────┤
│                                │
│   QUESTION (esquerda)          │
│                                │
│   OPTIONS (abaixo questão)     │
│                                │
│   [Back] [Next] [Submit]       │
│                                │
└────────────────────────────────┘
```

**Template JSON:**
```json
{
  "id": "classic",
  "name": "Classic",
  "description": "Layout tradicional com questão acima, opções abaixo",
  "sections": {
    "header": {
      "position": "top",
      "height": "auto",
      "components": ["title", "progress"]
    },
    "content": {
      "position": "main",
      "layout": "vertical",
      "components": ["question", "options"]
    },
    "footer": {
      "position": "bottom",
      "height": "auto",
      "components": ["navigation", "submit"]
    }
  },
  "css": {
    "layout": "flex",
    "direction": "column",
    "gap": "var(--spacing-lg)"
  }
}
```

### Layout 2: Modern (Cards com Sidebar)

```
┌─────────────────────────────────────┐
│          HEADER                     │
├───────────────┬─────────────────────┤
│ SIDEBAR       │ QUESTION CARD       │
│ - Quiz List   │ (CENTER)            │
│ - Timer       │ - Options as Cards  │
│ - Progress    │ - Buttons           │
│               │                     │
└───────────────┴─────────────────────┘
```

**Template JSON:**
```json
{
  "id": "modern",
  "name": "Modern",
  "description": "Layout com sidebar e cards",
  "sections": {
    "sidebar": {
      "position": "left",
      "width": "20%",
      "components": ["quiz-selector", "timer", "progress-bar"]
    },
    "main": {
      "position": "center",
      "width": "80%",
      "components": ["header", "question-card", "navigation"]
    }
  },
  "css": {
    "layout": "grid",
    "gridTemplateColumns": "20% 80%",
    "gap": "var(--spacing-xl)"
  }
}
```

### Layout 3: Minimal

```
┌──────────────────┐
│  QUESTÃO        │
│                 │
│  a) Opção 1    │
│  b) Opção 2    │
│  c) Opção 3    │
│  d) Opção 4    │
│                 │
│  [> Próxima]   │
└──────────────────┘
```

**Template JSON:**
```json
{
  "id": "minimal",
  "name": "Minimal",
  "description": "Layout minimalista - apenas essencial",
  "sections": {
    "container": {
      "position": "center",
      "width": "600px",
      "components": ["question", "options", "button-next"]
    }
  },
  "css": {
    "layout": "flex",
    "direction": "column",
    "gap": "var(--spacing-md)",
    "maxWidth": "600px",
    "margin": "0 auto"
  }
}
```

---

## 📝 Template JSON Schema

```json
{
  "id": "template-id",
  "name": "Template Name",
  "description": "Descrição do template",
  "version": "1.0.0",
  
  "sections": {
    "section-name": {
      "position": "top | left | right | bottom | center | main",
      "width": "100% | 50% | 300px",
      "height": "auto | 100px | 50vh",
      "components": ["component-1", "component-2"],
      "hidden": false,
      
      "style": {
        "backgroundColor": "var(--color-bg-secondary)",
        "padding": "var(--spacing-lg)",
        "borderRadius": "var(--radius-md)"
      }
    }
  },
  
  "css": {
    "layout": "flex | grid",
    "direction": "row | column",
    "gap": "var(--spacing-lg)",
    "gridTemplateColumns": "1fr 2fr",
    "responsive": {
      "mobile": {
        "gridTemplateColumns": "1fr",
        "gap": "var(--spacing-md)"
      }
    }
  },
  
  "components": {
    "component-id": {
      "type": "button | card | input | text",
      "label": "Label ou Placeholder",
      "style": {},
      "props": {}
    }
  }
}
```

---

## 🗂️ Estrutura de Arquivos (Godly Pattern)

```
web/
├── templates/
│   ├── classic.json       # Layout tradicional
│   ├── modern.json        # Layout com sidebar
│   ├── minimal.json       # Layout minimalista
│   └── index.json         # Índice de templates
├── layouts/
│   ├── QuizLayout.jsx     # Wrapper dinâmico
│   ├── ClassicLayout.jsx
│   ├── ModernLayout.jsx
│   └── MinimalLayout.jsx
└── hooks/
    └── useTemplate.js     # Hook para templates
```

---

## 💾 Salvar Template no localStorage

```javascript
// hooks/useTemplate.js

export function useTemplate() {
  const [template, setTemplate] = useState(() => {
    // Carregar template salvo ou padrão
    const saved = localStorage.getItem('quiz-template');
    return saved ? JSON.parse(saved) : TEMPLATES.classic;
  });

  const saveTemplate = (templateId) => {
    const newTemplate = TEMPLATES[templateId];
    setTemplate(newTemplate);
    localStorage.setItem('quiz-template', JSON.stringify(newTemplate));
  };

  return { template, saveTemplate, availableTemplates: Object.keys(TEMPLATES) };
}
```

---

## 🧩 Componente QuizLayout (Dinâmico)

```jsx
// layouts/QuizLayout.jsx

export function QuizLayout({ 
  template = 'classic',
  children,
  question,
  onAnswer,
  progress
}) {
  const { template: config } = useTemplate();

  // Renderizar dinamicamente baseado no template
  switch (config.id) {
    case 'classic':
      return (
        <ClassicLayout
          question={question}
          onAnswer={onAnswer}
          progress={progress}
        >
          {children}
        </ClassicLayout>
      );

    case 'modern':
      return (
        <ModernLayout
          question={question}
          onAnswer={onAnswer}
          progress={progress}
        >
          {children}
        </ModernLayout>
      );

    case 'minimal':
      return (
        <MinimalLayout
          question={question}
          onAnswer={onAnswer}
          progress={progress}
        >
          {children}
        </MinimalLayout>
      );

    default:
      return <ClassicLayout {...arguments[0]} />;
  }
}
```

---

## 🎨 Layout Responsivo

```jsx
// layouts/ClassicLayout.jsx

export function ClassicLayout({ question, onAnswer, progress, children }) {
  return (
    <div className="layout layout-classic">
      {/* Header */}
      <header className="layout-header">
        <h1>{progress.current} de {progress.total}</h1>
        <ProgressBar value={progress.percentage} />
      </header>

      {/* Main Content */}
      <main className="layout-main">
        <Card>
          <div className="question-section">
            <h2>{question.question}</h2>

            <div className="options-section">
              {question.options.map((option, index) => (
                <button
                  key={index}
                  className="option-button"
                  onClick={() => onAnswer(index)}
                >
                  <span className="option-letter">
                    {String.fromCharCode(97 + index)})
                  </span>
                  <span className="option-text">{option}</span>
                </button>
              ))}
            </div>
          </div>
        </Card>
      </main>

      {/* Footer/Navigation */}
      <footer className="layout-footer">
        <div className="navigation-buttons">
          <Button label="← Anterior" onClick={onPrevious} />
          <Button label="Próxima →" onClick={onNext} />
          <Button label="Enviar" onClick={onSubmit} variant="primary" />
        </div>
      </footer>
    </div>
  );
}
```

```css
/* styles/layouts/classic.css */

.layout-classic {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  gap: var(--spacing-xl);
  padding: var(--spacing-xl);
}

.layout-header {
  text-align: center;
  padding-bottom: var(--spacing-lg);
  border-bottom: 1px solid var(--color-secondary);
}

.layout-main {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.layout-main > .card {
  max-width: 800px;
  width: 100%;
}

.question-section {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
}

.options-section {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.option-button {
  display: flex;
  gap: var(--spacing-md);
  padding: var(--spacing-md);
  background-color: var(--color-bg-secondary);
  border: 2px solid var(--color-secondary);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all 0.2s;
}

.option-button:hover {
  background-color: var(--color-secondary);
  border-color: var(--color-primary);
}

.option-letter {
  font-weight: bold;
  color: var(--color-primary);
  min-width: 30px;
}

.layout-footer {
  display: flex;
  gap: var(--spacing-md);
  justify-content: center;
}

/* Responsivo */
@media (max-width: 768px) {
  .layout-classic {
    padding: var(--spacing-md);
    gap: var(--spacing-lg);
  }

  .layout-main > .card {
    max-width: 100%;
  }

  .layout-footer {
    flex-direction: column;
  }

  .layout-footer .btn {
    width: 100%;
  }
}
```

---

## 🌐 ModernLayout com Sidebar

```jsx
// layouts/ModernLayout.jsx

export function ModernLayout({ question, onAnswer, progress, children }) {
  return (
    <div className="layout layout-modern">
      {/* Sidebar */}
      <aside className="layout-sidebar">
        <div className="sidebar-section">
          <h3>Quiz List</h3>
          <QuizSelector />
        </div>

        <div className="sidebar-section">
          <h3>Progress</h3>
          <CircleProgress value={progress.percentage} />
        </div>

        <div className="sidebar-section">
          <h3>Time</h3>
          <Timer />
        </div>
      </aside>

      {/* Main Content */}
      <main className="layout-main-content">
        <QuestionCard question={question} onAnswer={onAnswer} />
      </main>
    </div>
  );
}
```

```css
.layout-modern {
  display: grid;
  grid-template-columns: 280px 1fr;
  min-height: 100vh;
  gap: var(--spacing-xl);
}

.layout-sidebar {
  background-color: var(--color-bg-secondary);
  padding: var(--spacing-lg);
  border-radius: var(--radius-lg);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xl);
  position: sticky;
  top: var(--spacing-lg);
  height: fit-content;
}

.layout-main-content {
  padding: var(--spacing-lg);
}

/* Mobile: Stack vertically */
@media (max-width: 768px) {
  .layout-modern {
    grid-template-columns: 1fr;
  }

  .layout-sidebar {
    position: static;
    flex-direction: row;
    overflow-x: auto;
  }
}
```

---

## 📋 Template Selector Component

```jsx
// components/TemplateSelector.jsx

export function TemplateSelector() {
  const { template, saveTemplate, availableTemplates } = useTemplate();

  return (
    <div className="template-selector">
      <label>Layout:</label>
      <select
        value={template.id}
        onChange={(e) => saveTemplate(e.target.value)}
      >
        {availableTemplates.map((id) => (
          <option key={id} value={id}>
            {TEMPLATES[id].name}
          </option>
        ))}
      </select>
    </div>
  );
}
```

---

## 🚀 Próximos Passos

1. [ ] Criar 3 templates em JSON
2. [ ] Implementar componente QuizLayout
3. [ ] Implementar useTemplate hook
4. [ ] Testar responsividade
5. [ ] Adicionar template customizador
6. [ ] Permitir salvar templates custom
7. [ ] Preview ao vivo (drag-drop)

---

## 🔗 Referências

- Godly Templates: https://godly.website/
- Grid Layout: https://developer.mozilla.org/en-US/docs/Web/CSS/CSS_Grid_Layout
- Responsive Design: https://web.dev/responsive-web-design-basics/
