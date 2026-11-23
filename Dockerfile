# syntax=docker/dockerfile:1
# SDG Align backend. CPU only. Built with Cloud Build (no local Docker needed). No secrets are baked in:
# GEMINI_API_KEY is injected at run time from Secret Manager. The source PDFs are NOT in the image.

# ---------- builder: wheels + the pinned embedding model ----------
FROM python:3.12-slim AS builder
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONDONTWRITEBYTECODE=1
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" HF_HOME=/opt/hf
WORKDIR /build
COPY requirements.txt requirements-local.txt ./
# CPU-only torch wheel (the default PyPI wheel pulls ~2 GB of CUDA libraries).
RUN pip install --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.txt -r requirements-local.txt
COPY scripts/ scripts/
COPY src/ src/
# The one place a download is allowed: pin = DEFAULT_REVISION in scripts/embedding_provider_local.py.
RUN ALLOW_MODEL_DOWNLOAD=true PYTHONPATH=/build python -c "\
from scripts.embedding_provider_local import _load_sentence_transformer as load, DEFAULT_MODEL_NAME as m, DEFAULT_REVISION as r; \
load(m, r, 1); print('baked', m, r)"

# ---------- runtime ----------
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" HF_HOME=/opt/hf HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
    EMBEDDING_PROVIDER=local NETWORK_CALLS_PERMITTED=false PYTHONPATH=/app
RUN useradd --system --uid 10001 --home /app app
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /opt/hf /opt/hf
COPY scripts/ scripts/
COPY src/ src/
COPY config/ config/
# Derived corpus only (manifest, chunks, index). No PDFs, no extracted text.
COPY data/proposals/manifest.json data/proposals/manifest.json
COPY data/proposals/chunks/ data/proposals/chunks/
COPY data/proposals/vector_index/ data/proposals/vector_index/
RUN chown -R app:app /app
USER app
EXPOSE 8080
ENV PORT=8080
# Startup checks (scripts/startup_checks.py) refuse to start if the corpus or index is missing or mismatched.
CMD ["sh", "-c", "exec uvicorn scripts.backend_server:app --host 0.0.0.0 --port ${PORT}"]
