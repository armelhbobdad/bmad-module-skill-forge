---
nextStepFile: 'step-doc-rot.md'
shardBodyProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-shard-body.py'
  - '{project-root}/src/shared/scripts/skf-shard-body.py'
sourceTreeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-source-tree.py'
  - '{project-root}/src/shared/scripts/skf-source-tree.py'
emitEnvelopeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py'
  - '{project-root}/src/shared/scripts/skf-emit-result-envelope.py'
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
- A HARD HALT, once step 3 §2a has bound `{source_tree}`, first runs `uv run {sourceTreeHelper} close --tree "{source_tree}"` from `{project-root}` (resolved from `{sourceTreeProbeOrder}`) and goes on whatever it prints, and emits through `{emitEnvelopeHelper}`, resolved from `{emitEnvelopeProbeOrder}` when it is not bound: it stages `{"phase": "<phase>", "halt_reason": "<halt_reason>", "reason": "<the halt message, one line>", "summary": {"halt_reason": "<halt_reason>", "evidence_report": null}}`, plus `"path"` when the HALT names a file or folder, as `{run_dir}/halt.json`, runs `uv run {emitEnvelopeHelper} emit-halt --workflow skf-create-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"`, displays the line it prints (the halt message alone when no path resolves) and stops with the HALT's exit code. After its envelope, under `--batch` it ends only this brief: return to `references/batch-mode.md` §3, even when the halt reads as the end of the run.

## MANDATORY SEQUENCE

### §0. Run the Shard Script

A script owns the counting, the section boundaries, the size sort, the file writes and the cross-reference blockquotes, on every run: do not count body lines or extract sections by hand.

**Resolve `{shardBodyHelper}`** from `{shardBodyProbeOrder}`; first existing path wins. If no candidate exists, **HARD HALT** (exit code 3, `helper-missing`, phase `auto-shard`): "Cannot shard the body: skf-shard-body.py is missing. Re-install SKF, then re-run create-skill."

Run:

```bash
uv run {shardBodyHelper} <staging-skill-dir>/SKILL.md --budget 400
```

Read its JSON and set context directly:

- **`action: "skip"`** → the body was already within budget. Log `"auto-shard: skipped (body {body_lines_before} lines)"`, set `auto_shard_triggered: false`, `sections_extracted: []`, `body_lines_before`/`body_lines_after` from the report, then skip to §1.
- **`action: "shard"`** → set `auto_shard_triggered: true` and copy `sections_extracted`, `body_lines_before`, `body_lines_after` straight from the report.
- If `tier1_preserved` is false, **HARD HALT** (exit code 5, `tier1-not-preserved`, phase `auto-shard`): `"Auto-shard removed Tier 1 section(s) {tier1_missing}. Aborting."`
- If `xref_ok` is false, **HARD HALT** (exit code 5, `shard-xref-broken`, phase `auto-shard`): `"Auto-shard cross-references did not resolve. Aborting."`
- If `under_budget` is false, selective Tier 2 extraction alone could not bring the body under budget (rare: Tier 1 itself exceeds about 300 lines). Trim `## Key API Summary` and `## Architecture at a Glance` until the body fits the 400-line budget, never moving a Tier 1 section to `references/`, then run the script again and take `body_lines_after` from it.

Log: `"auto-shard: {N} sections extracted, body reduced from {body_lines_before} to {body_lines_after} lines"`, then proceed to §1.

### §1. Auto-Proceed

Load, read the entire file, then execute `{nextStepFile}`.
