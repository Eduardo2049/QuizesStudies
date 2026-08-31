# Padrão de Desenvolvimento - Manus Style

## 🎯 Workflow de Desenvolvimento

Antes de escrever QUALQUER código, seguir este checklist:

### 1️⃣ ESPECIFICAÇÃO (Criar arquivo FEATURE.md)

```markdown
# Feature: [Nome]

## Objetivo
O que vai ser feito? Por quê?

## Entrada (Input)
- Parâmetros
- Tipos
- Validações

## Saída (Output)
- Retorno esperado
- Estrutura dos dados
- Casos extremos

## Exemplos
```python
# Entrada
input_exemplo = {...}

# Saída esperada
output_esperado = {...}
```

## Casos Extremos
- O que acontece se entrada é vazia?
- O que acontece se arquivo não existe?
- O que acontece se JSON é inválido?
```

### 2️⃣ DESIGN (Adicionar ao FEATURE.md)

```markdown
## Design

### Componentes
- Qual controller?
- Qual service?
- Qual repository?

### Fluxo
```
Request → Controller → Service → Repository → Response
```

### Mudanças em Arquivos
- Qual arquivo vai mudar?
- Qual classe será adicionada?
- Há impacto em outras partes?
```

### 3️⃣ IMPLEMENTAÇÃO

Regras:
- ✓ Seguir padrão Spring (Controller → Service → Repository)
- ✓ Criar DTOs para entrada/saída
- ✓ Criar exceções customizadas
- ✓ Adicionar docstrings
- ✓ Validar entrada

Não fazer:
- ✗ Lógica no Handler
- ✗ Arquivo direto no Controller
- ✗ Sem validação
- ✗ Sem testes

### 4️⃣ VALIDAÇÃO

Checklist:
- [ ] Código segue padrão?
- [ ] Testes passam?
- [ ] Sem regressões?
- [ ] Performance OK?
- [ ] Documentação atualizada?

---

## 📝 Exemplo Prático: Adicionar Upload de Quiz

### 1️⃣ ESPECIFICAÇÃO

```markdown
# Feature: Upload de Arquivo Markdown

## Objetivo
Permitir usuários enviar um arquivo .md com um novo quiz

## Entrada
```
POST /api/upload
{
  "filename": "meu_quiz.md",
  "content": "**1.** Pergunta?\na) opção..."
}
```

## Saída
```json
{
  "status": "success",
  "data": {
    "filename": "meu_quiz.md",
    "message": "Quiz criado com sucesso!"
  }
}
```

## Casos Extremos
- Filename vazio? → Erro 400
- Content vazio? → Erro 400
- Markdown inválido? → Erro 400 com mensagem
- Arquivo já existe? → Sobrescrever ou Erro?
```

### 2️⃣ DESIGN

**Componentes:**
- Controller: UploadController
- Service: MarkdownService
- Repository: QuizRepository
- Exception: InvalidMarkdownFormat

**Fluxo:**
```
POST /api/upload
    ↓
UploadController.upload_file()
    ↓
MarkdownService.validate_markdown()
    ↓
MarkdownService.save_quiz_from_markdown()
    ↓
QuizRepository.save_file()
    ↓
Response JSON
```

### 3️⃣ IMPLEMENTAÇÃO

```python
# api/controllers/upload_controller.py
class UploadController:
    def upload_file(self, filename: str, content: str) -> dict:
        """
        Faz upload de novo quiz.
        
        Args:
            filename: Nome do arquivo
            content: Conteúdo Markdown
            
        Returns:
            dict com status e dados
            
        Raises:
            QuizAPIException se inválido
        """
        # 1. Validar
        is_valid, error = self.markdown_service.validate_markdown(content)
        if not is_valid:
            raise InvalidMarkdownFormat(error)
        
        # 2. Salvar
        path = self.markdown_service.save_quiz_from_markdown(filename, content)
        
        # 3. Retornar
        return {
            "status": "success",
            "data": {
                "filename": path.name,
                "message": f"Quiz '{filename}' criado com sucesso!"
            }
        }
```

### 4️⃣ VALIDAÇÃO

Tests:
```python
def test_upload_valid_file():
    controller = UploadController()
    result = controller.upload_file("test.md", "**1.** Test?\na) Yes")
    assert result["status"] == "success"

def test_upload_invalid_markdown():
    controller = UploadController()
    with pytest.raises(InvalidMarkdownFormat):
        controller.upload_file("bad.md", "invalid content")
```

---

## 🎓 Padrões por Tipo de Feature

### Feature: Nova Rota GET

**Template:**
```python
# 1. DTO de resposta
@dataclass
class MyResponseDTO:
    data: str

# 2. Service
class MyService:
    def get_data(self) -> MyResponseDTO:
        return MyResponseDTO(data="...")

# 3. Controller
class MyController:
    def get_data(self) -> dict:
        dto = self.service.get_data()
        return {"status": "success", "data": dto}

# 4. Handler
def do_GET(self):
    if request.path == "/api/my-route":
        response = self.controller.get_data()
        self.send_json(200, response)
```

### Feature: Nova Validação

**Template:**
```python
# 1. Exception customizada
class InvalidMyData(QuizAPIException):
    def __init__(self):
        super().__init__("My data is invalid", 400)

# 2. Validator
def validate_my_data(data: str) -> bool:
    return len(data) > 0

# 3. Use no Service
def process_data(self, data: str):
    if not validate_my_data(data):
        raise InvalidMyData()
    # continuar...
```

### Feature: Novo Repository

**Template:**
```python
class MyRepository:
    def find_all(self) -> list:
        """Retorna todos"""
        pass
    
    def find_by_id(self, id: int):
        """Retorna um"""
        pass
    
    def save(self, item):
        """Salva"""
        pass
    
    def delete(self, id: int):
        """Deleta"""
        pass
```

---

## 📊 Checklist de Código

Antes de fazer PR:

- [ ] Arquivo FEATURE.md criado com Especificação + Design?
- [ ] DTO criado (entrada/saída)?
- [ ] Exception customizada criada?
- [ ] Camadas separadas (Controller → Service → Repository)?
- [ ] Testes escritos?
- [ ] Docstrings em todas as funções?
- [ ] Sem código duplicado?
- [ ] Segue style guide Python?
- [ ] Sem secrets/passwords no código?
- [ ] Performance aceitável?

---

## 🔗 Referências

- Spring Patterns: https://spring.io/guides/gs/
- Python Best Practices: https://pep8.org/
- Dataclass: https://docs.python.org/3/library/dataclasses.html
- Type Hints: https://docs.python.org/3/library/typing.html

---

## ✅ Próximas Features

1. [ ] Upload de PDF → Extração de texto
2. [ ] Integração n8n
3. [ ] Temas customizáveis (RealtimeColors)
4. [ ] Templates de layout (Godly)
5. [ ] Analytics dashboard
