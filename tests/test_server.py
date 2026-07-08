"""Phase 1 tests for the EchoLedger MCP server.

Strategy: the live-RPC seam (`_make_provider`) is monkeypatched to a
fake provider that returns hand-built V2/V3 snapshot dataclasses. The
*real* StateTwinBuilder and the *real* defipy primitives then run, so
dispatch / identity-stripping / token-resolution / chain-guard / receipt
logic is exercised end-to-end with no web3 and no network.

The live-RPC gate (CheckPoolHealth + CalculateSlippage against real
mainnet V2 and V3 pools) lives in test_live.py and is skipped unless
ECHOLEDGER_TEST_RPC_URL is set.
"""

import asyncio
import json
import math

import pytest

from defipy.twin import StateTwinBuilder
from defipy.twin import snapshot as snapshot_module
from defipy.twin.snapshot import (
    V2PoolSnapshot, V3PoolSnapshot, BalancerPoolSnapshot, StableswapPoolSnapshot,
)
from echoledger_mcp import server


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


# A real mainnet-shaped Balancer 50/50 ETH/DAI pool and a 2-coin USDC/DAI
# plain Stableswap pool — reserves synthetic, only a coherent snapshot is
# needed. (The live-gate fixtures in test_live.py use real on-chain pools:
# BAL/WETH 80/20 and the crvUSD/USDC 2-coin pool.)
ETH_DAI_BALANCER = "0x0000000000000000000000000000000000bal5050"
USDC_DAI_STABLESWAP = "0x00000000000000000000000000000000005wapa10"


def _balancer_snap(chain_id=1):
    return BalancerPoolSnapshot(
        pool_id=ETH_DAI_BALANCER,
        token0_name="ETH",
        token1_name="DAI",
        reserve0=1_000.0,
        reserve1=100_000.0,
        weight0=0.5,
        weight1=0.5,
        pool_shares_init=100.0,
        chain_id=chain_id,
    )


def _stableswap_snap(chain_id=1):
    return StableswapPoolSnapshot(
        pool_id=USDC_DAI_STABLESWAP,
        token_names=["USDC", "DAI"],
        reserves=[100_000.0, 100_000.0],
        A=10,
        decimals=18,
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


def test_enumerates_all_ten_tools():
    schemas = server._wrap_schemas_with_pool_identity()
    names = sorted(s["name"] for s in schemas)
    # Exposed names are the public aliases (registry names stay canonical).
    expected = sorted(server._public_name(n) for n in server.TOOL_NAMES)
    assert names == expected
    assert len(names) == 10
    # The 5 v0.2 Balancer/Stableswap tools are all present (public names).
    assert {"AnalyzeBalancerLP", "SimulateBalancerMove",
            "AnalyzeStableswapLP", "SimulateStableswapMove",
            "AssessDepegRisk"}.issubset(set(names))


def test_exposed_names_fit_namespaced_64_char_limit():
    # Regression: claude.ai (and similar clients) prefix-namespace tool
    # names and cap the combined name at 64 chars. SimulateStableswapPriceMove
    # (27) overflowed and blocked the whole connector. Keep exposed names
    # short enough that even a ~40-char client prefix stays under 64.
    names = [s["name"] for s in server._wrap_schemas_with_pool_identity()]
    longest = max(names, key=len)
    assert len(longest) <= 22, "{} is {} chars".format(longest, len(longest))
    assert "SimulateStableswapPriceMove" not in names  # the offending name


def test_public_alias_and_canonical_both_dispatch(patch_provider):
    # call_tool must accept the short public alias AND the original registry
    # name (back-compat for any caller using the old name).
    for name in ("SimulateStableswapMove", "SimulateStableswapPriceMove"):
        patch_provider(_stableswap_snap())
        out = json.loads(_text(_call(name, {
            "pool_address": USDC_DAI_STABLESWAP, "rpc_url": "http://fake",
            "pool_type": "stableswap",
            "price_change_pct": -0.02, "lp_init_amt": 100.0,
        })))
        assert out["token_names"] == ["USDC", "DAI"]


def test_identity_fields_injected_and_required():
    for s in server._wrap_schemas_with_pool_identity():
        props = s["inputSchema"]["properties"]
        required = s["inputSchema"]["required"]
        for key in ("pool_address", "rpc_url", "pool_type"):
            assert key in props
            assert key in required
        # SPEC 1.1: pool_type is per-tool now — it advertises EXACTLY the
        # values that tool accepts, not the full four-value union. Each enum
        # must be non-empty and match the tool's accepted set.
        registry_name = server._to_registry_name(s["name"])
        assert props["pool_type"]["enum"] == \
            server._accepted_pool_types(registry_name)
        assert props["pool_type"]["enum"], s["name"]
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
    assert srv.name == "echoledger"


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


# ─── Task A: dispatch coverage for the 3 previously-uninvoked tools ──────────
# AnalyzePosition / SimulatePriceMove / DetectRugSignals were enumeration-only.
# Invoke each through real dispatch + real builder + real primitive (V2 and V3
# where ticks apply) and assert the primitive's key output fields.

# Position basis consistent with the synthetic reserves (token0:token1 = 2000:1).
_POS = {"lp_init_amt": 100.0, "entry_x_amt": 4000.0, "entry_y_amt": 2.0}


def test_analyze_position_v2(patch_provider):
    patch_provider(_v2_snap())
    out = json.loads(_text(_call("AnalyzePosition", {
        "pool_address": USDC_WETH_V2, "rpc_url": "http://fake",
        "pool_type": "uniswap_v2", **_POS})))
    assert isinstance(out["net_pnl"], (int, float))
    assert isinstance(out["il_percentage"], (int, float))
    assert out["diagnosis"] in {"net_positive", "fee_compensated", "il_dominant"}


def test_analyze_position_v3(patch_provider):
    # V3 with no caller ticks: dispatch defaults to the snapshot full range.
    patch_provider(_v3_snap())
    out = json.loads(_text(_call("AnalyzePosition", {
        "pool_address": USDC_WETH_V3, "rpc_url": "http://fake",
        "pool_type": "uniswap_v3", **_POS})))
    assert isinstance(out["net_pnl"], (int, float))
    assert isinstance(out["il_percentage"], (int, float))
    assert out["diagnosis"] in {"net_positive", "fee_compensated", "il_dominant"}


def test_simulate_price_move_v2_anchors_to_il_formula(patch_provider):
    patch_provider(_v2_snap())
    out = json.loads(_text(_call("SimulatePriceMove", {
        "pool_address": USDC_WETH_V2, "rpc_url": "http://fake",
        "pool_type": "uniswap_v2", "price_change_pct": 0.30,
        "position_size_lp": 100.0})))
    assert isinstance(out["new_value"], (int, float))
    assert isinstance(out["value_change_pct"], (int, float))
    # Absolute parity anchor: V2 IL is the classic 2*sqrt(a)/(1+a)-1 closed
    # form. For a +30% move (alpha=1.30) that is ~-0.0085431.
    expected = 2 * math.sqrt(1.30) / (1 + 1.30) - 1
    assert out["il_at_new_price"] == pytest.approx(expected, abs=1e-6)


def test_simulate_price_move_v3(patch_provider):
    # V3 full-range default path produces a coherent scenario.
    patch_provider(_v3_snap())
    out = json.loads(_text(_call("SimulatePriceMove", {
        "pool_address": USDC_WETH_V3, "rpc_url": "http://fake",
        "pool_type": "uniswap_v3", "price_change_pct": 0.30,
        "position_size_lp": 100.0})))
    assert isinstance(out["new_value"], (int, float))
    assert isinstance(out["il_at_new_price"], (int, float))
    assert isinstance(out["value_change_pct"], (int, float))
    assert out["il_at_new_price"] <= 0.0  # IL is a loss for any alpha != 1


def test_detect_rug_signals_v2(patch_provider):
    patch_provider(_v2_snap())
    out = json.loads(_text(_call("DetectRugSignals", {
        "pool_address": USDC_WETH_V2, "rpc_url": "http://fake",
        "pool_type": "uniswap_v2"})))
    assert out["risk_level"] in {"low", "medium", "high", "critical"}
    assert isinstance(out["signals_detected"], int)
    assert 0 <= out["signals_detected"] <= 3


def test_detect_rug_signals_v3(patch_provider):
    patch_provider(_v3_snap())
    out = json.loads(_text(_call("DetectRugSignals", {
        "pool_address": USDC_WETH_V3, "rpc_url": "http://fake",
        "pool_type": "uniswap_v3"})))
    assert out["risk_level"] in {"low", "medium", "high", "critical"}
    assert isinstance(out["signals_detected"], int)


# ─── Task B: V3 concentrated-liquidity IL differential (the diagnostic) ──────


def test_v3_il_differential_tight_vs_full(patch_provider):
    """A narrow tick band must amplify IL for a given move vs full range.

    Proves caller-supplied lwr_tick/upr_tick actually reach the V3 IL math
    (UniswapImpLoss.calc_price_range -> scale = sqrt(r)/(sqrt(r)-1)).
    Diagnostic: if TIGHT does not materially exceed FULL, the ticks aren't
    engaging the concentrated-IL path — a real bug, not a test to relax.
    """
    snap = _v3_snap()
    # Read the built twin's current tick so the band straddles current price.
    cur_tick = StateTwinBuilder().build(snap).slot0.tick
    patch_provider(snap)

    base = {"pool_address": USDC_WETH_V3, "rpc_url": "http://fake",
            "pool_type": "uniswap_v3", "price_change_pct": 0.30,
            "position_size_lp": 100.0}

    full = json.loads(_text(_call("SimulatePriceMove", dict(base))))

    # Tight band: +/-4000 ticks around current, snapped to spacing 10. The
    # +30% move is ~2624 ticks, so the post-move price stays inside the band.
    sp = 10
    lwr = ((cur_tick - 4000) // sp) * sp
    upr = ((cur_tick + 4000) // sp) * sp
    tight = json.loads(_text(_call("SimulatePriceMove",
                       {**base, "lwr_tick": lwr, "upr_tick": upr})))

    il_full = abs(full["il_at_new_price"])
    il_tight = abs(tight["il_at_new_price"])

    # Concentrated liquidity amplifies IL. Observed ~26x; require a clear
    # multiple (>3x), not a rounding-level difference.
    assert il_tight > 3 * il_full, (
        "tight-band IL must materially exceed full-range IL; "
        "got tight={} full={}".format(
            tight["il_at_new_price"], full["il_at_new_price"]))

    # Full-range V3 collapses to the V2 closed-form IL for this move — the
    # scale factor goes to ~1 when the band spans the whole price axis.
    expected_v2 = abs(2 * math.sqrt(1.30) / (1 + 1.30) - 1)
    assert il_full == pytest.approx(expected_v2, abs=1e-6)


# ─── v0.2: Balancer + Stableswap dispatch (fake provider, real primitives) ───
# Each of the 5 new tools dispatches through real builder + real primitive
# against a hand-built Balancer/Stableswap snapshot, and returns the expected
# result dataclass. Mirrors the V2/V3 coverage above for the new pool types.


def test_analyze_balancer_position(patch_provider):
    patch_provider(_balancer_snap())
    out = json.loads(_text(_call("AnalyzeBalancerPosition", {
        "pool_address": ETH_DAI_BALANCER, "rpc_url": "http://fake",
        "pool_type": "balancer",
        "lp_init_amt": 10.0, "entry_base_amt": 100.0, "entry_opp_amt": 10_000.0,
    })))
    assert out["base_tkn_name"] == "ETH"
    assert out["base_weight"] == 0.5
    assert isinstance(out["net_pnl"], (int, float))
    assert out["diagnosis"] in {"net_positive", "fee_compensated", "il_dominant"}


def test_simulate_balancer_price_move(patch_provider):
    patch_provider(_balancer_snap())
    out = json.loads(_text(_call("SimulateBalancerPriceMove", {
        "pool_address": ETH_DAI_BALANCER, "rpc_url": "http://fake",
        "pool_type": "balancer",
        "price_change_pct": -0.30, "lp_init_amt": 10.0,
    })))
    assert isinstance(out["new_value"], (int, float))
    assert isinstance(out["il_at_new_price"], (int, float))
    assert out["il_at_new_price"] <= 0.0  # IL is a loss for any move
    assert out["new_price_ratio"] == pytest.approx(0.70, abs=1e-9)


def test_analyze_stableswap_position(patch_provider):
    patch_provider(_stableswap_snap())
    out = json.loads(_text(_call("AnalyzeStableswapPosition", {
        "pool_address": USDC_DAI_STABLESWAP, "rpc_url": "http://fake",
        "pool_type": "stableswap",
        "lp_init_amt": 100.0, "entry_amounts": [100.0, 100.0],
    })))
    assert out["token_names"] == ["USDC", "DAI"]
    assert out["A"] == 10
    assert "il_percentage" in out
    assert isinstance(out["diagnosis"], str)


def test_simulate_stableswap_price_move(patch_provider):
    # At A=10 a small (-2%) shock is reachable, so fields are populated.
    patch_provider(_stableswap_snap())
    out = json.loads(_text(_call("SimulateStableswapPriceMove", {
        "pool_address": USDC_DAI_STABLESWAP, "rpc_url": "http://fake",
        "pool_type": "stableswap",
        "price_change_pct": -0.02, "lp_init_amt": 100.0,
    })))
    assert out["token_names"] == ["USDC", "DAI"]
    assert "new_value" in out and "il_at_new_price" in out
    assert out["new_price_ratio"] == pytest.approx(0.98, abs=1e-9)


def test_assess_depeg_risk(patch_provider):
    patch_provider(_stableswap_snap())
    out = json.loads(_text(_call("AssessDepegRisk", {
        "pool_address": USDC_DAI_STABLESWAP, "rpc_url": "http://fake",
        "pool_type": "stableswap",
        "lp_init_amt": 100.0, "depeg_token_name": "USDC",
    })))
    assert out["depeg_token"] == "USDC"
    assert out["protocol_type"] == "stableswap"
    assert out["n_assets"] == 2
    assert len(out["scenarios"]) == 5
    assert out["current_peg_deviation"] is not None


def test_assess_depeg_risk_defaults_token(patch_provider):
    # depeg_token_name is optional; dispatch must supply the pool's first
    # token so the upstream primitive (which requires a depeg_token ERC20)
    # still runs. Without a default this would crash on a missing arg.
    snap = _stableswap_snap()
    patch_provider(snap)
    out = json.loads(_text(_call("AssessDepegRisk", {
        "pool_address": USDC_DAI_STABLESWAP, "rpc_url": "http://fake",
        "pool_type": "stableswap", "lp_init_amt": 100.0,
    })))
    # Resolves to one of the pool's two tokens (the vault's first).
    assert out["depeg_token"] in {"USDC", "DAI"}
    assert len(out["scenarios"]) == 5


def test_incompatible_pool_type_is_rejected(patch_provider):
    # A stableswap-only tool pointed at a uniswap_v2 pool must fail with a
    # clean IncompatiblePoolType error BEFORE any chain read (no snapshot).
    fake = patch_provider(_v2_snap())
    out = _call("AssessDepegRisk", {
        "pool_address": USDC_WETH_V2, "rpc_url": "http://fake",
        "pool_type": "uniswap_v2", "lp_init_amt": 100.0,
    })
    assert "not compatible" in _text(out)
    assert "stableswap" in _text(out)
    assert fake.calls == []  # gated before the provider was ever called


def test_balancer_tool_rejects_stableswap_pool(patch_provider):
    fake = patch_provider(_stableswap_snap())
    out = _call("AnalyzeBalancerPosition", {
        "pool_address": USDC_DAI_STABLESWAP, "rpc_url": "http://fake",
        "pool_type": "stableswap",
        "lp_init_amt": 10.0, "entry_base_amt": 1.0, "entry_opp_amt": 1.0,
    })
    assert "not compatible" in _text(out)
    assert "balancer" in _text(out)
    assert fake.calls == []


# ─── SPEC 1.1: pool_type routing is honest (advertised == accepted) ──────────
# The advertised pool_type enum on each tool must list ONLY the values that
# tool actually accepts, and an unsupported value must be rejected cleanly
# (no chain read, no stack trace) naming the accepted values.

# Independent source of truth for the expected per-tool enums (the SPEC 1.1
# table), keyed by exposed public name. Hardcoded on purpose so this catches
# drift in _TOOL_POOL_TYPES rather than re-deriving from it.
_EXPECTED_POOL_TYPE_ENUMS = {
    "AnalyzePosition":        ["uniswap_v2", "uniswap_v3"],
    "SimulatePriceMove":      ["uniswap_v2", "uniswap_v3"],
    "CheckPoolHealth":        ["uniswap_v2", "uniswap_v3"],
    "DetectRugSignals":       ["uniswap_v2", "uniswap_v3"],
    "CalculateSlippage":      ["uniswap_v2", "uniswap_v3"],
    "AnalyzeBalancerLP":      ["balancer"],
    "SimulateBalancerMove":   ["balancer"],
    "AnalyzeStableswapLP":    ["stableswap"],
    "SimulateStableswapMove": ["stableswap"],
    "AssessDepegRisk":        ["stableswap"],
}


def test_advertised_pool_type_enum_matches_accepted_per_tool():
    schemas = {s["name"]: s for s in server._wrap_schemas_with_pool_identity()}
    # Every exposed tool is covered by the expectation table, and vice versa.
    assert set(schemas) == set(_EXPECTED_POOL_TYPE_ENUMS)
    for name, expected in _EXPECTED_POOL_TYPE_ENUMS.items():
        enum = schemas[name]["inputSchema"]["properties"]["pool_type"]["enum"]
        assert enum == expected, "{}: advertised {} != accepted {}".format(
            name, enum, expected)
        # Single-type tools must pin (one value); none may advertise the
        # full four-value union any more.
        assert len(enum) < 4


# One unsupported pool_type per tool — paired so each is a VALID protocol
# (hits the per-tool IncompatiblePoolType gate, not the BadPoolType path).
_UNSUPPORTED_CASES = [
    ("AnalyzePosition", "balancer"),
    ("SimulatePriceMove", "stableswap"),
    ("CheckPoolHealth", "balancer"),
    ("DetectRugSignals", "stableswap"),
    ("CalculateSlippage", "balancer"),
    ("AnalyzeBalancerLP", "uniswap_v2"),
    ("SimulateBalancerMove", "stableswap"),
    ("AnalyzeStableswapLP", "uniswap_v3"),
    ("SimulateStableswapMove", "balancer"),
    ("AssessDepegRisk", "uniswap_v2"),
]


@pytest.mark.parametrize("tool_name,bad_type", _UNSUPPORTED_CASES)
def test_unsupported_pool_type_rejected_per_tool(patch_provider, tool_name,
                                                 bad_type):
    # A supported value is exercised per tool elsewhere; here we assert every
    # tool rejects an unsupported (but valid) pool_type with a clean
    # IncompatiblePoolType error BEFORE any chain read, naming the accepted
    # values — never a runtime crash.
    fake = patch_provider(_v2_snap())
    out = _text(_call(tool_name, {
        "pool_address": "0xabc", "rpc_url": "http://fake",
        "pool_type": bad_type,
    }))
    assert "not compatible" in out
    registry_name = server._to_registry_name(tool_name)
    for accepted in server._accepted_pool_types(registry_name):
        assert accepted in out
    assert bad_type not in server._accepted_pool_types(registry_name)
    assert fake.calls == []  # gated before the provider was ever called


# ─── SPEC 1.2: vectorized scenario inputs ────────────────────────────────────
# Scenario-shaped tools accept an array alongside their scalar: one twin build,
# one result per entry, returned in input order. The scalar stays accepted
# (back-compat); supplying both is rejected; over-length fails fast (no RPC).

# (public tool, snap factory, pool_type, pool_addr, scalar, vector, scalar_val,
#  vec_vals, extra primitive args)
_VECTOR_CASES = [
    ("SimulatePriceMove", _v2_snap, "uniswap_v2", USDC_WETH_V2,
     "price_change_pct", "price_change_pcts", -0.30, [-0.30, -0.10, 0.20],
     {"position_size_lp": 100.0}),
    ("CalculateSlippage", _v2_snap, "uniswap_v2", USDC_WETH_V2,
     "amount_in", "amounts_in", 1000.0, [1000.0, 5000.0, 10_000.0],
     {"token_in_name": "USDC"}),
    ("SimulateBalancerMove", _balancer_snap, "balancer", ETH_DAI_BALANCER,
     "price_change_pct", "price_change_pcts", -0.30, [-0.30, -0.10, 0.20],
     {"lp_init_amt": 10.0}),
    ("SimulateStableswapMove", _stableswap_snap, "stableswap",
     USDC_DAI_STABLESWAP, "price_change_pct", "price_change_pcts",
     -0.02, [-0.02, -0.01, 0.01], {"lp_init_amt": 100.0}),
]
_VECTOR_IDS = [c[0] for c in _VECTOR_CASES]


def _vector_base(pool_type, pool_addr):
    return {"pool_address": pool_addr, "rpc_url": "http://fake",
            "pool_type": pool_type}


def test_vector_schema_shape():
    schemas = {s["name"]: s for s in server._wrap_schemas_with_pool_identity()}
    for (tool, _snap, _pt, _addr, scalar, vector, *_rest) in _VECTOR_CASES:
        sch = schemas[tool]["inputSchema"]
        prop = sch["properties"][vector]
        assert prop["type"] == "array"
        assert prop["items"]["type"] == "number"
        assert prop["maxItems"] == server._MAX_VECTOR_LEN
        # Scalar still advertised, but no longer required (either/or now).
        assert scalar in sch["properties"]
        assert scalar not in sch["required"], tool
    # AssessDepegRisk's depeg_levels stays array-exposed (native vector input).
    adr = schemas["AssessDepegRisk"]["inputSchema"]["properties"]["depeg_levels"]
    assert "array" in adr["type"]


@pytest.mark.parametrize(
    "tool,snap_fn,pool_type,pool_addr,scalar,vector,scalar_val,vec_vals,extra",
    _VECTOR_CASES, ids=_VECTOR_IDS)
def test_vector_scalar_single_multi(patch_provider, tool, snap_fn, pool_type,
                                    pool_addr, scalar, vector, scalar_val,
                                    vec_vals, extra):
    base = _vector_base(pool_type, pool_addr)

    # Scalar (back-compat): a single result OBJECT, not an array.
    patch_provider(snap_fn())
    scalar_out = json.loads(_text(_call(
        tool, {**base, scalar: scalar_val, **extra})))
    assert isinstance(scalar_out, dict)

    # Single-element vector: an array of length 1 whose only entry equals the
    # scalar result for the same value (same primitive, same state).
    patch_provider(snap_fn())
    single_out = json.loads(_text(_call(
        tool, {**base, vector: [scalar_val], **extra})))
    assert isinstance(single_out, list) and len(single_out) == 1
    assert single_out[0] == scalar_out

    # Multi-element vector: an ordered array, one result per input.
    fake = patch_provider(snap_fn())
    multi_out = json.loads(_text(_call(
        tool, {**base, vector: vec_vals, **extra})))
    assert isinstance(multi_out, list)
    assert len(multi_out) == len(vec_vals)
    # Twin built exactly once regardless of vector length (one RPC read).
    assert len(fake.calls) == 1


@pytest.mark.parametrize(
    "tool,snap_fn,pool_type,pool_addr,scalar,vector,scalar_val,vec_vals,extra",
    _VECTOR_CASES, ids=_VECTOR_IDS)
def test_vector_order_preserved(patch_provider, tool, snap_fn, pool_type,
                                pool_addr, scalar, vector, scalar_val,
                                vec_vals, extra):
    # The i-th array entry must equal the scalar result computed for vec_vals[i].
    base = _vector_base(pool_type, pool_addr)
    patch_provider(snap_fn())
    multi = json.loads(_text(_call(tool, {**base, vector: vec_vals, **extra})))
    for i, v in enumerate(vec_vals):
        patch_provider(snap_fn())
        one = json.loads(_text(_call(tool, {**base, scalar: v, **extra})))
        assert multi[i] == one, "{}: entry {} out of order".format(tool, i)


def test_vector_both_supplied_rejected(patch_provider):
    fake = patch_provider(_v2_snap())
    out = _text(_call("SimulatePriceMove", {
        **_vector_base("uniswap_v2", USDC_WETH_V2),
        "price_change_pct": -0.1, "price_change_pcts": [-0.1, -0.2],
        "position_size_lp": 100.0}))
    assert "not both" in out
    assert fake.calls == []  # rejected before any chain read


def test_vector_neither_supplied_rejected(patch_provider):
    fake = patch_provider(_v2_snap())
    out = _text(_call("SimulatePriceMove", {
        **_vector_base("uniswap_v2", USDC_WETH_V2), "position_size_lp": 100.0}))
    assert "either" in out.lower()
    assert fake.calls == []


def test_vector_over_length_rejected_pre_rpc(patch_provider):
    # Over-length must fail fast with a clear error, not a timeout / no RPC.
    fake = patch_provider(_v2_snap())
    too_many = [0.0] * (server._MAX_VECTOR_LEN + 1)
    out = _text(_call("SimulatePriceMove", {
        **_vector_base("uniswap_v2", USDC_WETH_V2),
        "price_change_pcts": too_many, "position_size_lp": 100.0}))
    assert str(server._MAX_VECTOR_LEN) in out
    assert fake.calls == []


def test_vector_empty_and_nonnumeric_rejected(patch_provider):
    base = _vector_base("uniswap_v2", USDC_WETH_V2)
    fake = patch_provider(_v2_snap())
    empty = _text(_call("SimulatePriceMove", {
        **base, "price_change_pcts": [], "position_size_lp": 100.0}))
    assert "empty" in empty.lower()
    bad = _text(_call("SimulatePriceMove", {
        **base, "price_change_pcts": [0.1, "oops"], "position_size_lp": 100.0}))
    assert "number" in bad.lower()
    assert fake.calls == []  # both rejected pre-RPC


def test_max_vector_len_is_a_few_hundred():
    # Sanity on the cap: bounded but generous (SPEC 1.2 "a few hundred").
    assert 100 <= server._MAX_VECTOR_LEN <= 1000


def test_vector_v3_with_tick_defaults(patch_provider):
    # V3 + vector: dispatch defaults lwr/upr ticks once (full range, shared
    # across the sweep), then loops the scenario. One build, ordered array.
    fake = patch_provider(_v3_snap())
    out = json.loads(_text(_call("SimulatePriceMove", {
        "pool_address": USDC_WETH_V3, "rpc_url": "http://fake",
        "pool_type": "uniswap_v3",
        "price_change_pcts": [-0.20, 0.0, 0.30], "position_size_lp": 100.0})))
    assert isinstance(out, list) and len(out) == 3
    assert len(fake.calls) == 1                      # twin built once
    assert out[1]["new_price_ratio"] == pytest.approx(1.0)  # the 0.0 scenario


# ─── SPEC 1.3: BuildStateTwin (the 11th tool) ────────────────────────────────
# A managed-RPC twin oracle: reads chain once, serializes the PoolSnapshot to
# the wire form { "__type__", <fields>, "content_hash" } a client rehydrates
# locally. Spans all four pool types; no twin build, no primitive.

import hashlib  # noqa: E402  (local to the SPEC 1.3 block)


# (pool_type, snap factory, expected snapshot class name)
_TWIN_CASES = [
    ("uniswap_v2", _v2_snap, "V2PoolSnapshot"),
    ("uniswap_v3", _v3_snap, "V3PoolSnapshot"),
    ("balancer", _balancer_snap, "BalancerPoolSnapshot"),
    ("stableswap", _stableswap_snap, "StableswapPoolSnapshot"),
]
_TWIN_IDS = [c[0] for c in _TWIN_CASES]


def _twin_call(pool_type, **extra):
    return json.loads(_text(_call("BuildStateTwin", {
        "pool_address": "0xpool", "rpc_url": "http://fake",
        "pool_type": pool_type, **extra})))


def test_surface_has_eleven_tools_with_build_state_twin():
    names = [s["name"] for s in server._all_tool_schemas()]
    assert len(names) == 11
    assert "BuildStateTwin" in names
    bst = next(s for s in server._all_tool_schemas()
               if s["name"] == "BuildStateTwin")
    props = bst["inputSchema"]["properties"]
    # All four pool types are genuinely supported here (spans every snapshot).
    assert props["pool_type"]["enum"] == [
        "uniswap_v2", "uniswap_v3", "balancer", "stableswap"]
    for key in ("pool_address", "rpc_url", "pool_type"):
        assert key in bst["inputSchema"]["required"]
    # Tick params advertised (v3 position scope).
    assert "lwr_tick" in props and "upr_tick" in props


def test_build_state_twin_in_health():
    from starlette.testclient import TestClient
    with TestClient(server.create_app()) as client:
        tools = client.get("/health").json()["tools"]
    assert "BuildStateTwin" in tools
    assert len(tools) == 11


@pytest.mark.parametrize("pool_type,snap_fn,cls_name", _TWIN_CASES,
                         ids=_TWIN_IDS)
def test_build_state_twin_wire_format(patch_provider, pool_type, snap_fn,
                                      cls_name):
    snap = snap_fn()
    patch_provider(snap)
    twin = _twin_call(pool_type)

    # __type__ matches the actual snapshot class; protocol is the discriminator.
    assert twin["__type__"] == cls_name
    assert twin["protocol"] == pool_type

    # content_hash: 0x + 64 hex chars, recomputable from the canonical body
    # (everything except the __type__/content_hash envelope keys).
    assert twin["content_hash"].startswith("0x")
    assert len(twin["content_hash"]) == 66
    body = {k: v for k, v in twin.items()
            if k not in ("__type__", "content_hash")}
    recomputed = "0x" + hashlib.sha256(
        json.dumps(body, sort_keys=True).encode("utf-8")).hexdigest()
    assert recomputed == twin["content_hash"]

    # Round-trips through getattr(snapshot_module, __type__)(**body) back to an
    # equal snapshot (the 1.4 rehydration contract).
    rehydrated = getattr(snapshot_module, twin["__type__"])(**body)
    assert rehydrated == snap


def test_build_state_twin_hash_deterministic(patch_provider):
    # Identical pool state at the same block → identical content_hash.
    patch_provider(_v3_snap())
    h1 = _twin_call("uniswap_v3")["content_hash"]
    patch_provider(_v3_snap())
    h2 = _twin_call("uniswap_v3")["content_hash"]
    assert h1 == h2
    # Different state → different hash (sanity that the hash tracks the body).
    patch_provider(_v2_snap())
    assert _twin_call("uniswap_v2")["content_hash"] != h1


def test_build_state_twin_passes_pool_id_and_block(patch_provider):
    fake = patch_provider(_v2_snap())
    _twin_call("uniswap_v2", block_number=19_500_000)
    pool_id, kwargs = fake.calls[0]
    assert pool_id == "uniswap_v2:0xpool"        # "<protocol>:<address>"
    assert kwargs == {"block_number": 19_500_000}
    assert len(fake.calls) == 1                  # reads chain exactly once


def test_build_state_twin_forwards_v3_ticks(patch_provider):
    # V3: caller ticks reach LiveProvider.snapshot kwargs (position scope).
    fake = patch_provider(_v3_snap())
    _twin_call("uniswap_v3", lwr_tick=-120, upr_tick=120)
    _pid, kwargs = fake.calls[0]
    assert kwargs.get("lwr_tick") == -120 and kwargs.get("upr_tick") == 120


def test_build_state_twin_ignores_ticks_off_v3(patch_provider):
    # Ticks are uniswap_v3-only; for other types they're not forwarded.
    fake = patch_provider(_balancer_snap())
    _twin_call("balancer", lwr_tick=-120, upr_tick=120)
    _pid, kwargs = fake.calls[0]
    assert "lwr_tick" not in kwargs and "upr_tick" not in kwargs


def test_build_state_twin_bad_pool_type():
    out = _text(_call("BuildStateTwin", {
        "pool_address": "0xabc", "rpc_url": "http://fake",
        "pool_type": "sushiswap"}))
    assert "must be one of" in out


def test_build_state_twin_missing_args():
    out = _text(_call("BuildStateTwin", {"pool_type": "uniswap_v2"}))
    assert "required" in out.lower()


def test_build_state_twin_chain_id_mismatch(patch_provider):
    patch_provider(_v2_snap(chain_id=8453))  # RPC reports Base
    out = _text(_call("BuildStateTwin", {
        "pool_address": "0xpool", "rpc_url": "http://fake",
        "pool_type": "uniswap_v2", "chain_id": 1}))
    assert "chain_id" in out


def test_build_state_twin_rpc_scrubbed(monkeypatch, capsys):
    secret = "https://eth-mainnet.example/v2/TWIN_SECRET_42"

    class Leaky:
        def snapshot(self, *a, **k):
            raise ConnectionError(
                "Max retries with url: /v2/TWIN_SECRET_42 (host='x')")
    monkeypatch.setattr(server, "_make_provider", lambda rpc_url: Leaky())
    out = _text(_call("BuildStateTwin", {
        "pool_address": "0xabc", "rpc_url": secret,
        "pool_type": "uniswap_v2"}))
    assert "TWIN_SECRET_42" not in out
    assert "TWIN_SECRET_42" not in capsys.readouterr().err


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
    out = _call("NotARealTool", {
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


# ─── HTTP routing: /mcp must serve directly, no 307 redirect ─────────────────


def test_mcp_endpoint_does_not_redirect():
    """`/mcp` must be answered by the app directly, not 307-redirected to
    `/mcp/` (which behind a TLS proxy also downgrades the Location to http://
    and can fail Smithery's scan). Offline routing assertion — no network."""
    from starlette.testclient import TestClient

    with TestClient(server.create_app()) as client:
        # Accept: application/json (NOT text/event-stream) so the MCP manager
        # returns a fast 406 rather than opening a standing SSE stream.
        r = client.get("/mcp", headers={"accept": "application/json"},
                       follow_redirects=False)
        assert not (300 <= r.status_code < 400), (
            "/mcp must serve directly; got redirect {} -> {}".format(
                r.status_code, r.headers.get("location", "?")))
        assert r.status_code == 406  # reached the MCP session manager

        # /health is matched ahead of the root mount and still works.
        h = client.get("/health")
        assert h.status_code == 200
        assert h.json()["status"] == "ok"
