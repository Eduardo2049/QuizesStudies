"""
Quiz API - Servidor HTTP para aplicação de Quizzes

Execução:
  python quiz_api.py
  
Ou usando o novo módulo estruturado:
  python -m api.main

Estrutura do projeto:
  api/
    ├── main.py              (servidor principal)
    ├── handlers/
    │   └── quiz_handler.py  (requisições HTTP)
    └── utils/
        ├── config.py        (configurações)
        ├── markdown_parser.py (parse de questões)
        └── quiz_logic.py    (lógica de correção)
"""

from api.main import start_server

if __name__ == "__main__":
    start_server()
