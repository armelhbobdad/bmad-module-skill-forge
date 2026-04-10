# Roadmap

Future work planned for Skill Forge. Items here are directional, not scheduled. Layered items ship when their trigger conditions are met, not on a timeline.

**North-star principle for workspace/infrastructure work:** *The workspace is an optimization, never a gate.* Every failure path degrades gracefully to the existing ephemeral behavior.

---

## Persistent Workspace (`~/.skf/workspace/`)

A shared, system-level cache of git clones and their tool indexes, replacing per-forge ephemeral cloning. Designed as four layers that ship independently when real usage proves the need.

### Layer 0 — Core Workspace *(current)*

Persistent clones + CCC indexes preserved across forges, projects, and sessions. Zero new dependencies. Lazy creation on first remote forge. Always falls back to ephemeral on any failure.

### Layer 1 — Registry Intelligence *(triggered)*

Ship when real users cache 5+ repos, disk complaints arrive, concurrent forge failures surface, or users start asking "what's in my workspace?" Scope: `registry.json` with `schema_version`, staleness thresholds, disk budget + LRU eviction, PID-based locking, CLI (`skf workspace list/remove/clean/migrate`), cross-platform hardening (Windows long paths, case-sensitivity detection, file-lock retry), and recovery paths (self-healing registry, git health check, auth-failure degradation).

### Layer 2 — Tool Tenants *(triggered)*

Ship when Layer 1 is stable and a target tool meets the **Tool Maturity Gate**: versioned schema, 6+ months of releases, no critical security fixes in the last 3 months, deletion handling in incremental updates, and Linux/macOS/Windows support. Tools persist outputs inside repo checkouts (`.cocoindex_code/`, `graphify-out/`, etc.); the registry's extensible `tools` section tracks per-tool state without tool-specific code.

### Layer 3 — Cross-Repo Intelligence *(triggered)*

Ship when Layer 2 graphify (or alternative) integration is proven AND a graph-merging API exists. Scope: merge per-repo graphs into a unified stack graph, Leiden community detection across repos for architectural layers, forge intelligence prompts ("you've forged N skills from this repo, here are unexplored communities"), stack-skill drift detection at the relationship level, and workspace-level QMD collections.

---

## Graphify Upstream Contribution

Partner with [safishamsi/graphify](https://github.com/safishamsi/graphify) (MIT, 16.6k stars) to mature it into a viable Layer 2 tenant. SKF commits to contributing upstream rather than forking.

**P0 blockers for Layer 2 integration:**
- Schema versioning for `graph.json` (currently unversioned)
- File deletion handling in `--update` (ghost nodes persist after deletes)
- Full Windows support across build/query/watch/MCP server

**P1 blockers for Layer 3 integration:**
- Graph merging API (CLI or Python) for cross-repo unified graphs
- Stable, documented Python API for programmatic consumption
- Shallow-clone compatibility validation

Backup candidates if graphify stalls: GitNexus (watching for MIT relicense), CodeGraphContext (MIT, 2.2k stars), CodeGraph-Rust.

---

## Spec Sync Mechanism

Pending an upstream agentskills.io spec endpoint. SKF currently version-pins to an agentskills.io spec at release time; once upstream publishes a canonical endpoint, SKF will add a sync path — likely a maintainer-side release script, not a runtime CLI flag.
