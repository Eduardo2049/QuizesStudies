"""
DEPRECATED - Quiz API Legacy

Este arquivo era o ponto de entrada original.
Agora use o novo entry point que usa padrão Spring Pattern.

Substitua:
  python quiz_api_legacy.py
  
Por:
  python quiz_api.py
  
Ou:
  python -m api.main

A nova arquitetura é totalmente compatível com as mesmas funcionalidades!
"""

from api.main import start_server

if __name__ == "__main__":
    print("⚠️  quiz_api_legacy.py está DEPRECATED")
    print("✓ Use 'python quiz_api.py' em vez disso")
    print()
    start_server()
