# DeFiMind MCP — tool reference (11 tools)

The hosted endpoint (`https://mcp.defimind.ai/mcp`) exposes **11 tools** over
live Uniswap V2/V3, Balancer V2 weighted (2-asset), and Curve plain Stableswap
(2-asset) pools. This is the complete, verified reference for the shipped
surface. Examples are captured from the real handlers.

## Two surfaces

The toolkit has two consumer models:

- **Reactive primitives (10 tools)** — one question, one answer, one chain
  read. For one-shot / no-install consumers. Four of them also accept a
  **vector** input to sweep a whole grid/curve in a single call (one read, N
  results).
- **State-twin builder (1 tool, `BuildStateTwin`)** — hands back a *serialized
  State Twin* (the pool's state as JSON). A client rehydrates it locally and
  runs unlimited counterfactuals **off the MCP, with zero further RPC**. See
  [the twin round-trip](#buildstatetwin) and the
  [`defimind` package guide](https://github.com/defimind-ai/defimind).

## Common input — pool identity

Every tool takes the same pool-identity fields (BYO-RPC; nothing is stored or
logged):

| Field | Required | Notes |
|---|---|---|
| `pool_address` | yes | On-chain pool/pair address. Any casing. |
| `rpc_url` | yes | Your Ethereum/L2 JSON-RPC URL. May carry a key — never persisted or logged. |
| `pool_type` | yes | The protocol. **Each tool advertises only the values it accepts** (post-SPEC-1.1) — see each tool below. |
| `chain_id` | no | Guard: if the RPC reports a different chain, the call is rejected. |
| `block_number` | no | Pin the read to a historical block. Omit for latest. |

Each reactive tool is protocol-specific: pointing one at an unsupported
`pool_type` returns a clean `IncompatiblePoolType` error **before any chain
read**, never a stack trace.

**Scope:** Balancer tools cover **2-asset weighted** pools; stableswap tools
cover **2-asset plain Curve** pools. A tool pointed at a 3-asset or
rate-bearing pool fails cleanly (metapools / LSD / N-coin are a later release).

---

## Uniswap V2/V3

### `AnalyzePosition`
**Purpose:** why an LP position is gaining or losing — PnL decomposed into IL,
fees, and net. · **pool_type:** `uniswap_v2` | `uniswap_v3`

**Params:** `lp_init_amt` (req), `entry_x_amt` (req), `entry_y_amt` (req),
`holding_period_days` (opt), `lwr_tick`/`upr_tick` (V3 position range; default
full range).

**Returns:** `current_value`, `hold_value`, `il_percentage`, `il_with_fees`,
`fee_income`, `net_pnl`, `real_apr`, `diagnosis`
(`net_positive`|`fee_compensated`|`il_dominant`).

```json
// AnalyzePosition · {pool_type:"uniswap_v2", lp_init_amt:100, entry_x_amt:5773, entry_y_amt:1.732, holding_period_days:30}
{
  "current_value": 11547.0, "hold_value": 11546.3,
  "il_percentage": -4.2e-10, "il_with_fees": 5.8e-05,
  "fee_income": 0.672, "net_pnl": 0.672, "real_apr": 0.00071,
  "diagnosis": "net_positive"
}
```

### `SimulatePriceMove`
**Purpose:** project a position's value at a hypothetical price change from
**current** state. · **pool_type:** `uniswap_v2` | `uniswap_v3`

**Params:** `price_change_pct` **or** `price_change_pcts[]` (vector — see
[Vector inputs](#vector-inputs)); `position_size_lp` (req); `lwr_tick`/`upr_tick`
(V3).

**Returns:** `new_price_ratio`, `new_value`, `il_at_new_price`,
`fee_projection` (always null), `value_change_pct`.

```json
// SimulatePriceMove · {pool_type:"uniswap_v2", price_change_pct:-0.2, position_size_lp:100}
{ "new_price_ratio": 0.8, "new_value": 12909.9,
  "il_at_new_price": -0.00619, "fee_projection": null,
  "value_change_pct": 0.118 }
```

### `CheckPoolHealth`
**Purpose:** pool-level health — TVL, reserves, LP concentration, activity. ·
**pool_type:** `uniswap_v2` | `uniswap_v3`

**Params:** `recent_window` (opt, V2-only rolling window). **Returns:**
`tvl_in_token0`, `reserve0/1`, `spot_price`, `num_lps`, `top_lp_share_pct`,
`has_activity`, `total_fee0/1`, `num_swaps`, `fee_accrual_rate_recent`, …

> **Single-block honest gap:** `num_lps`, `top_lp_share_pct`, `num_swaps`,
> `fee_accrual_rate_recent` are history-derived and come back `null` on a live
> single-block snapshot — they are recoverable only from a server-side history
> read, not from the State Twin.

```json
// CheckPoolHealth · {pool_type:"uniswap_v3"}
{ "version": "V3", "token0_name": "USDC", "token1_name": "WETH",
  "spot_price": 0.0003, "reserve0": 50000000.0, "reserve1": 15000.0,
  "tvl_in_token0": 100000000.0, "tvl_in_token1": 30000.0,
  "num_lps": null, "top_lp_share_pct": null, "has_activity": false,
  "fee_pips": 500, "tick_current": -81122 }
```

### `DetectRugSignals`
**Purpose:** threshold-based rug flags over a pool's on-chain state. ·
**pool_type:** `uniswap_v2` | `uniswap_v3`

**Params:** `lp_concentration_threshold` (opt, default 0.90), `tvl_floor`
(opt, default 10.0). **Returns:** `risk_level`
(`low`|`medium`|`high`|`critical`), `signals_detected`,
`tvl_suspiciously_low`, `single_sided_concentration`,
`inactive_with_liquidity`, `details[]`, nested `pool_health`.

```json
// DetectRugSignals · {pool_type:"uniswap_v2"}
{ "tvl_suspiciously_low": false, "single_sided_concentration": false,
  "inactive_with_liquidity": false, "signals_detected": 0,
  "risk_level": "low", "details": ["inactive_with_liquidity: not evaluated (swap history unavailable for a live snapshot)"] }
```

### `CalculateSlippage`
**Purpose:** slippage / price-impact decomposition for a proposed trade. ·
**pool_type:** `uniswap_v2` | `uniswap_v3`

**Params:** `token_in_name` (req — a token symbol in the pool), `amount_in`
**or** `amounts_in[]` (vector); `lwr_tick`/`upr_tick` (V3). **Returns:**
`spot_price`, `execution_price`, `slippage_pct`, `slippage_cost`,
`price_impact_pct`, `max_size_at_1pct` (V2 only; `null` for V3).

```json
// CalculateSlippage · {pool_type:"uniswap_v3", token_in_name:"USDC", amount_in:50000}
{ "spot_price": 0.0003, "execution_price": 0.0002988,
  "slippage_pct": 0.00399, "slippage_cost": 0.0599,
  "price_impact_pct": 0.00199, "max_size_at_1pct": null }
```

---

## Balancer (2-asset weighted)

### `AnalyzeBalancerLP`
**Purpose:** PnL for a 2-asset Balancer weighted-pool position (weight shapes
IL). · **pool_type:** `balancer`

**Params:** `lp_init_amt` (req), `entry_base_amt` (req), `entry_opp_amt` (req),
`holding_period_days` (opt). **Returns:** `base_tkn_name`, `opp_tkn_name`,
`base_weight`, `current_value`, `hold_value`, `il_percentage`, `net_pnl`,
`alpha`, `diagnosis`. *(Fee income is not attributed in v1 — Balancer exposes
only vault-level fees.)*

```json
// AnalyzeBalancerLP · {pool_type:"balancer", lp_init_amt:10, entry_base_amt:3, entry_opp_amt:1200}
{ "base_tkn_name": "WETH", "opp_tkn_name": "BAL", "base_weight": 0.8,
  "current_value": 60000.0, "hold_value": 6000.0, "il_percentage": 0.0,
  "net_pnl": 54000.0, "alpha": 1.0, "diagnosis": "net_positive" }
```

### `SimulateBalancerMove`
**Purpose:** project a 2-asset Balancer position at a hypothetical base-token
move. · **pool_type:** `balancer`

**Params:** `price_change_pct` **or** `price_change_pcts[]` (vector);
`lp_init_amt` (req). **Returns:** `new_price_ratio`, `new_value`,
`il_at_new_price`, `value_change_pct`, plus `base_weight`/token names.

```json
// SimulateBalancerMove · {pool_type:"balancer", price_change_pct:-0.3, lp_init_amt:10}
{ "base_tkn_name": "WETH", "base_weight": 0.8, "new_price_ratio": 0.7,
  "new_value": 45105.5, "il_at_new_price": -0.01084, "value_change_pct": -0.2482 }
```

---

## Curve stableswap (2-asset plain)

### `AnalyzeStableswapLP`
**Purpose:** PnL for a 2-asset Curve stableswap position via the
amplified-invariant IL formula (small depegs → outsized IL at high A). ·
**pool_type:** `stableswap`

**Params:** `lp_init_amt` (req), `entry_amounts[]` (req — 2 entries),
`holding_period_days` (opt). **Returns:** `token_names`, `A`, `current_value`,
`hold_value`, `il_percentage`, `net_pnl`, `alpha`, `diagnosis`,
`per_token_init/current`.

```json
// AnalyzeStableswapLP · {pool_type:"stableswap", lp_init_amt:1000, entry_amounts:[500,500]}
{ "token_names": ["USDC","DAI"], "A": 100, "current_value": 1000.0,
  "hold_value": 1000.0, "il_percentage": 0.0, "net_pnl": 0.0,
  "alpha": 1.0, "diagnosis": "at_peg" }
```

### `SimulateStableswapMove`
**Purpose:** project a 2-asset stableswap position at a hypothetical peg shift.
· **pool_type:** `stableswap`

**Params:** `price_change_pct` **or** `price_change_pcts[]` (vector);
`lp_init_amt` (req). **Returns:** `new_price_ratio`, `new_value`,
`il_at_new_price`, `value_change_pct`. At high A, large shocks may be
physically unreachable — those fields come back `null`.

```json
// SimulateStableswapMove · {pool_type:"stableswap", price_change_pct:-0.02, lp_init_amt:1000}
{ "token_names": ["USDC","DAI"], "A": 100, "new_price_ratio": 0.98,
  "new_value": null, "il_at_new_price": null, "value_change_pct": null }
```

### `AssessDepegRisk`
**Purpose:** IL across a ladder of depeg levels for a 2-asset stableswap
position, with an optional constant-product benchmark. · **pool_type:**
`stableswap`

**Params:** `lp_init_amt` (req), `depeg_token_name` (opt — defaults to the
pool's first token), `depeg_levels` (opt — default `[0.02,0.05,0.10,0.20,0.50]`),
`compare_v2` (opt, default true). **Returns:** `depeg_token`, `protocol_type`,
`n_assets`, `current_peg_deviation`, `scenarios[]` (each: `depeg_pct`,
`peg_price`, `il_pct`, `lp_value_at_depeg`, `hold_value_at_depeg`,
`v2_il_comparison`).

```json
// AssessDepegRisk · {pool_type:"stableswap", lp_init_amt:1000, depeg_token_name:"USDC"}  (scenarios trimmed to 2 of 5)
{ "depeg_token": "USDC", "protocol_type": "stableswap", "n_assets": 2,
  "current_peg_deviation": 0.0,
  "scenarios": [
    { "depeg_pct": 0.02, "peg_price": 0.98, "il_pct": null, "v2_il_comparison": -5.1e-05 },
    { "depeg_pct": 0.50, "peg_price": 0.50, "il_pct": null, "v2_il_comparison": -0.0572 }
  ] }
```

---

## Vector inputs

Four scenario-shaped tools accept an **array** alongside their scalar so you
can sweep a grid/curve in **one call** — the pool is read once and you get an
ordered array of results:

| Tool | Scalar | Vector |
|---|---|---|
| `SimulatePriceMove` | `price_change_pct` | `price_change_pcts[]` |
| `SimulateBalancerMove` | `price_change_pct` | `price_change_pcts[]` |
| `SimulateStableswapMove` | `price_change_pct` | `price_change_pcts[]` |
| `CalculateSlippage` | `amount_in` | `amounts_in[]` |

(`AssessDepegRisk` is already multi-level via `depeg_levels[]`.) Supply
**exactly one** of scalar/vector — passing both is a clean error. Max 256
entries. The scalar form is unchanged (back-compat) and returns a single
object; the vector form returns an array.

```json
// SimulatePriceMove · {pool_type:"uniswap_v2", price_change_pcts:[-0.2, 0.0, 0.2], position_size_lp:100}
[ { "new_price_ratio": 0.8, "new_value": 12909.9, "il_at_new_price": -0.00619, "value_change_pct": 0.118 },
  { "new_price_ratio": 1.0, "new_value": 11547.0, "il_at_new_price": 0.0,      "value_change_pct": 0.0 },
  { "new_price_ratio": 1.2, "new_value": 10540.9, "il_at_new_price": -0.00414, "value_change_pct": -0.0871 } ]
```

---

## `BuildStateTwin`

**Purpose:** read a pool once and return its state as a **serialized State
Twin** — the wire form a client rehydrates locally to run unlimited
counterfactuals off the MCP. · **pool_type:** `uniswap_v2` | `uniswap_v3` |
`balancer` | `stableswap` (**all four** — this tool spans every snapshot type).

**Params:** `block_number` (opt), `chain_id` (opt), `lwr_tick`/`upr_tick` (opt,
`uniswap_v3` only — position range; ignored otherwise).

**Returns** the wire form: `__type__` (snapshot class), all snapshot fields,
and `content_hash`:

```json
// BuildStateTwin · {pool_type:"uniswap_v3", pool_address:"0x88e6…"}
{
  "__type__": "V3PoolSnapshot",
  "pool_id": "0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640",
  "protocol": "uniswap_v3", "block_number": 20000000,
  "timestamp": 1718900000, "chain_id": 1,
  "token0_name": "USDC", "token1_name": "WETH",
  "reserve0": 50000000.0, "reserve1": 15000.0,
  "fee": 500, "tick_spacing": 10, "lwr_tick": -887270, "upr_tick": 887270,
  "content_hash": "0x597a840ef684a18d196149b861c7b3b96335efab23e6fee2e5fdf664e48a59ef"
}
```

`content_hash = "0x" + sha256(json.dumps(<body>, sort_keys=True))`, computed
over the snapshot body **before** the `__type__`/`content_hash` keys are added
— so a client can recompute and verify it.

### The twin round-trip (build once, run N, zero RPC)

```python
from defimind.client import build, sweep, verify_content_hash      # pip install defimind[twin]
from defipy.primitives.position import SimulatePriceMove

wire = ...                              # the BuildStateTwin JSON above
assert verify_content_hash(wire)        # optional integrity check
exchange = build(wire)                  # rehydrate -> runnable twin (no RPC)

results = sweep(SimulatePriceMove(), exchange, "price_change_pct",
                [-0.3, -0.1, 0.0, 0.2], position_size_lp=100.0)   # N evals, 0 RPC
```

The same twin can be built **BYO-RPC** with no hosted call —
`defimind.client.build_from_rpc("uniswap_v3:0x88e6…", rpc_url)`. See the
[`defimind` package guide](https://github.com/defimind-ai/defimind).

> **Honest gap:** `BuildStateTwin` is a single-block **STATE** twin.
> History-derived health metrics (swap counts, fee accrual, LP concentration)
> are **not** in it and remain server-side reads inside `CheckPoolHealth` /
> `DetectRugSignals`.
