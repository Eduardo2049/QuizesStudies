# ─── Stage 1: Builder ────────────────────────────────────────────────────────
# Compila dependências que requerem gcc (ex: psycopg2-binary)
FROM python:3.11.11-slim@sha256:614c8e5efd88a1e02137d281a69baa675c5797a2e5da0fc4a5d56b05a1964e6c AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ─── Stage 2: Runtime (sem gcc, menor e mais seguro) ─────────────────────────
FROM python:3.11.11-slim@sha256:614c8e5efd88a1e02137d281a69baa675c5797a2e5da0fc4a5d56b05a1964e6c

WORKDIR /app

# Apenas dependências de runtime (libpq para psycopg2)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Configurações de ambiente
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOST=0.0.0.0 \
    PORT=8000

# Copiar pacotes Python compilados do builder
COPY --from=builder /install /usr/local

# Criar usuário não-root ANTES de copiar código
RUN useradd -m -u 1000 appuser

# Copiar código da aplicação com ownership correto (sem chown -R posterior)
COPY --chown=appuser:appuser . .

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["sh", "-c", "curl -f http://localhost:8000/api/quizzes || exit 1"]

CMD ["python", "quiz_api.py"]
