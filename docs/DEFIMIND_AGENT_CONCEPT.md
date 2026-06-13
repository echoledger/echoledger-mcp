# DeFiMind Agent — Concept & Build Notes

*Status: **concept, unbuilt.** Brainstorm capture, not a build spec. Captures the
`defimind-agent` idea, its reasoning "modes," build best-practices, and the
adoption thesis behind it. Decisions here are provisional; the discipline is
work-drives-research — build the minimal version first, let real usage settle
the rest.*

*Captured: June 13, 2026 — same day DeFiMind MCP went live (`mcp.defimind.ai`,
Smithery + registry.modelcontextprotocol.io listed, defimind.ai/mcp).*

---

## 1. What `defimind-agent` is (and is not)

**It is:** a forkable **reference application** — a *remote client* of the
hosted DeFiMind MCP endpoint (`https://mcp.defimind.ai/mcp`). Someone clones it,
points it at their own RPC and a pool watchlist, runs it, and it calls the five
DeFiMind tools over HTTP. The analytics run **on DeFiMind's server**, not theirs.

**The full provenance chain, stated plainly:**
`defimind-agent` (reference client) → calls the **DeFiMind MCP endpoint**
(`mcp.defimind.ai`) → which is backed by **defipy's State Twins** concept (the
State Twin substrate: a stateless, snapshot-once / branch-many model of live AMM
state). The agent and the endpoint are the **DeFiMind** brand layer; State Twins
and defipy are the **substrate** beneath them. The agent never touches the
substrate directly — it consumes it through the hosted endpoint, which is exactly
how a third-party builder would. So every call the agent makes is leveraging
years of defipy / State Twins work via the productized DeFiMind surface.

**It is not:**
- **Not a Python package.** Nobody `pip install`s it to get analytics. It is a
  thing you *clone and run*, not a dependency you import.
- **Not a defipy consumer.** It must **not** `import defipy`. If it did, it would
  be a local defipy script, which defeats the entire point. It talks to the
  *hosted* endpoint exactly as a third-party builder's agent would. Keeping it a
  thin remote client is what makes it a faithful reference for the product.
- **Not a `defimind` package either.** There is no `defimind` Python package and
  there should not be. defipy = open substrate; DeFiMind = hosted product +
  practice. The agent is a *demo of the product*, so it lives in its own repo,
  e.g. `defimind-ai/defimind-agent` — outside both defipy and the MCP server.

### The core strategic fact

When a shop clones and runs `defimind-agent`, **every analysis it performs is a
call to `mcp.defimind.ai`.** The repo is free; the value it produces only works
by hitting the endpoint. So the agent is not the thing being given away — it is a
**distribution mechanism for repeated calls to the API.** Open-sourcing the
on-ramp, not the value. This is the whole reason the agent matters: it converts a
free artifact into standing, repeated, metered usage of DeFiMind infrastructure —
which is the usage that the ranking, the citable-artifact story, and ultimately
cashflow all depend on.

---

## 2. Reasoning "modes"

A useful way to frame the agent: each **mode is a distinct question-shape asked of
the State Twin**, and the twin's *snapshot-once / branch-many* property is what
makes each one cheap and internally consistent.

| Mode | Question | Tools | One-liner |
|---|---|---|---|
| **Counterfactual** | "What happens if…" | `SimulatePriceMove` | One position, sweep hypothetical futures (price moves, range, entry timing) over a fixed twin. |
| **Ensemble / distribution** | "What's the *shape* of the risk" | `SimulatePriceMove` ×N | Same sweep, aggregated into a distribution — expected IL, tail risk, prob-of-loss. Monte-Carlo-over-twin. *(Counterfactual is its degenerate single-path case.)* |
| **Monitoring** | "Tell me when something changes" | `CheckPoolHealth`, `DetectRugSignals` | Same question, repeated on a schedule against fresh snapshots; alert on drift / threshold crossings. |
| **Screening** | "Which of these is safe / attractive" | `CheckPoolHealth`, `DetectRugSignals`, `CalculateSlippage` | One question across *many* pools at a point in time, ranked. Pre-entry due diligence at portfolio scale. |
| **Comparative** | "Where should this liquidity live" | `Analyze*`, `Simulate*` | Same position evaluated across pool types (V2 vs V3 range vs Curve), reconciled. |

### The insight worth keeping

**These modes are the four consulting SKUs re-expressed as agent reasoning
patterns.** Counterfactual + ensemble ≈ *LP Position Audit* risk decomposition;
screening ≈ *Pool Health & Rug Risk*; comparative-across-a-book ≈ *DAO Treasury
Review*. The agent is therefore not a side project — it is the **automated
analytical core of the practice**. The free agent funnels calls; the endpoint
meters them; the SKUs convert the serious ones.

### Guardrails on the mode taxonomy (read before extending it)

- **Modes are discovered by building, not designed up front.** Ship *one*
  (monitoring), let a real user wanting screening tell you mode #2 is real. A
  five-mode framework with zero users is the failure mode. Do not ship the
  taxonomy ahead of the artifact.
- **"Ensemble" has three meanings — only some are real.** Ensemble-over-*scenarios*
  (distribution over counterfactual paths) is the strong, distinctive one and is
  uniquely enabled by stateless consistent twins. Ensemble-over-*models* (V2/V3/
  Balancer/Curve as views) is real but narrower. Ensemble-*of-agents* (multiple
  LLM reasoners voting) is **probably noise** for a quant analytics endpoint —
  adds cost, not signal. The value is the *computed distribution*, not a vote.
- The genuinely fresh, defensible concept: **an agent that uses the State Twin as
  a consistent branch point for a distribution of counterfactual futures, and
  reasons over the outcome distribution rather than a point estimate.** A normal
  RPC-bound tool can't do this cheaply without hammering the chain or losing
  cross-read consistency. If this proves out once built, it is a *State Twins
  follow-on paper*, named after the artifact exists — not before.

---

## 3. Build best-practices

### The standard you needed was MCP — and it's already adopted

The relevant interop standard is **MCP itself, which the server already speaks.**
Because the ecosystem standardized on MCP, every agent framework (LangGraph,
Pydantic AI, Mastra, OpenAI Agents SDK, Claude Agent SDK, …) consumes the
DeFiMind tools natively, and tool integrations port almost trivially between
frameworks. **Consequence: framework choice is the *forker's*, not yours.** You
do not pick a framework "for the ecosystem" — yours works with all of them.

### Two artifacts, two jobs — don't make one carry both

1. **Reference / on-ramp (build first): framework-*less*.** A plain MCP client +
   a scheduled loop. Its job is to be *read in five minutes and copied*. A heavy
   framework here is a liability — it makes the reference harder to read and
   couples your demo to a dependency the forker may not use. For a reference,
   minimal **is** the standard. Expose the integration plainly; hide nothing.
2. **Flagship *running* agent (optional, later): pick one framework.** If you
   want a production agent that publicly does the monitoring-and-catches-things
   demo, build *that one* on **Pydantic AI** (Python-first, type-safe, structured
   outputs — natural fit given the dataclass outputs the tools already return) or
   **LangGraph** (the default for stateful / scheduled / durable workflows). The
   bare reference teaches the integration; the framework-based one shows
   production-grade orchestration.

> Note from the MCP-SDK landscape: the MCP server SDK is the right starting point
> for *server* work and the wrong starting point for a production *agent* — you'll
> reach for an orchestration framework within the first sprint. That split is
> exactly why the reference stays thin and any flagship gets a real framework.

### Other practices

- **BYO-RPC, remote-first.** The agent supplies the caller's own RPC per call and
  connects to the hosted endpoint over HTTP. No local analytics, no defipy import.
- **Minimal dependencies in the reference.** Copyability dies with dependencies.
- **Config over code:** RPC, watchlist, thresholds, schedule in config — so a
  forker changes those, not the source.
- **Make the README a 10-minute path:** clone → set RPC → set pools → run → see
  your pools analyzed. The README is the conversion surface.

---

## 4. Adoption thesis

**The agent exists to create usage; usage is the live constraint** (cashflow is
downstream of usage; credibility is largely banked via the ethereum.org defipy
listing).

### Why cold proposals are the weakest path

A proposal asks a shop to read it, *believe* an unverified value claim, and spend
eng time — all before experiencing anything. Talk is the cheapest signal, so it's
the most discounted. (DefiLlama states this directly: their filter is "did you
ship something useful," not "did you describe something.") A proposal is *you*
asserting value; adoption happens when *they* experience it.

### What actually works — artifact, then demonstrated use, then narrow outreach

1. **Build the artifact** so the value is self-evident and zero-activation-energy
   to experience: a forkable agent that runs on real data and visibly catches
   real things (a rug signal, an IL blowout) on known pools, posted publicly.
2. **Demonstrated use travels:** someone sees the public result → clones the repo
   → points it at their pools → wires the pattern into their own system → tells
   someone. None of these steps is a cold proposal.
3. **Then** targeted, researched outreach to the specific shops the demo has
   effectively pre-qualified — the warm/narrow-outreach instinct, not a broadcast.

**Order: build → demonstrate → narrow outreach. Never cold-proposal-first.** A
"proposal" is, at most, a thin link wrapped around a working artifact. If you have
the artifact you barely need the proposal; if you don't, the proposal can't
substitute for it.

### Likely first callers: builders and agents, not human prompters

Realistically the people who add a DeFi analytics MCP *and* have a live RPC are
developers wiring it into something, or agents/systems making repeated scheduled
calls — not casual desktop prompters. So the worked example should target
**builders**: "here's the config and the exact call, drop it in your agent,"
not "ask Claude about your LP position."

### Keep separate from the DefiLlama (or any) job application

A reference agent submitted as a job-application artifact conflates DeFiMind (the
independent practice) with employment exploration — two paths deliberately kept
separate. If pursuing a role somewhere, contribute to *their* repo the way they
ask; build `defimind-agent` for DeFiMind. Don't fuse them — it halves the impact
of each.

---

## 5. The decision that "they're using my API" forces

The endpoint is currently **authless + BYO-RPC**. The agent makes the trade-off
concrete and it is *the* seam between usage and cashflow:

- **You bear the compute.** Forkers' calls run on DeFiMind's Railway container
  (their RPC, your CPU). Trivial at launch and exactly what frictionless adoption
  wants; a knob to watch at scale.
- **Authless = invisible usage.** A shop can run the endpoint forever and you
  never know they exist. Great for adoption, bad for lead-gen — you can't offer
  the deeper paid work to a heavy user you can't see.
- **The loop:** free agent (funnel) → repeated calls (meter) → SKUs (conversion).
  Converting "usage" → "cashflow" probably wants **optional identification** — a
  *free* API key that grants visibility into who's calling, without auth that
  blocks anyone. Encourage identification; don't require it. **Decide this
  deliberately before the agent ships**, because the agent is what populates it.

---

## 6. Open decisions (resolve by building, not up front)

- **Language of the reference:** Python (home turf, ecosystem fit) vs TypeScript
  (larger pool of agent/automation builders; mirrors the `ar-mcp` Workers
  precedent). Follows from *which builders you want cloning it first*.
- **Reference app vs installable thin client lib:** a clone-and-run app (teaches
  the integration) vs a small `defimind-client` wrapper a shop imports into *their*
  agent (two-line wire-in). Different adopters; both still funnel calls, neither
  puts analytics on their machine. Possibly both, eventually.
- **Auth/visibility seam:** authless-for-adoption vs free-key-for-visibility (§5).
- **Flagship framework (if/when):** Pydantic AI vs LangGraph (§3).

---

## 7. Next concrete step

Build the **minimal monitoring reference**: `defimind-ai/defimind-agent`, a
framework-less, thin remote MCP client (BYO-RPC, no defipy import) that watches a
few pools and calls the tools on a schedule, with a README that makes
clone→run→result a 10-minute path. It doubles as the substance of a public
weekly-analysis post.

Everything else in this doc is concept space around that one artifact. Build the
one thing; let real usage reveal which mode, which framework, and which seam
matter next.
