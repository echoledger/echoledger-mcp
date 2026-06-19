# defimind-mcp

DeFiMind's MCP server. Analyze **live** Uniswap V2/V3, Balancer, and
Curve stableswap pools — positions, price moves, pool health, rug
signals, slippage, and depeg risk — from any MCP-compatible AI client.
Reads real chain state via a caller-supplied RPC; the endpoint itself is
authless.

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![MCP](https://img.shields.io/badge/MCP-streamable--http-6ea8ff)](https://modelcontextprotocol.io)
[![Python](https://img.shields.io/badge/Python-3.11+-3776ab)](https://www.python.org)
[![arXiv](https://img.shields.io/badge/arXiv-2605.11522-b31b1b.svg)](https://arxiv.org/abs/2605.11522)
[![smithery badge](https://smithery.ai/badge/ic3moore/defimind)](https://smithery.ai/servers/ic3moore/defimind)

Endpoint: **`https://mcp.defimind.ai/mcp`** (streamable-HTTP, authless).

## Install

### Claude Desktop
Settings → Integrations → Add server.
URL: `https://mcp.defimind.ai/mcp`

### Claude Code
```bash
claude mcp add --transport http defimind https://mcp.defimind.ai/mcp
```

### Cursor
Settings → MCP → Add new MCP server.
Name: `defimind` · Type: `http` · URL: `https://mcp.defimind.ai/mcp`

### Smithery
Listed at [smithery.ai/servers/ic3moore/defimind](https://smithery.ai/servers/ic3moore/defimind) — connect via the Smithery gateway from any supported client.

## Tools

v0.2 ships **10 tools** across Uniswap V2/V3, Balancer weighted, and
Curve stableswap pools, reading live pool state. Each call takes
`pool_address`, `rpc_url`, and `pool_type` (`uniswap_v2` | `uniswap_v3`
| `balancer` | `stableswap`), plus optional `chain_id` guard and
`block_number` pin — nothing is stored. Each tool is protocol-specific;
pointing one at the wrong `pool_type` returns a clean error before any
chain read.

**Scope:** the Balancer tools cover **2-asset weighted** pools; the
stableswap tools cover **2-asset plain Curve** pools (rate-bearing pools
— metapools, LSD — are a later release). A `stableswap` tool pointed at a
3-coin or rate-bearing pool fails cleanly.

### Uniswap V2/V3

#### `AnalyzePosition`
PnL decomposition for an LP position — impermanent loss, fees, and net.

> "Analyze my position in the V3 USDC/ETH pool."

#### `SimulatePriceMove`
"What if price moves X%?" — projected reserves, position value, and IL.

> "If ETH drops 20%, what happens to my V3 ETH/DAI position?"

#### `CheckPoolHealth`
TVL, reserves, LP concentration, and recent activity for a pool.

> "Is this V3 pool healthy?"

#### `DetectRugSignals`
Threshold-based rug flags on a pool's on-chain state.

> "Any rug signals on this V2 pair?"

#### `CalculateSlippage`
Slippage, price impact, and max trade size for a given trade.

> "How much slippage on a 50 ETH buy in this V3 pool?"

### Balancer (2-asset weighted)

#### `AnalyzeBalancerLP`
PnL decomposition for a 2-asset Balancer weighted-pool position, using
the weighted-pool IL formula where the token weight shapes IL magnitude.

> "How is my 80/20 BAL/WETH Balancer position doing?"

#### `SimulateBalancerMove`
"What if the base token moves X%?" — projected value and IL on a 2-asset
weighted pool, weight-aware.

> "If BAL drops 30%, what happens to my BAL/WETH Balancer LP?"

### Curve stableswap (2-asset plain)

#### `AnalyzeStableswapLP`
PnL decomposition for a 2-asset Curve stableswap position via the
amplified-invariant IL formula — small depegs can produce outsized IL at
high A.

> "Analyze my position in the crvUSD/USDC pool."

#### `SimulateStableswapMove`
"What if the peg shifts X%?" — projected value and IL on a 2-asset
stableswap pool. At high A, large shocks may be physically unreachable
(returned as null).

> "What happens to my USDC/DAI Curve LP if USDC depegs 2%?"

#### `AssessDepegRisk`
IL across a ladder of depeg levels (default 2%, 5%, 10%, 20%, 50%) for a
2-asset stableswap position, with an optional constant-product benchmark.

> "How exposed is my crvUSD/USDC position to a depeg?"

## How it works

`defimind-mcp` reads **live** Uniswap V2/V3, Balancer, and Curve
stableswap pool state through a caller-supplied RPC endpoint (BYO-RPC,
passed per tool call). The endpoint is **authless** — no API key, no
account. Nothing is logged or stored; each call pulls state, runs the
analysis, and returns a typed result.

The analytics are powered by open-source [DeFiPy](https://defipy.org) —
the same primitives, twin, and tools that run against synthetic recipes,
now pointed at real pools. **The math is open; the reports are paid.**

## Roadmap

- **v0.2 — Balancer & Stableswap live reads** ✓ shipped. The 5
  Balancer/Stableswap tools went live on DeFiPy 2.2's LiveProviders
  (2-asset weighted + 2-asset plain Curve).
- **N-asset & rate-bearing pools** — 3-asset Balancer, N-coin and
  rate-bearing (metapool/LSD) Curve, once the upstream DeFiPy primitives
  extend past 2 assets.
- **Distribution polish** — OCI-package listing, DNS-verified namespace,
  and OIDC auto-publish.

## Develop

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Run the server over streamable HTTP (binds to `$PORT`, default 8080):
```bash
PORT=8080 python -m defimind_mcp.server      # endpoint at http://localhost:8080/mcp
```

Or over stdio for a local MCP Inspector smoke-test:
```bash
python -m defimind_mcp.server --stdio
npx @modelcontextprotocol/inspector python -m defimind_mcp.server --stdio
```

Tests (offline — fake provider + real twin/primitives):
```bash
pytest tests/
```

Live-RPC gate (real mainnet Uniswap V2/V3, Balancer, and Curve pools;
needs your own RPC):
```bash
DEFIMIND_TEST_RPC_URL="https://eth-mainnet.example/v2/<key>" pytest tests/test_live.py -v
```

## License

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

This project adapts code from [DeFiPy](https://defipy.org) (Apache-2.0).

## See also

- DeFiPy (open-source substrate): https://defipy.org
- DeFiMind: https://defimind.ai
- State Twins paper: https://arxiv.org/abs/2605.11522
