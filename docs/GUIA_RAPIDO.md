# GUIA RÁPIDO - Onde Começar

## 🎯 Você precisa de...

### Entender a nova arquitetura?
→ Leia: `docs/RESUMO_EXECUTIVO.md` (5 min)

### Entender Spring Pattern no backend?
→ Leia: `docs/MELHORIAS_ARQUITETURAIS.md` (10 min)

### Sou desenvolvedor backend, como contribuo?
→ Leia: `docs/PADROES_DESENVOLVIMENTO_MANUS.md` (15 min)
→ Ver exemplo em: `api/controllers/` , `api/services/` , `api/repositories/`

### Sou desenvolvedor frontend, como contribuo?
→ Leia: `docs/COMPONENTES_WATERMELON.md` (15 min)
→ Leia: `docs/TEMAS_REALTIMECOLORS.md` (10 min)
→ Leia: `docs/TEMPLATES_GODLY.md` (10 min)

### Quero customizar cores?
→ Vá para: https://www.realtimecolors.com/
→ Leia: `docs/TEMAS_REALTIMECOLORS.md` - Seção "Exportar Paleta"
→ Arquivo a editar: `web/styles/variables.css`

### Quero adicionar novo layout?
→ Leia: `docs/TEMPLATES_GODLY.md`
→ Criar: `web/templates/seu-layout.json`
→ Criar: `web/layouts/SeuLayout.jsx`

### Quero adicionar novo endpoint?
→ Leia: `docs/PADROES_DESENVOLVIMENTO_MANUS.md` - Seção "Feature: Nova Rota GET"
→ Criar arquivo FEATURE.md com especificação
→ Implementar: Controller → Service → Repository

### Preciso de testes?
→ Pasta: `tests/` (será criada)
→ Padrão: Um arquivo de teste por módulo

---

## 📂 Estrutura de Arquivos Explicada

```
api/
├── controllers/          ← ROTAS (HTTP)
│   └── quiz_controller.py
│       └── get_quizzes()  ← Método GET /api/quizzes
│       └── get_quiz()     ← Método GET /api/quiz?source=...
│       └── submit_answers() ← Método POST /api/quiz/submit

├── services/             ← LÓGICA (Negócio)
│   └── quiz_service.py
│       └── service = QuizService(repository)
│       └── service.get_all_quizzes()
│       └── service.get_quiz()
│       └── service.submit_answers()

├── repositories/         ← DADOS (Leitura/Escrita)
│   └── quiz_repository.py
│       └── find_all_sources()
│       └── find_by_name()
│       └── read_file()
│       └── save_file()

├── models/               ← ESTRUTURAS (DTOs)
│   └── dtos.py
│       └── QuestionDTO
│       └── QuizDTO
│       └── SubmitAnswersDTO
│       └── GradeResultDTO

├── exceptions/           ← ERROS (Centralizados)
│   └── quiz_exceptions.py
│       └── QuizNotFound
│       └── InvalidAnswersFormat
│       └── InvalidMarkdownFormat

└── handlers/             ← HTTP (Entrada/Saída)
    ├── quiz_handler_v2.py ← ✓ NOVO (Spring Pattern)
    │   └── do_GET()
    │   └── do_POST()
    │   └── send_json()
    └── quiz_handler.py   ← Legacy (antes)
```

---

## 🔄 Fluxo Completo - Exemplo

### Usuário clica "Enviar Respostas"

```
1. FRONTEND (web/src/App.jsx)
   ├─ Coleta respostas
   ├─ POST /api/quiz/submit
   └─ { answers: {1: 2, 2: 0, ...}, source: "1 test" }

2. HTTP HANDLER (api/handlers/quiz_handler_v2.py)
   ├─ do_POST() captura requisição
   ├─ Valida JSON
   └─ Chama controller.submit_answers(payload)

3. CONTROLLER (api/controllers/quiz_controller.py)
   ├─ Valida formato: answers é dict?
   ├─ Cria DTO: SubmitAnswersDTO
   └─ Chama service.submit_answers()

4. SERVICE (api/services/quiz_service.py)
   ├─ Obtém caminho do quiz: find_by_name()
   ├─ Carrega questões com respostas
   ├─ Chama grade_answers(answers, questions)
   └─ Retorna GradeResultDTO

5. REPOSITORY (api/repositories/quiz_repository.py)
   ├─ find_by_name("1 test") → Path
   └─ Retorna caminho do arquivo

6. UTILS (api/utils/quiz_logic.py)
   ├─ grade_answers()
   ├─ Compara resposta com gabarito
   ├─ Calcula score/percentage
   └─ Retorna resultado

7. BACKEND (api/handlers/quiz_handler_v2.py)
   ├─ Formata resposta JSON
   └─ Retorna: { status: "success", data: { ... } }

8. FRONTEND (web/src/App.jsx)
   ├─ Recebe JSON
   ├─ Renderiza resultado
   └─ Exibe "Acertou 7/10"
```

---

## 💡 Padrão de Desenvolvimento (Manus)

### Você quer adicionar "Favoritar Quiz"

#### Fase 1: ESPECIFICAÇÃO
Crie arquivo `FEATURE_FAVORITE_QUIZ.md`:
```markdown
# Feature: Favoritar Quiz

## Objetivo
Permitir usuário marcar quizzes como favoritos

## Entrada
POST /api/quiz/1/favorite
{ "isFavorite": true }

## Saída
{ "status": "success", "data": { "favorited": true } }

## Casos Extremos
- Quiz não existe? → 404
- Usuário não autenticado? → 401
```

#### Fase 2: DESIGN
```markdown
## Design

### Componentes
- Controller: QuizController.favorite_quiz()
- Service: QuizService.toggle_favorite()
- Repository: QuizRepository.save_favorite()
- Exception: QuizNotFound, UnauthorizedException

### Fluxo
Request → Controller → Service → Repository → Response
```

#### Fase 3: IMPLEMENTAÇÃO

**1. DTO (models/dtos.py)**
```python
@dataclass
class FavoriteDTO:
    quiz_id: int
    is_favorite: bool
```

**2. Exception (exceptions/quiz_exceptions.py)**
```python
class UnauthorizedException(QuizAPIException):
    def __init__(self):
        super().__init__("Acesso negado", 401)
```

**3. Repository (repositories/quiz_repository.py)**
```python
def save_favorite(self, quiz_id: int, is_favorite: bool):
    # Salvar em arquivo ou BD
    pass
```

**4. Service (services/quiz_service.py)**
```python
def toggle_favorite(self, quiz_id: int, is_favorite: bool):
    self.repository.save_favorite(quiz_id, is_favorite)
    return {"favorited": is_favorite}
```

**5. Controller (controllers/quiz_controller.py)**
```python
def toggle_favorite(self, quiz_id: int, is_favorite: bool):
    self.service.toggle_favorite(quiz_id, is_favorite)
    return {"status": "success", "data": {"favorited": is_favorite}}
```

**6. Handler (handlers/quiz_handler_v2.py)**
```python
if request.path == f"/api/quiz/{quiz_id}/favorite":
    response = self.quiz_controller.toggle_favorite(...)
    self.send_json(200, response)
```

#### Fase 4: TESTES
```python
# tests/test_quiz_service.py
def test_favorite_quiz():
    service = QuizService()
    result = service.toggle_favorite(1, True)
    assert result["favorited"] == True
```

---

## 🎨 Como Usar o Theme System

### 1. Mudar cor em tempo real
```javascript
// web/src/hooks/useTheme.js
const { theme, toggleTheme } = useTheme();

// Mudar para dark
toggleTheme(); // light → dark

// Ou direto
setTheme('dark');
```

### 2. Usar cores nos componentes
```css
/* Usar variáveis */
.btn {
  background-color: var(--color-primary);
  color: var(--color-bg);
  padding: var(--spacing-md);
}
```

### 3. Gerar paleta nova
1. Ir para https://www.realtimecolors.com/
2. Escolher cores
3. Clicar "Export" → "CSS Variables"
4. Colar em `web/styles/variables.css`
5. Pronto! Tudo muda automaticamente

---

## 📐 Como Usar Layouts (Godly)

### 1. Selecionar layout
```jsx
// Componente no App.jsx
<TemplateSelector />

// Usuário clica "Modern" → Salva em localStorage
// Próxima vez que abrir, já está em Modern
```

### 2. Criar novo layout
```
1. Criar arquivo: web/templates/seu-layout.json
2. Copiar estrutura do classic.json
3. Mudar valores de grid/flex
4. Criar web/layouts/SeuLayout.jsx
5. Adicionar case no QuizLayout.jsx
```

### 3. Exemplo: Layout de Poster
```json
{
  "id": "poster",
  "name": "Poster",
  "sections": {
    "main": {
      "layout": "vertical",
      "components": ["title", "big-question", "options-grid"]
    }
  }
}
```

---

## 🚀 Executar Hoje

### Teste a nova arquitetura:
```bash
# Terminal
python quiz_api.py

# Deve mostrar:
# ✓ Quiz online em http://localhost:8000
# Handler: QuizHandlerV2 (Spring Pattern)
```

### Verificar que tudo funciona:
1. Abra http://localhost:8000
2. Clique "Selecionar Quiz"
3. Responda as questões
4. Clique "Enviar"
5. Veja resultado

### Por trás dos panos:
- `Handler V2` recebeu a requisição
- `QuizController` processou
- `QuizService` executou lógica
- `QuizRepository` leu arquivo
- Tudo funcionou! ✓

---

## 📊 Próximas Horas/Dias

| Atividade | Tempo | Arquivo |
|-----------|-------|---------|
| Ler arquitetura | 5 min | RESUMO_EXECUTIVO.md |
| Implementar componentes | 2-4 h | web/src/components/ |
| Integrar theme system | 1-2 h | web/styles/ + hooks/ |
| Criar 3 layouts | 2-3 h | web/templates/ + layouts/ |
| Testes unitários | 2-3 h | tests/ |
| Deploy | 1-2 h | n8n + Docker |

---

## ❓ FAQ

**P: Preciso deletar o código antigo?**  
R: Não, `quiz_api.py` ainda funciona como antes. A refatoração é compatível.

**P: Posso usar Handler V1?**  
R: Sim, `USE_V2_HANDLER=false python quiz_api.py`

**P: Como testo os componentes?**  
R: Instale Storybook: `npm install -D @storybook/react`

**P: Posso mudar a paleta de cores?**  
R: Sim! Vá para RealtimeColors.com e exporte as variáveis.

**P: Como integro n8n?**  
R: Veja `docs/MELHORIAS_ARQUITETURAIS.md` - Fase 4

---

## 🎓 Links Úteis

- 📖 Documentação completa: `docs/`
- 🧪 Exemplos de código: `api/controllers/`, `api/services/`
- 🎨 Componentes: `web/src/components/` (será criado)
- 🎭 Layouts: `web/layouts/` (será criado)
- 🌈 Cores: `web/styles/variables.css` (será criado)

---

## ✅ Checklist Onboarding

- [ ] Li RESUMO_EXECUTIVO.md
- [ ] Entendi Spring Pattern
- [ ] Testei backend (python quiz_api.py)
- [ ] Apliquei novo Handler V2
- [ ] Criei primeiro componente React
- [ ] Testei theme switching
- [ ] Criei novo layout
- [ ] Pronto para produção!

---

**Bem-vindo à arquitetura IFuture_Study 2.0! 🚀**
