---
nextStepFile: 'update-context.md'
snippetFormatData: '{snippetFormatPath}'
---

<!-- Config: communicate in {communication_language}. Generate snippet content in {document_output_language}. -->

# Step 2: Generate Snippet

## STEP GOAL:

To generate or update context-snippet.md for the skill in the Vercel-aligned indexed format, with T1-now content only.

## Rules

- Focus only on generating the context-snippet.md content — T1-now only, no T2 annotations
- If `passive_context: false` was detected in step 1, skip this step entirely
- **Multi-skill mode:** when step 1 loaded more than one skill (`len(skill_batch) > 1`), iterate sections 2 to 5 per skill. Each skill has its own prior snippet state (§2.5: its `prior_gotchas` carry-forward and its `prior_api`): do not share state across skills. §2.7 resolves `{skill_root}`, the snippet's root only, and §2.8 creates the stage folder once for the run (neither depends on the skill).
- Every HALT names its exit code, `halt_reason` and phase; in headless mode it first emits its envelope as `references/result-envelope.md` states

## MANDATORY SEQUENCE

### 1. Check Passive Context Setting

**If `passive_context: false` was detected in step 1:**

"**Passive context disabled in preferences.yaml. Skipping snippet generation.**"

Auto-proceed immediately to {nextStepFile}.

**If `passive_context: true` (default):** Continue to §2.

### 2. Load Snippet Format

Load {snippetFormatData} and read the format template for the skill type.

### 2.5. Check Existing Snippet

Read the prior snippet's `|gotchas:` and `|api:` lines, and whether an export wrote it, with the helper:

```bash
python3 {rebuildManagedSectionsHelper} gotchas prior "{resolved_skill_package}/context-snippet.md" --skills-folder "{skills_output_folder}" --skill {skill-name}
```

Bind `prior_gotchas` ← its `prior_gotchas` (each prior pitfall, in line order, as `{text, already_carried, read_whole}`: `already_carried` when the line marked it `[CARRIED]`, `read_whole` for an older or hand-written value of more than 3 pitfalls read as one; null for no prior snippet, no `|gotchas:` line or an empty one), `prior_api` ← its `prior_api` (each name, in line order, as `{name, parens}`: `parens` when the line wrote it with `()`; `[]` with no `|api:` line) and `is_first_export` ← its `is_first_export` (true until an export records the skill in the export manifest).

When it exits non-zero, delete the `{export_stage_dir}` folder when it is bound and HALT (exit code 4, `halt_reason: "context-rebuild-failed"`, phase `generate-snippet §2.5`): "SKF cannot read the prior snippet of {skill-name}: {its error}. Fix the file it names, then re-run the export."

### 2.7. Resolve Skill Root Path

**If `{snippet_skill_root_override}` is set** (by `config.yaml`, or for this run by step 1's snippet-root option (d)): use its value directly as `{skill_root}` and skip the IDE-mapping lookup below. This is the authoring-repo escape hatch, for repos where skills live under a single shared directory (e.g. `skills/`) that does not match any per-IDE skill root. Log: "Using snippet_skill_root_override: `{override}`, bypassing the IDE mapping for the snippet root path."

**Otherwise (default):** Using the first entry in `target_context_files` (resolved in step 1), take its `skill_root` value. This is the IDE's actual skill directory (e.g., `.claude/skills/`, `.windsurf/skills/`, `.github/skills/`).

Store `{skill_root}` for use in snippet generation: it is the snippet's root only, the `root:` path of the context-snippet.md this step stages. It is not a context file's root: step 3 builds each context file's managed section with that target's own skill root, so with `ides` [claude-code, codex] the AGENTS.md rows take `.agents/skills/` while the snippet keeps `.claude/skills/`.

### 2.8. Stage Folder

Once per run (skip this when `{export_stage_dir}` is already bound, as for the second skill of a batch), create the run's stage folder outside the project and bind `{export_stage_dir}` to the path this prints:

```bash
python3 -c "import tempfile; print(tempfile.mkdtemp(prefix='skf-export-'))"
```

§3a writes each skill's gotchas judgments there, under `gotchas/`, §4 stages each skill's snippet draft there, under `drafts/{skill-name}/`, and step 3 stages each context file's new section there, under `previews/`, so a dry run leaves nothing beside a skill package or a context file. Step 3 deletes the folder on every exit, cancels and halts included.

### 3. Generate Snippet Content

#### 3a. Gotchas (Both Skill Types)

Derive the gotchas (breaking changes, deprecations, async requirements and version-specific behavior) from the current sources. A gotcha is **derived** when a current source states it:

1. **The evidence report:** a T2-future annotation in the evidence report at `{forge_evidence_report}`, when step 1 §2 bound that path (when it is null, the skill has no evidence report to read).
2. **The current SKILL.md** (`{resolved_skill_package}/SKILL.md`, the published, test-verified artifact): a bullet of a section whose heading names gotchas, deprecations, migration, breaking changes or import corrections (such as `## Migration & Deprecation Warnings`), a `## Key API Summary` row whose purpose says deprecated or removed, and an async requirement its Quick Start shows (an API it calls with `await`).
3. **A prior pitfall still stated:** a pitfall of `prior_gotchas` (§2.5), already carried or not, that source 1 states or that the current SKILL.md still says anywhere (its frontmatter `description` and its whole body, not only source 2's places), kept in its prior wording without the `[CARRIED]` marker. SKILL.md still says a pitfall when it states the pitfall's main claim (what to do or avoid, with any version or name the pitfall gives) in SKILL.md's own words: a detail the pitfall adds need not appear, and a pitfall whose main claim SKILL.md no longer states, or now contradicts with another version or name in any place (even while another place still states it), stays unbacked. New gotchas come only from source 1 and source 2's places: a pitfall SKILL.md states only elsewhere is kept when the prior line holds it, never added as a new one. SKILL.md prose outside source 2's places backs only a prior pitfall that is one pitfall (a parenthesis that adds detail to it does not make it several): one that joins several pitfalls that each warn on their own is still stated only when one T2-future annotation, or one bullet, row or Quick Start call of source 2, states it whole, every pitfall it joins included, so it stays unbacked when SKILL.md states its pitfalls only apart or only in other prose, such as a pitfall `gotchas prior` marks `read_whole`, the one pitfall it reads back as once §3a has written it (its `; ` written as `, `), or an older export's line that joined its pitfalls with `, `. A prior pitfall that source 1 or source 2 states, one that joins several included, is written once, as that prior pitfall in its prior wording, never also as a new gotcha.

A gotcha the current SKILL.md states is therefore derived even when the evidence report records no T2-future annotation. `[CARRIED]` applies only to a prior pitfall no current source backs.

Write your judgments to `{export_stage_dir}/gotchas/{skill-name}.json` with your file-write tool (a pitfall can hold backticks, quotes or `$`), as one JSON object: `backed` holds one `true` or `false` per `prior_gotchas` entry, in its order (`[]` when `prior_gotchas` is null), true when source 3 keeps that pitfall and false when no current source backs it; `new_gotchas` holds the other gotchas source 1 and source 2's places state, in source order (source 1, then source 2 in SKILL.md order), each on one line and without a `[CARRIED]` marker.

```json
{"backed": [true, false], "new_gotchas": ["`parse()` throws on an unknown key since v4"]}
```

Then place them on the line:

```bash
python3 {rebuildManagedSectionsHelper} gotchas resolve "{resolved_skill_package}/context-snippet.md" --skills-folder "{skills_output_folder}" --skill {skill-name} --judgments "{export_stage_dir}/gotchas/{skill-name}.json"
```

The helper reads `prior_gotchas` and `is_first_export` again and applies the slot order, the `[CARRIED]` marker with its one-cycle expiry and the `; ` separator, and on a first export it writes an unbacked prior pitfall unmarked, since the workflow that built or updated the skill (create-skill, create-stack-skill, quick-skill or update-skill) wrote that line. Bind `{gotchas_line}` ← its `line` (null when it writes no pitfall), and emit each warning its result calls for:

- **When `left_off` is not empty**, emit warning: "**New gotchas left off the line:** {each one, with where it is stated: the evidence report's T2-future section, or the SKILL.md section, `## Key API Summary` row or Quick Start call}. The line's 3 slots went first to the prior pitfalls a T2-future annotation or the current SKILL.md still states, in their prior order, then to new gotchas in source order. Review now whether the line holds the pitfalls that matter most: to give a left-off gotcha a slot, remove from the `|gotchas:` line of `{resolved_skill_package}/context-snippet.md` a prior pitfall that SKILL.md states only in other prose, then re-run export. A pitfall a T2-future annotation or one of those SKILL.md places states comes back as a new gotcha, in source order, so removing it frees a slot only for a left-off gotcha stated before it."
- **When `carried` is not empty**, emit warning: "**Gotchas preserved from prior export (one-cycle carry-forward):** {the pitfalls}. They will be DROPPED on the next export unless a T2-future annotation in the evidence report states them, or the current SKILL.md states them and no place in it contradicts them with another version or name, except one that joins several pitfalls, such as a whole older line, which is dropped unless one T2-future annotation, one bullet of a section whose heading names gotchas, deprecations, migration, breaking changes or import corrections, one `## Key API Summary` row whose purpose says deprecated or removed, or one Quick Start `await` call states it whole. Review now if they are still applicable."
- **When `dropped` is not empty**, emit warning, each pitfall's `reason` saying why it was dropped (`already-carried`: it was already carried forward once; `no-slot`: the line's 3 slots went to current gotchas): "**Stale gotchas dropped:** {each pitfall, with why it was dropped: it was already carried forward once, or the line's 3 slots went to current gotchas, and, for one that joins several pitfalls, that no single place states it whole}. The pitfalls that do not join several no longer appear in the current SKILL.md or evidence report, or a place in SKILL.md now contradicts them with another version or name. A dropped pitfall comes back only as a new gotcha: if one is still relevant, re-forge the skill with update-skill so its SKILL.md states it in a bullet of a section whose heading names gotchas, deprecations, migration, breaking changes or import corrections, in a `## Key API Summary` row whose purpose says deprecated or removed, or as an async requirement its Quick Start shows (other SKILL.md prose that says it does not add it back), or add it to the evidence report's T2-future section, then re-run export. For one that joins several pitfalls, state it whole in one such place, or each of its pitfalls in its own."

When it exits non-zero, correct the judgments file as its `error` says and run it once more. When it fails again, delete the `{export_stage_dir}` folder and HALT (exit code 4, `halt_reason: "context-rebuild-failed"`, phase `generate-snippet §3a`): "SKF cannot place the gotchas of {skill-name}: {its error}. Re-run the export."

#### 3b. Single Skills (`skill_type: "single"`)

1. Read metadata.json for `version`, `exports` array
2. **Rank the api names**, so the `|api:` line stays the same from export to export while the surface does: first the `prior_api` names (the prior snippet's `|api:` line, §2.5), in order; then the names of the rows of SKILL.md's `## Key API Summary` table, in row order (for a component library, the Key Components of its `## Component Catalog` rows; for a reference app, the surfaces of its `## Pattern Surface` rows); then the metadata.json `exports`, in order. Match a row's name to `exports` without backticks, `()`, a module qualifier (`cognee.add` is `add`) or generic parameters (`Meta<T = Args>` is `Meta`), and split a cell that names several on `/` (a Key Components cell on commas). Take each name once, only when metadata.json `exports` lists it, and never one the current SKILL.md marks deprecated or removed: a bullet of a section whose heading names deprecations, migration or breaking changes gives it as the deprecated, removed or renamed name (not as its replacement), or its `## Key API Summary` row's purpose says deprecated or removed. Keep the first 10 for the Deep tier, 5 for the other tiers. Write each `prior_api` name as the prior `|api:` line wrote it, with `()` or bare, whatever its `export_type`: a kind does not say how the line marks a name (an AST recipe labels a const arrow function `function` where a by-eye read can label it `const`, and a component declared with `function` is labeled `function` though the line can write it bare), so a kind never changes the mark of a name the line lists. A name new to the line (one `prior_api` does not hold, every name when there is no prior snippet) takes `()` when its `export_type` in the provenance map at `{forge_provenance_map}` is a function, and is written bare for any other kind, or when that map is null or gives no kind for the name.
3. Read SKILL.md to extract: heading slugs for `#quick-start` and `#key-types`, inline summary of key types (~10 words)
4. **Anchor verification (split-body awareness):** For each section anchor (`#quick-start`, `#key-types`): when SKILL.md has the heading, keep `SKILL.md#{slug}`. Only when SKILL.md lacks the heading and the skill is split-body (a `references/` directory exists and the `## Full` headings in SKILL.md are absent or stubs; not a stack skill's structural references), point the anchor at the `references/{file}.md#{slug}` that holds the heading. When neither holds it, omit that anchor line from the snippet.

Emit the single-skill template from {snippetFormatData} (loaded in §2), filling `api` from the names ranked above (all of them when fewer than the limit; omit the line when there are none), `key-types` from the inline summary extracted above, and `gotchas` from `{gotchas_line}` (omit the line when it is null).

#### 3c. Stack Skills (`skill_type: "stack"`)

Emit the stack-skill template from {snippetFormatData}, filling `version` from metadata.json `version`, `stack` from metadata.json `components`, `integrations` from metadata.json `integrations` and `gotchas` from `{gotchas_line}` (omit the line when it is null).

### 4. Verify Token Count

Write the generated snippet to `{export_stage_dir}/drafts/{skill-name}/context-snippet.md` with your file-write tool, and measure the draft with `{countTokensHelper}`, the count step 4's token report uses:

```bash
python3 {countTokensHelper} "{export_stage_dir}/drafts/{skill-name}"
```

Bind `{count}` ← the `tokens` value of its `context-snippet.md` row (`len(text)//4`, the SKF-wide convention).

- Target: ~80-120 tokens per skill (aspirational for Quick/Forge tiers)
- Hard ceiling: 300 tokens (Deep tier may legitimately exceed 120 when gotchas carry load-bearing breaking-change notices)
- If `{count}` is above 300, drop api names from the end of the §3b ranking, one at a time, writing the draft again and measuring it again after each, until `{count}` is 300 or below; only when the api line is gone and `{count}` is still above 300, shorten the key-types summary the same way. **Do NOT drop gotchas to fit**: gotchas exist precisely to deliver the "do not rely on training data" signal and are the last thing to cut

When the helper exits non-zero, delete the `{export_stage_dir}` folder and HALT (exit code 4, `halt_reason: "context-rebuild-failed"`, phase `generate-snippet §4`): "SKF cannot measure the snippet: {the helper's error}. Re-install SKF and re-run the export."

### 5. Preview the Snippet

Nothing is written to a skill package in this step: step 3 copies each measured draft into its package after its [C] gate (§9c), and a dry run never does.

**If dry-run mode:**

"**[DRY RUN] context-snippet.md would be written to:**
`{resolved_skill_package}/context-snippet.md`

**Content:**
```
{generated snippet content}
```

**Estimated tokens:** {count}"

**If NOT dry-run:**

"**context-snippet.md staged.** Step 3 writes it to `{resolved_skill_package}/context-snippet.md` once its context-update gate passes.
**Estimated tokens:** {count}"

### 6. Proceed to Context Update

Display: "**Proceeding to context update...**"

Auto-proceed (no user choices): once each snippet is staged (or generation is skipped via the `passive_context` opt-out), load, read entirely, and execute `{nextStepFile}`.

