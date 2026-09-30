---
nextStepFile: 'update-context.md'
snippetFormatData: '{snippetFormatPath}'
# Resolve `{countTokensHelper}` by probing `{countTokensProbeOrder}` in order
# (installed SKF module path first, src/ dev-checkout fallback); the first
# existing path wins. §4 measures the staged snippet draft with it
# (char-over-four, the count step 5's token report uses), so the 300-token
# ceiling is gated by a number, not by an estimate made in the prompt. HALT
# if no candidate exists.
countTokensProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-count-tokens.py'
  - '{project-root}/src/shared/scripts/skf-count-tokens.py'
# Resolve `{manifestOpsHelper}` similarly. §3 reads the skill's manifest
# entry with its `get` action, which returns it in the v2 shape whatever is
# on disk.
manifestOpsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-manifest-ops.py'
  - '{project-root}/src/shared/scripts/skf-manifest-ops.py'
---

<!-- Config: communicate in {communication_language}. Generate snippet content in {document_output_language}. -->

# Step 3: Generate Snippet

## STEP GOAL:

To generate or update context-snippet.md for the skill in the Vercel-aligned indexed format, targeting ~80-120 tokens per skill with T1-now content only.

## Rules

- Focus only on generating the context-snippet.md content — T1-now only, no T2 annotations
- If `passive_context: false` was detected in step 1, skip this step entirely
- **Multi-skill mode:** when step 1 loaded more than one skill (`len(skill_batch) > 1`), iterate sections 2–5 per skill. Each skill has its own prior-gotchas carry-forward state (§2.5): do not share state across skills. §2.7 resolves `{skill_root}` and §2.8 creates the stage folder once for the run (neither depends on the skill). See step 1 §1c.

## MANDATORY SEQUENCE

### 1. Check Passive Context Setting

**If `passive_context: false` was detected in step 1:**

"**Passive context disabled in preferences.yaml. Skipping snippet generation.**"

Auto-proceed immediately to {nextStepFile}.

**If `passive_context: true` (default):** Continue to step 2.

### 2. Load Snippet Format

Load {snippetFormatData} and read the format template for the skill type.

### 2.5. Check Existing Snippet

Before generating new snippet content, check for a prior snippet:

1. Read `{resolved_skill_package}/context-snippet.md` if it exists (resolved in step 1 — see `knowledge/version-paths.md`)
2. If it exists, extract the `|gotchas:` line (if any). Trim leading whitespace and the `|gotchas:` prefix, then capture the remaining content as `prior_gotchas_content`.
3. **Detect the carry-forward marker:** If `prior_gotchas_content` starts with the token `[CARRIED]` (whitespace-insensitive), set `prior_gotchas_already_carried = true` and strip the marker before storing the remainder. Otherwise set `prior_gotchas_already_carried = false`.
4. **Distinguish empty from absent:** If the `|gotchas:` line exists but has no non-whitespace content after the prefix, treat it as **absent** — set `prior_gotchas = null`. Only a non-empty value counts as a prior gotchas line worth carrying forward.
5. If no prior snippet exists at all, set `prior_gotchas = null` and `prior_gotchas_already_carried = false`.

These values will be used as a fallback in section 3 if new gotchas cannot be derived. The `[CARRIED]` marker provides a **hard one-cycle expiry**: gotchas that were already carried once will be dropped on the next carry-forward attempt rather than preserved indefinitely.

### 2.7. Resolve Skill Root Path

**If `snippet_skill_root_override` is set in config.yaml:** Use its value directly as `{skill_root}` and skip the IDE-mapping lookup below. This is the authoring-repo escape hatch — repos where skills live under a single shared directory (e.g. `skills/`) that does not match any per-IDE skill root. Log: "Using snippet_skill_root_override: `{override}` — bypassing IDE mapping for snippet root path."

**Otherwise (default):** Using the first entry in `target_context_files` (resolved in step 1), take its `skill_root` value. This is the IDE's actual skill directory (e.g., `.claude/skills/`, `.windsurf/skills/`, `.github/skills/`).

Store `{skill_root}` for use in snippet generation. The context-snippet.md written to disk uses this resolved skill root path.

### 2.8. Stage Folder

Once per run (skip this when `{export_stage_dir}` is already bound, as for the second skill of a batch), create the run's stage folder outside the project and bind `{export_stage_dir}` to the path this prints:

```bash
python3 -c "import tempfile; print(tempfile.mkdtemp(prefix='skf-export-'))"
```

§4 stages each skill's snippet draft there, under `drafts/{skill-name}/`, and step 4 stages each context file's new section there, under `previews/`, so a dry run leaves nothing beside a skill package or a context file, and a cancelled export leaves nothing beside a context file. Step 4 deletes the folder on every exit, cancels and halts included.

### 3. Generate Snippet Content

**For single skills (`skill_type: "single"`):**

1. Read metadata.json for `version`, `exports` array
2. Select top exports (up to 10 for Deep tier, 5 otherwise). Append `()` to function names.
3. Read SKILL.md to extract: heading slugs for `#quick-start` and `#key-types`, inline summary of key types (~10 words)
4. **Anchor verification (split-body awareness):** For each section anchor (`#quick-start`, `#key-types`), verify the heading exists in SKILL.md. If a `references/` directory exists and `## Full` headings in SKILL.md are absent or stubs (indicating split-body, not a stack skill's structural references), rewrite the anchor to point to the reference file path (e.g., `references/{file}.md#key-types`). If the heading cannot be resolved in either location, omit that anchor line from the snippet.
5. Derive gotchas from: T2-future annotations in evidence report (breaking changes), async requirements, version-specific behavior.

   **Detect first-export state before applying carry-forward logic.** The `[CARRIED]` one-cycle expiry is meaningful only on a *re-export*. On a first export, the prior `context-snippet.md` was authored by `create-skill` (or `update-skill`) from the evidence report inside the same forge cycle — those gotchas are freshly derived, not "left over from a previous export." Treating them as carry-forward primes them for premature expiry on the second export.

   Resolve `{manifestOpsHelper}` from `{manifestOpsProbeOrder}` (first existing path wins) and read the skill's manifest entry: `python3 {manifestOpsHelper} {skills_output_folder} get {skill-name}`. When it returns `not_found`, or an `entry` none of whose `versions` records a `last_exported`, this is a first export: set `is_first_export = true`. Otherwise `is_first_export = false`. The helper returns the entry in the v2 shape whatever is on disk, so a v1 manifest reads the same here as in step 4.

   - **If new gotchas are derived:** Use them (they supersede any prior gotchas). Write as `|gotchas: {pitfall-1}, {pitfall-2}` with no marker.
   - **If NO new gotchas are derived AND `is_first_export == true` AND `prior_gotchas` exists:** Treat the prior gotchas as **freshly derived** by create-skill/update-skill — write them **without** the `[CARRIED]` marker. (The marker only applies to re-exports.) No warning needed; this is the normal first-export shape.
   - **If NO new gotchas are derived BUT `prior_gotchas` exists AND `is_first_export == false` AND `prior_gotchas_already_carried == false`:** First carry-forward cycle on a re-export — preserve the prior gotchas line, prefixing the value with `[CARRIED]` so the next export can detect that expiry has been reached. Write as `|gotchas: [CARRIED] {prior gotchas content}`. Emit warning: "**Gotchas preserved from prior export (one-cycle carry-forward).** These gotchas will be DROPPED on the next export unless new gotchas are derived or you manually refresh them. Review now if they are still applicable."
   - **If NO new gotchas are derived AND `prior_gotchas` exists AND `prior_gotchas_already_carried == true`:** Expiry reached (re-export only — first-export branch above takes precedence) — drop the gotchas line entirely. Emit warning: "**Stale gotchas dropped** — the prior gotchas were already carried forward once and cannot be derived from the current evidence report. The snippet now has no gotchas line. If the prior gotchas are still relevant, re-add them to the evidence report's T2-future section and re-run export."
   - **If NO new gotchas derived AND no `prior_gotchas`:** Omit the gotchas line.

Emit the single-skill template from {snippetFormatData} (loaded in §2), filling `api` from the exports selected above (list all if fewer than the limit; omit the line if there are none), `key-types` from the inline summary extracted above, and `gotchas` per the carry-forward decision tree above (omit the line when it resolves to none).

**For stack skills (`skill_type: "stack"`):**

Emit the stack-skill template from {snippetFormatData}, filling `stack` from metadata.json `components` and `integrations` from metadata.json `integrations`.

**Stack skill gotchas carry-forward:** Same one-cycle expiry logic as single skills. If no new gotchas derived and `prior_gotchas_already_carried == false`, preserve with the `[CARRIED]` prefix. If already carried once (`prior_gotchas_already_carried == true`), drop the line and warn loudly. See the single-skill steps for the complete protocol.

### 4. Verify Token Count

Write the generated snippet to `{export_stage_dir}/drafts/{skill-name}/context-snippet.md` with your file-write tool, resolve `{countTokensHelper}` from `{countTokensProbeOrder}` (first existing path wins), and measure the draft with it, the count step 5's token report uses:

```bash
python3 {countTokensHelper} "{export_stage_dir}/drafts/{skill-name}"
```

Bind `{count}` ← the `tokens` value of its `context-snippet.md` row (`len(text)//4`, the SKF-wide convention).

- Target: ~80-120 tokens per skill (aspirational for Quick/Forge tiers)
- Hard ceiling: 300 tokens (Deep tier may legitimately exceed 120 when gotchas carry load-bearing breaking-change notices)
- If `{count}` is above 300, trim the description, the exports list or the refs, write the draft again and measure it again, until `{count}` is 300 or below. **Do NOT drop gotchas to fit**: gotchas exist precisely to deliver the "do not rely on training data" signal and are the last thing to cut

When no `{countTokensProbeOrder}` candidate exists, or the helper exits non-zero, delete the `{export_stage_dir}` folder and HALT (exit code 4, `halt_reason: "context-rebuild-failed"`): "SKF cannot measure the snippet: {`skf-count-tokens.py` is missing, or the helper's error}. Re-install SKF and re-run the export." In headless mode, emit the error envelope per `references/result-envelope.md` with the resolved `skills`, `context_files_updated: []` and `manifest_path: null`.

### 5. Write or Preview Snippet

**If dry-run mode:**

"**[DRY RUN] context-snippet.md would be written to:**
`{resolved_skill_package}/context-snippet.md`

**Content:**
```
{generated snippet content}
```

**Estimated tokens:** {count}"

Nothing is written to the package: step 4 builds its preview from the draft.

**If NOT dry-run:**

Copy the measured draft into the package, byte for byte, so `{count}` is the count of the written file:

```bash
cp "{export_stage_dir}/drafts/{skill-name}/context-snippet.md" "{resolved_skill_package}/context-snippet.md"
```

"**context-snippet.md written.**
**Path:** `{resolved_skill_package}/context-snippet.md`
**Estimated tokens:** {count}"

### 6. Proceed to Context Update

Display: "**Proceeding to context update...**"

Auto-proceed (no user choices): once snippet generation is complete (or skipped via the `passive_context` opt-out), load, read entirely, and execute `{nextStepFile}`.

