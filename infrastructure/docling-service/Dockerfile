# Docling conversion service for Cloud Run. Build from the repo root:
#   docker build -f infrastructure/docling-service/Dockerfile -t docling-service .
#
# Cloud Run is linux/amd64 (the dev-caa VM is arm64); both resolve from the same
# uv.lock. Only the `service` dependency group is installed, so the image carries
# docling and the web server but none of the app's agent/database dependencies.
FROM python:3.12-slim-bookworm

# OpenCV runtime libraries docling needs for table extraction (see playbook.yml).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PATH="/app/.venv/bin:$PATH"

# Dependencies first: this layer only changes when pyproject.toml / uv.lock do.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --only-group service --no-install-project

# Bake the models into the image so a cold start downloads nothing. Pipeline
# stages the app uses: layout, table structure, OCR (rapidocr is what docling's
# "auto" engine selects on Linux with this lock). If a stage is added to
# convert_content, add its model here or it will fail offline.
ENV DOCLING_ARTIFACTS_PATH=/opt/docling-models
RUN docling-tools models download -q -o "$DOCLING_ARTIFACTS_PATH" \
    layout tableformer rapidocr
ENV HF_HUB_OFFLINE=1

COPY lib ./lib

# Requests may write only below this directory (see lib/docling_service/app.py).
ENV DOCLING_ALLOWED_ROOT=/var/caa
RUN useradd --create-home service && mkdir -p /var/caa && chown service /var/caa
USER service

# Cloud Run supplies $PORT. One conversion at a time per instance: deploy with
# --concurrency=1.
CMD ["sh", "-c", "exec uvicorn lib.docling_service.app:app --host 0.0.0.0 --port ${PORT:-8080}"]
