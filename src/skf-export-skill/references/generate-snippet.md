---
nextStepFile: 'update-context.md'
snippetFormatData: '{snippetFormatPath}'
# SKILL.md's On Activation resolved {countTokensHelper}, which measures the
# staged draft in §4, and {manifestOpsHelper}, whose `get` reads the skill's
# manifest entry in §3a.
---

<!-- Config: communicate in {communication_language}. Generate snippet content in {document_output_language}. -->

# Step 2: Generate Snippet

## STEP GOAL:

To generate or update context-snippet.md for the skill in the Vercel-aligned indexed format, targeting ~80-120 tokens per skill with T1-now content only.

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

Before generating new snippet content, check for a prior snippet:

1. Read `{resolved_skill_package}/context-snippet.md` if it exists (resolved in step 1 — see `knowledge/version-paths.md`)
2. If it exists, extract the `|gotchas:` line (if any). Trim leading whitespace and the `|gotchas:` prefix, then capture the remaining content as `prior_gotchas_content`.
3. **Split it into pitfalls and detect the carry-forward marker:** split `prior_gotchas_content` on the pitfall separator {snippetFormatData} gives (`; `), and keep the pitfalls, in order, as `prior_gotchas`. A `; ` is a separator only when an even number of backticks precede it (it is outside a code span) and every `(` before it outside a code span is closed before it (a `)` outside a code span closes the last `(` still open, and one with no `(` open closes nothing); any other `; ` stays inside its pitfall. A split that gives more than 3 pieces comes from a line §3a never writes, such as an older or hand-written one: the whole value is then one pitfall, already carried when it starts with `[CARRIED]`. §3a counts such a value as unbacked, even when the current SKILL.md states each of its pitfalls, unless one T2-future annotation, or one bullet, row or Quick Start call of §3a's source 2, states it whole: a T2-future annotation and the SKILL.md places of §3a's source 2 give its still-true pitfalls back as new gotchas, and one that only other SKILL.md prose states is dropped with the value, which gets at most one `[CARRIED]` cycle. A pitfall that starts with the token `[CARRIED]` (whitespace-insensitive) is **already carried**: strip the marker and record that. A line an older export marked once at its start (`[CARRIED] a, b`) reads as one pitfall, already carried.
4. **Distinguish empty from absent:** If the `|gotchas:` line exists but has no non-whitespace content after the prefix, treat it as **absent** — set `prior_gotchas = null`. Only a non-empty value counts as a prior gotchas line worth carrying forward.
5. **Capture the prior api names:** if the prior snippet has an `|api:` line, split its value on commas, drop each name's trailing `()` and surrounding spaces, and capture the names, in order, as `prior_api` (no `()`, no spaces), noting each name the line wrote with `()`. With no `|api:` line, `prior_api` is empty.
6. If no prior snippet exists at all, set `prior_gotchas = null` and `prior_api` to an empty list.

§3a gives the gotchas line's free slots to the prior pitfalls no current source states, and §3b ranks the `prior_api` names first. The `[CARRIED]` marker provides a **hard one-cycle expiry**: a pitfall already carried once is dropped on the next export rather than preserved indefinitely.

### 2.7. Resolve Skill Root Path

**If `{snippet_skill_root_override}` is set** (by `config.yaml`, or for this run by step 1's snippet-root option (d)): use its value directly as `{skill_root}` and skip the IDE-mapping lookup below. This is the authoring-repo escape hatch, for repos where skills live under a single shared directory (e.g. `skills/`) that does not match any per-IDE skill root. Log: "Using snippet_skill_root_override: `{override}`, bypassing the IDE mapping for the snippet root path."

**Otherwise (default):** Using the first entry in `target_context_files` (resolved in step 1), take its `skill_root` value. This is the IDE's actual skill directory (e.g., `.claude/skills/`, `.windsurf/skills/`, `.github/skills/`).

Store `{skill_root}` for use in snippet generation: it is the snippet's root only, the `root:` path of the context-snippet.md this step stages. It is not a context file's root: step 3 builds each context file's managed section with that target's own skill root, so with `ides` [claude-code, codex] the AGENTS.md rows take `.agents/skills/` while the snippet keeps `.claude/skills/`.

### 2.8. Stage Folder

Once per run (skip this when `{export_stage_dir}` is already bound, as for the second skill of a batch), create the run's stage folder outside the project and bind `{export_stage_dir}` to the path this prints:

```bash
python3 -c "import tempfile; print(tempfile.mkdtemp(prefix='skf-export-'))"
```

§4 stages each skill's snippet draft there, under `drafts/{skill-name}/`, and step 3 stages each context file's new section there, under `previews/`, so a dry run leaves nothing beside a skill package or a context file. Step 3 deletes the folder on every exit, cancels and halts included.

### 3. Generate Snippet Content

#### 3a. Gotchas (Both Skill Types)

Derive the gotchas (breaking changes, deprecations, async requirements and version-specific behavior) from the current sources. A gotcha is **derived** when a current source states it:

1. **The evidence report:** a T2-future annotation in the evidence report at `{forge_evidence_report}`, when step 1 §2 bound that path (when it is null, the skill has no evidence report to read).
2. **The current SKILL.md** (`{resolved_skill_package}/SKILL.md`, the published, test-verified artifact): a bullet of a section whose heading names gotchas, deprecations, migration, breaking changes or import corrections (such as `## Migration & Deprecation Warnings`), a `## Key API Summary` row whose purpose says deprecated or removed, and an async requirement its Quick Start shows (an API it calls with `await`).
3. **A prior pitfall still stated:** a pitfall of `prior_gotchas` (§2.5), already carried or not, that source 1 states or that the current SKILL.md still says anywhere (its frontmatter `description` and its whole body, not only source 2's places), kept in its prior wording without the `[CARRIED]` marker. SKILL.md still says a pitfall when it states the pitfall's main claim (what to do or avoid, with any version or name the pitfall gives) in SKILL.md's own words: a detail the pitfall adds need not appear, and a pitfall whose main claim SKILL.md no longer states, or now contradicts with another version or name in any place (even while another place still states it), stays unbacked. New gotchas come only from source 1 and source 2's places: a pitfall SKILL.md states only elsewhere is kept when the prior line holds it, never added as a new one. SKILL.md prose outside source 2's places backs only a prior pitfall that is one pitfall (a parenthesis that adds detail to it does not make it several): one that joins several pitfalls that each warn on their own is still stated only when one T2-future annotation, or one bullet, row or Quick Start call of source 2, states it whole, every pitfall it joins included, so it stays unbacked when SKILL.md states its pitfalls only apart or only in other prose, such as a value §2.5 reads whole, the one pitfall that value reads back as once §3a has written it (its `; ` written as `, `), or an older export's line that joined its pitfalls with `, `. A prior pitfall that source 1 or source 2 states, one that joins several included, is written once, as that prior pitfall in its prior wording, never also as a new gotcha.

A gotcha the current SKILL.md states is therefore derived even when the evidence report records no T2-future annotation. `[CARRIED]` applies only to a prior pitfall no current source backs.

**Detect first-export state before applying carry-forward logic.** The `[CARRIED]` one-cycle expiry is meaningful only on a *re-export*. On a first export, the prior `context-snippet.md` was written by the workflow that built or updated the skill (create-skill, create-stack-skill, quick-skill or update-skill) inside the same forge cycle: those gotchas are freshly derived, not "left over from a previous export." Treating them as carry-forward primes them for premature expiry on the second export.

Read the skill's manifest entry: `python3 {manifestOpsHelper} {skills_output_folder} get {skill-name}`. When it returns `not_found`, or an `entry` none of whose `versions` records a `last_exported`, this is a first export: set `is_first_export = true`. Otherwise `is_first_export = false`. The helper returns the entry in the v2 shape whatever is on disk, so a v1 manifest reads the same here as in step 3.

Resolve the gotchas line by this decision tree. The line holds at most 3 pitfalls, joined by the separator {snippetFormatData} gives (`|gotchas: {pitfall-1}; {pitfall-2}; {pitfall-3}`). A pitfall never holds the separator: in every pitfall the line writes, a prior one kept or carried included, write a `; ` outside a code span as `, ` (a code span keeps its `; `). A prior pitfall no current source states is **unbacked**.

- **If gotchas are derived:** Write them first, with no marker: the prior pitfalls a current source still states, in their prior order (source 3, a pitfall only SKILL.md's prose states included), then the new ones, in source order (source 1, then source 2 in SKILL.md order), the first 3 of them. Each slot left free goes to an unbacked prior pitfall, in prior order, by the next three branches; when no gotcha is derived, all 3 slots are free. When a new gotcha gets no slot, emit warning: "**New gotchas left off the line:** {each one, with where it is stated: the evidence report's T2-future section, or the SKILL.md section, `## Key API Summary` row or Quick Start call}. The line's 3 slots went first to the prior pitfalls a T2-future annotation or the current SKILL.md still states, in their prior order, then to new gotchas in source order. Review now whether the line holds the pitfalls that matter most: to give a left-off gotcha a slot, remove from the `|gotchas:` line of `{resolved_skill_package}/context-snippet.md` a prior pitfall that SKILL.md states only in other prose, then re-run export. A pitfall a T2-future annotation or one of those SKILL.md places states comes back as a new gotcha, in source order, so removing it frees a slot only for a left-off gotcha stated before it."
- **If an unbacked prior pitfall gets a free slot AND `is_first_export == true`:** Treat it as **freshly derived** by the workflow that wrote it, and write it **without** the `[CARRIED]` marker. (The marker only applies to re-exports.) No warning needed; this is the normal first-export shape.
- **If an unbacked prior pitfall gets a free slot AND `is_first_export == false` AND it is not already carried:** First carry-forward cycle on a re-export: write it as `[CARRIED] {pitfall}`, beside any derived ones, so the next export can detect that expiry has been reached. Emit warning: "**Gotchas preserved from prior export (one-cycle carry-forward):** {the pitfalls}. They will be DROPPED on the next export unless a T2-future annotation in the evidence report states them, or the current SKILL.md states them and no place in it contradicts them with another version or name, except one that joins several pitfalls, such as a whole older line, which is dropped unless one T2-future annotation, one bullet of a section whose heading names gotchas, deprecations, migration, breaking changes or import corrections, one `## Key API Summary` row whose purpose says deprecated or removed, or one Quick Start `await` call states it whole. Review now if they are still applicable."
- **If an unbacked prior pitfall is already carried (expiry reached; re-export only, as the first-export branch above takes precedence) or gets no free slot:** Drop it. Emit warning: "**Stale gotchas dropped:** {each pitfall, with why it was dropped: it was already carried forward once, or the line's 3 slots went to current gotchas, and, for one that joins several pitfalls, that no single place states it whole}. The pitfalls that do not join several no longer appear in the current SKILL.md or evidence report, or a place in SKILL.md now contradicts them with another version or name. A dropped pitfall comes back only as a new gotcha: if one is still relevant, re-forge the skill with update-skill so its SKILL.md states it in a bullet of a section whose heading names gotchas, deprecations, migration, breaking changes or import corrections, in a `## Key API Summary` row whose purpose says deprecated or removed, or as an async requirement its Quick Start shows (other SKILL.md prose that says it does not add it back), or add it to the evidence report's T2-future section, then re-run export. For one that joins several pitfalls, state it whole in one such place, or each of its pitfalls in its own."
- **If no pitfall is written:** Omit the gotchas line.

#### 3b. Single Skills (`skill_type: "single"`)

1. Read metadata.json for `version`, `exports` array
2. **Rank the api names**, so the `|api:` line stays the same from export to export while the surface does: first the `prior_api` names (the prior snippet's `|api:` line, §2.5), in order; then the names of the rows of SKILL.md's `## Key API Summary` table, in row order (for a component library, the Key Components of its `## Component Catalog` rows; for a reference app, the surfaces of its `## Pattern Surface` rows); then the metadata.json `exports`, in order. Match a row's name to `exports` without backticks, `()`, a module qualifier (`cognee.add` is `add`) or generic parameters (`Meta<T = Args>` is `Meta`), and split a cell that names several on `/` (a Key Components cell on commas). Take each name once, only when metadata.json `exports` lists it, and never one the current SKILL.md marks deprecated or removed: a bullet of a section whose heading names deprecations, migration or breaking changes gives it as the deprecated, removed or renamed name (not as its replacement), or its `## Key API Summary` row's purpose says deprecated or removed. Keep the first 10 for the Deep tier, 5 for the other tiers. Write each `prior_api` name as the prior `|api:` line wrote it, with `()` or bare, whatever its `export_type`: a kind does not say how the line marks a name (an AST recipe labels a const arrow function `function` where a by-eye read can label it `const`, and a component declared with `function` is labeled `function` though the line can write it bare), so a kind never changes the mark of a name the line lists. A name new to the line (one `prior_api` does not hold, every name when there is no prior snippet) takes `()` when its `export_type` in the provenance map at `{forge_provenance_map}` is a function, and is written bare for any other kind, or when that map is null or gives no kind for the name.
3. Read SKILL.md to extract: heading slugs for `#quick-start` and `#key-types`, inline summary of key types (~10 words)
4. **Anchor verification (split-body awareness):** For each section anchor (`#quick-start`, `#key-types`): when SKILL.md has the heading, keep `SKILL.md#{slug}`. Only when SKILL.md lacks the heading and the skill is split-body (a `references/` directory exists and the `## Full` headings in SKILL.md are absent or stubs; not a stack skill's structural references), point the anchor at the `references/{file}.md#{slug}` that holds the heading. When neither holds it, omit that anchor line from the snippet.

Emit the single-skill template from {snippetFormatData} (loaded in §2), filling `api` from the names ranked above (all of them when fewer than the limit; omit the line when there are none), `key-types` from the inline summary extracted above, and `gotchas` per the §3a decision tree (omit the line when it resolves to none).

#### 3c. Stack Skills (`skill_type: "stack"`)

Emit the stack-skill template from {snippetFormatData}, filling `stack` from metadata.json `components` and `integrations` from metadata.json `integrations`.

Stack skills: apply the gotchas decision tree above unchanged, including the first-export branch.

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

