# Phase 1 — Server Build (5 live V2/V3 tools, HTTP)

*defimind-mcp v0.1 build. Master plan: `DEFIMIND_MCP_EXECUTION_PLAN.md`. Execute via Claude Code.*

**Objective:** Build the HTTP MCP server that serves the 5 live Uniswap V2/V3 tools, by lifting and adapting defipy's stdio MockProvider server into `src/`. This is the core engineering phase — it does four things at once: subset to 5 tools, swap MockProvider→LiveProvider, replace the input model with live pool identity, and swap stdio→streamable HTTP.

**Preconditions:** Phase 0 skeleton done.

## Source of truth (read first)
- `/Users/ian_moore/repos/defipy/python/mcp/defipy_mcp_server.py` — the server to adapt. Authoritative for tool wrapping, dispatch, token resolution, receipts.
- `/Users/ian_moore/repos/defipy/python/prod/twin/live_provider.py` — LiveProvider API (read the docstrings).
- `/Users/ian_moore/repos/defipy/python/prod/twin/builder.py` — `StateTwinBuilder.build(snapshot)`.
- `defipy.tools` — `TOOL_REGISTRY`, `get_schemas("mcp")`; `TOOL_REGISTRY[name].primitive_cls().apply(lp, **args)`.

## Grounded API facts (do not re-derive)
- Construction: `LiveProvider(rpc_url)`.
- Snapshot: `provider.snapshot("uniswap_v2:0xADDR")` or `"uniswap_v3:0xADDR"`; kwargs `block_number` (both), `lwr_tick`/`upr_tick` (V3 only). Returns `V2PoolSnapshot` / `V3PoolSnapshot`.
- Build twin: `lp = StateTwinBuilder().build(snapshot)`.
- **`chain_id` is read from the RPC inside `.snapshot()`** — it is not a required read input. A `chain_id` tool input is an optional guard only.
- Address casing is normalized internally (lower/upper/checksum all accepted).
- Requires `defipy[chain]` (web3scout + web3); imported lazily on first snapshot.
- **The 5 tools** (defipy CHANGELOG names these as the V2/V3-LiveProvider-compatible primitives): `AnalyzePosition`, `SimulatePriceMove`, `CheckPoolHealth`, `DetectRugSignals`, `CalculateSlippage`.

## Resolve at the top (master-plan Decisions 1 & 2)
- **D1 (lift vs import):** lift the server file's wrapping/dispatch/token-resolution/receipt code into `src/`, then adapt. We're rewriting the provider and input model anyway, so a clean adaptation (not a verbatim copy) is correct. Depend on `defipy[chain]` + `mcp`. *Future note:* the wrapping logic could later move upstream into defipy so the stdio and HTTP servers share one source — out of scope for v0.1.
- **D2 (FastMCP vs low-level):** recommended — keep the low-level `mcp.server.Server` + hand-registered `list_tools`/`call_tool` handlers (preserves the proven dispatch) and mount over streamable HTTP. Fall back to FastMCP only if the low-level HTTP mount proves fiddly.

## Steps

1. **Subset to 5 tools.** Filter `get_schemas("mcp")` / `TOOL_REGISTRY` to `{AnalyzePosition, SimulatePriceMove, CheckPoolHealth, DetectRugSignals, CalculateSlippage}`. Drop the Balancer/Stableswap tools and all MockProvider recipe machinery from the production path.

2. **Replace the input model.** Rewrite `_wrap_schemas_with_pool_id` → `_wrap_schemas_with_pool_identity`. Inject onto each tool's `inputSchema`:
   - `pool_address` — string, **required**.
   - `rpc_url` — string, **required**. (Caller's RPC; carries their key. Endpoint stores/logs nothing — state this in the description.)
   - `pool_type` — string enum `["uniswap_v2", "uniswap_v3"]`, **required**.
   - `chain_id` — integer, **optional**, default 1 (guard only; see step 4).
   - `block_number` — integer, **optional** (pin historical reads).
   - For the V3 case on position tools: optional `lwr_tick` / `upr_tick`.
   Keep CalculateSlippage's existing token-name string arg.

3. **Replace provider wiring in dispatch.** Per call (stateless, fresh per call — preserve that contract):
   - read `pool_address`, `rpc_url`, `pool_type`, optional `block_number`/`lwr_tick`/`upr_tick`;
   - `provider = LiveProvider(rpc_url)`;
   - `snap = provider.snapshot(f"{pool_type}:{pool_address}", **present_kwargs)`;
   - `lp = StateTwinBuilder().build(snap)`;
   - strip the identity args, then `TOOL_REGISTRY[name].primitive_cls().apply(lp, **primitive_args)`.
   Preserve: token resolution for CalculateSlippage (`_resolve_token` works unchanged against a live-built V2/V3 `lp`), stderr JSON receipts, structured error returns.

4. **chain_id guard (optional but cheap).** If `chain_id` is supplied and `snap.chain_id` differs, return a structured error ("declared chain_id N but the RPC reports M"). Catches users pointing the wrong RPC at a pool.

5. **Transport: stdio → streamable HTTP.** Replace the `stdio_server` main with a streamable-HTTP ASGI app: CORS middleware (browser clients), bind to the `PORT` env var (default e.g. 8080). Keep an optional stdio entrypoint for local Inspector smoke-tests.

6. **Validate composition per tool.** Pool-level tools (`CheckPoolHealth`, `DetectRugSignals`, `CalculateSlippage`) compose cleanly with a live `lp`. The two **position** tools (`AnalyzePosition`, `SimulatePriceMove`) take a *user's* position basis (entry amounts, `lp_init_amt`) on top of the live pool; for **V3** the live snapshot defaults to full-range active liquidity. Confirm the position-basis args compose sensibly against a live twin and **document any modeling caveat** in a code comment + README note (e.g. V3 position analysis assumes the supplied range / full-range default). Do not silently ship a position tool whose semantics are unclear against live state.

7. **Tests** (`tests/`): enumeration returns exactly 5; dispatch of `CheckPoolHealth` + `CalculateSlippage` against a known mainnet V2 pool (e.g. USDC/WETH) and a V3 pool, using a real RPC or a mocked `_rpc` client (see defipy's `python/test/twin/_fake_rpc.py` pattern); error paths (bad `pool_type`, unreachable RPC, chain mismatch).

## Gate
- MCP Inspector (`npx @modelcontextprotocol/inspector <local-url-or-stdio>`) enumerates **exactly 5** tools.
- A live invocation of `CheckPoolHealth` and `CalculateSlippage` against a real mainnet **V2** and **V3** pool returns correct structured results.
- Receipts emit to stderr; the server runs over HTTP bound to `PORT` locally.

## Out of scope
Balancer/Stableswap tools (no live provider until defipy 2.2). MockProvider as a production path (keep only for tests/examples). Container, deploy, listings.

## Handoff to Phase 2
A locally-runnable HTTP server module + the confirmed runtime dep list (`defipy[chain]`, `mcp`, the HTTP server lib + version), and the `PORT`/entrypoint contract the Dockerfile will use.
