"""Live-RPC gate tests — the real-chain half of the gate.

Skipped unless ECHOLEDGER_TEST_RPC_URL is set to an Ethereum-mainnet RPC.
Run:  ECHOLEDGER_TEST_RPC_URL="https://eth-mainnet.../v2/<key>" \\
          .venv/bin/pytest tests/test_live.py -v

Exercises the dispatch path against real mainnet pools through the real
LiveProvider — no fakes:
  - Uniswap V2/V3 (USDC/WETH): CheckPoolHealth + CalculateSlippage.
  - Balancer 2-asset weighted (BAL/WETH 80/20): AnalyzeBalancerPosition +
    SimulateBalancerPriceMove.
  - Curve plain 2-asset stableswap (crvUSD/USDC): AnalyzeStableswapPosition
    + AssessDepegRisk. (SimulateStableswapPriceMove is intentionally not
    asserted live: at the pool's high A a small depeg is physically
    unreachable and the primitive correctly returns null sentinels.)
"""

import asyncio
import json
import os

import pytest

from echoledger_mcp import server

RPC = os.environ.get("ECHOLEDGER_TEST_RPC_URL")
pytestmark = pytest.mark.skipif(
    not RPC, reason="set ECHOLEDGER_TEST_RPC_URL to run live-RPC gate tests")

USDC_WETH_V2 = "0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc"
USDC_WETH_V3 = "0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640"
# Archetypal 2-asset Balancer weighted pool: 80/20 BAL/WETH.
BAL_WETH_BALANCER = "0x5c6Ee304399DBdB9C8Ef030aB642B10820DB8F56"
# 2-coin plain Curve stableswap pool: crvUSD/USDC (A=2000).
CRVUSD_USDC_STABLESWAP = "0x4DEcE678ceceb27446b35C672dC7d61F30bAD69E"


def _call(name, args):
    return asyncio.run(server.call_tool(name, args))[0].text


def test_pool_health_v2_live():
    payload = json.loads(_call("CheckPoolHealth", {
        "pool_address": USDC_WETH_V2, "rpc_url": RPC,
        "pool_type": "uniswap_v2",
    }))
    assert payload["tvl_in_token0"] > 0


def test_pool_health_v3_live():
    payload = json.loads(_call("CheckPoolHealth", {
        "pool_address": USDC_WETH_V3, "rpc_url": RPC,
        "pool_type": "uniswap_v3",
    }))
    assert payload["tvl_in_token0"] > 0


def test_slippage_v2_live():
    payload = json.loads(_call("CalculateSlippage", {
        "pool_address": USDC_WETH_V2, "rpc_url": RPC,
        "pool_type": "uniswap_v2", "amount_in": 10_000.0,
        "token_in_name": "USDC",
    }))
    assert payload["slippage_pct"] is not None


def test_slippage_v3_live():
    payload = json.loads(_call("CalculateSlippage", {
        "pool_address": USDC_WETH_V3, "rpc_url": RPC,
        "pool_type": "uniswap_v3", "amount_in": 10_000.0,
        "token_in_name": "USDC",
    }))
    assert payload["slippage_pct"] is not None


# ─── v0.2: Balancer + Stableswap live gate ───────────────────────────────────


def test_balancer_position_live():
    payload = json.loads(_call("AnalyzeBalancerPosition", {
        "pool_address": BAL_WETH_BALANCER, "rpc_url": RPC,
        "pool_type": "balancer",
        "lp_init_amt": 10.0, "entry_base_amt": 1_000.0, "entry_opp_amt": 10.0,
    }))
    assert 0.0 < payload["base_weight"] < 1.0
    assert isinstance(payload["net_pnl"], (int, float))
    assert payload["diagnosis"] in {
        "net_positive", "fee_compensated", "il_dominant"}


def test_balancer_price_move_live():
    payload = json.loads(_call("SimulateBalancerPriceMove", {
        "pool_address": BAL_WETH_BALANCER, "rpc_url": RPC,
        "pool_type": "balancer",
        "price_change_pct": -0.30, "lp_init_amt": 10.0,
    }))
    assert payload["new_value"] is not None
    assert payload["il_at_new_price"] <= 0.0


def test_analyze_stableswap_position_live():
    payload = json.loads(_call("AnalyzeStableswapPosition", {
        "pool_address": CRVUSD_USDC_STABLESWAP, "rpc_url": RPC,
        "pool_type": "stableswap",
        "lp_init_amt": 100.0, "entry_amounts": [100.0, 100.0],
    }))
    assert len(payload["token_names"]) == 2
    assert payload["A"] > 0
    assert isinstance(payload["diagnosis"], str)


def test_assess_depeg_risk_live():
    payload = json.loads(_call("AssessDepegRisk", {
        "pool_address": CRVUSD_USDC_STABLESWAP, "rpc_url": RPC,
        "pool_type": "stableswap", "lp_init_amt": 100.0,
    }))
    assert payload["protocol_type"] == "stableswap"
    assert payload["n_assets"] == 2
    assert payload["current_peg_deviation"] is not None
    assert len(payload["scenarios"]) == 5


def test_incompatible_pool_type_live():
    # A stableswap tool on a V2 pool address must be gated cleanly, never
    # reaching the chain (no RPC round-trip, no upstream crash).
    out = _call("AssessDepegRisk", {
        "pool_address": USDC_WETH_V2, "rpc_url": RPC,
        "pool_type": "uniswap_v2", "lp_init_amt": 100.0,
    })
    assert "not compatible" in out
