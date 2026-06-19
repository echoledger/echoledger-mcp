# ─────────────────────────────────────────────────────────────────────────────
# Apache 2.0 License (DeFiMind MCP)
# ─────────────────────────────────────────────────────────────────────────────
# Copyright 2026 Ian Moore / DeFiMind Inc.
#
# Adapted from DeFiPy's stdio MCP server (python/mcp/defipy_mcp_server.py),
# Copyright 2023–2026 Ian Moore, Apache-2.0. See NOTICE.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""DeFiMind MCP server — 10 live LP analytics tools over HTTP.

Covers Uniswap V2/V3, Balancer V2 weighted (2-asset), and Curve plain
Stableswap (2-asset) pools. Lifted and adapted from DeFiPy's stdio
MockProvider MCP server. Four changes from that source:

  1. Subset to the 10 LiveProvider-compatible tools (the full curated
     DeFiPy registry: 5 Uniswap V2/V3 tools + 3 Balancer/Stableswap
     position tools + Balancer/Stableswap price-move + depeg-risk).
  2. Input model: a recipe `pool_id` enum is replaced with live pool
     identity — `pool_address`, `rpc_url` (caller's, BYO-RPC),
     `pool_type` (uniswap_v2 | uniswap_v3 | balancer | stableswap), and
     optional `chain_id` guard + `block_number` pin.
  3. Provider: MockProvider recipes → `LiveProvider(rpc_url).snapshot()`.
  4. Transport: stdio → streamable HTTP (CORS, bound to $PORT).

Protocol scope (honest limits, surfaced in the tool descriptions):
the Balancer tools handle 2-asset weighted pools (3-asset raises
upstream); the Stableswap tools handle 2-asset plain Curve pools
(rate-bearing pools — metapools, LSD — are upstream v2.3). A
`balancer`/`stableswap` tool pointed at an out-of-scope pool fails
cleanly (the upstream snapshot/primitive raises; dispatch scrubs the
RPC from the message and returns a structured error, never a stack
trace). Per-tool protocol gating (`_TOOL_POOL_TYPES`) rejects an
obvious mismatch — e.g. AssessDepegRisk on a uniswap_v2 pool — before
any chain read.

Statelessness is preserved exactly: a fresh `LiveProvider` + twin is
built per call; nothing is cached or held between requests. One JSON
receipt per invocation goes to stderr — and the caller's `rpc_url`
(which carries their key) is redacted from it. The endpoint stores and
logs nothing else.

V3 modeling caveat
------------------
The V3 twin is built from a **full-range active-liquidity** snapshot
(the LiveProvider default). Caller-supplied `lwr_tick`/`upr_tick` are
*position*-range arguments passed straight to the primitive — they
describe the position being analyzed, not a re-scoping of the pool
snapshot. When the caller omits them on a V3 tool that accepts them,
they default to the snapshot's full range (so V3 slippage/position
calls work out of the box at full range). Concentrated-liquidity reads
beyond the active range (tick-bitmap walking) are deferred upstream to
DeFiPy (active-liquidity only). So V3 position analysis assumes the
supplied range against a full-range twin.
"""

import contextlib
import copy
import json
import os
import sys
import time
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone

from mcp.server import Server
from mcp.types import Tool, TextContent

from defipy.tools import TOOL_REGISTRY, get_schemas
from defipy.twin import LiveProvider, StateTwinBuilder


# ─── Tool subset + dispatch config ───────────────────────────────────────────

# The full 10-tool curated DeFiPy registry, all composing with the
# LiveProvider. The first 5 are Uniswap V2/V3; the last 5 are the
# Balancer/Stableswap tools that DeFiPy 2.2 unblocked (v0.2 surface
# expansion). This must equal the DeFiPy registry's curated set.
TOOL_NAMES = (
    "AnalyzePosition",
    "SimulatePriceMove",
    "CheckPoolHealth",
    "DetectRugSignals",
    "CalculateSlippage",
    "AnalyzeBalancerPosition",
    "SimulateBalancerPriceMove",
    "AnalyzeStableswapPosition",
    "SimulateStableswapPriceMove",
    "AssessDepegRisk",
)

# Supported live pool types (LiveProvider pool_id protocol prefixes).
# Each must match a DeFiPy 2.2 LiveProvider prefix exactly — the dispatch
# builds the snapshot id as "{pool_type}:{pool_address}".
POOL_TYPES = ("uniswap_v2", "uniswap_v3", "balancer", "stableswap")

# Per-tool protocol gating. Each tool is protocol-specific: the Uniswap
# tools only make sense on uniswap_v2/v3, the Balancer tools on balancer,
# the Stableswap tools on stableswap. A tool+pool_type mismatch is
# rejected with a clean IncompatiblePoolType error before any chain read
# (mirrors the MockProvider server's _COMPATIBLE_RECIPES gate, keyed by
# pool_type family instead of recipe name).
_TOOL_POOL_TYPES = {
    "AnalyzePosition":             {"uniswap_v2", "uniswap_v3"},
    "SimulatePriceMove":          {"uniswap_v2", "uniswap_v3"},
    "CheckPoolHealth":            {"uniswap_v2", "uniswap_v3"},
    "DetectRugSignals":           {"uniswap_v2", "uniswap_v3"},
    "CalculateSlippage":          {"uniswap_v2", "uniswap_v3"},
    "AnalyzeBalancerPosition":    {"balancer"},
    "SimulateBalancerPriceMove":  {"balancer"},
    "AnalyzeStableswapPosition":  {"stableswap"},
    "SimulateStableswapPriceMove": {"stableswap"},
    "AssessDepegRisk":            {"stableswap"},
}

# Args consumed by the dispatch layer to build the live twin. Stripped
# from the LLM's arguments before the primitive is invoked.
IDENTITY_KEYS = frozenset(
    {"pool_address", "rpc_url", "pool_type", "chain_id", "block_number"}
)

# Tools with an ERC20 parameter the LLM specifies as a token-name string.
# Maps tool name → (schema-arg-name, primitive-arg-name). The named token
# is resolved to an ERC20 at dispatch time via _resolve_token.
#   - CalculateSlippage.token_in_name is REQUIRED (which token is bought).
#   - AssessDepegRisk.depeg_token_name is OPTIONAL: which asset is assumed
#     to depeg; when omitted, dispatch defaults it to the pool's first
#     token so the tool works out of the box (see call_tool). The upstream
#     primitive requires a depeg_token ERC20, but the registry schema
#     leaves it dispatch-supplied (required = ["lp_init_amt"]).
_TOKEN_ARG_RENAMES = {
    "CalculateSlippage": ("token_in_name", "token_in"),
    "AssessDepegRisk": ("depeg_token_name", "depeg_token"),
}

# Renamed token args that are required of the LLM (vs. dispatch-defaulted).
_REQUIRED_TOKEN_ARGS = frozenset({"CalculateSlippage"})

_BUILDER = StateTwinBuilder()


def _make_provider(rpc_url: str):
    """Provider factory seam. Production returns a live, chain-reading
    provider; tests monkeypatch this to inject a fake provider that
    yields hand-built snapshots (no web3, no network)."""
    return LiveProvider(rpc_url)


# ─── Schema wrapping ─────────────────────────────────────────────────────────


def _wrap_schemas_with_pool_identity() -> list[dict]:
    """Subset to the 10 registry tools and inject live pool-identity fields
    onto each tool's inputSchema, replacing the MockProvider recipe
    `pool_id` enum."""
    wrapped = []
    for s in get_schemas("mcp"):
        if s["name"] not in TOOL_NAMES:
            continue
        w = copy.deepcopy(s)
        tool_name = w["name"]
        props = w["inputSchema"].setdefault("properties", {})
        required = w["inputSchema"].setdefault("required", [])

        props["pool_address"] = {
            "type": "string",
            "description": (
                "On-chain address of the pool/pair to analyze (Uniswap V2/V3 "
                "pair, Balancer weighted pool, or Curve stableswap pool). "
                "Required. Lowercase, uppercase, or checksum casing all work."
            ),
        }
        props["rpc_url"] = {
            "type": "string",
            "description": (
                "An Ethereum (or L2) JSON-RPC URL used to read live pool "
                "state. Required; supplied by you per call (BYO-RPC) and may "
                "carry your provider key. The endpoint stores and logs "
                "nothing — the URL is never persisted or written to logs."
            ),
        }
        props["pool_type"] = {
            "type": "string",
            "enum": list(POOL_TYPES),
            "description": (
                "Which protocol the pool address belongs to: 'uniswap_v2' | "
                "'uniswap_v3' | 'balancer' (2-asset weighted pool) | "
                "'stableswap' (2-asset plain Curve pool). Must match the tool: "
                "the position/price/health/rug/slippage Uniswap tools take "
                "uniswap_v2|uniswap_v3; the Balancer tools take balancer; the "
                "Stableswap/depeg tools take stableswap."
            ),
        }
        props["chain_id"] = {
            "type": "integer",
            "description": (
                "Optional guard. If supplied and the RPC reports a different "
                "chain id, the call is rejected. Defaults to 1 (Ethereum "
                "mainnet) conceptually; omit to skip the check."
            ),
        }
        props["block_number"] = {
            "type": "integer",
            "description": (
                "Optional block number to pin the read to a historical "
                "block. Omit to read the latest block."
            ),
        }
        for key in ("pool_address", "rpc_url", "pool_type"):
            if key not in required:
                required.append(key)

        # Tools with an ERC20 parameter exposed to the LLM as a token-name
        # string. CalculateSlippage.token_in_name is required; AssessDepegRisk
        # .depeg_token_name is optional (defaults to the pool's first token).
        if tool_name in _TOKEN_ARG_RENAMES:
            schema_name, _primitive_name = _TOKEN_ARG_RENAMES[tool_name]
            if tool_name == "AssessDepegRisk":
                desc = (
                    "Optional. Symbol of the asset assumed to depeg (e.g. "
                    "'USDC', 'DAI'). Must be one of the two tokens in the "
                    "pool. If omitted, the pool's first token is used."
                )
            else:
                desc = (
                    "Symbol of the input token for the trade (e.g. 'USDC', "
                    "'WETH'). Must be one of the two tokens in the pool."
                )
            props[schema_name] = {"type": "string", "description": desc}
            if tool_name in _REQUIRED_TOKEN_ARGS and schema_name not in required:
                required.append(schema_name)

        wrapped.append(w)
    return wrapped


# ─── Token resolution ────────────────────────────────────────────────────────


def _resolve_token(lp, token_name: str):
    """Resolve a token-name string to the ERC20 object the primitive expects.
    Works unchanged against a live-built V2/V3 twin (factory path)."""
    factory = getattr(lp, "factory", None)
    if factory is not None and hasattr(factory, "token_from_exchange"):
        tokens = factory.token_from_exchange.get(lp.name, {})
        if token_name in tokens:
            return tokens[token_name]

    vault = getattr(lp, "vault", None)
    if vault is not None and hasattr(vault, "get_token"):
        if token_name in vault.get_names():
            return vault.get_token(token_name)

    raise ValueError(
        "Token {!r} not found in pool. Available: {}".format(
            token_name, _list_pool_tokens(lp)
        )
    )


def _list_pool_tokens(lp) -> list[str]:
    factory = getattr(lp, "factory", None)
    if factory is not None and hasattr(factory, "token_from_exchange"):
        return sorted(factory.token_from_exchange.get(lp.name, {}).keys())
    vault = getattr(lp, "vault", None)
    if vault is not None and hasattr(vault, "get_names"):
        return list(vault.get_names())
    return []


# ─── Receipt logging ─────────────────────────────────────────────────────────


def _redact(args: dict) -> dict:
    """Strip the caller's RPC URL (carries their key) before logging."""
    safe = dict(args)
    if "rpc_url" in safe:
        safe["rpc_url"] = "<redacted>"
    return safe


def _scrub_secrets(text: str, rpc_url) -> str:
    """Remove any trace of the caller's RPC URL from free-text error
    messages. web3/urllib exceptions echo the URL — including the key in
    its path/host — so redacting only the `args` field isn't enough. We
    blank the full URL and each of its components (path carries the key,
    netloc can carry it in a subdomain or userinfo)."""
    if not text or not rpc_url:
        return text
    from urllib.parse import urlparse
    parts = {str(rpc_url)}
    try:
        u = urlparse(str(rpc_url))
        for p in (u.path, u.query, u.params, u.netloc, u.hostname):
            if p:
                parts.add(p)
        if u.path:
            seg = u.path.rstrip("/").rsplit("/", 1)[-1]
            if seg:
                parts.add(seg)
    except Exception:
        pass
    out = text
    for p in sorted((p for p in parts if p), key=len, reverse=True):
        out = out.replace(p, "<redacted-rpc>")
    return out


def _log_receipt(tool_name: str, pool_ref: str, args: dict,
                 status: str, duration_ms: float,
                 result_summary: str = "",
                 error_type: str = "", error_message: str = "") -> None:
    event = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "tool": tool_name,
        "pool": pool_ref,
        "args": _redact(args),
        "status": status,
        "duration_ms": round(duration_ms, 2),
    }
    if status == "ok":
        event["result_summary"] = result_summary
    else:
        event["error_type"] = error_type
        event["error_message"] = error_message
    print(json.dumps(event, ensure_ascii=True, default=str),
          file=sys.stderr, flush=True)


# ─── Result summarization ────────────────────────────────────────────────────


def _fmt_opt(v, spec=".4f"):
    if v is None:
        return "None"
    try:
        return format(v, spec)
    except (TypeError, ValueError):
        return str(v)


_SUMMARIZERS = {
    "AnalyzePosition": lambda r: (
        "diagnosis={}, net_pnl={}".format(r.diagnosis, _fmt_opt(r.net_pnl))
    ),
    "SimulatePriceMove": lambda r: (
        "new_value={}, il={}, value_change_pct={}".format(
            _fmt_opt(r.new_value), _fmt_opt(r.il_at_new_price),
            _fmt_opt(r.value_change_pct)
        )
    ),
    "CheckPoolHealth": lambda r: (
        "tvl={}, num_lps={}, has_activity={}".format(
            _fmt_opt(r.tvl_in_token0, ".2f"), r.num_lps, r.has_activity
        )
    ),
    "DetectRugSignals": lambda r: (
        "risk={}, signals={}".format(r.risk_level, r.signals_detected)
    ),
    "CalculateSlippage": lambda r: (
        "slippage_pct={}, price_impact_pct={}, max_at_1pct={}".format(
            _fmt_opt(r.slippage_pct), _fmt_opt(r.price_impact_pct),
            _fmt_opt(r.max_size_at_1pct, ".2f")
        )
    ),
    "AnalyzeBalancerPosition": lambda r: (
        "diagnosis={}, net_pnl={}, alpha={}".format(
            r.diagnosis, _fmt_opt(r.net_pnl), _fmt_opt(r.alpha)
        )
    ),
    "SimulateBalancerPriceMove": lambda r: (
        "new_value={}, il={}, new_price_ratio={}".format(
            _fmt_opt(r.new_value), _fmt_opt(r.il_at_new_price),
            _fmt_opt(r.new_price_ratio)
        )
    ),
    "AnalyzeStableswapPosition": lambda r: (
        "diagnosis={}, il_pct={}, alpha={}".format(
            r.diagnosis, _fmt_opt(r.il_percentage), _fmt_opt(r.alpha)
        )
    ),
    "SimulateStableswapPriceMove": lambda r: (
        "new_value={}, il={}, new_price_ratio={}".format(
            _fmt_opt(r.new_value), _fmt_opt(r.il_at_new_price),
            _fmt_opt(r.new_price_ratio)
        )
    ),
    "AssessDepegRisk": lambda r: (
        "n_scenarios={}, current_dev={}".format(
            len(r.scenarios), _fmt_opt(r.current_peg_deviation)
        )
    ),
}


def _summarize(tool_name: str, result) -> str:
    fn = _SUMMARIZERS.get(tool_name)
    if fn is None:
        return "<no summarizer for {}>".format(tool_name)
    try:
        return fn(result)
    except Exception as e:
        return "<summarizer error: {}>".format(e)


def _serialize_result(result) -> str:
    payload = asdict(result) if is_dataclass(result) else result
    return json.dumps(payload, indent=2, default=str)


# ─── Core dispatch ───────────────────────────────────────────────────────────


def _err(name, pool_ref, args, t0, exc_type, msg, prefix="Error"):
    _log_receipt(name, pool_ref, args, "error", (time.monotonic() - t0) * 1000,
                 error_type=exc_type, error_message=msg)
    return [TextContent(type="text", text="{}: {}".format(prefix, msg))]


async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Dispatch a single tool invocation against live chain state. Separable
    from the transport loop so tests can exercise it directly."""

    t0 = time.monotonic()
    arguments = dict(arguments or {})
    pool_address = arguments.get("pool_address", "")
    pool_type = arguments.get("pool_type", "")
    pool_ref = "{}:{}".format(pool_type or "?", pool_address or "?")

    # Unknown / unsupported tool.
    if name not in TOOL_NAMES or name not in TOOL_REGISTRY:
        return _err(name, pool_ref, arguments, t0, "UnknownTool",
                    "Unknown tool: {}".format(name))

    # Required identity present + valid pool_type.
    rpc_url = arguments.get("rpc_url")
    if not pool_address or not rpc_url or not pool_type:
        return _err(name, pool_ref, arguments, t0, "MissingArgument",
                    "pool_address, rpc_url, and pool_type are all required.")
    if pool_type not in POOL_TYPES:
        return _err(name, pool_ref, arguments, t0, "BadPoolType",
                    "pool_type {!r} must be one of {}.".format(
                        pool_type, list(POOL_TYPES)))

    # Per-tool protocol gate: reject an obvious tool+pool_type mismatch
    # (e.g. AssessDepegRisk on a uniswap_v2 pool) before any chain read,
    # so the LLM gets a clean error instead of a confusing upstream crash.
    compatible = _TOOL_POOL_TYPES.get(name, set())
    if pool_type not in compatible:
        return _err(name, pool_ref, arguments, t0, "IncompatiblePoolType",
                    "Tool {!r} is not compatible with pool_type {!r}. "
                    "Compatible pool types: {}.".format(
                        name, pool_type, sorted(compatible)))

    declared_chain_id = arguments.get("chain_id")
    block_number = arguments.get("block_number")

    # Build a fresh live twin per call (stateless contract).
    snap_kwargs = {}
    if block_number is not None:
        snap_kwargs["block_number"] = block_number
    try:
        provider = _make_provider(rpc_url)
        snap = provider.snapshot(
            "{}:{}".format(pool_type, pool_address), **snap_kwargs)
    except Exception as e:
        return _err(name, pool_ref, arguments, t0, type(e).__name__,
                    _scrub_secrets("Failed to read pool state: {}".format(e),
                                   rpc_url),
                    prefix="Error reading pool")

    # chain_id guard — catches an RPC pointed at the wrong chain.
    snap_chain_id = getattr(snap, "chain_id", None)
    if (declared_chain_id is not None and snap_chain_id is not None
            and int(declared_chain_id) != int(snap_chain_id)):
        return _err(name, pool_ref, arguments, t0, "ChainMismatch",
                    "declared chain_id {} but the RPC reports {}.".format(
                        declared_chain_id, snap_chain_id))

    try:
        lp = _BUILDER.build(snap)
    except Exception as e:
        return _err(name, pool_ref, arguments, t0, type(e).__name__,
                    _scrub_secrets("Failed to build twin: {}".format(e),
                                   rpc_url),
                    prefix="Error building twin")

    # Primitive args = everything that isn't pool identity.
    primitive_args = {k: v for k, v in arguments.items()
                      if k not in IDENTITY_KEYS}

    # Resolve the token-name string to an ERC20 the primitive expects.
    # CalculateSlippage.token_in is required (the LLM names it). AssessDepegRisk
    # .depeg_token is dispatch-supplied: use the caller's depeg_token_name if
    # given, else default to the pool's first token so the tool works without
    # the LLM having to choose (the V3-tick-default philosophy, applied to the
    # depeg asset). Either way the upstream primitive gets a concrete ERC20.
    if name in _TOKEN_ARG_RENAMES:
        schema_name, primitive_name = _TOKEN_ARG_RENAMES[name]
        token_name = primitive_args.pop(schema_name, None)
        if token_name is None and name == "AssessDepegRisk":
            pool_tokens = _list_pool_tokens(lp)
            token_name = pool_tokens[0] if pool_tokens else None
        if token_name is not None:
            try:
                primitive_args[primitive_name] = _resolve_token(lp, token_name)
            except Exception as e:
                return _err(name, pool_ref, arguments, t0, type(e).__name__,
                            _scrub_secrets(str(e), rpc_url),
                            prefix="Error resolving token")

    # V3 full-range default. The position/slippage primitives take
    # lwr_tick/upr_tick and feed them into V3 tick math that can't accept
    # None. When the caller omits them, default to the snapshot's range —
    # which is the pool's full active-liquidity range (the documented V3
    # default). Only applied to tools that actually accept ticks, so
    # pool-level tools (CheckPoolHealth/DetectRugSignals) are untouched.
    if pool_type == "uniswap_v3":
        sig = TOOL_REGISTRY[name].signature_params
        for tick in ("lwr_tick", "upr_tick"):
            if tick in sig and primitive_args.get(tick) is None:
                primitive_args[tick] = getattr(snap, tick, None)

    # Invoke the primitive.
    try:
        result = TOOL_REGISTRY[name].primitive_cls().apply(lp, **primitive_args)
    except Exception as e:
        return _err(name, pool_ref, arguments, t0, type(e).__name__,
                    _scrub_secrets(str(e), rpc_url))

    _log_receipt(name, pool_ref, arguments, "ok",
                 (time.monotonic() - t0) * 1000,
                 result_summary=_summarize(name, result))
    return [TextContent(type="text", text=_serialize_result(result))]


# ─── Server init ─────────────────────────────────────────────────────────────


def build_server() -> Server:
    """Configure the low-level MCP server with list_tools + call_tool."""
    server = Server("defimind", version="0.2.0")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(name=s["name"], description=s["description"],
                 inputSchema=s["inputSchema"])
            for s in _wrap_schemas_with_pool_identity()
        ]

    @server.call_tool()
    async def handle_call(name: str, arguments: dict) -> list[TextContent]:
        return await call_tool(name, arguments)

    return server


# ─── Transport: streamable HTTP ──────────────────────────────────────────────


def create_app():
    """Build the streamable-HTTP ASGI app serving the MCP endpoint at /mcp.

    The MCP session manager is mounted at the root ("/"), not at "/mcp".
    A `Mount("/mcp", ...)` makes Starlette 307-redirect a bare `/mcp` to
    `/mcp/`; behind a TLS-terminating proxy (Railway/Cloudflare) that
    Location also downgrades to http://, which can fail Smithery's scan
    and break strict clients. Mounting at root means `/mcp` (and `/mcp/`)
    reach the session manager directly with no redirect — the manager
    handles the MCP protocol independent of path. `/health` is matched
    first, so it stays a plain JSON route.
    """
    from starlette.applications import Starlette
    from starlette.routing import Mount, Route
    from starlette.responses import JSONResponse
    from starlette.middleware.cors import CORSMiddleware
    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

    server = build_server()
    session_manager = StreamableHTTPSessionManager(app=server, stateless=True)

    async def handle_mcp(scope, receive, send):
        await session_manager.handle_request(scope, receive, send)

    async def health(_request):
        return JSONResponse({"status": "ok", "tools": list(TOOL_NAMES)})

    @contextlib.asynccontextmanager
    async def lifespan(_app):
        async with session_manager.run():
            yield

    app = Starlette(
        routes=[
            Route("/health", health, methods=["GET"]),
            Mount("/", app=handle_mcp),
        ],
        lifespan=lifespan,
    )
    return CORSMiddleware(
        app,
        allow_origins=["*"],
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["mcp-session-id"],
    )


def run_http():
    """Entry point: serve the streamable-HTTP app on $PORT (default 8080)."""
    import uvicorn
    port = int(os.environ.get("PORT", "8080"))
    host = os.environ.get("HOST", "0.0.0.0")
    # Trust X-Forwarded-* from the TLS-terminating proxy (Railway/Cloudflare)
    # so the app sees scheme=https and never builds http:// redirect URLs.
    uvicorn.run(create_app(), host=host, port=port,
                proxy_headers=True, forwarded_allow_ips="*")


async def run_stdio():
    """Optional stdio entry point for local MCP Inspector smoke-tests."""
    from mcp.server.stdio import stdio_server
    server = build_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream,
                         server.create_initialization_options())


if __name__ == "__main__":
    if "--stdio" in sys.argv:
        import asyncio
        asyncio.run(run_stdio())
    else:
        run_http()
