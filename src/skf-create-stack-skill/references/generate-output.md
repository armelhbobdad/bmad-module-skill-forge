---
nextStepFile: 'validate.md'
stackSkillTemplate: 'assets/stack-skill-template.md'
provenanceMapSchemaPath: 'assets/provenance-map-schema.md'
# Resolve `{atomicWriteHelper}` by probing `{atomicWriteProbeOrder}` in order
# (installed SKF module path first, src/ dev-checkout fallback); first existing
# path wins. HALT if neither resolves — stage/commit/flip-link/write below
# MUST go through the atomic helper, per §1 rollback contract.
atomicWriteProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-atomic-write.py'
  - '{project-root}/src/shared/scripts/skf-atomic-write.py'
# Resolve `{frontmatterValidator}` by probing `{frontmatterValidatorProbeOrder}`
# in order (installed SKF module path first, src/ dev-checkout fallback); first
# existing path wins. Used by the §8 pre-commit frontmatter + body-size gate
# (`--max-body-lines`). If neither resolves, the gate degrades to a WARNING —
# step 8 (validate.md) still runs the full post-commit check.
frontmatterValidatorProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-validate-frontmatter.py'
  - '{project-root}/src/shared/scripts/skf-validate-frontmatter.py'
---

<!-- Config: communicate in {communication_language}. Artifact text in {document_output_language}. -->

# Step 7: Generate Output Files

## STEP GOAL:

Write all deliverable and workspace artifact files to their target directories.

## Rules

- Write all output files in correct directory structure — do not modify compiled content from Step 06
- Create directory structure before writing files
- Report each file written with path and size

## MANDATORY SEQUENCE

### 1. Resolve Paths and Stage Target Directory

Resolve `{version}` per S11 below — the primary library version in code-mode, or the stack-local scheme in compose-mode (`1.0.0` for a new stack, or a bump of `{prior_stack_version}` on re-composition). The final artifact paths are:

```
{skill_group}                          # {skills_output_folder}/{project_name}-stack/
{skill_package}                        # {skills_output_folder}/{project_name}-stack/{version}/{project_name}-stack/
├── references/
│   └── integrations/
{forge_version}                        # {forge_data_folder}/{project_name}-stack/{version}/
```

Where the skill name is `{project_name}-stack` and `{version}` is the semver version (with build metadata stripped per `knowledge/version-paths.md`).

**Primary library definition (S11):** In code-mode, the primary library is the dependency with the highest import count from step 3; its `version` (from the manifest) becomes `{primary_library_version}`, falling back to `1.0.0` if unavailable. In compose-mode, the stack carries its own release identity: default `{version}` to `1.0.0` (a stack-local scheme) — do NOT borrow the highest constituent semver. Constituent versions are preserved in `dependencies[]`, so no information is lost, and the package no longer reads as tracking whichever constituent happened to have the highest version. The `1.0.0` default applies only to a **genuinely new** stack — see the re-composition rule below.

**Re-composition versioning (S11, compose-mode):** When the S3 pre-flight resolves a `{prior_stack_version}` (re-composing a stack that already has a release line), continue that line instead of resetting — defaulting to `1.0.0` would publish a version *below* the existing release (e.g. `1.0.0` shadowing a prior `3.0.5`, a backward jump). Bump `{prior_stack_version}`:

- **Major** if any library in `{prior_libraries}` is removed or replaced — dropping a documented library is breaking for consumers of the stack.
- **Minor** otherwise — libraries only added, and/or integration content changed (backward-compatible).

Never emit a `{version}` ≤ `{prior_stack_version}`. Narrate the resolved version and the bump rationale.

**Pre-flight: group-dir type check (S3):** If `{skills_output_folder}/{project_name}-stack/` already exists, probe `{skills_output_folder}/{project_name}-stack/active/{project_name}-stack/metadata.json`. If that metadata exists and `skill_type != "stack"`, HALT with:

"**Cannot proceed.** `{skills_output_folder}/{project_name}-stack/` exists but is not a stack skill (`skill_type={found_type}`). Rename the existing directory or choose a different `project_name` to avoid collision."

Do NOT proceed to staging or commit.

If that metadata exists and `skill_type == "stack"`, this run is a **re-composition**: capture its `version` as `{prior_stack_version}` and its `libraries` array as `{prior_libraries}` for the S11 re-composition rule above. If the group dir is absent — or exists but has no resolvable `active` stack metadata — treat this as a new stack and leave `{prior_stack_version}` unset.

**Atomic write strategy (C2 / B5):** All artifact writes for `{skill_package}` MUST stage into a temp directory first, then commit atomically via `skf-atomic-write.py commit-dir`. The active symlink flip only happens AFTER the commit succeeds.

Create the staging directory:

```bash
python3 {atomicWriteHelper} stage-dir --target {skill_package}
```

After this call, writes land in `{skill_package}.skf-tmp/` (referred to below as `{skill_staging}`). Create the required subdirectories inside the staging dir:

```bash
mkdir -p {skill_staging}/references/integrations
```

Also create the forge workspace directory directly (these are workspace artifacts, not deliverables — they do not need stage-dir / commit-dir):

```bash
mkdir -p {forge_version}
```

**Rollback contract:** If ANY write in sections 2–7 below fails, immediately run:

```bash
python3 {atomicWriteHelper} commit-dir --rollback --target {skill_package}
```

Then abort with a structured error contract (see B7): purge any `{forge_version}/*-tmp` staging artifacts, emit `{"status":"error","skill":"skf-create-stack-skill","stage":"step 7","reason":"<message>"}` on stderr, and halt the workflow.

### 2. Stage SKILL.md

Write the approved `skill_content` from step 06 to `{skill_staging}/SKILL.md` (regular write — the whole staging dir will be atomically committed later).

### 3. Stage Per-Library Reference Files

For each confirmed library, write `{skill_staging}/references/{library_name}.md`:

Load structure from `{stackSkillTemplate}` references section:
- Library name, version from manifest (**in compose-mode**: version from source skill `metadata.json`)
- Import count and file count (**in compose-mode**: export count from source skill metadata)
- Key exports with signatures
- Usage patterns with file:line citations (**in compose-mode**: usage patterns from source skill SKILL.md)
- Confidence tier label

**If the catalog was extracted** (large stack — step 06 §4 placed the `Library Reference Index` + `Per-Library Summaries` out of SKILL.md), also write `{skill_staging}/references/stack-catalog.md` using the structure in `{stackSkillTemplate}`, and confirm SKILL.md carries the inline pointer instead of the two sections. Small stacks keep the catalog inline and write no `stack-catalog.md`.

### 4. Stage Integration Pair Reference Files

For each detected integration pair, write `{skill_staging}/references/integrations/{libraryA}-{libraryB}.md`:

Load structure from `{stackSkillTemplate}` integrations section:
- Library pair and integration type
- Co-import file count
- Integration pattern description with file:line citations
- Usage convention
- Confidence tier label

**If no integrations detected:** Skip this section (no files to write).

### 5. Stage context-snippet.md

Write `{skill_staging}/context-snippet.md`:

Use the Vercel-aligned indexed format targeting **~80-120 tokens** (M2). Token estimation is heuristic — use `ceil(char_count / 4)` as the working approximation (the standard rule-of-thumb for English text in BPE-style tokenizers; precise counts differ per model). Compute against the rendered snippet body (excluding trailing newline).

```
[{project_name}-stack v{version — per S11: code-mode primary_library_version or 1.0.0; compose-mode stack-local scheme — 1.0.0 for a new stack, or the bumped {prior_stack_version} on re-composition}]|root: skills/{project_name}-stack/
|IMPORTANT: {project_name}-stack — read SKILL.md before writing integration code. Do NOT rely on training data.
|stack: {dep-1}@{v1}, {dep-2}@{v2}, {dep-3}@{v3}
|integrations: {pattern-1}, {pattern-2}
|gotchas: {1-2 most critical integration pitfalls}
```

**Overflow strategy (M2):** If the estimated token count exceeds **120 tokens**, trim in this fixed order until under budget:

1. **Drop the `gotchas` line first.** Pitfalls live in SKILL.md and references; the snippet's job is discovery, not full warning surface.
2. **Strip versions from the `stack` line** (`{dep-1}, {dep-2}` instead of `{dep-1}@{v1}`). Versions are recoverable from `metadata.json`.
3. **Truncate the `stack` list to the top 8 dependencies by import count** (or by export count in compose-mode), appending `, ...+{N} more`.
4. **Truncate the `integrations` list to the top 5 by file count**, appending `, ...+{N} more`.

If the snippet is still over budget after step 4, log a warning to workflow_warnings (see Workflow Rules in SKILL.md) — do not block the write. The `IMPORTANT:` line is mandatory and never trimmed.

**Underflow note:** Snippets below ~80 tokens are acceptable (small stacks naturally produce short snippets). The lower bound is informational, not enforced.

### 6. Stage metadata.json

Write `{skill_staging}/metadata.json`:

Populate all fields from the metadata.json schema defined in `{stackSkillTemplate}`.

**Tier fields:**
- `forge_tier` — the run tier (Quick/Forge/Forge+/Deep) resolved in step 1.
- `confidence_tier` — the dominant T-code from `confidence_distribution`. Pick the tier with the highest count; resolve ties toward the weaker tier (T1-low > T1, T2 > T1-low, T3 > T2) so the reported value never overstates confidence. When `confidence_distribution` is empty (no libraries extracted), emit `"T1-low"` as the conservative default.

```json
{
  "skill_type": "stack",
  "name": "{project_name}-stack",
  "version": "{version — resolved per S11: code-mode primary_library_version or 1.0.0; compose-mode 1.0.0 (new stack) or bumped {prior_stack_version} (re-composition)}",
  "generation_date": "{current_date}",
  "forge_tier": "{Quick|Forge|Forge+|Deep — the tier under which this run executed}",
  "confidence_tier": "{T1|T1-low|T2|T3 — dominant T-code from confidence_distribution below}",
  "spec_version": "1.3",
  "source_authority": "{official|community|internal — use the lowest authority among constituent skills}",
  "generated_by": "create-stack-skill",
  "exports": [],
  "library_count": N,
  "integration_count": N,
  "libraries": ["lib1", "lib2"],
  "integration_pairs": [["lib1", "lib2"]],
  "language": "{primary language or list of languages from constituent skills}",
  "ast_node_count": "{number or omit if no AST extraction performed}",
  "confidence_distribution": {"t1": N, "t1_low": N, "t2": N, "t3": N},
  "tool_versions": {
    "ast_grep": "{version or null}",
    "qmd": "{version or null}",
    "skf": "{skf_version}"
  },
  "stats": {
    "exports_documented": N,
    "exports_public_api": N,
    "exports_internal": N,
    "exports_total": N,
    "public_api_coverage": 0.0,
    "total_coverage": 0.0,
    "scripts_count": N,
    "assets_count": N
  },
  "dependencies": [],
  "compatibility": "{semver-range}"
}
```

### 7. Write Forge Data Artifacts (Workspace)

Write workspace artifacts directly to `{forge_version}` (these are workspace-only, not part of the skill package — no staging required). Each individual file MUST be written via `skf-atomic-write.py write` to avoid partial-write corruption:

```bash
<json-content> | python3 {atomicWriteHelper} write --target {forge_version}/provenance-map.json
<md-content>   | python3 {atomicWriteHelper} write --target {forge_version}/evidence-report.md
```

If any workspace write fails, invoke the rollback contract from §1.

**provenance-map.json:**

Use the schema from `{provenanceMapSchemaPath}` — see that asset for the canonical templates and field definitions of both variants:

- **In code-mode:** use the code-mode variant (`source_repo` / `source_commit` populated; `extraction_method` ∈ `ast_bridge|source_reading|qmd_bridge`; `detection_method = "co-import grep"`).
- **In compose-mode:** use the compose-mode variant (source-anchor fields `null`; `extraction_method = "compose-from-skill"`; `detection_method ∈ "architecture_co_mention|constituent_documented_contract|inferred_from_shared_domain"`; includes the additional `constituents[]` array for drift detection).

**Use the `metadata_hash` value already stored in workflow state during step 2 (S13) — do NOT re-read and re-hash at step 7 time. The stored hash captures the state as it was at manifest-detection time, which is the correct provenance anchor.**

**evidence-report.md:**
- Extraction summary per library
- Integration detection results per pair
- Warnings and failures encountered
- Confidence tier distribution

### 8. Pre-Commit Frontmatter & Body-Size Gate

The full schema/frontmatter validation runs in step 8 (`validate.md`) — but that runs *after* commit-dir and flip-link have already published the package. The two most common non-auto-fixable `skill-check` hard rejects — a `description` over the 1024-char limit (which `skill-check --fix` cannot trim for you) and a SKILL.md body over the `body.max_lines` limit (default **500**) — would therefore only surface on an already-committed, symlink-active artifact, forcing edits to the live `SKILL.md`. Additive re-composition of an already-large stack grows the body monotonically, so the body overflow is the likeliest trigger. Catch both here, while the package is still in `.skf-tmp`.

Resolve `{frontmatterValidator}` from `{frontmatterValidatorProbeOrder}` (first existing path wins). Run it against the **staged** `SKILL.md`, passing the real skill name so the directory-match check is not fooled by the `.skf-tmp` staging suffix, and `--max-body-lines 500` to assert the skill-check body limit pre-commit:

```bash
uv run {frontmatterValidator} {skill_staging}/SKILL.md --skill-dir-name {project_name}-stack --max-body-lines 500
```

The validator emits JSON: `status` (`pass`/`warn`/`fail`), `issues[]` (each with `severity` ∈ `high|medium|low`, `field`, `message`), `body_lines` (the counted body size), and `summary`. Disposition:

- **`status` is `fail`, OR any `issues[]` entry has `severity` `high` or `medium`** — a hard violation that `npx skill-check` (step 8) would reject and `--fix` cannot auto-correct. HALT-to-fix **in staging**, then re-run the validator until it clears. Remediate by `field`:
  - `description` / `name` / `compatibility` — trim/correct `{skill_staging}/SKILL.md` (e.g. shorten `description` to ≤ 1024 chars).
  - `body` (`body lines N exceeds max 500`) — reduce the staged body: prefer a **selective split** of the largest Tier-2 section(s) into `{skill_staging}/references/`, keeping Tier-1 content inline (mirrors `validate.md` §3); or trim redundant content. Re-run the gate until `body_lines ≤ 500`.

  Do NOT proceed to §9 commit-dir with an unresolved high/medium issue. Note: an over-long `description` is rated `medium` and exits `0`, so key the HALT on the issue severities above — not on the exit code.
- **Only `low`-severity issues (e.g. an unexpected field)** — record each as a WARNING in the evidence report and proceed; these do not block the commit.

**If `{frontmatterValidator}` does not resolve** (neither probe path exists) **or the invocation cannot run**, emit a WARNING ("pre-commit frontmatter + body-size gate skipped — validator unavailable") and proceed. Step 8 (`validate.md`) remains the post-commit backstop (including the `body.max_lines` split path in its §3); this gate is a best-effort early catch, never a new hard dependency.

### 9. Commit Staging Directory

After all staged writes in sections 2–6 completed successfully, atomically swap the staging dir into place:

```bash
python3 {atomicWriteHelper} commit-dir --target {skill_package}
```

The helper moves any existing `{skill_package}` aside to a `.skf-rollback-<pid>` dir before the swap. On failure the helper restores the prior target and exits non-zero — in that case invoke the rollback contract from §1 and HALT.

### 10. Flip Active Symlink

ONLY AFTER `commit-dir` succeeds, flip the `{skill_group}/active` symlink to point at `{version}`:

```bash
python3 {atomicWriteHelper} flip-link --link {skill_group}/active --target {version}
```

The helper holds an flock on `{skill_group}/active.skf-lock` and refuses to replace a non-symlink at `{skill_group}/active` — this guards against accidentally overwriting a real directory (ECH BLOCKER 6/B6). After the flip, `{skill_group}/active/{project_name}-stack/` resolves to the just-committed skill package.

If `flip-link` fails, emit a warning (the committed package is still valid), note the symlink-flip failure in the evidence report, and continue.

### 11. Display Write Summary

"**Output files written.**

**Deliverables** ({skill_package}):
- SKILL.md ({line_count} lines)
- context-snippet.md ({token_estimate} tokens)
- metadata.json
- references/ -- {lib_count} library files
- references/integrations/ -- {pair_count} integration files

**Workspace** ({forge_version}):
- provenance-map.json
- evidence-report.md

**Symlink:** {skill_group}/active -> {version}

**Total files written:** {total_count}

**Proceeding to validation...**"

### 12. Auto-Proceed to Next Step

Load, read the full file and then execute `{nextStepFile}`.

