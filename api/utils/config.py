"""Configurações da aplicação"""
import os
from pathlib import Path

# Caminhos
ROOT = Path(__file__).parent.parent.parent
API_DIR = ROOT / "api"
WEB_DIR = ROOT / "web"

# Server
HOST = "127.0.0.1"
PORT = int(os.getenv("QUIZ_PORT", "8000"))

# Logging
DEBUG = os.getenv("DEBUG", "false").lower() == "true"
