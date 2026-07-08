# echoledger-mcp v0.2 — Expand the live tool surface 5 → 10

*Hand-off spec for Claude Code. Adds the 5 Balancer/Stableswap tools to the live
`echoledger-mcp` endpoint, taking it from 5 live tools to the full 10-tool curated
DeFiPy registry. Unblocked by **DeFiPy v2.2** (2026-06-18), which shipped the
Balancer & Stableswap LiveProviders the existing server was explicitly waiting on.*

*Captured: June 19, 2026.*

---

## Why now (the unlock)

The live server (`src/echoledger_mcp/server.py`) serves **5 tools** — exactly the
V2/V3-LiveProvider-compatible subset of DeFiPy's 10-tool registry. Its own comment
states the reason and the trigger:

> "The 5 tools that compose with the V2/V3 LiveProvider. Balancer and Stableswap
> tools return in **v0.2 once DeFiPy 2.2 ships their providers**."

And the README roadmap:

> "**v0.2 — Balancer & Stableswap live reads**, once DeFiPy 2.2 ships their
> LiveProviders."

**That precondition is now met.** DeFiPy v2.2 completes the LiveProvider read path
for Balancer V2 weighted pools (`provider.snapshot("balancer:0xADDR")`) and Curve
plain Stableswap pools (`provider.snapshot("stableswap:0xADDR")`) — all four
protocol prefixes are now implemented upstream. The 5 deferred tools were never
missing; they were waiting for live Balancer/Stableswap reads, which now exist.

## What this is (and is NOT)

**Is:** expose the 5 registry tools that need Balancer/Stableswap pools, by
extending the existing dispatch pattern to two new `pool_type` values. The work is
structurally identical to what the server already does for V2/V3.

The 5 tools added:

| Tool | Protocol | New `pool_type` |
|---|---|---|
| `AnalyzeBalancerPosition` | Balancer 2-asset weighted | `balancer` |
| `SimulateBalancerPriceMove` | Balancer 2-asset weighted | `balancer` |
| `AnalyzeStableswapPosition` | Curve 2-asset stableswap | `stableswap` |
| `SimulateStableswapPriceMove` | Curve 2-asset stableswap | `stableswap` |
| `AssessDepegRisk` | Curve 2-asset stableswap | `stableswap` |

**Is NOT:**
- **Not** an expansion *beyond* the 10-tool registry. DeFiPy has 21 primitives; 11
  are deliberately not in `TOOL_REGISTRY` (curation principles: leaf-over-composition,
  direct-question-to-answer, multi-step-reasoning deferred). Going past 10 is a
  separate upstream `defipy.tools` decision — explicitly **out of scope** here.
- **Not** an N-asset expansion. Per DeFiPy v2.2's own release notes, the three
  position/risk primitives (`AnalyzeStableswapPosition`, `AnalyzeBalancerPosition`,
  `AssessDepegRisk`) are **2-asset only** until DeFiPy v2.3. The LiveProvider can
  read N-coin Stableswap snapshots, but these primitives still only handle 2 assets.
  The tool surface here is **2-asset Balancer weighted + 2-asset Curve plain**.

## The two protocol scope limits to carry into descriptions (be honest)

1. **2-asset only.** Balancer: 2-asset weighted pools (3-asset raises
   `NotImplementedError` upstream). Stableswap: 2-asset plain pools (the LiveProvider
   reads N∈{2,3}, but the position/risk primitives are 2-asset).
2. **Plain Stableswap only.** Curve plain pools (`stored_rate = 1`, `A()` not
   `A_precise()`). Rate-bearing pools (metapools, LSD) are upstream v2.3.

If a caller points a `stableswap` tool at a 3-coin or rate-bearing pool, it should
fail clearly (the upstream snapshot/primitive will raise; the dispatch layer must
surface it as a clean error, not a stack trace — same `_scrub_secrets` discipline as
today).

---

## Phase list

| Phase | Name | Gate |
|---|---|---|
| **0** | Pin bump & live read confirmation | `defipy[chain]>=2.2` installs; a real Balancer pool and a real Stableswap pool each return a snapshot via the LiveProvider from a throwaway script. |
| **1** | Wire the 5 tools into dispatch | `TOOL_NAMES` = 10; `POOL_TYPES` includes `balancer`/`stableswap`; schema wrap + token resolution + V3-tick-default guard all handle the new pool types; offline tests green. |
| **2** | Tests, docs, redeploy | Live-gate tests pass against real Balancer + Stableswap pools; README/`/health`/`server.json`/`smithery.yaml` updated; version bumped; deployed to Railway; `curl /health` shows 10 tools. |
| **3** | Re-publish to the registries | The updated `server.json` is re-published to `registry.modelcontextprotocol.io` (`mcp-publisher publish`); Smithery re-ingests the 10-tool surface; both listings resolve with the new tool count. |

Do the phases in order. Each gate must hold before advancing.

> **Why Phase 3 exists (don't skip it).** Editing `server.json` and `smithery.yaml`
> in the repo does **not** update the live registry entries — those are separate
> published artifacts. The official MCP registry holds a *published snapshot* of
> `server.json`; Smithery holds its own ingested copy. Without Phase 3, the endpoint
> serves 10 tools but every public listing still advertises 5. Phase 2 ships the
> running server; Phase 3 makes the catalogs tell the truth.

---

## Phase 0 — Pin bump & live read confirmation

The current pin is **deliberately capped below 2.2** to freeze the tool surface:
```toml
"defipy[chain]>=2.1,<2.2",   # "Pinned to 2.1.x so the hosted tool surface can't silently shift."
```
This expansion is the deliberate surface change, so the cap lifts.

**Tasks:**
1. In `pyproject.toml`, change the pin to `defipy[chain]>=2.2,<2.3` (keep the upper
   cap — same "no silent shift" discipline, now allowing the 2.2 line).
2. `pip install -e ".[dev]"` in a fresh venv; confirm `defipy` 2.2.x resolves and
   `from defipy.twin import LiveProvider, StateTwinBuilder` still imports.
3. Throwaway confirmation script (NOT committed), using a real RPC:
   - `LiveProvider(rpc).snapshot("balancer:0x<real 2-asset weighted pool>")` → builds.
   - `LiveProvider(rpc).snapshot("stableswap:0x<real 2-asset plain Curve pool>")` → builds.
   - Build a twin from each via `StateTwinBuilder().build(snap)` and confirm it has
     the vault/token interface the primitives + `_resolve_token` expect (the vault
     `get_token`/`get_names` path — see `_resolve_token` in server.py).
   - Record real pool addresses that work — they become the live-test fixtures in
     Phase 2. (Suggest well-known pools: a Balancer 2-asset weighted, e.g. a
     WETH/<token> 80/20 or 50/50; a Curve 2-asset plain, e.g. a stable/stable plain
     pool. Confirm each is *plain*/2-asset, not a metapool or 3-pool.)

**Gate:** `defipy 2.2` installed; a real Balancer pool and a real Stableswap pool
each snapshot + build a twin cleanly; working pool addresses recorded for Phase 2.

**Out of scope:** any server.py code changes (Phase 1).

---

## Phase 1 — Wire the 5 tools into dispatch

All changes are in `src/echoledger_mcp/server.py`, extending the existing patterns.
**The V2/V3 path must remain byte-for-byte behaviorally unchanged** — this is purely
additive.

**Tasks:**

1. **`TOOL_NAMES`** — extend the tuple from 5 to all 10:
   ```python
   TOOL_NAMES = (
       "AnalyzePosition", "SimulatePriceMove", "CheckPoolHealth",
       "DetectRugSignals", "CalculateSlippage",
       "AnalyzeBalancerPosition", "SimulateBalancerPriceMove",
       "AnalyzeStableswapPosition", "SimulateStableswapPriceMove",
       "AssessDepegRisk",
   )
   ```

2. **`POOL_TYPES`** — add the two new prefixes:
   ```python
   POOL_TYPES = ("uniswap_v2", "uniswap_v3", "balancer", "stableswap")
   ```
   These must match the DeFiPy LiveProvider `pool_id` protocol prefixes exactly
   (`"balancer:0x..."`, `"stableswap:0x..."`). The dispatch already builds the
   snapshot id as `"{pool_type}:{pool_address}"`, so no change to that line — but
   confirm the prefix strings match what DeFiPy 2.2 expects.

3. **`pool_type` enum description** — update the `pool_type` schema prop text in
   `_wrap_schemas_with_pool_identity()` to mention all four, and note scope: e.g.
   "'uniswap_v2' | 'uniswap_v3' | 'balancer' (2-asset weighted) | 'stableswap'
   (2-asset plain Curve)."

4. **Per-tool pool-type compatibility (the one genuinely new dispatch concern).**
   Today every live tool is V2/V3, so there's no per-tool pool-type gating beyond the
   global `POOL_TYPES` check. Now tools are protocol-specific: `AnalyzeBalancerPosition`
   only makes sense with `pool_type=balancer`; `AssessDepegRisk` only with
   `stableswap`; the 5 Uniswap tools only with `uniswap_v2|v3`. Add a compatibility
   map (mirror the MockProvider server's `_COMPATIBLE_RECIPES` idea, but keyed by
   pool_type family), e.g.:
   ```python
   _TOOL_POOL_TYPES = {
       "AnalyzePosition": {"uniswap_v2", "uniswap_v3"},
       "SimulatePriceMove": {"uniswap_v2", "uniswap_v3"},
       "CheckPoolHealth": {"uniswap_v2", "uniswap_v3"},
       "DetectRugSignals": {"uniswap_v2", "uniswap_v3"},
       "CalculateSlippage": {"uniswap_v2", "uniswap_v3"},
       "AnalyzeBalancerPosition": {"balancer"},
       "SimulateBalancerPriceMove": {"balancer"},
       "AnalyzeStableswapPosition": {"stableswap"},
       "SimulateStableswapPriceMove": {"stableswap"},
       "AssessDepegRisk": {"stableswap"},
   }
   ```
   In `call_tool`, after validating `pool_type in POOL_TYPES`, also reject a
   tool+pool_type mismatch with a clean `IncompatiblePoolType` error (mirrors the
   MockProvider server's `IncompatiblePool` check). This prevents an LLM from calling
   `AssessDepegRisk` on a `uniswap_v2` pool and getting a confusing upstream crash.

5. **Token resolution (`_resolve_token`).** It already has the vault path
   (`vault.get_token` / `vault.get_names`) for Balancer/Stableswap — confirm it works
   against the live-built Balancer/Stableswap twins from Phase 0. Note: of the 5 new
   tools, **none currently takes a token-name arg** (only `CalculateSlippage` is in
   `_TOKEN_ARG_RENAMES`, and it stays V2/V3). So `_TOKEN_ARG_RENAMES` is unchanged.
   `AnalyzeStableswapPosition` takes `entry_amounts` (an array), not a token object;
   `AssessDepegRisk`'s `depeg_token` is a `DISPATCH_SUPPLIED_PARAM` upstream but the
   registry schema does **not** expose it as a required LLM arg (confirm against the
   registry — `AssessDepegRisk` required = `["lp_init_amt"]`). Verify none of the 5
   need a new token-name rename; if one does, add it to `_TOKEN_ARG_RENAMES`
   following the `CalculateSlippage` pattern.

6. **V3 tick-default guard.** The `if pool_type == "uniswap_v3":` block that defaults
   `lwr_tick`/`upr_tick` is V3-specific and must **not** run for balancer/stableswap.
   It's already gated on `pool_type == "uniswap_v3"`, so it's correctly skipped —
   just confirm the new tools (which don't take ticks) pass through untouched.

7. **`/health` tool list** — already returns `list(TOOL_NAMES)`, so it auto-updates
   to 10 once `TOOL_NAMES` grows. No change needed; confirm.

8. **Summarizers** — `_SUMMARIZERS` only has the 5 V2/V3 tools. Add summarizer lines
   for the 5 new tools (one short line each, mirroring the MockProvider server's
   summarizers for these exact tools — they already exist there and can be copied:
   `AnalyzeBalancerPosition`, `AnalyzeStableswapPosition`, `SimulateBalancerPriceMove`,
   `SimulateStableswapPriceMove`, `AssessDepegRisk`). Missing summarizers don't crash
   (there's a `<no summarizer>` fallback) but the receipts should be complete.

**Gate:**
- `TOOL_NAMES` has 10; `POOL_TYPES` has 4; `_TOOL_POOL_TYPES` gates per-tool.
- Offline tests green (fake-provider path — see Phase 2 for the new fixtures).
- V2/V3 behavior unchanged (existing offline + the existing 5 summarizers intact).
- A tool+pool_type mismatch returns a clean error, not a crash.

**Out of scope:** README/listing/version (Phase 2); live-RPC validation (Phase 2).

---

## Phase 2 — Tests, docs, redeploy

**Tests:**
1. **Offline** (`tests/test_server.py` pattern — the `_make_provider` seam is
   monkeypatched to inject a fake provider yielding hand-built snapshots). Add fake
   Balancer + Stableswap snapshots and assert each of the 5 new tools dispatches and
   returns the right dataclass. Add a mismatch test (`AssessDepegRisk` on
   `uniswap_v2` → `IncompatiblePoolType`).
2. **Live gate** (`tests/test_live.py`). Add real Balancer + Stableswap cases using
   the pool addresses recorded in Phase 0 — mirror the existing `test_*_live`
   structure. At minimum: `AnalyzeBalancerPosition` (or `SimulateBalancerPriceMove`)
   on the real Balancer pool, and `AssessDepegRisk` (or `AnalyzeStableswapPosition`)
   on the real Stableswap pool, asserting a sane non-null field. Keep them behind the
   `ECHOLEDGER_TEST_RPC_URL` skip gate.

**Docs / listings — update every place the "5 tools" / "V2/V3" claim appears:**
3. **`README.md`** — the "## Tools" section ("v0.1 ships **5 tools** over Uniswap
   V2/V3"): update to 10 tools across V2/V3 + Balancer + Stableswap, add the 5 new
   tool blurbs with example prompts, and state the 2-asset / plain-pool scope. Move
   the v0.2 Balancer/Stableswap roadmap line to a "shipped" framing; the lead
   paragraph ("Analyze **live** Uniswap V2/V3 pools") should now say V2/V3, Balancer,
   and Curve.
4. **`server.json`** and **`smithery.yaml`** — if either enumerates tools or describes
   the surface as V2/V3-only, update to the 10-tool / 4-protocol description. (Read
   both; update tool counts/descriptions to match.)
5. **`CITATION.cff`** — bump version if it carries one.
6. The Smithery listing description (the marketing copy) — note for the operator to
   update it post-deploy (that's a web action, not a repo change): "10 tools over
   Uniswap V2/V3, Balancer, and Curve Stableswap."

**Version + deploy:**
7. Bump `version` in `pyproject.toml` `0.1.0 → 0.2.0` (and `server.py`'s
   `Server("echoledger", version="0.1.0")` → `0.2.0`, and anywhere else the version
   string lives — grep for `0.1.0`).
8. Redeploy to Railway (the `sunny-recreation` project / `mcp.echoledger.ai`).
9. **Post-deploy verification:** `curl https://mcp.echoledger.ai/health` → `tools` array
   has all 10. Then a real MCP client call to one Balancer tool and one Stableswap
   tool against real pools (with a real RPC) returns a sane result.

**Gate (v0.2 shipped):**
- Offline + live tests green (live gated on RPC env var).
- `curl /health` shows 10 tools.
- A real Balancer-tool call and a real Stableswap-tool call each return sane results
  through the deployed endpoint.
- README, `server.json`, `smithery.yaml`, version strings all say 10 tools / 4
  protocols with honest 2-asset scope notes. No "5 tools" / "V2/V3 only" stragglers.

---

## Phase 3 — Re-publish to the registries

The endpoint now serves 10 tools (Phase 2), but the **public catalogs still advertise
5** until their published copies are refreshed. This phase re-publishes to both
registries the endpoint was originally listed on. Mirrors the original distribution
procedure (`operating-notes/mcp-spec-docs/PHASE_4_DISTRIBUTION.md`) — re-run, not
first-run, so most of it is editing an existing entry rather than creating one.

**Preconditions:** Phase 2 gate met — the deployed `mcp.echoledger.ai` serves 10 tools
(`curl /health` confirms), and `server.json` in the repo is updated (version `0.2.0`,
description covering V2/V3 + Balancer + Curve, `remotes[0].url` =
`https://mcp.echoledger.ai/mcp`).

### Tier 1 — Official MCP registry (`registry.modelcontextprotocol.io`)

The registry holds a **published snapshot** of `server.json`; the entry is editable
and re-publishing overwrites it. Confirm the repo `server.json` is fully updated
first (Phase 2), then:

1. **Re-confirm `server.json` content** for the v0.2 surface:
   - `version` → `0.2.0` (must match the deployed `pyproject.toml` / `server.py`).
   - `description` → covers all four protocols, e.g. *"Live LP analytics over Uniswap
     V2/V3, Balancer weighted, and Curve stableswap pools — position PnL, price-move
     scenarios, pool health, rug signals, slippage, depeg risk. Bring your own RPC."*
     Keep it ~100 chars / front-door voice / credits defipy openly / honors the
     claims-to-avoid list (no "first"/"only"/bare "unique").
   - `remotes[0].url` stays `https://mcp.echoledger.ai/mcp` (already migrated).
   - No `packages` block (remote-listed; ownership via the GitHub-org namespace).
2. **Publish via `mcp-publisher`** (the documented original path):
   - Install/locate the `mcp-publisher` CLI.
   - `mcp-publisher login github` — authenticate as the **echoledger-ai** org so the
     `io.github.echoledger-ai/*` namespace is authorized.
   - `mcp-publisher publish` from the repo root. The registry is preview /
     high-traffic — retry on transient failures.
3. **Verify:**
   ```bash
   curl "https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.echoledger-ai/echoledger-mcp"
   ```
   Returns the updated metadata: `version` `0.2.0`, new description.

### Tier 2 — Smithery (`smithery.ai/servers/ic3moore/echoledger`)

Smithery holds its **own ingested copy** of the server surface; updating
`smithery.yaml` in the repo is necessary but not sufficient — Smithery must re-ingest.

4. **Confirm `smithery.yaml`** reflects the 10-tool surface (updated in Phase 2).
5. **Trigger a Smithery re-scan / re-deploy** of `ic3moore/echoledger` so it picks up
   the new tool list. (Via the Smithery dashboard for the listing, or a redeploy
   trigger — confirm the mechanism in the dashboard; Smithery re-reads on redeploy.)
6. **Update the Smithery listing description** (marketing copy — a web action in the
   dashboard, not a repo change): "10 tools over Uniswap V2/V3, Balancer, and Curve
   Stableswap. Bring your own RPC."
7. **Verify:** the Smithery listing page shows 10 tools, and a call routed through the
   Smithery gateway hits a Balancer or Stableswap tool successfully.

### Tier 3 — Aggregators (only if manually submitted originally)

8. Most aggregators (mcp.so, etc.) **auto-ingest from the official registry** — the
   Tier 1 re-publish propagates to them with no action. For any that were *manually*
   submitted originally (per `PHASE_4_DISTRIBUTION.md`: mcpmarket.com, and possibly
   awesome-mcp-servers / FlowHunt / SERP AI), update only if they don't auto-refresh
   and the stale "5 tools" copy is worth correcting. Low priority; skip where
   upstream propagation handles it.

**Gate (registries refreshed):**
- Official registry search API returns `version 0.2.0` with the 4-protocol description.
- Smithery listing shows 10 tools; a gateway-routed Balancer/Stableswap call succeeds.
- No public listing still advertises "5 tools" / "V2/V3 only" (except low-priority
  aggregators that auto-refresh on their own schedule).

**Out of scope:** OCI-package listing, DNS-verified namespace, OIDC auto-publish
(still v0.2+ distribution polish per the original Phase 4 "out of scope"); a fresh
Zenodo DOI for v0.2 (the v0.1 citation artifact stands unless you decide to mint a
versioned DOI — separate decision, see `PHASE_5_CITATION.md`).

---

## Cross-cutting rules

- **V2/V3 path unchanged.** This is purely additive; existing 5-tool behavior,
  schemas, and receipts must not regress.
- **Statelessness preserved.** Fresh `LiveProvider` + twin per call; nothing cached.
- **Secret hygiene unchanged.** `rpc_url` stays redacted in receipts and scrubbed
  from error text (`_redact` / `_scrub_secrets`) — confirm the new error paths
  (incompatible pool type, Balancer/Stableswap upstream raises) route through
  `_scrub_secrets` too.
- **Honest scope in descriptions.** Every new tool's surfaced description must state
  2-asset (and plain-pool, for stableswap) scope. Do not imply N-asset or
  rate-bearing support that the primitives don't have.
- **Don't exceed the registry.** Only the 5 already-curated Balancer/Stableswap tools.
  No new primitives, no registry edits in `defipy`. Beyond-10 is a separate decision.
- **Keep the `<2.3` cap.** Same "no silent surface shift" discipline that capped
  `<2.2` before — lift to allow 2.2, cap below 2.3.
