# Output Contract Schema

Every pipeline-capable skill writes a result JSON file at its final step. This enables reliable CI integration and pipeline chaining.

## Schema

```json
{
  "skill": "skf-skill-name",
  "status": "success" | "failed" | "partial",
  "timestamp": "ISO-8601",
  "outputs": [
    {"type": "report|skill|manifest|config", "path": "relative/path/to/file"}
  ],
  "summary": {
    // skill-specific summary fields
  }
}
```

## Filenames

Each run writes **two files** to `{output_dir}`:

1. **Per-run record** (audit trail): `{skill-name}-result-{YYYYMMDD-HHmmss}.json`
   - Timestamp is UTC, resolution to seconds — e.g., `update-skill-result-20260413-145230.json`
   - Never overwritten by subsequent runs — preserves a durable audit trail across retries, aborts, and re-runs
2. **Stable latest pointer** (pipeline consumption): `{skill-name}-result-latest.json`
   - A **copy** (not a symlink) of the per-run record just written
   - Always present at a deterministic path so CI / pipelines / the forger can read `summary.*` without enumerating timestamps
   - Overwritten on every successful write

Write the per-run record first, then copy it to the `-latest.json` path. If the copy fails, the per-run record still exists — the run is not lost.

**Consumers (forger, CI, chained workflows):** read from `{skill-name}-result-latest.json`. Do not enumerate timestamped files unless inspecting prior-run history.

## Available Helpers

There is no generic helper that writes the schema above; each skill assembles the JSON in its terminal step today. One specialised helper exists:

- **`src/shared/scripts/skf-emit-result-envelope.py`** — `skf-setup`-specific. Writes a different envelope (`SKF_SETUP_RESULT_JSON: {…}`) following the JSON schema at `src/shared/scripts/schemas/skf-setup-result-envelope.v1.json`. Carries setup-specific fields (`tier`, `previous_tier`, `tools`, `ccc_index`, `tier_override_*`, `qmd_status`, etc.) that have no analogue in other workflows. **Do not reuse for non-skf-setup skills.**

A generalised emitter (matching this document's schema) is a reasonable future helper when a second consumer materialises with the same shape. For now, skills that write this contract assemble the JSON in their terminal step — the work is small (5–8 fields) and skill-specific summary content benefits from being expressed inline alongside the rest of the step's logic.

skf-quick-skill writes both the success-variant contract (`step-06-finalize.md` §3) and the error-variant contract on every HARD HALT (per `SKILL.md` § "Result Contract on HARD HALT") in this hand-assembled style.
