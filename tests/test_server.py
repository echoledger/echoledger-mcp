"""Phase 1 tests for the DeFiMind MCP server.

Strategy: the live-RPC seam (`_make_provider`) is monkeypatched to a
fake provider that returns hand-built V2/V3 snapshot dataclasses. The
*real* StateTwinBuilder and the *real* defipy primitives then run, so
dispatch / identity-stripping / token-resolution / chain-guard / receipt
logic is exercised end-to-end with no web3 and no network.

The live-RPC gate (CheckPoolHealth + CalculateSlippage against real
mainnet V2 and V3 pools) lives in test_live.py and is skipped unless
DEFIMIND_TEST_RPC_URL is set.
"""

import asyncio
import json

import pytest

from defipy.twin.snapshot import V2PoolSnapshot, V3PoolSnapshot
from defimind_mcp import server


# ─── Fake provider ──────────────────────────────────────────────────────────

# A real mainnet-shaped V2 pair (USDC/WETH) and V3 pool (USDC/WETH 0.05%),
# but reserves/price are synthetic — we only need a coherent snapshot.
USDC_WETH_V2 = "0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc"
USDC_WETH_V3 = "0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640"


class FakeProvider:
    def __init__(self, snapshot):
        self._snapshot = snapshot
        self.calls = []

    def snapshot(self, pool_id, **kwargs):
        self.calls.append((pool_id, kwargs))
        return self._snapshot


def _v2_snap(chain_id=1):
    return V2PoolSnapshot(
        pool_id=USDC_WETH_V2,
        token0_name="USDC",
        token1_name="WETH",
        reserve0=2_000_000.0,
        reserve1=1_000.0,
        chain_id=chain_id,
    )


def _v3_snap(chain_id=1):
    return V3PoolSnapshot(
        pool_id=USDC_WETH_V3,
        token0_name="USDC",
        token1_name="WETH",
        reserve0=2_000_000.0,
        reserve1=1_000.0,
        fee=500,
        tick_spacing=10,
        chain_id=chain_id,
    )


@pytest.fixture
def patch_provider(monkeypatch):
    def _install(snapshot):
        fake = FakeProvider(snapshot)
        monkeypatch.setattr(server, "_make_provider", lambda rpc_url: fake)
        return fake
    return _install


def _call(name, args):
    return asyncio.run(server.call_tool(name, args))


def _text(result):
    return result[0].text


# ─── Enumeration / schema shape ─────────────────────────────────────────────


def test_enumerates_exactly_five_tools():
    schemas = server._wrap_schemas_with_pool_identity()
    names = sorted(s["name"] for s in schemas)
    assert names == sorted(server.TOOL_NAMES)
    assert len(names) == 5


def test_identity_fields_injected_and_required():
    for s in server._wrap_schemas_with_pool_identity():
        props = s["inputSchema"]["properties"]
        required = s["inputSchema"]["required"]
        for key in ("pool_address", "rpc_url", "pool_type"):
            assert key in props
            assert key in required
        assert props["pool_type"]["enum"] == ["uniswap_v2", "uniswap_v3"]
        # Recipe pool_id must be gone.
        assert "pool_id" not in props


def test_slippage_exposes_token_name_string():
    schema = next(s for s in server._wrap_schemas_with_pool_identity()
                  if s["name"] == "CalculateSlippage")
    props = schema["inputSchema"]["properties"]
    assert props["token_in_name"]["type"] == "string"
    assert "token_in_name" in schema["inputSchema"]["required"]


def test_build_server_registers_handlers():
    srv = server.build_server()
    assert srv.name == "defimind"


# ─── Dispatch (fake provider, real builder + primitives) ────────────────────


def test_check_pool_health_v2(patch_provider):
    patch_provider(_v2_snap())
    out = _call("CheckPoolHealth", {
        "pool_address": USDC_WETH_V2, "rpc_url": "http://fake",
        "pool_type": "uniswap_v2",
    })
    payload = json.loads(_text(out))
    assert "tvl_in_token0" in payload


def test_check_pool_health_v3(patch_provider):
    patch_provider(_v3_snap())
    out = _call("CheckPoolHealth", {
        "pool_address": USDC_WETH_V3, "rpc_url": "http://fake",
        "pool_type": "uniswap_v3",
    })
    payload = json.loads(_text(out))
    assert "tvl_in_token0" in payload


def test_calculate_slippage_v2_resolves_token(patch_provider):
    patch_provider(_v2_snap())
    out = _call("CalculateSlippage", {
        "pool_address": USDC_WETH_V2, "rpc_url": "http://fake",
        "pool_type": "uniswap_v2", "amount_in": 1000.0,
        "token_in_name": "USDC",
    })
    payload = json.loads(_text(out))
    assert "slippage_pct" in payload


def test_calculate_slippage_v3_defaults_ticks(patch_provider):
    # V3 slippage with no caller ticks must not break: dispatch defaults
    # lwr_tick/upr_tick to the snapshot's full range before the primitive.
    snap = _v3_snap()
    patch_provider(snap)
    out = _call("CalculateSlippage", {
        "pool_address": USDC_WETH_V3, "rpc_url": "http://fake",
        "pool_type": "uniswap_v3", "amount_in": 1000.0,
        "token_in_name": "USDC",
    })
    payload = json.loads(_text(out))
    assert "slippage_pct" in payload
    # Sanity: snapshot carries concrete full-range ticks to default from.
    assert snap.lwr_tick is not None and snap.upr_tick is not None


def test_block_number_passed_to_snapshot(patch_provider):
    fake = patch_provider(_v2_snap())
    _call("CheckPoolHealth", {
        "pool_address": USDC_WETH_V2, "rpc_url": "http://fake",
        "pool_type": "uniswap_v2", "block_number": 19_500_000,
    })
    assert fake.calls[0][1] == {"block_number": 19_500_000}


# ─── Error paths ────────────────────────────────────────────────────────────


def test_bad_pool_type():
    out = _call("CheckPoolHealth", {
        "pool_address": "0xabc", "rpc_url": "http://fake",
        "pool_type": "sushiswap",
    })
    assert "must be one of" in _text(out)


def test_missing_required_args():
    out = _call("CheckPoolHealth", {"pool_type": "uniswap_v2"})
    assert "required" in _text(out).lower()


def test_unknown_tool():
    out = _call("AnalyzeBalancerPosition", {
        "pool_address": "0xabc", "rpc_url": "http://fake",
        "pool_type": "uniswap_v2",
    })
    assert "Unknown tool" in _text(out)


def test_chain_id_mismatch(patch_provider):
    patch_provider(_v2_snap(chain_id=8453))  # RPC reports Base
    out = _call("CheckPoolHealth", {
        "pool_address": USDC_WETH_V2, "rpc_url": "http://fake",
        "pool_type": "uniswap_v2", "chain_id": 1,
    })
    assert "chain_id" in _text(out)


def test_unresolvable_token_errors(patch_provider):
    patch_provider(_v2_snap())
    out = _call("CalculateSlippage", {
        "pool_address": USDC_WETH_V2, "rpc_url": "http://fake",
        "pool_type": "uniswap_v2", "amount_in": 1000.0,
        "token_in_name": "NOPE",
    })
    assert "not found" in _text(out)


def test_unreachable_rpc_is_structured(monkeypatch):
    class Boom:
        def snapshot(self, *a, **k):
            raise ConnectionError("RPC unreachable")
    monkeypatch.setattr(server, "_make_provider", lambda rpc_url: Boom())
    out = _call("CheckPoolHealth", {
        "pool_address": "0xabc", "rpc_url": "http://dead",
        "pool_type": "uniswap_v2",
    })
    assert "Error reading pool" in _text(out)


def test_rpc_key_scrubbed_from_error_message(monkeypatch, capsys):
    secret = "https://eth-mainnet.example/v2/SECRET_KEY_123"

    class Leaky:
        def snapshot(self, *a, **k):
            # web3/urllib echo the full URL (incl. the key) in their text.
            raise ConnectionError(
                "Max retries exceeded with url: /v2/SECRET_KEY_123 "
                "(host='eth-mainnet.example')")
    monkeypatch.setattr(server, "_make_provider", lambda rpc_url: Leaky())
    out = _call("CheckPoolHealth", {
        "pool_address": "0xabc", "rpc_url": secret,
        "pool_type": "uniswap_v2",
    })
    # Neither the client-facing error nor the stderr receipt may leak the key.
    assert "SECRET_KEY_123" not in _text(out)
    assert "SECRET_KEY_123" not in capsys.readouterr().err


# ─── Receipt redaction ──────────────────────────────────────────────────────


def test_rpc_url_redacted_in_receipt(patch_provider, capsys):
    patch_provider(_v2_snap())
    secret = "https://eth-mainnet.example/v2/SECRET_KEY"
    _call("CheckPoolHealth", {
        "pool_address": USDC_WETH_V2, "rpc_url": secret,
        "pool_type": "uniswap_v2",
    })
    err = capsys.readouterr().err
    assert "SECRET_KEY" not in err
    assert "<redacted>" in err
