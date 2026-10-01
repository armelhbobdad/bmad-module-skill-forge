---
nextStepFile: 'step-doc-rot.md'
# Resolve `{shardBodyHelper}` by probing `{shardBodyProbeOrder}` in order
# (installed SKF module path first, src/ dev-checkout fallback); first existing
# path wins. HALT (exit code 3, helper-missing) if neither resolves: hand
# line-counting would silently ship an over-budget body or wrongly halt.
shardBodyProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-shard-body.py'
  - '{project-root}/src/shared/scripts/skf-shard-body.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 5b: Auto-Shard

## STEP GOAL:

Proactively reduce oversized SKILL.md bodies to under 400 lines by extracting Tier 2 sections (`## Full` headings) to `references/`, providing 100 lines of headroom below the 500-line `body.max_lines` ceiling. Tier 1 sections always remain inline. If the body is already within budget, skip cleanly.

## Rules

- Auto-proceed step — no user interaction required
- Graceful skip — if body is under threshold, proceed without modification
- Only extract Tier 2 sections (identified by `## Full` heading prefix)
- Tier 1 sections stay inline — moving one to references/ would break the standalone SKILL.md the two-tier design guarantees
- Do not modify frontmatter — only body content and references/ directory
- Do not invoke `npx skill-check split-body` — this step uses direct extraction
- Do not invoke the Description Guard Protocol — frontmatter is untouched

## MANDATORY SEQUENCE

### §0. Run the Shard Script

A script owns the counting, the section boundaries, the size sort, the file writes and the cross-reference blockquotes, on every run: do not count body lines or extract sections by hand.

**Resolve `{shardBodyHelper}`** from `{shardBodyProbeOrder}`; first existing path wins. If no candidate exists, **HARD HALT** (exit code 3, `helper-missing`, phase `auto-shard`; stage `{run_dir}/halt.json` per the Workflow Rules and run `uv run {emitEnvelopeHelper} emit-halt --workflow skf-create-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"`): "Cannot shard the body: skf-shard-body.py is missing. Re-install SKF, then re-run create-skill."

Run:

```bash
uv run {shardBodyHelper} <staging-skill-dir>/SKILL.md --budget 400
```

The script counts the body between the frontmatter close and EOF. Over 400 lines, it extracts the Tier 2 sections, the ones whose heading starts `## Full` (`## Full API Reference` goes to `references/full-api-reference.md`, `## Full Type Definitions` to `references/full-type-definitions.md`, `## Full Integration Patterns` to `references/full-integration-patterns.md`), largest first, until the body fits. It writes the extracted files and the trimmed SKILL.md through the atomic-write helper, puts a cross-reference blockquote (`> See [Full API Reference](references/full-api-reference.md)`) in each extracted section's place, and checks that every Tier 1 section inline before is still inline (`tier1_preserved`, with any pulled heading in `tier1_missing`) and that each cross-reference resolves (`xref_ok`). Read its JSON and set context directly:

- **`action: "skip"`** → the body was already within budget. Log `"auto-shard: skipped (body {body_lines_before} lines)"`, set `auto_shard_triggered: false`, `sections_extracted: []`, `body_lines_before`/`body_lines_after` from the report, then skip to §1.
- **`action: "shard"`** → set `auto_shard_triggered: true` and copy `sections_extracted`, `body_lines_before`, `body_lines_after` straight from the report.
- If `tier1_preserved` is false, **HARD HALT** (exit code 5, `tier1-not-preserved`, phase `auto-shard`; stage `{run_dir}/halt.json` per the Workflow Rules and run `uv run {emitEnvelopeHelper} emit-halt --workflow skf-create-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"`): `"Auto-shard removed Tier 1 section(s) {tier1_missing}. Aborting."`
- If `xref_ok` is false, **HARD HALT** (exit code 5, `shard-xref-broken`, phase `auto-shard`; stage `{run_dir}/halt.json` per the Workflow Rules and run `uv run {emitEnvelopeHelper} emit-halt --workflow skf-create-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"`): `"Auto-shard cross-references did not resolve. Aborting."`
- If `under_budget` is false, selective Tier 2 extraction alone could not bring the body under budget (rare: Tier 1 itself exceeds about 300 lines). Trim `## Key API Summary` and `## Architecture at a Glance` until the body fits the 400-line budget, never moving a Tier 1 section to `references/`, then run the script again and take `body_lines_after` from it.

Log: `"auto-shard: {N} sections extracted, body reduced from {body_lines_before} to {body_lines_after} lines"`, then proceed to §1.

### §1. Auto-Proceed

Load, read the entire file, then execute `{nextStepFile}`.
