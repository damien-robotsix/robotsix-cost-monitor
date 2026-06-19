# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Builder stage: resolve and install the locked dependency set + the project
# into a self-contained virtual environment the runtime stage simply COPYies.
# ---------------------------------------------------------------------------
FROM python:3.13-slim AS builder

# Bring in the uv static binary (pinned to a released version for reproducibility).
COPY --from=ghcr.io/astral-sh/uv:0.11.21 /uv /usr/local/bin/uv

# git is needed to install the `analyst` extra's git dependencies
# (robotsix-llmio / robotsix-agent-comm) during the uv pip install below.
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

# Export the EXACT revisions pinned in uv.lock (no fresh resolution), install
# them, then install the project itself with --no-deps so they are not
# re-resolved. The `analyst` extra (robotsix-llmio + robotsix-agent-comm) is
# included so the optional LLM cost-analyst + broker ticket filing work when
# configured; the dashboard runs fine without it.
RUN uv export --frozen --no-emit-project --no-hashes --extra analyst > requirements.txt \
    && uv pip install --python /opt/venv/bin/python -r requirements.txt \
    && uv pip install --python /opt/venv/bin/python --no-deps .

# ---------------------------------------------------------------------------
# Runtime stage: minimal image with only the prebuilt virtual environment,
# running as a non-root user.
# ---------------------------------------------------------------------------
FROM python:3.13-slim AS runtime

# Copy the prebuilt virtual environment (deps + project) from the builder stage.
COPY --from=builder /opt/venv /opt/venv
ENV VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

# Claude Agent SDK transport: the level-3 orchestrator runs on Claude Opus when
# analyst.orchestrator_provider == "claude-sdk", which drives the `claude` CLI
# subprocess for subscription auth. Install Node + the CLI globally; the
# subscription credentials come from a bind-mounted ~/.claude (see the deploy
# compose). Harmless when the analyst falls back to OpenRouter.
# hadolint ignore=DL3008
RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs npm \
    && npm install -g @anthropic-ai/claude-code@2.1.158 \
    && claude --version \
    && rm -rf /var/lib/apt/lists/*

# Run as a non-root user with a writable home/work directory. Pre-create an
# appuser-owned ~/.claude so the `claude` CLI can write state/cache; the host's
# credentials are bind-mounted into it at deploy time.
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /home/appuser/config /home/appuser/.data /home/appuser/.claude \
    && chown -R appuser:appuser /home/appuser/config /home/appuser/.data /home/appuser/.claude
WORKDIR /home/appuser
USER appuser

# Config + runtime-state locations resolved via env vars (see config.py).
# Both point at bind-mounted / persisted paths under the home directory.
ENV COST_MONITOR_CONFIG=/home/appuser/config/projects.yaml \
    COST_MONITOR_DATA=/home/appuser/.data

# Serve on all interfaces inside the container on 8080 (the stack convention;
# a host nginx terminates TLS + auth and proxies to 127.0.0.1:8080).
EXPOSE 8080

# Probe the in-container /health route using only the Python stdlib.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/health').status==200 else 1)"

ENTRYPOINT ["robotsix-cost-monitor"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8080"]
