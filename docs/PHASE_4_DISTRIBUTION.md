# Phase 4 — Marketplace & Registry Distribution

*defimind-mcp v0.1 build. Master plan: `DEFIMIND_MCP_EXECUTION_PLAN.md`. Execute via Claude Code.*

**Objective:** Make the endpoint discoverable across the MCP landscape — the official registry first (canonical upstream), then aggregators.

**Preconditions:** `mcp.defimind.ai` live (Phase 3). The referenced endpoint must already exist — the registry validates it.

## Tier 1 — Official MCP Registry (canonical upstream)

1. **`server.json` at repo root** — mirror `ar-mcp/server.json` exactly:
   ```json
   {
     "$schema": "https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json",
     "name": "io.github.defimind-ai/defimind-mcp",
     "title": "DeFiMind",
     "description": "Live Uniswap V2/V3 LP diagnostics — position PnL, price-move scenarios, pool health, rug signals, slippage. Bring your own RPC.",
     "repository": { "url": "https://github.com/defimind-ai/defimind-mcp", "source": "github" },
     "version": "0.1.0",
     "websiteUrl": "https://defimind.ai",
     "remotes": [
       { "type": "streamable-http", "url": "<HOSTED_URL_FROM_PHASE_3>" }
     ]
   }
   ```
   - **`url`:** for v0.1 this is the **Smithery-hosted endpoint URL captured in Phase 3** (a smithery.ai address). After the post-traction migration to `mcp.defimind.ai`, edit this to `https://mcp.defimind.ai/mcp` and re-publish (entries are editable).
   - Add an `sse` remote only if `/sse` is actually served. **No `packages` block** (remote-listed; ownership verifies via the GitHub-org namespace + repo). Keep `description` ≤ ~100 chars, DeFiMind front-door voice that credits defipy openly.

2. **Publish via `mcp-publisher`.** Install the CLI; `mcp-publisher login github` (authenticate as the **defimind-ai** org so the `io.github.defimind-ai/*` namespace is authorized); `mcp-publisher publish`. The registry is in **preview / high-traffic** — retry on transient failures.

3. **Verify:** `curl "https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.defimind-ai/defimind-mcp"` returns the server metadata.

## Tier 2 — Aggregators / directories

4. **Listing copy.** Adapt `defipy/doc/v2_mvp_execution/MCP_CATALOG_SUBMISSIONS.md` to the **DeFiMind front-door** voice: 5 live tools, real V2/V3 pools, BYO-RPC, powered by open-source defipy. Honor the **claims-to-avoid** list ("first"/"only"/bare "unique"). Commit the canonical copy to `docs/` for reuse.

5. **Submit:**
   - **mcpmarket.com** — self-serve form.
   - **mcp.so** — submit flow; **check whether it auto-ingests from the official registry first** and skip the manual step if upstream already propagated.
   - Carryovers: **awesome-mcp-servers** (GitHub PR, match house style), **FlowHunt**, **SERP AI**.
   For each: skip manual submission where the official-registry publish already populated it.

## Gate
Resolvable on the official-registry search API; live on Smithery (Phase 3); submitted to mcpmarket + mcp.so; `server.json` committed at repo root; canonical listing copy committed to `docs/`.

## Out of scope
OCI-package listing, DNS-verified `ai.defimind/*` namespace, OIDC release-automation — all v0.2 (ar-mcp shipped remote-only and that was sufficient). Zenodo DOI (Phase 5).

## Handoff to Phase 5
A published, registry-resolvable server — ready to be tagged and archived as a citable artifact.
