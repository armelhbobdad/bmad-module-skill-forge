# Portfolio-Similarity Check

Loaded by step 1 §6 at Deep tier when `tools.qmd` is true in the `tools` step 0 §1 bound.

This check catches **semantic near-duplicates** that exact-name collision misses (e.g. `markdown-renderer` proposed when `marked` already exists, or `auth-gateway` when `auth-middleware` already exists). Exact-name collision is handled separately at §6 before this check runs.

## Procedure

The brief portfolio is already indexed in QMD collections, one `<name>-brief` collection per existing brief, registered by step 5 §3b (step-auto-validate.md §3 on an `[auto]` run) of every prior Deep-tier run. Resolve `{qmdPortfolioSimilarityHelper}` from `{qmdPortfolioSimilarityProbeOrder}` (first existing path wins) and compare the proposed name and the §4 intent with them in one call:

```bash
uv run {qmdPortfolioSimilarityHelper} similar --name "{name}" --text-file - --cap 12 --concurrency 4 --timeout 20 --min-score 0.6 --top 3 <<'SKF_QUERY'
<the §4 intent>
SKF_QUERY
```

It asks the first 12 `-brief` collections QMD lists, never the proposed name's own, at most 4 at a time and each for at most 20 seconds, since each query cold-starts an embedding model. It prints `{hits, skipped}`: `hits` holds the 3 best `{name, collection, score, description}` at or above 0.6, best first, and `skipped` a `{collection, reason}` for each query that timed out or failed. If any hits come back, show them in the step 1 §7 message as a heads-up, *not* a HALT, where the user can give another name; whether to rename stays the user's call at §8:

```
**Heads up: these existing briefs look semantically close to `{name}`:**
- {hit-name} (similarity: {score}): {description}
```

Each bullet is one hit: `{hit-name}` is its `name`, `{score}` and `{description}` its own; a hit whose `description` is null ends at its score.

## Failure modes

When the call exits 1 (`qmd` is not on PATH, or its collection list failed) or prints no JSON, when `{qmdPortfolioSimilarityHelper}` has no path, or when `skipped` is not empty, log `"warn: portfolio-similarity check skipped: {reason}"`, with `{reason}` the first line of its stderr, `skf-qmd-portfolio-similarity.py not found`, or each skipped collection with its reason, write it to `{run_dir}/warning.txt` with a file write, never `echo`, run `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "$(cat "{run_dir}/warning.txt")"`, and go on: never HALT. The hits still show. No `-brief` collection is no failure: a first Deep-tier brief has no portfolio to compare, the helper prints `{"hits": [], "skipped": []}`, and nothing is recorded. Quick / Forge / Forge+ tiers do not run this check (qmd is Deep-tier-only per the canonical tier definition: `Deep = + ast-grep + gh + QMD` in `skf-forge-tier-rw.py`).
