FROM python:3.11-slim

WORKDIR /app

# Dependências do sistema para pdfplumber (poppler)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpoppler-cpp-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Configurações de ambiente
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOST=0.0.0.0 \
    PORT=8000

# Dependências Python
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Código da aplicação
COPY . .

EXPOSE 8000

CMD ["python", "quiz_api.py"]
