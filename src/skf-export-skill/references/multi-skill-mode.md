---
# Static reference loaded by load-skill.md §1c only when
# `len(skill_batch) > 1` (multi-skill mode activated via `--all`,
# multi-selection at the discovery menu, or explicit multi-argument
# invocation). In single-skill mode the per-step matrix below does
# not apply and this file is never loaded. Loaded once per export run.
---

<!-- Config: communicate in {communication_language}. -->

# Multi-skill Mode — Per-step Behavior Matrix

## Purpose

When multiple skills are exported in a single run, the workflow does NOT loop the full step 1 → step 7 sequence once per skill. Instead, it partitions work across steps to avoid repeated gates and redundant batch work (one §3b orphan-detection pass, one §4 skill-index rebuild, one §6 user gate, one health check, etc.).

Loaded by `load-skill.md` §1c when `len(skill_batch) > 1`.

## Per-step matrix

| Step | Behavior in multi-skill mode |
|------|------------------------------|
| step 1 §2–5 | **Iterate per skill** — load, validate, read metadata, and check the test report for every skill in `skill_batch`. Collect per-skill results. |
| step 1 §6 | **Single gate** — present one consolidated summary table (one row per skill) and a single [C] gate for the whole batch. |
| step 2 | **Iterate per skill** — validate each skill's package structure and collect per-skill readiness. |
| step 3 | **Iterate per skill**: regenerate each skill's `context-snippet.md` independently (each skill has its own prior-gotchas carry-forward state), staging and measuring each draft in the run's one stage folder. |
| step 4 | **Batch once**: §3b orphan detection, §4 section build, §5 to §9 check, preview, gate and write all run once for the entire batch. Each `assemble` call names every skill in `skill_batch` with `--include`, beside every skill of the manifest, so no batch member is left out, even on a first export. §9b records every skill in `skill_batch` with one `set` each. |
| step 5 | **Iterate per skill** — compute token counts per skill, then present one aggregate report. |
| step 6 | **One batch summary + one result contract** — the files-written table lists every skill; the result contract JSON covers the whole run, and `outputs` enumerates every context-snippet + target context file touched. |
| step 7 | **Runs once** — health check is per-workflow-run, not per-skill. |

## Halt semantics

If any single skill fails validation in step 1 §2 (required-file or metadata-field failure) or is refused by the §2 ownership gate (`not-skf-output`: a flat skill SKF did not generate), halt the entire batch before step 4: do not partially export. Report which skill failed and why. The principle: a multi-skill run is a unit of work, not a per-skill best-effort sweep: partial exports leave the manifest and managed sections in an ambiguous state that's expensive for the operator to reconcile.

## Single-skill mode (reference)

`len(skill_batch) == 1` runs the single-skill path: every section operates on the one skill without iteration, no gate consolidation, no per-step table consultation. This file does not need to be loaded.
