"""Live-RPC gate tests — the Phase 1 gate's real-chain half.

Skipped unless DEFIMIND_TEST_RPC_URL is set to an Ethereum-mainnet RPC.
Run:  DEFIMIND_TEST_RPC_URL="https://eth-mainnet.../v2/<key>" \\
          .venv/bin/pytest tests/test_live.py -v

Exercises CheckPoolHealth + CalculateSlippage against a real mainnet V2
pool (USDC/WETH) and V3 pool (USDC/WETH 0.05%), through the real
LiveProvider — no fakes.
"""

import asyncio
import json
import os

import pytest

from defimind_mcp import server

RPC = os.environ.get("DEFIMIND_TEST_RPC_URL")
pytestmark = pytest.mark.skipif(
    not RPC, reason="set DEFIMIND_TEST_RPC_URL to run live-RPC gate tests")

USDC_WETH_V2 = "0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc"
USDC_WETH_V3 = "0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640"


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
