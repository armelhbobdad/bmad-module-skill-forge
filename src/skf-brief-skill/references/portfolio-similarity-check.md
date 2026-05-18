# Portfolio-Similarity Check

Loaded by step 1 §6 only when **all three** preconditions hold:

1. Forge tier is `Deep`
2. `tools.qmd` is true in `forge-tier.yaml`
3. The flow is interactive (the headless path skips this check entirely — it would either need to HALT on duplicates [over-aggressive for an automator] or silently log [no operator to act on it]; either choice has a side effect on the QMD index that is best avoided headlessly)

This check catches **semantic near-duplicates** that exact-name collision misses (e.g. `markdown-renderer` proposed when `marked` already exists, or `auth-gateway` when `auth-middleware` already exists). Exact-name collision is handled separately at §6 before this check runs.

## Procedure

The brief portfolio is already indexed in QMD collections — one `{skill-name}-brief` collection per existing brief, registered by step 5 §5 of every prior Deep-tier run. The qmd CLI does not support glob-style collection selection, so enumerate first then query per collection in **a single message with N parallel Bash calls**:

```bash
# 1. Enumerate brief collections (one per existing brief)
qmd collection list | awk '/-brief$/{print $1}'

# 2. For each collection, query the proposed name + intent text:
qmd query "{name} {synthesized-or-intent-text}" -c {collection-name} -n 1 --min-score 0.6
```

Aggregate the top hits across all `-brief` collections; keep the 3 highest-scoring across the union. If any results come back, surface them as a heads-up — *not* a HALT:

```
**Heads up — these existing briefs look semantically close to `{name}`:**
  1. {existing-name} (similarity: {score})  — {existing-description}
  2. {existing-name} (similarity: {score})  — {existing-description}

Continue with `{name}`, or pick a different name?
```

## Failure modes

On any QMD failure (binary missing, collection list empty, any per-collection query times out): log `"warn: portfolio-similarity check skipped — qmd query failed: {error}"` and continue silently — never HALT. Quick / Forge / Forge+ tiers do not run this check (qmd is Deep-tier-only per the canonical tier definition: `Deep = + ast-grep + gh + QMD` in `skf-forge-tier-rw.py`).
