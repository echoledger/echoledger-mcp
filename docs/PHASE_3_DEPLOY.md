# Phase 3 — Deploy & List the Endpoint (Smithery-hosted)

*defimind-mcp v0.1 build. Master plan: `DEFIMIND_MCP_EXECUTION_PLAN.md`. Execute via Claude Code.*

**Objective:** Get the endpoint live and listed by deploying on **Smithery-hosted** (free tier) — the lean v0.1 choice (Decision 6). Smithery builds the container and runs it; you operate no infra and pay ~$0 while early traffic is ~0. Own-domain self-host (`mcp.defimind.ai`) is the documented upgrade once there's traction.

**Preconditions:** working container (Phase 2), including a valid `smithery.yaml`.

> **Status — executed 2026-06-13 (reality differs from the plan below).** v0.1 deployed **directly to Railway at `https://mcp.defimind.ai`** (Cloudflare-fronted) — i.e. the "Upgrade path" own-domain host was taken at launch rather than Smithery-hosted. Rationale: the branded domain + full control were wanted up front, and Railway built the heavy Python container without the free-tier-fit concern Smithery raised.
> - Gate **met**: `/mcp` enumerates **5 tools** authless and live **V2 + V3** calls (incl. a V3 concentrated-range case showing ~26× IL amplification) work end-to-end through the hosted URL.
> - One deploy-time fix landed: `/mcp` 307-redirected to `http://…/mcp/` behind the TLS proxy; fixed by mounting the MCP handler at root + trusting proxy headers (commit `ed4a730`). `curl -i https://mcp.defimind.ai/mcp` now returns a direct 406 (correct — client must send `Accept: text/event-stream`), no redirect, https preserved.
> - **Smithery *listing* not done here** — it moves to Phase 4 as an aggregator submission. `smithery.yaml` + `Dockerfile` stay valid for a future Smithery listing or the Cloud Run fallback image.
> - **Hosted URL for Phase 4 `server.json` `remotes`:** `https://mcp.defimind.ai/mcp`.

## Decision 6 — settled: Smithery-hosted for v0.1
Rationale: the heavy Python container can't use the cheap Workers path ar-mcp uses, so self-hosting means paying for an always-on box (~$4–6/mo on Railway, billed even at idle) for an endpoint nobody's discovered yet. Smithery-hosted is ~$0 at idle and zero-ops, and every asset with brand/citation value (repo, `io.github.defimind-ai` namespace, Zenodo DOI) stays host-independent. The branded `mcp.defimind.ai` URL is deferred to the post-traction migration (see "Upgrade path").

## Steps

1. **Push to GitHub** (`defimind-ai/defimind-mcp`), then connect the repo at **smithery.ai/new**. Smithery builds the container from the `Dockerfile` + `smithery.yaml` and hosts it under the `ic3moore/defimind` namespace (alongside the live `ic3moore/anchorregistry`).

2. **Container-fit check — the one real risk.** Confirm Smithery's build succeeds and the running container stays within free-tier build/memory limits. The heavy scipy/numpy/gmpy2 image is the concern. **If it doesn't fit:** fall back to **Cloud Run** — deploy the *same image* (scale-to-zero, ~$0 at idle, cold start on first call), optionally front it with `mcp.defimind.ai`, and treat that as the host. Either way the endpoint costs ~$0 at idle; you are never forced onto a paid always-on box.

3. **Verify the hosted endpoint.**
   - Confirm Smithery's deploy-time **tool scan enumerates all 5 tools** authless (BYO-RPC is a per-call arg, so the scan needs no secret/config).
   - Smoke-test: MCP Inspector against the hosted URL; `claude mcp add --transport http defimind <hosted-url>`; a live **V2 + V3** call end-to-end (include a V3 concentrated-range case); confirm receipts appear in Smithery's logs.

4. **Capture the hosted URL.** Smithery assigns the endpoint URL — record it. It's what goes in the `server.json` `remotes` array (Phase 4) and the README.

## Gate
Endpoint live (Smithery-hosted, or Cloud Run fallback); deploy-time scan enumerates **5 tools** authless; a live V2 + V3 call works end-to-end through the hosted URL; the endpoint is listed on Smithery.

## Out of scope
Official registry + other catalogs (Phase 4); Zenodo DOI (Phase 5); the branded-domain migration (post-traction — see below).

## Upgrade path (documented now; execute when traction justifies it)
**Trigger:** Smithery usage starts incurring charges, a free-tier limit is hit, or traction makes the branded domain / full control worth it. **Migration is a redeploy, not a rewrite:**
1. Deploy the *same image* to Cloud Run (scale-to-zero) or Railway at `mcp.defimind.ai`.
2. Update the `server.json` `remotes` URL to `https://mcp.defimind.ai/mcp` and re-publish to the official registry (entries are editable).
3. Optionally keep both URLs live during transition (list both, deprecate the smithery one over time) — no hard cutover for existing clients.

## Handoff to Phase 4
The captured hosted endpoint URL — for the `server.json` `remotes` array.
