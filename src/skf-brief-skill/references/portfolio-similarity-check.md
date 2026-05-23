# Portfolio-Similarity Check

Loaded by step 1 §6 only when **all three** preconditions hold:

1. Forge tier is `Deep`
2. `tools.qmd` is true in `forge-tier.yaml`
3. The flow is interactive (the headless path skips this check entirely — it would either need to HALT on duplicates [over-aggressive for an automator] or silently log [no operator to act on it]; either choice has a side effect on the QMD index that is best avoided headlessly)

This check catches **semantic near-duplicates** that exact-name collision misses (e.g. `markdown-renderer` proposed when `marked` already exists, or `auth-gateway` when `auth-middleware` already exists). Exact-name collision is handled separately at §6 before this check runs.

## Procedure

The brief portfolio is already indexed in QMD collections — one `{skill-name}-brief` collection per existing brief, registered by step 5 §5 of every prior Deep-tier run. The qmd CLI does not support glob-style collection selection, so enumerate first (capping the sweep), then query the capped set per collection in **bounded parallel batches (≈4 concurrent Bash calls at a time)** — each `qmd query` cold-starts an embedding model, so issuing all of them at once on a large portfolio thrashes memory and stalls:

```bash
# 1. Enumerate brief collections (one per existing brief), capping the sweep.
#    Match the first whitespace field, not the whole line: `qmd collection list`
#    rows end in a `(qmd://name/)` URI suffix, so a line-anchored `/-brief$/`
#    matches nothing and the check silently no-ops. The cap bounds wall-time and
#    concurrent model loads as the portfolio grows; `qmd collection list` has no
#    guaranteed recency order, so this caps total count, not "newest N".
qmd collection list | awk '$1 ~ /-brief$/ {print $1}' | head -n 12

# 2. For each capped collection, query the proposed name + intent text.
#    `timeout` bounds each cold model start so a slow qmd degrades instead of
#    hanging; a non-zero exit (124 = timed out) falls through to the
#    "times out → warn and continue" failure-mode branch below.
timeout 20 qmd query "{name} {synthesized-or-intent-text}" -c {collection-name} -n 1 --min-score 0.6
```

Aggregate the top hits across the swept `-brief` collections; keep the 3 highest-scoring across the union. If any results come back, surface them as a heads-up — *not* a HALT:

```
**Heads up — these existing briefs look semantically close to `{name}`:**
  1. {existing-name} (similarity: {score})  — {existing-description}
  2. {existing-name} (similarity: {score})  — {existing-description}

Continue with `{name}`, or pick a different name?
```

## Failure modes

On any QMD failure (binary missing, collection list empty, any per-collection query times out — `timeout` returns exit code 124): log `"warn: portfolio-similarity check skipped — qmd query failed: {error}"` and continue silently — never HALT. A timed-out or failed query drops only that collection from the aggregate; the remaining hits still surface. Quick / Forge / Forge+ tiers do not run this check (qmd is Deep-tier-only per the canonical tier definition: `Deep = + ast-grep + gh + QMD` in `skf-forge-tier-rw.py`).
