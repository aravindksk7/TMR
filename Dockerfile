# ── Stage 1: base — Python 3.11 slim + Microsoft ODBC Driver 18 ───────────────
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System packages + Microsoft ODBC Driver 18 for SQL Server
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl gnupg unixodbc unixodbc-dev \
    && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc \
       | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
    && curl -fsSL https://packages.microsoft.com/config/debian/12/prod.list \
       > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 mssql-tools18 \
    && ln -sfn /opt/mssql-tools18/bin/sqlcmd /usr/local/bin/sqlcmd \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Stage 2: deps — install Python dependencies (no package source needed) ────
FROM base AS deps

# Copy only the manifest so this layer is cached unless deps change
COPY pyproject.toml ./
# Create a minimal stub so pip can resolve the project metadata
RUN mkdir -p src/qa_pipeline && touch src/qa_pipeline/__init__.py

# Install all runtime + dev deps; skip installing the package itself here
RUN pip install \
        httpx>=0.27 \
        tenacity>=8.3 \
        "pydantic>=2.7" \
        "pydantic-settings>=2.3" \
        "pyodbc>=5.1" \
        "APScheduler>=3.10,<4" \
        "SQLAlchemy>=2.0" \
        "structlog>=24.1" \
        "python-dotenv>=1.0" \
        "pytest>=8.2" \
        "pytest-mock>=3.14" \
        "respx>=0.21"

# ── Stage 3: app — add source and install the package ─────────────────────────
FROM deps AS app

# Remove the stub and copy the real source
RUN rm -rf src/qa_pipeline
COPY src/       ./src/
COPY config/    ./config/
COPY scripts/   ./scripts/
COPY tests/     ./tests/
COPY docker/    ./docker/

# Install the qa_pipeline package in editable mode (resolves imports)
RUN pip install -e .

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["test"]
