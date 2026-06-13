# DeFiMind MCP — Canonical Listing Copy

*Reusable copy for MCP catalog/registry listings. DeFiMind front-door voice,
crediting open-source DeFiPy as the methodology underneath. Honors the
claims-to-avoid list (no "first" / "only" / bare "unique").*

Endpoint: `https://mcp.defimind.ai/mcp` (streamable-HTTP, authless) ·
Namespace: `io.github.defimind-ai/defimind-mcp`

---

## Name

**DeFiMind**

## One-liner (≤ 120 chars)

> Live Uniswap V2/V3 LP analytics over MCP — position PnL, price scenarios, pool health, rug signals, slippage. Bring your own RPC.

## Short description (≤ 100 chars — registry/index)

> Live Uniswap V2/V3 LP analytics — position PnL, price scenarios, pool health, rug signals, slippage.

## Long description (catalog detail pages)

DeFiMind is an MCP endpoint for live Uniswap V2/V3 LP analysis. It exposes
five tools that read **real pool state** through a caller-supplied RPC URL
(BYO-RPC, passed per call) and answer specific LP questions: position PnL
decomposition, hypothetical price-move scenarios, pool-health snapshots,
rug-signal detection, and slippage/price-impact analysis.

The endpoint is **authless** — no account, no API key. You supply the RPC
per call; nothing is stored or logged (the RPC URL is redacted from every
receipt). Each call reads pool state, runs the analysis, and returns a
typed result.

The analytics aren't API wrappers — they're exact AMM math. DeFiMind is
powered by the open-source [DeFiPy](https://defipy.org) library: the same
closed-form invariants, State Twin substrate, and composable primitives,
now pointed at live pools. Position analysis decomposes PnL into
impermanent loss, fees, and net result; V3 IL is computed over the
position's tick range via concentrated-liquidity math. **The math is open;
the reports are paid.**

Connect from any MCP client:

    claude mcp add --transport http defimind https://mcp.defimind.ai/mcp

Then ask natural-language questions — *"Is this V3 pool healthy?"*,
*"What's my IL if ETH drops 30% on this position?"*, *"How much slippage on
a 50-ETH buy?"* — and the agent calls a DeFiMind tool, gets a typed result,
and answers with exact-math backing.

## Example queries

1. **"Check the health of this Uniswap V3 pool: `<address>`."**
   → `CheckPoolHealth` → TVL, reserves, LP concentration, fee tier, current tick.
2. **"If ETH drops 30%, what happens to my position in this V3 pool?"**
   → `SimulatePriceMove` → new value, IL at the new price, value-change %.
3. **"How much slippage on a 50,000 USDC buy in this V2 pair?"**
   → `CalculateSlippage` → spot vs execution price, slippage %, price impact.

## Available tools (5)

- `AnalyzePosition` — V2/V3 LP PnL decomposition (IL, fees, net).
- `SimulatePriceMove` — V2/V3 "what if price moves X%?" scenarios.
- `CheckPoolHealth` — V2/V3 pool-health snapshot (TVL, reserves, concentration).
- `DetectRugSignals` — V2/V3 threshold-based rug-signal flags.
- `CalculateSlippage` — V2/V3 slippage, price impact, max trade size.

Each tool takes `pool_address`, `rpc_url`, and `pool_type`
(`uniswap_v2` | `uniswap_v3`), plus optional `chain_id` guard and
`block_number` pin. Balancer and Stableswap tools return in v0.2 when
DeFiPy 2.2 ships their live providers.

## Links

- **Endpoint**: https://mcp.defimind.ai/mcp
- **Source**: https://github.com/defimind-ai/defimind-mcp
- **DeFiMind**: https://defimind.ai
- **DeFiPy (open-source substrate)**: https://defipy.org
- **State Twins paper**: https://arxiv.org/abs/2605.11522

## Claims to avoid (carried from DeFiPy catalog copy)

- Avoid **"first"** — predecessors exist.
- Avoid **"only"** — other DeFi MCP servers exist; the differentiation is
  exact-math depth and live concentrated-liquidity analysis, not exclusivity.
- Avoid bare **"unique"** — always pair with a specific axis (exact math,
  primitive composition, open-substrate framing).
