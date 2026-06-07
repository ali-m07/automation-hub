# syntax=docker/dockerfile:1.7

ARG PYTHON_VERSION=3.11

# Shared Python runtime settings. This stage contains no application code.
FROM python:${PYTHON_VERSION}-slim-bookworm AS python-base

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_DATA_DIR=/app/data \
    FONT_DIR=/app/fonts

WORKDIR /app


# Compile/download Python dependencies into portable wheels. Compilers and
# headers stay in this stage and never enter the final runtime image.
FROM python-base AS wheels

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        unixodbc-dev

COPY requirements.txt /tmp/requirements.txt

RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip wheel \
        --wheel-dir=/tmp/wheels \
        --requirement=/tmp/requirements.txt


# Install only wheels into a clean prefix. This keeps build tooling and pip
# download state out of the production image.
FROM python-base AS python-deps

COPY --from=wheels /tmp/wheels /tmp/wheels
COPY requirements.txt /tmp/requirements.txt

RUN python -m pip install \
        --no-index \
        --find-links=/tmp/wheels \
        --prefix=/opt/python \
        --requirement=/tmp/requirements.txt \
    && rm -rf /tmp/wheels /tmp/requirements.txt


# Minimal production runtime.
FROM python-base AS runtime

ARG TARGETARCH

# Runtime libraries for pandas/numpy, image/font processing, and SQL Server.
# TARGETARCH keeps Microsoft's repository aligned with BuildKit multi-platform
# builds (amd64 and arm64).
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        gnupg \
        libgomp1 \
        fonts-dejavu-core \
        fonts-liberation \
    && install -d -m 0755 /etc/apt/keyrings \
    && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc \
        | gpg --dearmor -o /etc/apt/keyrings/microsoft.gpg \
    && printf 'deb [arch=%s signed-by=/etc/apt/keyrings/microsoft.gpg] https://packages.microsoft.com/debian/12/prod bookworm main\n' "${TARGETARCH:-amd64}" \
        > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends \
        msodbcsql18 \
        unixodbc \
    && apt-get purge -y --auto-remove gnupg \
    && rm -rf /var/lib/apt/lists/*

# Create the runtime identity before copying application source.
RUN groupadd --system --gid 10001 hubgroup \
    && useradd --system --uid 10001 --gid hubgroup --home-dir /app hubuser \
    && mkdir -p \
        /app/data \
        /app/uploads \
        /app/outputs \
        /app/gallery \
        /app/templates_psd \
        /app/fonts \
    && chown -R hubuser:hubgroup \
        /app/data \
        /app/uploads \
        /app/outputs \
        /app/gallery \
        /app/templates_psd \
        /app/fonts

COPY --from=python-deps /opt/python /usr/local
COPY --chown=hubuser:hubgroup . /app

USER hubuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5)"]

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
