# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Builder stage: resolve and install the locked dependency set + the project
# into a self-contained virtual environment the runtime stage simply COPYies.
# ---------------------------------------------------------------------------
FROM python:3.14-slim AS builder

# Bring in the uv static binary (pinned to a released version for reproducibility).
COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /usr/local/bin/uv

# git is needed to install git dependencies (robotsix-llmio, etc.)
# during the uv pip install below.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

ENV UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# Create the self-contained virtual environment up front.
RUN python -m venv /opt/venv
ENV VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

# Copy only what is needed to resolve and build the project. README.md is
# included because pyproject declares it as the project readme — hatchling
# reads it while building the wheel.
COPY pyproject.toml uv.lock README.md ./
COPY src ./src

# robotsix-ui shared CSS — install the npm package and copy the compiled
# dist/style.css into the static directory so the dashboard can serve it
# at /static/robotsix-ui/style.css without vendoring the CSS in the repo.
# Node is already available at this point (the base python:3.14-slim image
# does not ship npm; we add it here).
RUN apt-get update \
    && apt-get install -y --no-install-recommends npm \
    && rm -rf /var/lib/apt/lists/*
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts \
    && mkdir -p src/robotsix_cost_monitor/web/static/robotsix-ui \
    && cp node_modules/@robotsix/ui/dist/style.css \
       node_modules/@robotsix/ui/dist/vanilla.js \
       src/robotsix_cost_monitor/web/static/robotsix-ui/ \
    && rm -rf node_modules package.json package-lock.json

# Export the EXACT revisions pinned in uv.lock (no fresh resolution), install
# them, then install the project itself with --no-deps so they are not
# re-resolved. The LLM cost-analyst (robotsix-llmio) is a regular dependency
# so it is always included; the dashboard runs fine without configuring it.
RUN uv export --frozen --no-emit-project --no-hashes > requirements.txt \
    && uv pip install --python /opt/venv/bin/python -r requirements.txt \
    && uv pip install --python /opt/venv/bin/python --no-deps . \
    && uv export --format cyclonedx1.5 --frozen --preview-features sbom-export > /app/sbom.cyclonedx.json

# ---------------------------------------------------------------------------
# Runtime stage: minimal image with only the prebuilt virtual environment,
# running as a non-root user.
# ---------------------------------------------------------------------------
FROM python:3.14-slim AS runtime

# Copy the prebuilt virtual environment (deps + project) from the builder stage.
COPY --from=builder /opt/venv /opt/venv

# Include the CycloneDX SBOM generated in the builder stage.
COPY --from=builder /app/sbom.cyclonedx.json /home/app/sbom.cyclonedx.json
ENV VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

# Run as a non-root user with a writable home directory.
# Persistent runtime state lives under /data
# (bind-mounted or volume-backed in production).
ARG APP_UID=1001
ARG APP_GID=1001
RUN groupadd --gid ${APP_GID} app \
    && useradd --create-home --uid ${APP_UID} --gid ${APP_GID} app \
    && mkdir -p /home/app/config /data \
    && chown -R app:app /home/app/config /data
WORKDIR /home/app
USER app

# Config location resolved via ROBOTSIX_CONFIG_FILE (see config.py).
# Data dir is set via settings.data_dir in the config file (default .data).
ENV ROBOTSIX_CONFIG_FILE=/home/app/config/config.json

# Serve on all interfaces inside the container on 8080 (the stack convention;
# a host nginx terminates TLS + auth and proxies to 127.0.0.1:8080).
EXPOSE 8080

# Probe the in-container /health route using only the Python stdlib.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/health').status==200 else 1)"

ENTRYPOINT ["robotsix-cost-monitor"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8080"]
