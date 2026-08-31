# Componentes Reutilizáveis - Watermelon Pattern

## 📦 Filosofia Watermelon

Components **simples**, **reusáveis** e **compostas** para qualquer aplicação.

- ✓ Um componente = uma responsabilidade
- ✓ Props claras e bem tipadas
- ✓ Sem dependências externas (se possível)
- ✓ Estilização via CSS classes
- ✓ Composição sobre herança

---

## 🎨 Componentes Base (Web/Frontend)

### 1. Button - Padrão Único

```jsx
/**
 * Button - Botão reutilizável
 * 
 * Props:
 * - label (string): Texto do botão
 * - onClick (function): Callback ao clicar
 * - variant (string): 'primary' | 'secondary' | 'danger' | 'ghost'
 * - size (string): 'sm' | 'md' | 'lg'
 * - disabled (bool): Desabilitar
 * - loading (bool): Estado de carregamento
 * - className (string): Classes CSS adicionais
 */
export function Button({
  label,
  onClick,
  variant = "primary",
  size = "md",
  disabled = false,
  loading = false,
  className = ""
}) {
  return (
    <button
      className={`btn btn-${variant} btn-${size} ${className}`}
      onClick={onClick}
      disabled={disabled || loading}
      aria-busy={loading}
    >
      {loading ? (
        <span className="spinner" />
      ) : (
        label
      )}
    </button>
  );
}

// Exemplos de uso:
<Button label="Enviar" onClick={handleSubmit} />
<Button label="Deletar" variant="danger" />
<Button label="Processando..." loading={true} disabled={true} />
```

### 2. Card - Container Flexível

```jsx
/**
 * Card - Container com header, body e footer
 * 
 * Props:
 * - title (string): Título do card
 * - children (ReactNode): Conteúdo
 * - footer (ReactNode): Rodapé
 * - className (string): Classes adicionais
 * - onClick (function): Callback se clicável
 */
export function Card({
  title,
  children,
  footer = null,
  className = "",
  onClick = null
}) {
  return (
    <div
      className={`card ${className}`}
      onClick={onClick}
      role={onClick ? "button" : undefined}
    >
      {title && (
        <div className="card-header">
          <h3>{title}</h3>
        </div>
      )}
      <div className="card-body">
        {children}
      </div>
      {footer && (
        <div className="card-footer">
          {footer}
        </div>
      )}
    </div>
  );
}

// Exemplos:
<Card title="Quiz 1">
  <p>10 questões</p>
  <footer={<Button label="Fazer" />} />
</Card>

<Card onClick={() => selectQuiz(1)}>
  Clique aqui para selecionar
</Card>
```

### 3. Form - Input Controlado

```jsx
/**
 * Form - Wrapper para inputs com validação
 * 
 * Props:
 * - onSubmit (function): Callback ao submeter
 * - children (ReactNode): Inputs
 * - className (string): Classes
 */
export function Form({
  onSubmit,
  children,
  className = ""
}) {
  const handleSubmit = (e) => {
    e.preventDefault();
    onSubmit(e);
  };

  return (
    <form
      className={`form ${className}`}
      onSubmit={handleSubmit}
    >
      {children}
    </form>
  );
}

/**
 * FormInput - Input com label e validação
 * 
 * Props:
 * - label (string): Label
 * - name (string): Nome do input
 * - type (string): 'text' | 'email' | 'password' | etc
 * - value (string): Valor
 * - onChange (function): Callback ao mudar
 * - error (string): Mensagem de erro
 * - required (bool): Campo obrigatório
 */
export function FormInput({
  label,
  name,
  type = "text",
  value,
  onChange,
  error = null,
  required = false
}) {
  return (
    <div className="form-group">
      <label htmlFor={name}>
        {label}
        {required && <span className="required">*</span>}
      </label>
      <input
        id={name}
        name={name}
        type={type}
        value={value}
        onChange={onChange}
        className={error ? "input-error" : ""}
        required={required}
      />
      {error && (
        <span className="error-message">{error}</span>
      )}
    </div>
  );
}

// Exemplo:
<Form onSubmit={handleSubmit}>
  <FormInput
    label="Email"
    name="email"
    type="email"
    value={email}
    onChange={(e) => setEmail(e.target.value)}
    error={emailError}
    required
  />
  <Button label="Enviar" type="submit" />
</Form>
```

### 4. Modal - Diálogo Reutilizável

```jsx
/**
 * Modal - Diálogo com overlay
 * 
 * Props:
 * - isOpen (bool): Visível?
 * - onClose (function): Callback ao fechar
 * - title (string): Título
 * - children (ReactNode): Conteúdo
 * - footer (ReactNode): Ações
 */
export function Modal({
  isOpen,
  onClose,
  title,
  children,
  footer = null
}) {
  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal-content"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-header">
          <h2>{title}</h2>
          <button
            className="modal-close"
            onClick={onClose}
            aria-label="Fechar"
          >
            ×
          </button>
        </div>
        <div className="modal-body">
          {children}
        </div>
        {footer && (
          <div className="modal-footer">
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}

// Exemplo:
const [isOpen, setIsOpen] = useState(false);

<Modal
  isOpen={isOpen}
  onClose={() => setIsOpen(false)}
  title="Confirmação"
>
  Tem certeza?
  <footer={
    <>
      <Button label="Cancelar" onClick={() => setIsOpen(false)} />
      <Button label="Confirmar" onClick={handleConfirm} variant="danger" />
    </>
  } />
</Modal>
```

### 5. Alert - Notificações

```jsx
/**
 * Alert - Mensagem ao usuário
 * 
 * Props:
 * - message (string): Mensagem
 * - type (string): 'success' | 'error' | 'warning' | 'info'
 * - onClose (function): Callback ao fechar
 */
export function Alert({
  message,
  type = "info",
  onClose
}) {
  return (
    <div className={`alert alert-${type}`}>
      <span>{message}</span>
      {onClose && (
        <button onClick={onClose} className="alert-close">
          ×
        </button>
      )}
    </div>
  );
}

// Exemplo:
<Alert
  type="success"
  message="Quiz enviado com sucesso!"
  onClose={() => setAlert(null)}
/>
```

---

## 🧩 Componentes Compostos

Combinar componentes base para formar componentes maiores.

### QuestionCard - Card + Button

```jsx
export function QuestionCard({ question, onSelect }) {
  return (
    <Card
      title={`Questão ${question.id}`}
      onClick={() => onSelect(question.id)}
    >
      <p className="question-text">{question.question}</p>
      <div className="options">
        {question.options.map((opt, i) => (
          <div key={i} className="option">
            {String.fromCharCode(97 + i)}) {opt}
          </div>
        ))}
      </div>
      <footer={
        <Button
          label="Responder"
          size="sm"
          onClick={() => onSelect(question.id)}
        />
      } />
    </Card>
  );
}
```

### QuizResult - Card + Alert

```jsx
export function QuizResult({ result }) {
  return (
    <Card title="Resultado">
      <Alert
        type={result.percentage >= 70 ? "success" : "warning"}
        message={`Você acertou ${result.score}/${result.total}`}
      />
      <div className="result-details">
        <p>Percentual: {result.percentage}%</p>
      </div>
      <footer={
        <Button label="Voltar" onClick={() => window.location.reload()} />
      } />
    </Card>
  );
}
```

---

## 🎨 CSS Classes Pattern

```css
/* Components seguem padrão consistente */

.btn {
  /* Base */
  padding: var(--spacing-md);
  border: 1px solid;
  border-radius: var(--radius-md);
  cursor: pointer;
  font-weight: 500;
  transition: all 0.2s;
}

.btn-primary {
  background-color: var(--color-primary);
  color: white;
  border-color: var(--color-primary);
}

.btn-primary:hover {
  background-color: var(--color-primary-dark);
}

.btn-secondary {
  background-color: var(--color-secondary);
  color: var(--color-text);
  border-color: var(--color-secondary);
}

/* Variações de tamanho */
.btn-sm {
  padding: var(--spacing-sm);
  font-size: 0.875rem;
}

.btn-lg {
  padding: var(--spacing-lg);
  font-size: 1.125rem;
}

/* Desabilitar */
.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
```

---

## 📝 Checklist para Novo Componente

Antes de criar um novo componente:

- [ ] É reutilizável em 2+ lugares?
- [ ] Tem uma única responsabilidade?
- [ ] Props são claras e bem nomeadas?
- [ ] Tem defaultProps para valores opcionais?
- [ ] Tem JSDoc comentário?
- [ ] É acessível (a11y)?
- [ ] Funciona sem dependências externas?
- [ ] Há exemplos de uso?
- [ ] Testado manualmente?

---

## 🚀 Próximos Componentes

- [ ] Pagination - Navegação entre páginas
- [ ] Table - Tabelas reutilizáveis
- [ ] Dropdown - Menus suspensos
- [ ] Loading - Estado de carregamento
- [ ] Tooltip - Dicas de ferramentas
- [ ] Stepper - Progresso passo-a-passo

---

## 🔗 Storybook (Futuro)

Para documentar e testar componentes:

```bash
npm install -D @storybook/react

# Storybook para Button
// Button.stories.jsx
export default {
  title: "Components/Button",
  component: Button,
};

export const Primary = () => (
  <Button label="Click me" variant="primary" />
);

export const Loading = () => (
  <Button label="Loading..." loading={true} />
);
```
