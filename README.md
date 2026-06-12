# defimind-mcp

DeFiMind's MCP server. Analyze **live** Uniswap V2/V3 pools — positions,
price moves, pool health, rug signals, and slippage — from any
MCP-compatible AI client. Reads real chain state via a caller-supplied
RPC; the endpoint itself is authless.

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![MCP](https://img.shields.io/badge/MCP-streamable--http-6ea8ff)](https://modelcontextprotocol.io)
[![Python](https://img.shields.io/badge/Python-3.11+-3776ab)](https://www.python.org)
[![arXiv](https://img.shields.io/badge/arXiv-2605.11522-b31b1b.svg)](https://arxiv.org/abs/2605.11522)

Endpoint: **TBD** _(captured in Phase 3 once the endpoint is deployed; the
branded `mcp.defimind.ai` URL is a post-traction migration)._

## Install

> The endpoint URL below is a placeholder until Phase 3. Tool details are
> finalized in Phase 1.

### Claude Desktop
Settings → Integrations → Add server.
URL: `<endpoint-url>`

### Claude Code
```bash
claude mcp add --transport http defimind <endpoint-url>
```

### Cursor
Settings → MCP → Add new MCP server.
Name: `defimind` · Type: `http` · URL: `<endpoint-url>`

## Tools

v0.1 ships **5 tools** over Uniswap V2/V3, reading live pool state. Each
call takes an RPC URL and a pool address — nothing is stored. _(Schemas
and exact argument shapes are finalized in Phase 1.)_

### `AnalyzePosition`
PnL decomposition for an LP position — impermanent loss, fees, and net.

> "Analyze my position in the V3 USDC/ETH pool."

### `SimulatePriceMove`
"What if price moves X%?" — projected reserves, position value, and IL.

> "If ETH drops 20%, what happens to my V3 ETH/DAI position?"

### `CheckPoolHealth`
TVL, reserves, LP concentration, and recent activity for a pool.

> "Is this V3 pool healthy?"

### `DetectRugSignals`
Threshold-based rug flags on a pool's on-chain state.

> "Any rug signals on this V2 pair?"

### `CalculateSlippage`
Slippage, price impact, and max trade size for a given trade.

> "How much slippage on a 50 ETH buy in this V3 pool?"

## How it works

`defimind-mcp` reads **live** Uniswap V2/V3 pool state through a
caller-supplied RPC endpoint (BYO-RPC, passed per tool call). The
endpoint is **authless** — no API key, no account. Nothing is logged or
stored; each call pulls state, runs the analysis, and returns a typed
result.

The analytics are powered by open-source [DeFiPy](https://defipy.org) —
the same primitives, twin, and tools that run against synthetic recipes,
now pointed at real pools. **The math is open; the reports are paid.**

## Roadmap

- **v0.2 — Balancer & Stableswap live reads**, once DeFiPy 2.2 ships
  their LiveProviders.
- **Own-domain migration** — redeploy the same image to
  `mcp.defimind.ai` when traction justifies it (a redeploy, not a
  rewrite).
- **Distribution polish** — OCI-package listing, DNS-verified namespace,
  and OIDC auto-publish.

## Develop

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

_(Server entry point and local run/test commands land in Phase 1.)_

Verify locally with the MCP inspector:
```bash
npx @modelcontextprotocol/inspector <local-endpoint>
```

## License

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

This project adapts code from [DeFiPy](https://defipy.org) (Apache-2.0).

## See also

- DeFiPy (open-source substrate): https://defipy.org
- DeFiMind: https://defimind.ai
- State Twins paper: https://arxiv.org/abs/2605.11522
