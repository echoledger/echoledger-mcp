# Phase 2 — Containerize

*defimind-mcp v0.1 build. Master plan: `DEFIMIND_MCP_EXECUTION_PLAN.md`. Execute via Claude Code.*

**Objective:** Package the Phase 1 server in a container that runs identically locally and on the host, with the native-dependency build (`gmpy2`/`scipy`/`numpy`) working from a clean build.

**Preconditions:** Phase 1 server runs locally over HTTP and enumerates the 5 tools.

## Steps

1. **`Dockerfile`.**
   - Base: `python:3.11-slim` (or 3.12). 
   - **Build deps for `gmpy2` before pip** — this is the most likely failure point:
     ```dockerfile
     RUN apt-get update && apt-get install -y --no-install-recommends \
         build-essential libgmp-dev libmpfr-dev libmpc-dev \
       && rm -rf /var/lib/apt/lists/*
     ```
   - Install the package: `pip install .` (pulls `defipy[chain]` + `mcp` + the HTTP lib from `pyproject.toml`). `[chain]` is required — v0.1 does live reads; `[mcp]` alone is insufficient.
   - Copy `src/`; serve the streamable-HTTP entrypoint on `$PORT` (default 8080); `CMD` runs it.
   - **Multi-stage recommended** — build wheels in a builder stage (with the dev headers), copy site-packages into a slim runtime, to keep the image small despite scipy/numpy/gmpy2.
   - **Runtime egress:** live reads make outbound HTTPS calls to the caller's RPC. Ensure the host/network allows outbound HTTPS.

2. **`.dockerignore`.** `.venv`, `tests`, `docs`, `.git`, `__pycache__`, `*.egg-info`, build artifacts.

3. **`smithery.yaml` — required.** Smithery builds + hosts from it (Decision 6 = Smithery-hosted). Fields: `runtime: container`, `build.dockerfile`, `startCommand.type: http`, and an **empty/minimal `configSchema`** (BYO-RPC is a per-call tool argument, not server config — this keeps Smithery's deploy-time tool scan secret-free). The same Dockerfile also serves the Cloud Run fallback if the container doesn't fit Smithery's free tier.

4. **Local verification.** `docker build` from clean; run the container; point MCP Inspector at the container URL; confirm the 5 tools enumerate authless and a live V2 + V3 call succeeds from inside the container.

## Gate
- `docker build` succeeds from scratch (gmpy2 compiles, image builds).
- Container serves HTTP on `$PORT`; 5 tools enumerate **authless / zero-config**.
- A live V2 and V3 invocation succeeds from within the running container.

## Out of scope
Deploying to a host; domain/TLS; registry and catalog listings.

## Handoff to Phase 3
A built, runnable image + its run command (port, env), ready to deploy to the chosen host.
