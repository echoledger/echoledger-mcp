# syntax=docker/dockerfile:1
# ─────────────────────────────────────────────────────────────────────────────
# DeFiMind MCP — container image (Phase 2)
#
# Multi-stage: a builder stage with the native toolchain + GMP/MPFR/MPC
# headers (gmpy2 is a hard transitive dep of defipy and the most likely
# build-time failure), and a slim runtime stage that carries only the
# installed virtualenv. Serves the streamable-HTTP MCP endpoint on $PORT.
# ─────────────────────────────────────────────────────────────────────────────

# ── Builder ──────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

# Build toolchain + GMP/MPFR/MPC dev headers for gmpy2. Most deps ship
# manylinux wheels (numpy/scipy/gmpy2), but keep these so an sdist
# fallback still compiles from clean.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libgmp-dev \
        libmpfr-dev \
        libmpc-dev \
    && rm -rf /var/lib/apt/lists/*

# Isolated venv we can copy wholesale into the runtime stage.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app
# README.md is referenced by pyproject (readme=); copy metadata + source,
# then install the package, which pulls defipy[chain] + mcp + the HTTP lib.
COPY pyproject.toml README.md LICENSE NOTICE ./
COPY src/ ./src/
RUN pip install --upgrade pip && pip install .

# ── Runtime ──────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# Shared runtime libraries for gmpy2 (if it linked against the system
# GMP/MPFR/MPC rather than a bundled wheel copy).
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgmp10 \
        libmpfr6 \
        libmpc3 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH" \
    PORT=8080 \
    HOST=0.0.0.0 \
    PYTHONUNBUFFERED=1

# Non-root.
RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8080

# Liveness: the /health route enumerates the 5 tools with zero config.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8080')+'/health').read()" || exit 1

# Serve streamable HTTP on $PORT (MCP endpoint at /mcp).
CMD ["python", "-m", "defimind_mcp.server"]
