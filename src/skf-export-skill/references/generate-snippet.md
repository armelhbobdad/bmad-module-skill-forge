---
nextStepFile: 'update-context.md'
snippetFormatData: '{snippetFormatPath}'
# SKILL.md's On Activation resolved {countTokensHelper}, which measures the
# staged draft in §4, and {manifestOpsHelper}, whose `get` reads the skill's
# manifest entry in §3a.
---

<!-- Config: communicate in {communication_language}. Generate snippet content in {document_output_language}. -->

# Step 3: Generate Snippet

## STEP GOAL:

To generate or update context-snippet.md for the skill in the Vercel-aligned indexed format, targeting ~80-120 tokens per skill with T1-now content only.

## Rules

- Focus only on generating the context-snippet.md content — T1-now only, no T2 annotations
- If `passive_context: false` was detected in step 1, skip this step entirely
- **Multi-skill mode:** when step 1 loaded more than one skill (`len(skill_batch) > 1`), iterate sections 2 to 5 per skill. Each skill has its own prior-gotchas carry-forward state (§2.5): do not share state across skills. §2.7 resolves `{skill_root}`, the snippet's root only, and §2.8 creates the stage folder once for the run (neither depends on the skill). See step 1 §1c.
- Every HALT names its exit code, `halt_reason` and phase; in headless mode it first emits its envelope as `references/result-envelope.md` states

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

These values will be used as a fallback in §3a if new gotchas cannot be derived. The `[CARRIED]` marker provides a **hard one-cycle expiry**: gotchas that were already carried once will be dropped on the next carry-forward attempt rather than preserved indefinitely.

### 2.7. Resolve Skill Root Path

**If `{snippet_skill_root_override}` is set** (by `config.yaml`, or for this run by step 1's snippet-root option (d)): use its value directly as `{skill_root}` and skip the IDE-mapping lookup below. This is the authoring-repo escape hatch, for repos where skills live under a single shared directory (e.g. `skills/`) that does not match any per-IDE skill root. Log: "Using snippet_skill_root_override: `{override}`, bypassing the IDE mapping for the snippet root path."

**Otherwise (default):** Using the first entry in `target_context_files` (resolved in step 1), take its `skill_root` value. This is the IDE's actual skill directory (e.g., `.claude/skills/`, `.windsurf/skills/`, `.github/skills/`).

Store `{skill_root}` for use in snippet generation: it is the snippet's root only, the `root:` path of the context-snippet.md this step stages. It is not a context file's root: step 4 builds each context file's managed section with that target's own skill root, so with `ides` [claude-code, codex] the AGENTS.md rows take `.agents/skills/` while the snippet keeps `.claude/skills/`.

### 2.8. Stage Folder

Once per run (skip this when `{export_stage_dir}` is already bound, as for the second skill of a batch), create the run's stage folder outside the project and bind `{export_stage_dir}` to the path this prints:

```bash
python3 -c "import tempfile; print(tempfile.mkdtemp(prefix='skf-export-'))"
```

§4 stages each skill's snippet draft there, under `drafts/{skill-name}/`, and step 4 stages each context file's new section there, under `previews/`, so a dry run leaves nothing beside a skill package or a context file. Step 4 deletes the folder on every exit, cancels and halts included.

### 3. Generate Snippet Content

#### 3a. Gotchas (Both Skill Types)

Derive new gotchas from the T2-future annotations in the evidence report at `{forge_evidence_report}` (breaking changes), async requirements and version-specific behavior. Step 1 §2 bound that path; when it is null, the skill has no evidence report to read.

**Detect first-export state before applying carry-forward logic.** The `[CARRIED]` one-cycle expiry is meaningful only on a *re-export*. On a first export, the prior `context-snippet.md` was written by the workflow that built or updated the skill (create-skill, create-stack-skill, quick-skill or update-skill) inside the same forge cycle: those gotchas are freshly derived, not "left over from a previous export." Treating them as carry-forward primes them for premature expiry on the second export.

Read the skill's manifest entry: `python3 {manifestOpsHelper} {skills_output_folder} get {skill-name}`. When it returns `not_found`, or an `entry` none of whose `versions` records a `last_exported`, this is a first export: set `is_first_export = true`. Otherwise `is_first_export = false`. The helper returns the entry in the v2 shape whatever is on disk, so a v1 manifest reads the same here as in step 4.

Resolve the gotchas line by this decision tree:

- **If new gotchas are derived:** Use them (they supersede any prior gotchas). Write as `|gotchas: {pitfall-1}, {pitfall-2}` with no marker.
- **If NO new gotchas are derived AND `is_first_export == true` AND `prior_gotchas` exists:** Treat the prior gotchas as **freshly derived** by the workflow that wrote them, and write them **without** the `[CARRIED]` marker. (The marker only applies to re-exports.) No warning needed; this is the normal first-export shape.
- **If NO new gotchas are derived BUT `prior_gotchas` exists AND `is_first_export == false` AND `prior_gotchas_already_carried == false`:** First carry-forward cycle on a re-export: preserve the prior gotchas line, prefixing the value with `[CARRIED]` so the next export can detect that expiry has been reached. Write as `|gotchas: [CARRIED] {prior gotchas content}`. Emit warning: "**Gotchas preserved from prior export (one-cycle carry-forward).** These gotchas will be DROPPED on the next export unless new gotchas are derived or you manually refresh them. Review now if they are still applicable."
- **If NO new gotchas are derived AND `prior_gotchas` exists AND `prior_gotchas_already_carried == true`:** Expiry reached (re-export only: the first-export branch above takes precedence). Drop the gotchas line entirely. Emit warning: "**Stale gotchas dropped:** the prior gotchas were already carried forward once and cannot be derived from the current evidence report. The snippet now has no gotchas line. If the prior gotchas are still relevant, re-add them to the evidence report's T2-future section and re-run export."
- **If NO new gotchas derived AND no `prior_gotchas`:** Omit the gotchas line.

#### 3b. Single Skills (`skill_type: "single"`)

1. Read metadata.json for `version`, `exports` array
2. Select top exports (up to 10 for Deep tier, 5 otherwise). Append `()` to function names.
3. Read SKILL.md to extract: heading slugs for `#quick-start` and `#key-types`, inline summary of key types (~10 words)
4. **Anchor verification (split-body awareness):** For each section anchor (`#quick-start`, `#key-types`), verify the heading exists in SKILL.md. If a `references/` directory exists and `## Full` headings in SKILL.md are absent or stubs (indicating split-body, not a stack skill's structural references), rewrite the anchor to point to the reference file path (e.g., `references/{file}.md#key-types`). If the heading cannot be resolved in either location, omit that anchor line from the snippet.

Emit the single-skill template from {snippetFormatData} (loaded in §2), filling `api` from the exports selected above (list all if fewer than the limit; omit the line if there are none), `key-types` from the inline summary extracted above, and `gotchas` per the §3a decision tree (omit the line when it resolves to none).

#### 3c. Stack Skills (`skill_type: "stack"`)

Emit the stack-skill template from {snippetFormatData}, filling `stack` from metadata.json `components` and `integrations` from metadata.json `integrations`.

Stack skills: apply the gotchas decision tree above unchanged, including the first-export branch.

### 4. Verify Token Count

Write the generated snippet to `{export_stage_dir}/drafts/{skill-name}/context-snippet.md` with your file-write tool, and measure the draft with `{countTokensHelper}`, the count step 5's token report uses:

```bash
python3 {countTokensHelper} "{export_stage_dir}/drafts/{skill-name}"
```

Bind `{count}` ← the `tokens` value of its `context-snippet.md` row (`len(text)//4`, the SKF-wide convention).

- Target: ~80-120 tokens per skill (aspirational for Quick/Forge tiers)
- Hard ceiling: 300 tokens (Deep tier may legitimately exceed 120 when gotchas carry load-bearing breaking-change notices)
- If `{count}` is above 300, trim the description, the exports list or the refs, write the draft again and measure it again, until `{count}` is 300 or below. **Do NOT drop gotchas to fit**: gotchas exist precisely to deliver the "do not rely on training data" signal and are the last thing to cut

When the helper exits non-zero, delete the `{export_stage_dir}` folder and HALT (exit code 4, `halt_reason: "context-rebuild-failed"`, phase `generate-snippet §4`): "SKF cannot measure the snippet: {the helper's error}. Re-install SKF and re-run the export."

### 5. Preview the Snippet

Nothing is written to a skill package in this step: step 4 copies each measured draft into its package after its [C] gate (§9c), and a dry run never does.

**If dry-run mode:**

"**[DRY RUN] context-snippet.md would be written to:**
`{resolved_skill_package}/context-snippet.md`

**Content:**
```
{generated snippet content}
```

**Estimated tokens:** {count}"

**If NOT dry-run:**

"**context-snippet.md staged.** Step 4 writes it to `{resolved_skill_package}/context-snippet.md` once its context-update gate passes.
**Estimated tokens:** {count}"

### 6. Proceed to Context Update

Display: "**Proceeding to context update...**"

Auto-proceed (no user choices): once each snippet is staged (or generation is skipped via the `passive_context` opt-out), load, read entirely, and execute `{nextStepFile}`.

