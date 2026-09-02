"""Configurações da aplicação"""
import os
from pathlib import Path

# Caminhos
ROOT = Path(__file__).parent.parent.parent
API_DIR = ROOT / "api"
WEB_DIR = ROOT / "web"

# Server
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", os.getenv("QUIZ_PORT", "8000")))

# Logging
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

