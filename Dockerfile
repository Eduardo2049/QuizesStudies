FROM python:3.11-slim

WORKDIR /app

# Configurações de ambiente
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOST=0.0.0.0 \
    PORT=8000

# Instalação de dependências (se houver)
COPY requirements.txt ./
RUN if [ -s requirements.txt ]; then pip install --no-cache-dir -r requirements.txt; fi

# Cópia do código
COPY . .

EXPOSE 8000

CMD ["python", "quiz_api.py"]
