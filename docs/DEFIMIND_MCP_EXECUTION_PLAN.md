# DeFiMind MCP — Execution Plan (High-Level)

**Status:** Planning document (2026-06-11)
**Repo:** `defimind-ai/defimind-mcp` → Smithery endpoint `ic3moore/defimind`
**Context:** Lift the existing stdio MockProvider MCP server out of `defipy` and re-home it as a Smithery-hosted, HTTP-transport endpoint under the DeFiMind brand, then distribute it across the MCP catalog landscape and archive it as a citable artifact.
**Scope:** High-level shape only. Phases are stated as goal + gate; detailed sub-phase breakdown is the next pass (done together).

> **Scope update (2026-06-12) — read first.** v0.1 is now **live-first**: 5 Uniswap V2/V3 tools reading *real pools* via a caller-supplied RPC (BYO-RPC as a per-call tool argument; the endpoint stays authless). This supersedes the MockProvider-first / 10-tool framing that still appears in some sections below — that framing was inherited from the April seed, before defipy 2.1 shipped V2/V3 LiveProvider. The per-phase specs `PHASE_0_SCAFFOLD.md` … `PHASE_5_CITATION.md` are **authoritative for execution**; where this document and a phase spec disagree on v0.1 scope, the phase spec wins.
>
> Concretely: the 5 tools are `AnalyzePosition`, `SimulatePriceMove`, `CheckPoolHealth`, `DetectRugSignals`, `CalculateSlippage`. Container install extra is `defipy[chain]` (or `[agentic]`), **not** `[mcp]` — live reads need web3/web3scout. MockProvider is retained for tests/examples only. The other 5 tools (Balancer/Stableswap) return when defipy 2.2 ships their LiveProviders.

---

## TL;DR

Almost all of the server already exists and is proven: `defipy/python/mcp/defipy_mcp_server.py` ships 10 curated tools across Uniswap V2/V3, Balancer, and Curve-style Stableswap, dispatching against `MockProvider` twins with stateless per-call construction and stderr receipts. It speaks **stdio**. Smithery hosted needs **streamable HTTP**.

That transport swap is the only substantive engineering task in this build. Everything downstream — container, deploy, catalogs, DOI — is packaging and distribution. Estimate holds at ~3–5 focused days, weighted toward Phase 1 and Phase 4, not the deploy plumbing.

**v0.1 = MockProvider, zero-config, clean tool scan.** **v0.2 = V2/V3 LiveProvider** — which is now *unblocked*: defipy 2.1.0 (2026-05-07) shipped V2/V3 LiveProvider. The seed-era "v0.2 pending defipy v2.1" note is resolved. Live reads are deliberately held out of v0.1 anyway (see Decision 3), not because the substrate is missing.

---

## What already exists (the substrate)

**The server** — `defipy/python/mcp/defipy_mcp_server.py`:
- Low-level MCP `Server` API (`mcp.server.Server`), **stdio transport** (`mcp.server.stdio.stdio_server`).
- 10 tools from `defipy.tools` (`TOOL_REGISTRY`, `get_schemas("mcp")`), wrapped at exposure time with a required `pool_id` enum and string-name token args.
- 4 `MockProvider` recipes: `eth_dai_v2`, `eth_dai_v3`, `eth_dai_balancer_50_50`, `usdc_dai_stableswap_A10`. Per-tool recipe compatibility enforced.
- Stateless: fresh `MockProvider` snapshot + `StateTwinBuilder` twin built per call. Matches defipy's primitive contract.
- One JSON receipt per invocation to stderr. This is the v0.1 observability story.

This is ~95% of the runtime logic and it's battle-tested (23 MCP dispatch tests upstream). The port preserves it; it does not rewrite it.

**The library** — `defipy` 2.1.0 on PyPI, Apache-2.0:
- `[mcp]` extra → `mcp >= 1.27.0` (MockProvider path, no chain deps).
- `[agentic]` extra → `web3scout` + `web3` + `mcp` (the LiveProvider path for v0.2).
- v2.1 shipped V2/V3 LiveProvider (Multicall3-batched, block-pinned). Balancer/Stableswap LiveProvider deferred upstream to defipy v2.2.
- Depends on `uniswappy`, `balancerpy`, `stableswappy` (PyPI siblings). Hard transitive dep on `gmpy2` (needs system GMP/MPFR/MPC headers — a container concern, see Risks).

**Reusable copy** — `defipy/doc/v2_mvp_execution/MCP_CATALOG_SUBMISSIONS.md`: catalog target list (priority-ordered), canonical descriptions, positioning language, and an explicit claims-to-avoid list. Adapt, don't rewrite from scratch (see Decision 4).

**The gap:** any hosted/remote MCP serves over HTTP; the existing server speaks stdio. Phase 1 closes this regardless of where it ends up hosted.

---

## Precedent — ar-mcp (read 2026-06-12)

The AnchorRegistry MCP at `/Users/ian_moore/repos/ar-mcp` is a working precedent for the distribution half of this build — already deployed and registry-listed. What transfers and what doesn't:

**Transfers (distribution machinery):**
- **`server.json`** — exact template for the official-registry artifact: `io.github.<Org>/<repo>` namespace, `remotes` (streamable-http + sse), no `packages`, short description, `websiteUrl`. See Decision 5.
- **Self-host + remote-list pattern** — endpoint owned at a branded domain (`mcp.anchorregistry.ai`); Smithery + registry list it as a remote, not a build. See Decision 6.
- **README structure** — title, badges, prominent endpoint URL, per-client install (Claude Desktop / Claude Code `claude mcp add --transport http` / Cursor), tools-with-example-queries, "how it works", roadmap, develop, cross-links. Direct template for the defimind-mcp README.
- **Authless v0.1** — the endpoint is explicitly authless; tools enumerate with no credentials. Maps cleanly onto the MockProvider zero-config posture.
- **Dormant-tools pattern** — deferred tools live behind a one-line flip (ar-mcp keeps them in `src/future-tools.ts`). Good model for shipping the v0.2 LiveProvider tools dormant.
- **MCP Inspector** (`npx @modelcontextprotocol/inspector`) — the local verification tool. Use it as the Phase 1 gate.

**Does NOT transfer (runtime):**
- ar-mcp is **TypeScript on Cloudflare Workers** (`agents`/`McpAgent` + Durable Objects, `wrangler.jsonc`, `zod` schemas) and a **thin API-forwarding proxy** — stateless, tiny, ideal for Workers. defimind-mcp wraps a **heavy Python compute library**, which Workers can't run. The server code follows defipy's Python low-level `Server`, not ar-mcp's TS. `wrangler.jsonc` is the conceptual analog of the deploy config, but the actual host differs (Decision 6).

---

## Decisions to resolve when sub-phasing

Flagged here, not resolved. Each gets settled at the top of its phase.

**1. Vendor the server logic vs. import from defipy.**
Pure `import` is insufficient: the schema-wrapping / dispatch / token-resolution logic lives *in the server file* in the defipy repo, not in the installed `defipy` package. So v0.1 lifts that file into `defimind-mcp` and swaps its transport, while still depending on `defipy[mcp]` for the primitives, tools, and twin.
*Recommendation:* lift-and-adapt for v0.1. Note as future cleanup: that wrapping logic could migrate upstream into `defipy` (e.g. a `defipy.tools.mcp` helper) so both the local stdio server and the hosted HTTP server share one source of truth instead of drifting.

**2. FastMCP vs. low-level `Server` for the HTTP mount.**
Smithery's Python cookbook uses FastMCP + `streamable_http_app()`. The existing server is built on the low-level `Server` with hand-registered `list_tools` / `call_tool` handlers and the `pool_id` wrapping around them.
*Recommendation:* minimal change first — keep the low-level `Server` and mount it via the streamable-HTTP session manager, preserving the existing handlers verbatim. Only fall back to a FastMCP rewrite if the low-level mount proves fiddly. Decide empirically in Phase 1.

**3. v0.1 surface = MockProvider only.**
Even though V2/V3 LiveProvider now exists, hosted live reads need a BYO-RPC config supplied through `smithery.yaml`, which (a) complicates the deploy-time tool scan, (b) adds an RPC failure surface to every call, and (c) raises a key-handling question on hosted infra. v0.1 stays zero-config so the scan resolves cleanly and the listing populates without secrets.
*Recommendation:* hold the line. LiveProvider is v0.2, on its own merits, not a v0.1 stretch.

**4. Listing voice — DeFiMind front-door vs. defipy substrate.**
The reusable catalog copy is defipy-substrate-framed ("substrate, not agent"). This endpoint ships under the **DeFiMind** brand — the agentic-analytics front door. The listing should carry the application/front-door voice while *openly crediting defipy as the open methodology underneath* — which reinforces the "the math is open, the reports are paid" thesis rather than diluting it. Brand hygiene still holds: this is a DeFiMind surface that cites defipy; it is not an AnchorRegistry or consulting-outreach channel.
*Recommendation:* settle the exact copy at the top of Phase 4, starting from the defipy canonical copy and re-voicing the framing lines.

**5. Official-registry representation + namespace — *settled by ar-mcp precedent*.**
`ar-mcp/server.json` is the proven artifact: namespace `io.github.AnchorRegistry/ar-mcp`, a `remotes` array advertising both `streamable-http` (`/mcp`) and `sse` (`/sse`), **no `packages` block**, a one-line description, and `websiteUrl`. The open questions resolve by mirroring it: defimind-mcp uses `io.github.defimind-ai/defimind-mcp`, a `remotes` entry (streamable-http, optionally sse) pointing at the live endpoint, and no package/OCI block. The DNS-verified `ai.defimind/...` namespace and a GHCR OCI listing were *not* needed for ar-mcp — they stay optional v0.2 polish. Ownership verifies via the GitHub-org namespace + repo, so there's no PyPI/npm README marker to manage.

**6. Hosting model — *settled: Smithery-hosted for v0.1*.**
The choice was between self-host + remote-list (the ar-mcp pattern: branded `mcp.defimind.ai` on Railway/Cloud Run) and Smithery-hosted (Smithery builds + runs the container, smithery.ai URL). **Decided: Smithery-hosted**, on lean grounds. The heavy Python container can't use the cheap Cloudflare-Workers path ar-mcp relies on, so self-hosting means paying for an always-on box (~$4–6/mo on Railway, billed even at idle since Railway has no scale-to-zero) or running Cloud Run — and with early traffic ≈ 0, paying to keep an undiscovered endpoint warm isn't worth it. Smithery-hosted is ~$0 at idle and zero-ops.
- **Given up:** the branded `mcp.defimind.ai` URL (you get a smithery.ai address) and some dependence on Smithery's hosting/pricing (free tier; usage-based only at real traffic).
- **Not given up:** distribution (still listed on Smithery + the official registry + aggregators) and every brand/citation asset (repo, `io.github.defimind-ai` namespace, Zenodo DOI) — all host-independent.
- **Fallback:** Cloud Run (scale-to-zero, also ~$0 idle) if the container doesn't fit Smithery's free-tier build/memory limits.
- **Upgrade path** (documented in Phase 3): when traction justifies it, redeploy the *same image* to `mcp.defimind.ai` and repoint the `server.json` remote — a redeploy, not a rewrite.
Consequence: `smithery.yaml` is now **required** (Phase 2).

---

## Phases (high-level)

Each phase: goal + gate. Sub-steps are deliberately omitted — that's the next session.

### Phase 0 — Scaffold & license hygiene
**Goal:** Turn the near-empty repo into a clean skeleton mirroring the `ar-mcp` structural template (adapted Python/container). LICENSE is already Apache-2.0 (correct — matches the lifted defipy code; see the prior license decision). Add `NOTICE` carried from defipy, `CITATION.cff` (arXiv 2605.11522 State Twins + Zenodo DOI placeholder), `README.md`, `.gitignore`, and the directory layout (`src/`, `docs/`, container + Smithery config slots).
**Gate:** Repo has a complete skeleton; Apache-2.0 LICENSE + NOTICE + CITATION.cff present; README states what the endpoint is and which defipy version it pins.

### Phase 1 — Server lift + transport port *(the core engineering)*
**Goal:** Bring the server logic into `defimind-mcp` and replace stdio with streamable HTTP — CORS middleware for browser clients, bind to the `PORT` env Smithery injects. Preserve the tool set, `pool_id` wrapping, token resolution, stateless dispatch, and stderr receipts exactly. Resolve Decisions 1 and 2 here.
**Gate:** Server runs locally over HTTP; a local MCP client enumerates all 10 tools and successfully invokes at least one per protocol family against MockProvider; receipts emit correctly.

### Phase 2 — Containerize
**Goal:** `Dockerfile` (Python base; `apt` the GMP/MPFR/MPC headers for `gmpy2`; `pip install .` pulling `defipy[chain]` + the `mcp` SDK + HTTP lib; copy server; serve HTTP on `$PORT`) plus a **required** `smithery.yaml` (`runtime: container`, `build.dockerfile`, `startCommand.type: http`, empty/minimal `configSchema` — BYO-RPC is a per-call arg, so the deploy-time scan stays secret-free). Smithery builds from these (Decision 6); the same Dockerfile also serves the Cloud Run fallback.
**Gate:** `docker build` succeeds from clean; the container serves the HTTP endpoint locally; tool enumeration works inside the container with **zero config / no secrets** (this is the property the Smithery scan depends on).

### Phase 3 — Deploy & list the endpoint (Smithery-hosted)
**Goal:** Deploy on Smithery-hosted (Decision 6): push to GitHub, connect at smithery.ai/new, Smithery builds + hosts the container under `ic3moore/defimind`. Verify the deploy-time scan enumerates the **5 tools** authless and a live V2 + V3 call works end-to-end. **Fallback:** Cloud Run (scale-to-zero) if the container doesn't fit the free tier. Capture the hosted URL for the `server.json` remote. Getting onto Smithery here is the first of the marketplaces; the rest are Phase 4.
**Gate:** Endpoint live (Smithery-hosted or Cloud Run fallback); 5 tools enumerate authless; live V2 + V3 call works end-to-end; listed on Smithery.

### Phase 4 — Marketplace & registry distribution
**Goal:** Make the endpoint discoverable across the MCP landscape, in two tiers.

- **Upstream / canonical — the official MCP Registry (`registry.modelcontextprotocol.io`).** Highest-leverage single act: a `server.json` (current schema `2025-12-11`) published via the `mcp-publisher` CLI (`init` → `login github` → `publish`), with the namespace-ownership marker in place and the referenced endpoint/package existence validated by the registry. Several aggregators ingest from here, so an upstream publish can populate downstream catalogs automatically. Mirror `ar-mcp/server.json` exactly (it's the proven artifact): `io.github.defimind-ai/defimind-mcp`, a `remotes` array (streamable-http, optionally sse) pointing at the live endpoint, short description, `websiteUrl`, no `packages` (Decision 5). GitHub OIDC enables a secret-free publish from a release workflow — optional for v0.1, natural to wire alongside the Phase 5 release trigger.
- **Aggregators / directories — direct submissions.** Smithery is already done (Phase 3). Remaining named targets: **mcpmarket.com**, **mcp.so**, plus the carryover catalogs from `MCP_CATALOG_SUBMISSIONS.md` (awesome-mcp-servers, FlowHunt, SERP AI). For each, check whether it auto-pulls from the official registry before hand-submitting — skip the manual step where upstream already propagated.

Re-voice the defipy catalog copy for the DeFiMind front-door framing (Decision 4) and honor the claims-to-avoid list across every listing.

**Target marketplaces (the four named, plus carryovers):**

| Target | Mechanism | Notes |
|---|---|---|
| Smithery | Deploy (Phase 3) | Listing *is* the deploy; `ic3moore/defimind` |
| Official MCP Registry | `mcp-publisher` + `server.json` | Canonical upstream; others may pull from it |
| mcpmarket.com | Self-serve form | Largest aggregator |
| mcp.so | Submit flow / registry ingest | Confirm auto-pull before manual submit |
| awesome-mcp-servers | GitHub PR | Alphabetical; match house style |
| FlowHunt / SERP AI | Form / auto-ingest | Low-stakes, compounding |

**Gate:** Live on the official registry (resolvable via its search API) and on Smithery; submitted to mcpmarket and mcp.so; the `server.json` committed to repo root and the canonical listing copy committed to `defimind-mcp/docs/` for reuse.

### Phase 5 — Citable artifact (Zenodo DOI)
**Goal:** Cut a tagged release, mint a Zenodo DOI with the State Twins paper (arXiv 2605.11522) as the linked citation, and finalize `CITATION.cff` with the DOI so GitHub's "Cite this repository" resolves. This is the lever that turns the endpoint from a listing into a Scholar-visible artifact pointing back at the paper.
**Gate:** DOI minted and live; `CITATION.cff` carries both arXiv and Zenodo; "Cite this repository" renders on GitHub.

---

## v0.2 horizon (explicitly out of v0.1 scope)

- **V2/V3 LiveProvider via BYO-RPC.** Substrate is ready (defipy 2.1). Adds an RPC config to `smithery.yaml`, live-read failure handling, and a re-test of the tool scan with optional config. This is the next endpoint cycle, not a v0.1 task.
- **Balancer/Stableswap live reads.** Blocked upstream on defipy v2.2.
- **Structured receipt sink.** stderr JSON is the v0.1 story; structured ingestion tracks defipy's own observability roadmap.
- **OCI-package listing + DNS-verified namespace + OIDC auto-publish.** All optional. ar-mcp shipped remote-only under its GitHub namespace and that was sufficient. v0.2 *can* add a GHCR OCI-package listing for self-hosters, switch to a DNS-verified `ai.defimind/...` namespace, and wire a release-triggered GitHub Action that publishes `server.json` via OIDC with no stored secrets — none of it required for v0.1.
- **Migrate to own-domain hosting.** When traction justifies it (Smithery usage charges, free-tier limit, or the branded domain starts to matter), redeploy the *same image* to `mcp.defimind.ai` on Cloud Run (scale-to-zero) or Railway, and repoint the `server.json` remote — a redeploy, not a rewrite. See Phase 3's "upgrade path".

---

## v0.1 scope boundaries

**In:** 10 curated tools; 4 MockProvider recipes; HTTP transport; container + Smithery config; zero-config tool scan; marketplace + registry listings (Smithery, official MCP registry, mcpmarket, mcp.so, + carryover catalogs); Zenodo DOI.

**Out:** any live chain reads; any BYO-RPC config; Balancer/Stableswap live; execution/signing of any kind (the endpoint stays read-only analytics, inheriting defipy's non-executing contract); the consulting/outreach surface (separate brand motion, not this repo).

---

## Risk list (high-level)

1. **`gmpy2` in the container.** Needs GMP/MPFR/MPC headers at build time. Dockerfile must `apt-get install libgmp-dev libmpfr-dev libmpc-dev` (and `build-essential`) before `pip install`. This is the most likely build-time failure and is a known defipy install gotcha.
2. **Tool scan must run secret-free.** Smithery enumerates tools at deploy. The whole v0.1-MockProvider posture exists partly to keep this clean — don't let any config requirement creep into v0.1 that would gate enumeration on a secret.
3. **Transport-port subtleties.** The low-level `Server` → HTTP mount path is less documented than the FastMCP path. Decision 2 hedges this; budget a little slack in Phase 1 for the fallback.
4. **Logic drift between two servers.** Once lifted, `defimind-mcp` and the upstream defipy stdio server can diverge. Mitigation is the Decision 1 future note (migrate shared wrapping upstream). Until then, treat the defipy file as the reference and document the lift point.
5. **defipy version pin.** Pin an explicit `defipy==2.1.x` in the container so a future upstream change doesn't silently alter the hosted tool surface. Bump deliberately.
6. **Brand voice slip.** Keep the listing DeFiMind-front-door + defipy-credit, without pulling AnchorRegistry or consulting framing into a public MCP listing.
7. **Official-registry preview-mode friction.** The registry is in preview and documented as high-traffic — publishes can need several retries, and it validates that the referenced endpoint/package actually exists, so the Smithery endpoint (or GHCR image) must be live *before* publishing. Sequence the registry step after Phase 3.
8. **Ownership-verification marker.** The registry requires a namespace marker matching the chosen auth: GitHub auth needs `io.github.<owner>/...` and (for any listed package) a type-specific marker — an `mcp-name:` line in the README for PyPI, `mcpName` for npm, a label for OCI. A remote-only entry verifies via repo/namespace rather than a package marker. Get this right or the publish is rejected with a namespace/validation error.

---

## References (read before sub-phasing)

- `defipy/python/mcp/defipy_mcp_server.py` — the server being lifted. Authoritative for tool surface, wrapping, dispatch.
- `defipy/python/mcp/README.md` — current stdio setup, tool table, recipe table, limitations.
- `defipy/setup.py` — extras (`[mcp]`, `[chain]`, `[agentic]`), version, sibling pins.
- `defipy/CHANGELOG.md` — v2.0 → v2.1 delta; confirms LiveProvider availability and what's still deferred.
- `defipy/doc/v2_mvp_execution/MCP_CATALOG_SUBMISSIONS.md` — Phase 4 source copy + claims-to-avoid.
- `defipy/doc/v2_mvp_execution/DEFIPY_V2_AGENTIC_PLAN.md` — substrate/application boundary; the framing this endpoint inherits.
- `ar-mcp` (TypeScript/Cloudflare Workers) — structural template for repo layout and Smithery config patterns; note the runtime differs (container vs. Workers).
- `https://modelcontextprotocol.io/registry/quickstart` — official registry publish flow (`mcp-publisher`, `server.json`, ownership markers).
- `https://github.com/modelcontextprotocol/registry` — registry source: `server.json` schema, package-type / remote-server rules, namespace validation.
- `ar-mcp/server.json` — proven official-registry artifact (remote-listed, `io.github.*` namespace). Direct template for Phase 4.
- `ar-mcp/README.md` — listing-copy + per-client install structure. Template for the defimind-mcp README.
- `ar-mcp/wrangler.jsonc` + `ar-mcp/package.json` — the (non-transferable) Workers runtime; read only to understand what the self-host branch replaces with a Python host.

---

*High-level plan prepared 2026-06-11; ar-mcp precedent folded in 2026-06-12. Next pass: break Phases 0–5 into concrete sub-phases with per-step gates, starting from Phase 0 — but settle Decision 6 (hosting model) first, since it determines the Phase 2–3 deploy target.*
