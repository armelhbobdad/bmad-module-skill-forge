---
nextStepFile: 'summary.md'
# SKILL.md's On Activation resolved {countTokensHelper}.
---

<!-- Config: communicate in {communication_language}. Render the token report in {document_output_language}. -->

# Step 4: Token Report

## STEP GOAL:

To calculate approximate token counts for all exported artifacts and present a clear report showing the token cost of each component, helping users understand the context budget impact of their skills.

## Rules

- Focus only on token counting and reporting: this step writes nothing, and deletes only a dry run's stage folder (§3)
- Auto-proceed when complete
- **Multi-skill mode:** when step 1 loaded more than one skill (`len(skill_batch) > 1`), run the helper once per skill, then present one aggregate table with one row per skill (context-snippet.md, SKILL.md, metadata.json, references/, package total) and the Context Budget Impact per skill (its `context_budget.on_trigger`, `full_disclosure` and `snippet`). The `managed_section` and `context_budget.always_on` values are identical across runs (same target files): measure and report them once for the run.

## MANDATORY SEQUENCE

### 1. Measure Token Counts

Run `{countTokensHelper}` against the resolved skill package, passing every target context file so the shared managed section is measured:

```bash
python3 {countTokensHelper} {resolved_skill_package} --target-file {context_file_1} --target-file {context_file_2}
```

Pass one `--target-file` per entry in `target_context_files` (resolved in step 1). The helper measures the managed section from the first target file that contains a `<!-- SKF:BEGIN -->…<!-- SKF:END -->` block.

**On a dry run with passive context on**, nothing was written, so measure what this run staged: the skill's draft, and the body step 3 §4b staged for the first entry of `target_context_files` (`{context_file_1}`), which the helper wraps in markers as §9 would write it:

```bash
python3 {countTokensHelper} {resolved_skill_package} --snippet "{export_stage_dir}/drafts/{skill-name}/context-snippet.md" --section-file "{export_stage_dir}/previews/{context_file_1}.skf-content" --target-file {context_file_1} --target-file {context_file_2}
```

Each `tokens` value is a char-over-four estimate (`len(text)//4`, the SKF-wide convention shared with `skf-validate-output.py`); each `words` value is the whitespace-split count for the report's Words column.

**If `passive_context` was disabled:** run `python3 {countTokensHelper} {resolved_skill_package} --no-snippet`, with no `--target-file`, so it reports no `context-snippet.md` row and no managed section whatever is on disk, and render the context-snippet.md and Managed section rows, the always-on cost and the benchmark as "N/A (disabled)", since `{passive_context}` is false.

### 2. Present Token Report

Render the report straight from the helper JSON, with no re-counting. In each table row, `{n}` ← the row's `words` and `{t}` ← its `tokens`:

- `context-snippet.md` row → `files[].tokens` / `.words` for `role: context-snippet`
- `Managed section` row → `managed_section.words` / `.tokens`; `{target-file-list}` ← `managed_section.target_files`, joined with commas; `{skill-count}` ← `managed_section.skills` (report the row once for the run)
- `SKILL.md` row → `files[]` for `role: skill-md`
- `metadata.json` row → `files[]` for `role: metadata`
- `references/` row → `references_total.words` / `.tokens`; `{count}` ← `references_total.count`
- `Package total` row → `package_total.words` / `.tokens`

The Context Budget Impact lines, per skill in multi-skill mode (the always-on cost once for the run):

- `{managed-section-tokens}` ← `context_budget.always_on`, the managed section's tokens (N/A when null)
- `{measured-file}` ← `managed_section.source_file`, the target file the helper measured; on a dry run, which measures the staged preview, `{context_file_1}` instead
- `{skill-tokens}` ← `context_budget.on_trigger`, SKILL.md's tokens
- `{total-tokens}` ← `context_budget.full_disclosure`, SKILL.md's tokens plus `references_total.tokens` (never `package_total`, which also counts the snippet and metadata.json)
- `{snippet-tokens}` ← `context_budget.snippet`, the context-snippet.md row's tokens
- `{skill-name}` ← `skill_package`, its last folder (multi-skill mode only)

"**Token Report**

| Artifact | Words | Est. Tokens | Notes |
|----------|-------|-------------|-------|
| context-snippet.md | {n} | ~{t} | Passive context (always-on) |
| Managed section (all skills) | {n} | ~{t} | In {target-file-list}, all {skill-count} skills |
| SKILL.md | {n} | ~{t} | Active skill (on-trigger) |
| metadata.json | {n} | ~{t} | Machine-readable |
| references/ | {n} | ~{t} | {count} files |
| **Package total** | **{n}** | **~{t}** | **This skill's own artifacts (snippet + SKILL.md + metadata + references); excludes the shared Managed section row** |

**Context Budget Impact:**
- **Always-on cost:** ~{managed-section-tokens} tokens (measured in {measured-file}; the managed section is in {target-file-list})
- **On-trigger cost:** ~{skill-tokens} tokens (when SKILL.md is loaded)
- **Full disclosure cost:** ~{total-tokens} tokens (if references/ also loaded)

**Benchmark:** Target is ~80-120 tokens per skill in managed section. Current: ~{snippet-tokens} tokens."

**In multi-skill mode**, render the Context Budget Impact and the Benchmark this way instead: the always-on cost once for the run, then one line per skill, each from that skill's own run:

"**Context Budget Impact:**
- **Always-on cost:** ~{managed-section-tokens} tokens (measured in {measured-file}; the managed section is in {target-file-list})
- **{skill-name}:** on-trigger ~{skill-tokens} tokens, full disclosure ~{total-tokens} tokens, snippet ~{snippet-tokens} tokens

**Benchmark:** Target is ~80-120 tokens per skill in managed section."

### 3. Proceed to Summary

On a dry run with passive context on, delete the `{export_stage_dir}` folder.

Display: "**Proceeding to export summary...**"

Auto-proceed (no user choices): once the token report is displayed, load, read entirely, and execute `{nextStepFile}`.
