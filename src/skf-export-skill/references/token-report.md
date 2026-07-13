---
nextStepFile: 'summary.md'
# Resolve `{countTokensHelper}` by probing `{countTokensProbeOrder}` in order
# (installed SKF module path first, src/ dev-checkout fallback); the first
# existing path wins. The helper emits deterministic per-artifact word/token
# metrics as JSON so this step renders exact numbers instead of re-reading every
# reference file to word-count it in-prompt. `tokens` is the char-over-four
# estimate shared with skf-validate-output.py so all SKF token numbers agree.
countTokensProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-count-tokens.py'
  - '{project-root}/src/shared/scripts/skf-count-tokens.py'
---

<!-- Config: communicate in {communication_language}. Render the token report in {document_output_language}. -->

# Step 5: Token Report

## STEP GOAL:

To calculate approximate token counts for all exported artifacts and present a clear report showing the token cost of each component, helping users understand the context budget impact of their skills.

## Rules

- Focus only on token counting and reporting — read-only measurement
- Auto-proceed when complete
- **Multi-skill mode:** when step 1 loaded more than one skill (`len(skill_batch) > 1`), run the helper once per skill, then present one aggregate table with one row per skill (context-snippet.md, SKILL.md, metadata.json, references/, package total). The `managed_section` value is identical across runs (same target files) — measure and report it once for the run. See step 1 §1c.

## MANDATORY SEQUENCE

### 1. Measure Token Counts

Resolve `{countTokensHelper}` from `{countTokensProbeOrder}` (see frontmatter) — the first existing path wins. Then run it against the resolved skill package, passing every target context file so the shared managed section is measured:

```bash
python3 {countTokensHelper} {resolved_skill_package} --target-file {context_file_1} --target-file {context_file_2}
```

Pass one `--target-file` per entry in `target_context_files` (resolved in step 1). The helper measures the managed section from the first target file that contains a `<!-- SKF:BEGIN -->…<!-- SKF:END -->` block.

The helper emits JSON:

```json
{
  "files": [{"path": "…", "role": "…", "exists": true, "words": 0, "tokens": 0}],
  "references_total": {"count": 0, "words": 0, "tokens": 0},
  "managed_section": {"present": true, "source_file": "…", "words": 0, "tokens": 0},
  "package_total": {"words": 0, "tokens": 0}
}
```

**Read the JSON — do not re-count words in-prompt.** Each `tokens` value is a char-over-four estimate (`len(text)//4`, the SKF-wide convention shared with `skf-validate-output.py`); each `words` value is the whitespace-split count for the report's Words column. The `files` array carries one row per artifact — `role` is one of `context-snippet`, `skill-md`, `metadata`, `reference`. `package_total` already sums context-snippet.md + SKILL.md + metadata.json + `references_total` and **excludes** the `managed_section` row: the managed section is a shared all-skills cost (it bundles this skill's snippet plus every other skill's snippet), so folding it in would double-count this skill's snippet and pull in unrelated skills. It is reported separately under Context Budget Impact.

**If `passive_context` was disabled:** the helper reports the `context-snippet.md` row with `exists: false` and `managed_section.present: false` — render both as "N/A (disabled)".

**Graceful fallback (helper cannot run — e.g. no Python/uv on claude.ai web):** count the same artifacts in-prompt using the char-over-four convention (`tokens ≈ len(text)//4`, `words` = whitespace-split count). The JSON shape above documents exactly what to measure: context-snippet.md, SKILL.md, metadata.json, each file under references/ (summed as references_total), and the `<!-- SKF:BEGIN -->…<!-- SKF:END -->` block from the first target context file. The package total sums the first four and excludes the managed section.

### 2. Present Token Report

Render the table straight from the helper JSON — no re-counting.

- `context-snippet.md` row → `files[].tokens` / `.words` for `role: context-snippet`
- `Managed section` row → `managed_section.words` / `.tokens` (report once for the run)
- `SKILL.md` row → `files[]` for `role: skill-md`
- `metadata.json` row → `files[]` for `role: metadata`
- `references/` row → `references_total.words` / `.tokens`; `{count}` files = `references_total.count`
- `Package total` row → `package_total.words` / `.tokens`

"**Token Report**

| Artifact | Words | Est. Tokens | Notes |
|----------|-------|-------------|-------|
| context-snippet.md | {n} | ~{t} | Passive context (always-on) |
| Managed section (all skills) | {n} | ~{t} | In {target-file-list}, all {count} skills |
| SKILL.md | {n} | ~{t} | Active skill (on-trigger) |
| metadata.json | {n} | ~{t} | Machine-readable |
| references/ | {n} | ~{t} | {count} files |
| **Package total** | **{n}** | **~{t}** | **This skill's own artifacts (snippet + SKILL.md + metadata + references); excludes the shared Managed section row** |

**Context Budget Impact:**
- **Always-on cost:** ~{managed-section-tokens} tokens (managed section in {target-file-list})
- **On-trigger cost:** ~{skill-tokens} tokens (when SKILL.md is loaded)
- **Full disclosure cost:** ~{total-tokens} tokens (if references/ also loaded)

**Benchmark:** Target is ~80-120 tokens per skill in managed section. Current: ~{snippet-tokens} tokens."

### 3. Proceed to Summary

Display: "**Proceeding to export summary...**"

Auto-proceed (no user choices): once the token report is displayed, load, read entirely, and execute `{nextStepFile}`.
