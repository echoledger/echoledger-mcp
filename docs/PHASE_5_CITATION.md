# Phase 5 — Citable Artifact (Zenodo DOI)

*defimind-mcp v0.1 build. Master plan: `DEFIMIND_MCP_EXECUTION_PLAN.md`. Execute via Claude Code.*

**Objective:** Turn the endpoint into a Scholar-visible, citable artifact: a tagged release + a Zenodo DOI that cites the State Twins paper, with `CITATION.cff` finalized. This is the lever that points the listing back at the paper and drives citations.

**Preconditions:** Phase 4 published (server live on the official registry).

## Steps

1. **Tag the release.** Cut `v0.1.0` on `defimind-ai/defimind-mcp` (GitHub release).

2. **Zenodo archival.** Enable the GitHub ↔ Zenodo integration for the repo (or upload the release artifact manually); the release mints a DOI. In the Zenodo deposition metadata:
   - authors, title ("DeFiMind MCP"), license **Apache-2.0**;
   - add the **State Twins** paper (arXiv 2605.11522) as a **related identifier** (`cites` / `isSupplementTo`) — this is the citation linkage that does the work.

3. **Finalize `CITATION.cff`.** Uncomment / add the minted `doi:` (and an `identifiers:` entry), keep the State Twins paper under `references`. Confirm GitHub's **"Cite this repository"** button renders from the file.

4. **Cross-link.** Add the DOI badge to the README. (Referencing the DOI from defimind.ai's research section is a separate-repo edit — note it for later, don't do it here; brand hygiene + repo boundary.)

## Gate
DOI minted and live; `CITATION.cff` carries both the Zenodo DOI and the arXiv reference; "Cite this repository" renders; DOI badge in README.

## Out of scope
OIDC release-automation that auto-publishes `server.json` on tag (v0.2 polish); any defimind.ai website edits.

## Handoff — v0.1 complete
The endpoint is live, listed (Smithery + official registry + aggregators), and citable. **Next cycle (v0.2):** Balancer/Stableswap live tools when defipy 2.2 ships their LiveProviders (expanding 5 → 10); plus the optional OCI-package listing, DNS-verified `ai.defimind/*` namespace, and OIDC auto-publish. Tracked in the master plan's "v0.2 horizon".
