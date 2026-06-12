# Phase 0 — Repo Scaffold & License Hygiene

*defimind-mcp v0.1 build. Master plan: `DEFIMIND_MCP_EXECUTION_PLAN.md`. Execute via Claude Code.*

**Objective:** Turn the near-empty repo into a clean, conventional skeleton ready for the Phase 1 server build, with license / attribution / citation hygiene correct from the first commit.

**Preconditions:** repo at `/Users/ian_moore/repos/defimind-mcp` already has `LICENSE` (Apache-2.0) and `docs/` (holding these specs).

## Settled decisions (from master plan)
- **License:** Apache-2.0 — already present; matches the defipy code being lifted.
- **Registry namespace:** `io.github.defimind-ai/defimind-mcp`.
- **Hosting:** self-host + remote-list (ar-mcp pattern); assumed **Railway** (confirm in Phase 3).
- **v0.1 scope:** 5 live Uniswap V2/V3 tools, BYO-RPC supplied per tool call (endpoint stays authless).

## Steps

1. **Repo layout.** Create `src/` (Python server package; exact module names finalized in Phase 1), `tests/`, and the root files below. `docs/` already exists.

2. **`NOTICE`.** Carry forward defipy's NOTICE (Apache-2.0, attribution-retention request) and add DeFiMind. Content:
   ```
   DeFiMind MCP
   Copyright 2026 Ian Moore / DeFiMind Inc.

   This product includes and adapts software from DeFiPy
   (https://defipy.org), Copyright 2023–2026 Ian Moore, licensed under
   the Apache License, Version 2.0.

   Licensed under the Apache License, Version 2.0. You may obtain a copy
   at http://www.apache.org/licenses/LICENSE-2.0.
   ```

3. **`CITATION.cff`** (cff-version 1.2.0). Software entry for "DeFiMind MCP" (author: Ian Moore; repository-code; license Apache-2.0), with the State Twins paper under `references` and a Zenodo DOI placeholder filled in Phase 5:
   ```yaml
   cff-version: 1.2.0
   title: "DeFiMind MCP"
   message: "If you use this software, please cite it and the State Twins paper below."
   type: software
   authors:
     - family-names: Moore
       given-names: Ian
   repository-code: "https://github.com/defimind-ai/defimind-mcp"
   url: "https://defimind.ai"
   license: Apache-2.0
   version: 0.1.0
   # doi: 10.5281/zenodo.XXXXXXX   # filled in Phase 5
   references:
     - type: article
       title: "State Twins"        # confirm exact title from arXiv 2605.11522
       authors:
         - family-names: Moore
           given-names: Ian
       identifiers:
         - type: other
           value: "arXiv:2605.11522"
   ```

4. **`README.md`.** Structure on `ar-mcp/README.md`: title + one-liner; badges (Apache-2.0, MCP, Python); endpoint URL placeholder (the **Smithery-hosted URL** is captured in Phase 3 for v0.1; `mcp.defimind.ai` is the post-traction migration — leave TBD until Phase 3); per-client install (Claude Desktop / `claude mcp add --transport http defimind <url>` / Cursor); **Tools** section reserving the 5 (with example queries — lead with V3, since that's where the interest is); **How it works** (live V2/V3 reads via caller-supplied RPC; authless; nothing logged/stored; powered by open-source defipy — "the math is open, the reports are paid"); **Roadmap** (v0.2: Balancer/Stableswap live when defipy 2.2 ships; own-domain migration; OCI/DNS/OIDC polish); **Develop**; **License**; **See also** (defipy, defimind.ai, the paper). Tool details + live URL marked TBD until Phase 1/3.

5. **`.gitignore`.** Python (`.venv`, `__pycache__/`, `*.egg-info/`, `dist/`, `build/`), secrets (`.env`, `*.rpc`), OS cruft (`.DS_Store`). Add `.dockerignore` in Phase 2.

6. **`pyproject.toml`.** Package metadata: name `defimind-mcp`, license Apache-2.0, Python ≥3.11. Dependencies: `defipy[chain]>=2.1,<2.2` (chain reads), `mcp>=1.27.0`, and the HTTP-server lib chosen in Phase 1 (e.g. `uvicorn`+`starlette`, or whatever the streamable-HTTP mount needs). **Pin defipy to 2.1.x** so the hosted tool surface can't silently shift.

## Gate
Skeleton present; `NOTICE` + `CITATION.cff` + `README.md` + `.gitignore` + `pyproject.toml` committed; README renders; `CITATION.cff` parses as valid CFF. **No server code yet.**

## Out of scope
Server logic, Dockerfile, smithery.yaml, any deploy. Don't write tools here.

## Handoff to Phase 1
`src/` package + `pyproject.toml` exist; defipy pinned to `[chain]` 2.1.x; README tool list reserved for the 5.
