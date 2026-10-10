---
nextStepFile: 'step-doc-sources.md'
skillSectionsData: 'assets/skill-sections.md'
assemblyRulesData: 'assets/compile-assembly-rules.md'
# Loaded only when §4's stats helper reports a provenance label violation.
relabelRuleData: 'references/relabel-rule.md'
# Resolve `{renderMetadataStatsHelper}` by probing `{renderMetadataStatsProbeOrder}`
# in order (installed SKF module path first, src/ dev-checkout fallback); first
# existing path wins. HALT (exit code 3, helper-missing) if neither
# resolves: the metadata `stats` block and `confidence_distribution` are
# computed values that must not be hand-binned (the historical 147 ≠ 59
# miscount lived exactly here).
renderMetadataStatsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-render-metadata-stats.py'
  - '{project-root}/src/shared/scripts/skf-render-metadata-stats.py'
# Resolve `{verifyProvenanceCompletenessHelper}` to the first existing path.
# Advisory: if neither resolves, §4's relabel looks up no node kind with
# `kind-at` and leaves each one it needs as a WARN.
verifyProvenanceCompletenessProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-verify-provenance-completeness.py'
  - '{project-root}/src/shared/scripts/skf-verify-provenance-completeness.py'
# Resolve `{extractionInventoryHelper}` to the first existing path. §1 reads
# the inventory's counts through its `summary`, and §6 writes the
# provenance map through its `provenance`; step 3 §5 already halted when
# neither path exists.
extractionInventoryProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-extraction-inventory.py'
  - '{project-root}/src/shared/scripts/skf-extraction-inventory.py'
# Resolve `{extractionPatternsData}` to the first existing path, as step 3
# did: the Relabel Rule's `kind-at` reads the recipes there.
extractionPatternsDataProbeOrder:
  - '{project-root}/_bmad/skf/skf-create-skill/references/extraction-patterns.md'
  - '{project-root}/src/skf-create-skill/references/extraction-patterns.md'
# HARD HALT helpers (Rules).
sourceTreeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-source-tree.py'
  - '{project-root}/src/shared/scripts/skf-source-tree.py'
emitEnvelopeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py'
  - '{project-root}/src/shared/scripts/skf-emit-result-envelope.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 5: Compile

## STEP GOAL:

To assemble the complete skill content from the extraction inventory and enrichment annotations — building SKILL.md sections, context-snippet.md, metadata.json, and references/ content according to the agentskills.io format.

## Rules

- Focus only on assembling content from extraction inventory + enrichment
- Do not include any content without a provenance citation
- Write all compiled artifacts to the staging directory `_bmad-output/.skf-stage/{skill-name}/`. Do not write to `skills/` or `forge-data/` — step 7 promotes staged artifacts to their final versioned locations.
- Do not fabricate examples not found in source tests or docs
- Seed `<!-- [MANUAL] -->` markers for future update-skill compatibility
- A HARD HALT, once step 3 §2b has bound `{source_tree}`, first runs `uv run {sourceTreeHelper} close --tree "{source_tree}"` from `{project-root}` (resolved from `{sourceTreeProbeOrder}`) and goes on whatever it prints, and emits through `{emitEnvelopeHelper}`, resolved from `{emitEnvelopeProbeOrder}` when it is not bound. After its envelope, under `--batch` it ends only this brief: return to `references/batch-mode.md` §3, even when the halt reads as the end of the run.

## MANDATORY SEQUENCE

### 1. Load Data Files

Load `{skillSectionsData}` and `{assemblyRulesData}` completely. These define the agentskills.io-compliant format and detailed assembly rules for all output artifacts.

Then load `{extraction_inventory}` (`{project-root}/_bmad-output/.skf-stage/{skill-name}.inventory.json`) completely: the extraction inventory step 3 §5 wrote, with the T3 items step 3c and the T2 annotations step 4 added. Compile from this file, not from what context still holds of steps 3 and 4: its `exports[]` (an export marked `internal: true` stays out of `metadata.json`'s `exports[]`, and one marked `public: false`, off a `public-api` skill's public surface, stays out of SKILL.md, `references/`, `metadata.json`'s `exports[]` and the provenance map), `top_exports`, `t2_annotations`, `t3_items`, `scripts_inventory`, `assets_inventory`, `intent_mapping`, `promoted_docs`, `authoritative_files_scan`, `counts`, `arms`, `aggregates`, `co_imports` and `warnings` (a component library's `component_catalog` too) are every input below. Resolve `{extractionInventoryHelper}` ← first existing path in `{extractionInventoryProbeOrder}` and, from `{project-root}`, run `uv run {extractionInventoryHelper} summary --inventory "{extraction_inventory}"`: bind `{inventory_counts}` ← its `counts`, which §7 reads.

For a whole-language reference, also load `{project-root}/_bmad-output/.skf-stage/{skill-name}.language-guide.json`, the index step 3c §4a wrote, and build `language_guide[]` from it: for each of its `language_guide` entries, in order, `{url, label, prose}`, where `prose` is the substantive body (narrative, idioms, usage examples, conceptual reference) of the pages its `pages` lists in its `docs_folder`, lightly trimmed of navigation and boilerplate, each block cited `[EXT:{url}]`, and `null` when `pages` is empty (the fetch failed). When the file is missing, or a page it lists is gone, display "The Language Guide from step 3c is missing ({the file or page}): assembling without it." and leave `language_guide[]` empty: `{assemblyRulesData}`'s empty-guide guard then assembles a standard library skill.

### 1a. Create Staging Directory

Create `_bmad-output/.skf-stage/{skill-name}/` (and `_bmad-output/.skf-stage/{skill-name}/references/`) under `{project-root}`, empty, under `.skf-stage` so it never collides with a `skills_output_folder` or `forge_data_folder` set to `_bmad-output`: SKF never reads a `.skf-` name as a skill. Remove what an earlier run of this skill left there first, since step 7 promotes the whole folder; the inventory and the runner JSON beside it stay:

```bash
rm -rf "{project-root}/_bmad-output/.skf-stage/{skill-name}" && mkdir -p "{project-root}/_bmad-output/.skf-stage/{skill-name}/references"
```

If the command fails, **HARD HALT** (exit code 4, `write-failed`, phase `compile`; stage `{run_dir}/halt.json` per the Workflow Rules and run `uv run {emitEnvelopeHelper} emit-halt --workflow skf-create-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"`), with `"path"` the staging folder: "Cannot create the staging folder `_bmad-output/.skf-stage/{skill-name}/`: {the first stderr line}."

All artifacts produced in sections 2 to 7 below are written here:

- `SKILL.md`
- `context-snippet.md`
- `metadata.json`
- `references/*.md`
- `provenance-map.json`
- `evidence-report.md`

This is the `<staging-skill-dir>` referenced by step 6 (`npx skill-check check`, the description angle-bracket check, and Tessl Review when the user opted in, which uploads a copy holding only `SKILL.md`, `references/`, `scripts/` and `assets/`). Steps 5a to 6 edit the files here, and step 7 promotes this folder byte for byte: what it holds when step 6 ends is what ships.

### 1b. Signature Fidelity Rule

**When assembling function signatures, parameter lists, and return types in any SKILL.md section or reference file:**

- **T1 provenance-map entries (AST-extracted) are authoritative** for: function name, parameter names, parameter types, parameter order, return type, and optionality markers (e.g., `?`, `Optional`, `= default`).
- **T2 (QMD-enriched) and T3 (doc-derived) sources may add** contextual descriptions, usage notes, behavioral documentation, and examples to function entries, but must not replace structural signature data from T1 entries.
- **On conflict:** If a T2/T3 source provides a different signature than the T1 extraction for the same export (e.g., different parameter count, different types, missing `Partial<>` wrapper), keep the T1 signature and log a warning in the evidence report: "Signature conflict for `{export_name}`: T1 shows `{t1_signature}`, T2/T3 shows `{other_signature}`. T1 used as authoritative."
- **`signature_source` field:** Record `signature_source: "T1" | "T1-low" | "T2" | "T3"` in each provenance-map entry to indicate the highest-confidence tier that contributed the structural signature data (params, return_type). A signature an ast-grep rule matched contributes T1; a signature read by eye contributes T1-low at any tier, so an entry with `extraction_method: source-read` never carries `signature_source: "T1"`. This enables test-skill to verify signature provenance.

This rule applies to every section including Tier 1 Key API Summary, Tier 2 Full API Reference, and Section 4b Migration & Deprecation Warnings.

### 2. Build SKILL.md Content

Assemble each section in order using the assembly rules data file (`{assemblyRulesData}`). The data file specifies frontmatter format, Tier 1 section details (Sections 1-8, including conditional Section 7b for scripts/assets), Tier 2 section details (Sections 9-11), and assembly ordering rules. Follow it exactly. Assemble Section 7b (Scripts & Assets) only if `scripts_inventory` or `assets_inventory` is non-empty.

**Shape-specific overrides:** the assembly-rules file defines gated override blocks for `component-library`, `reference-app`, and **whole-language reference** skills. Apply the override whose gate matches this brief. A whole-language reference is gated on `assembly_shape: "whole-language-reference"` (a `doc_urls` entry with `source: language-registry`, as step 3c §1 determined and as `skf-derive-assembly-shape.py` reports) and uses the `language_guide[]` step 3c §4a wrote to `{skill-name}.language-guide.json` (§1): it foregrounds the Language Guide and demotes compiler internals. When no override gate matches, assemble the standard library-export layout unchanged.

### 2a. Description Sanitization Pass

**Before writing SKILL.md frontmatter to disk**, sanitize the assembled `description` string by replacing every `<` with `{` and every `>` with `}`. Apply this pass unconditionally to the final assembled description in context, then write the result to `SKILL.md`.

**Why unconditional?** The Claude platform does not accept a skill whose `description` contains XML tags, and the description is read as a raw string before any markdown parsing, so a backticked TypeScript generic like `` `Meta<typeof X>` `` still carries raw `<` and `>`. None of the validators SKF runs checks for this — skill-check has no such rule and Tessl Review accepts angle brackets — so SKF enforces it itself: replacing every `<` and `>` is simpler and safer than deciding which ones form a tag, and step 6 §6 checks the staged description with SKF's frontmatter validator.

**Scope:** This rule applies **only** to the frontmatter `description` field. Body content, code examples, reference files, and assembly-rule documents retain their original angle brackets — they are parsed through the markdown AST where backticks do protect content.

Record the count of substitutions in context as `description_sanitizations: {count}` for the evidence report.

If a later tool rewrites the description, step 6 §0's Description Guard restores this sanitized value, and step 6 §6 checks the final description and applies this substitution again before anything is promoted.

### 3. Build context-snippet.md Content

Vercel-aligned indexed format for CLAUDE.md managed section (~80-120 tokens):

```markdown
[{skill-name} v{version}]|root: skills/{skill-name}/
|IMPORTANT: {skill-name} v{version} — read SKILL.md before writing {skill-name} code. Do NOT rely on training data.
|quick-start:{SKILL.md#quick-start}
|api: {top exports with () for functions, comma-separated}
|key-types:{SKILL.md#key-types} — {inline summary of most important type values}
|gotchas: {2-3 most critical pitfalls or breaking changes, inline}
```

**Derivation rules:**

- **version**: From source detection (reconciled in step 3), not brief default
- **api**: Top 10 exports from extraction inventory, none marked `public: false`, append `()` to function names
- **key-types**: Inline summary of most important enum/type values from Key Types section
- **gotchas**: Derived from T2-future annotations (breaking changes) of exports not marked `public: false`, async requirements, version-specific behavior changes. If no gotchas available, omit the gotchas line.
- **Section anchors** (`#quick-start`, `#key-types`): Must match actual heading slugs in the assembled SKILL.md

### 4. Build metadata.json Content

Following the structure from the skill-sections data file:
- Populate all fields from brief_data, extraction inventory, and tier
- Set `generation_date` to current ISO-8601 timestamp
- Set `source_commit` from resolved source (if available)
- Set `source_ref` from resolved source ref (tag name, branch, or `HEAD`; null if unavailable)
- Set `scope_type` from the brief's `scope.type` value verbatim (`full-library`, `specific-modules`, `public-api`, `component-library`, `reference-app`, or `docs-only`). **Always emit this field.** `skf-test-skill` keys reference-app handling on `metadata.json.scope_type == "reference-app"`: both the scoring redistribution (Signature Accuracy / Type Coverage marked N/A) and the coverage-check §4b count-coherence skip. Omitting it silently mis-scores a reference-app skill as a library (zero-export barrel HALT or false metadata-drift findings). Consumers branch on other values too, such as `public-api` in Update Skill and Audit Skill (both keep a public-api skill's exports to its public surface, as Create Skill does) and `docs-only` in Audit Skill, so emit it for all scope types and the producer/consumer contract holds.
- **Compute the `stats` block and `confidence_distribution` deterministically** with `{renderMetadataStatsHelper}` (resolve from `{renderMetadataStatsProbeOrder}`; first existing path wins; if neither exists, **HARD HALT** (exit code 3, `helper-missing`, phase `compile`; stage `{run_dir}/halt.json` per the Workflow Rules and run `uv run {emitEnvelopeHelper} emit-halt --workflow skf-create-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"`): "Cannot compute the metadata stats: skf-render-metadata-stats.py is missing. Re-install SKF, then re-run create-skill."). The helper owns all the arithmetic (binning each provenance entry once by its `signature_source` tier, summing the bins, and computing every coverage ratio) and returns the finished `stats` + `confidence_distribution` objects to write into `metadata.json` verbatim. Run `uv run {renderMetadataStatsHelper} --help` for the full contract. You supply only the judgment payload below.

  **Judgment payload (passed as JSON on stdin):** the counts come from the inventory's `counts`, which step 3 §4b took from the recipe runner's `counts` (or counted from the entry points itself without them); what you decide is whether `effective_denominator` applies.
  - `exports_public_api`: `counts.exports_public_api`, the public names the package's entry points export (`outside_scope` ones included, and a namespace counted as its `members`, the names its module passes on), never the provenance-map entry count, which misses the exports extraction did not find
  - `exports_internal`: `counts.exports_internal`, the exports the recipes found that no entry point exports or makes reachable
  - `scripts` / `assets`: the `scripts_inventory` / `assets_inventory` arrays (or `[]` when empty) — the helper sets `stats.scripts_count` / `stats.assets_count` from their lengths
  - `effective_denominator` (**optional**: include it only for the curated-subset shapes condition 1 lists): `counts.effective_denominator`, the public names whose definition file matches `scope.tier_a_include` (else `scope.include`) and no `scope.exclude` glob, each name once, so a type counts once with its methods rolled up under it, and a namespace counts as its `members` there too, each member by its own file; `counts.effective_denominator_basis` names the globs it used. When step 3 counted the entry points itself, count it by the same unit. It is the unit `skf-test-skill` re-derives on the consumer side (`coverage-check.md` §2c excludes `kind: "method"` from `documented_set`), so the producer- and test-side denominators stay aligned: counting each method would let a type-heavy API inflate the denominator by an order of magnitude and auto-fail the coverage gate. This is the coverage denominator `skf-test-skill` uses when the brief documents a curated subset rather than a package's whole barrel, so it must match the brief's authoring intent. Include it when ALL of the following hold:
    1. The skill's coverage denominator is resolved by a `skf-test-skill` `references/source-access-protocol.md` §Source API Surface Definition clause that actually consumes `effective_denominator`: one of the `arms` step 3 recorded is true. When it recorded none, judge each from the source as its parenthesis says:
       - **(a) stratified-scope:** `arms.monorepo` (a workspace layout of a kind `skf-detect-workspaces.py` detects);
       - **(b) single-crate curated subset:** `arms.specific_modules` (a `specific-modules` scope, not a monorepo);
       - **(c) multi-entry (exports-map):** `arms.multi_subpath_exports` (an in-scope `package.json` whose `exports` map has more than one non-root subpath without `*` whose target is a JS/TS file, not a monorepo).

       Arms (b) and (c) are not a widening for its own sake — both consumer clauses already say "prefer `metadata.json.stats.effective_denominator`", and a monorepo-only emit condition makes those two rungs unreachable, so a non-monorepo curated scope has no way to lock its denominator.
    2. `scope.type` is not `full-library` (and not `reference-app` — see carve-out below), AND the resolved include list (`tier_a_include` if present, else `scope.include`) lists a curated file/directory subset rather than the full workspace.
    3. `scope.notes` is present and documents the stratification strategy (e.g., a tiered A/B/C plan) — this serves as the intent marker confirming the subset is by design.

    Otherwise omit it from the payload entirely — when absent, `skf-test-skill` falls back to `exports_public_api`. See `skf-test-skill` `references/source-access-protocol.md` §Source API Surface Definition ("Stratified-scope monorepo packages", "Single-crate curated subset", "Multi-entry (exports-map) packages") for the test-side consumption rules.

    **A `public-api` scope on a single-package repo with no multi-subpath `exports` map matches none of the three arms** — that shape falls to the standard root-barrel rule, which honors neither `effective_denominator` nor `tier_a_include`. Emitting the field there has no effect on the test-side denominator, so omit it.

    **That shape has no brief-side denominator lever, and `scope.exclude` is not one.** The root-barrel rule counts the named exports of a single entry-point file (`index.ts` / `__init__.py` / `lib.rs`), so excluding *files* cannot remove exports from the barrel's own export list — the denominator is unchanged. When the brief genuinely documents a curated subset of a single package's surface (citation-only files alongside a narrow `tier_a_include`), express that with `scope.type: "specific-modules"` rather than `public-api`: the single-crate curated-subset clause in `skf-test-skill` `references/source-access-protocol.md` filters the barrel by `scope.include` / `scope.exclude` **and** honors `effective_denominator`, so condition 1 arm (b) applies and the denominator matches the authoring intent. Reserve `public-api` for the case where the whole root barrel is the intended surface.

    **Reference-app carve-out:** never emit `effective_denominator` for `scope.type: "reference-app"`, even when the three conditions above are literally satisfied (a reference-app-in-monorepo matches all of them). A reference app's coverage basis is `pattern_surfaces_documented`, not library exports — see the Reference-App stats semantics in `assets/compile-assembly-rules.md`.
- **Shape:** pass `--shape reference-app` when the reference-app assembly-rules override applies (default `library`), and also put `pattern_surfaces_documented` (the Pattern Surface row count) in the payload: the helper uses it as `exports_documented`, emits `stats.pattern_surfaces_documented`, and refuses to emit `effective_denominator`; the distribution then sums to the per-citation count, not to `exports_documented`.
- **Invoke** — stage `provenance-map.json` (§6) first, since the helper reads its `entries[]`:

  ```bash
  echo '{"exports_public_api": {N}, "exports_internal": {M}, "scripts": {scripts_inventory-or-[]}, "assets": {assets_inventory-or-[]}}' \
    | uv run {renderMetadataStatsHelper} <staging-skill-dir>/provenance-map.json
  ```

  Write the returned `stats` and `confidence_distribution` verbatim. The helper derives `exports_documented` (the documented-export count = provenance `entries[]` count, which holds no export marked `public: false`), `exports_total` = `exports_public_api` + `exports_internal`, `public_api_coverage` = documented / public_api (`null` if public_api is 0), `total_coverage` = documented / total (`null` if total is 0), and bins `confidence_distribution.{t1, t1_low, t2, t3}` by each entry's `signature_source`, **each entry counted exactly once**, so the four bins provably sum to the documented-export count. This structurally prevents the recurring miscount where binning ~8 T2 annotations + ~80 T3 doc items on top of 59 exports produced a distribution summing to 147 ≠ 59 (`skf-test-skill` coverage-check §4b flags that sum as an internal-consistency defect). If the helper reports `coherence.ok: false`, fix the provenance map and re-run the helper; never hand-edit the stats. A `confidence_distribution` violation means some provenance entries carry a missing or unrecognized `signature_source`, and a `stats.scripts_count` / `stats.assets_count` violation means a file-entry count disagrees.

  **Label violations.** A violation whose `field` is `provenance.entries[<i>].<field>` means entry `<i>` (its `export_name` is in the violation) carries a label its `extraction_method` does not allow: relabel it by the Relabel Rule in `{relabelRuleData}` (labels follow the method, a node kind comes from the recipe that matched, never invented, and a violation the rule cannot settle stays as a WARN), resolving `{verifyProvenanceCompletenessHelper}` ← first existing path in `{verifyProvenanceCompletenessProbeOrder}` for its `kind-at` lookup. Write the relabeled map back to `<staging-skill-dir>/provenance-map.json`, the copy step 7 promotes, re-run the helper, and write the `stats` and `confidence_distribution` it returns: a relabeled `signature_source` moves the distribution, and a violation left as a WARN does not block the write. Note the relabeled export names, and each WARN left, in the evidence report's Remaining Warnings (§7).
- Set `description` from the SKILL.md frontmatter `description` field (already assembled in section 2)
- Set `language` from source analysis (e.g., `"typescript"`, `"python"`) — use the primary language of the entry point file
- Set `ast_node_count` to the number of exports ast-grep matched (the recipe runner's `aggregates.exports`) when ast-grep ran, otherwise omit
- Set `tool_versions` based on tier and available tools. Resolve `{skf_version}` using this resolution chain (try each in order, use the first that succeeds):
  1. `{project-root}/_bmad/skf/package.json` → read `.version` field
  2. `node -p "require('./node_modules/bmad-module-skill-forge/package.json').version"`
  3. `{project-root}/_bmad/skf/VERSION` → read plain text file (single line containing version string, written by the SKF installer)
  4. `"unknown"` (final fallback — add a warning to the evidence report)
  Never hardcode the version.
- Resolve `{ast_grep_version}` using this resolution chain (try each in order, use the first that succeeds):
  1. `ast-grep --version` → parse version string from output (e.g., `ast-grep 0.41.1` → `"0.41.1"`)
  2. `mcp__ast-grep__find_code` tool metadata (if version is exposed by the MCP server)
  3. `"unknown"` (final fallback — add a warning to the evidence report)
- Resolve `{qmd_version}` using this resolution chain (try each in order, use the first that succeeds):
  1. `qmd --version` → parse version string from output (e.g., `qmd 2.0.1` → `"2.0.1"`)
  2. `mcp__plugin_qmd-plugin_qmd__status` → parse version if exposed in status output
  3. `"unknown"` (final fallback — add a warning to the evidence report)
  Note: QMD is a Bun/Node package (`@tobilu/qmd`). Install via `bun install -g @tobilu/qmd`.
- Store `commit_short` = first 8 characters of `source_commit` (or `"unknown"` if unavailable) for use in step 8 report.
- If `scripts_inventory` is non-empty, populate the `scripts[]` array (per-file `{file, purpose, source_file, confidence}` rows). If `assets_inventory` is non-empty, populate the `assets[]` array. Omit the `scripts[]` / `assets[]` arrays entirely when their inventory is empty — `stats.scripts_count` / `stats.assets_count` were already set by `{renderMetadataStatsHelper}` from the `scripts` / `assets` payload you passed it (0 when empty).

### 5. Build references/ Content

Create one reference file per major function group or type, of the exports the provenance map holds (never one the inventory marks `public: false`):
- Full function signatures with detailed parameter descriptions
- Complete usage examples (from source only)
- Related functions cross-references
- Temporal annotations (Deep tier: T2-past, T2-future)

Group functions logically by module, file, or functional area.

### 6. Build provenance-map.json Content

The map holds one entry per export of the inventory's `exports[]` but one marked `public: false` (export_name, export_type, params[] as typed strings, return_type, source_file, source_line, confidence, extraction_method, ast_node_type, and signature_source, the tier that contributed the structural signature: "T1", "T1-low", "T2" or "T3"), then the entries and file entries the inventory does not hold. `{extractionInventoryHelper}` writes it: never type an entry the inventory holds. From `{project-root}`, run it with the source fields §4 set in metadata.json (`null` for one that is unavailable):

```bash
uv run {extractionInventoryHelper} provenance --inventory "{extraction_inventory}" --target "{project-root}/_bmad-output/.skf-stage/{skill-name}/provenance-map.json" <<'SKF_JSON'
{"source_repo": "<source_repo>", "source_commit": "<source_commit>", "source_ref": "<source_ref>"}
SKF_JSON
```

It writes the map's header (`provenance_version` `"2.0"`, the skill's name, `skill_type` `"single"` and `generated_at`) and every export's entry, labeled by the tool that produced it, at every forge tier:

- `extraction_method: "ast-grep"` (an ast-grep rule matched the export): `confidence: "T1"`, `signature_source: "T1"`, an `[AST:...]` citation, and `ast_node_type` the `kind` the matching recipe declares in extraction-patterns.md, copied from the recipe, never inferred from the source (validate.md §7a asks ast-grep whether it is a real kind).
- `extraction_method: "source-read"` (the export was read by eye): `confidence: "T1-low"`, `signature_source: "T1-low"`, a `[SRC:...]` citation and `ast_node_type: null`.

For a `public-api` skill it writes no entry for an export the inventory marks `public: false`, off the package's public surface (step 3 §5's `init` or `add` marked it, and one of the inventory's `warnings` names each such export), and SKILL.md, `references/` and `metadata.json`'s `exports[]` leave it out too. When the runner gave no surface the rule could read, nothing is marked: every export has its entry, and an inventory warning says why.

Its `unsigned` lists the functions whose signature nobody read, which extract.md §5's `patch` left: read each one's parameters and return type from the source at its `source_line`, send them through that `patch` call as extract.md §5 says, and run the command above again, which rewrites the map.

**Then add what the inventory does not hold**, in one call, leaving out a list that is empty and the call when both are: the T2 and T3 entries (a docs-only skill's exports, from the inventory's `t3_items`), each with the fields above, and the file entries below.

```bash
uv run {extractionInventoryHelper} provenance --inventory "{extraction_inventory}" --target "{project-root}/_bmad-output/.skf-stage/{skill-name}/provenance-map.json" --add-entries <<'SKF_JSON'
{"entries": [{"export_name": "...", "export_type": "...", "params": null, "return_type": null, "source_file": "...", "source_line": null, "confidence": "T3", "extraction_method": "...", "ast_node_type": null, "signature_source": "T3"}], "file_entries": [{"file_name": "...", "file_type": "...", "source_file": "...", "content_hash": "...", "confidence": "...", "extraction_method": "..."}]}
SKF_JSON
```

The helper appends them and skips an entry whose `export_name` and `source_file` the map already holds (its `duplicates`): T2 and T3 content never replaces an inventory export's entry. Send no entry for an export the inventory marks `public: false`: the helper skips one and lists it in its `not_public`. If either call exits non-zero, fix what its `message` names and run it again; when it fails twice, **HARD HALT** (exit code 4, `write-failed`, phase `compile`; stage `{run_dir}/halt.json` per the Workflow Rules and run `uv run {emitEnvelopeHelper} emit-halt --workflow skf-create-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"`), with `"path"` the staged `provenance-map.json`: "Cannot write the provenance map: {the helper's message}. Check permissions and disk space."

`{renderMetadataStatsHelper}` (§4) checks these pairings on every T1 or T1-low entry, and the `signature_source` of an entry read by eye at any other confidence too (T2, T3 or none): the distribution bins every entry by its `signature_source`, so a `source-read` entry that claims `"T1"` is a violation whatever its `confidence`. Besides the two values above it accepts only the stack-map values `ast_bridge` (pairs with T1), `source_reading` (pairs with T1-low and a `signature_source` other than T1), `qmd_bridge` and `compose-from-skill` (no pairing); any other `extraction_method` on a T1 or T1-low entry is a violation.

**File entries:** one `file_entries[]` row, sent in the `--add-entries` call above, per tracked non-code file when any of these inventories are non-empty:

- `scripts_inventory` → `file_type: "script"`, `extraction_method: "file-copy"`, stored in `{skill_package}/scripts/` by step 7
- `assets_inventory` → `file_type: "asset"`, `extraction_method: "file-copy"`, stored in `{skill_package}/assets/` by step 7
- `promoted_docs` (the inventory's, from step 3 §2a) → `file_type: "doc"`, `extraction_method: "promoted-authoritative"`, **not** copied into the skill package by step 7. The source file stays at its original path; only the provenance tracking entry is written. `content_hash` was pre-computed by §2a.

Each `file_entries[]` row has the same shape regardless of `file_type`: `{file_name, file_type, source_file, content_hash, confidence, extraction_method}`. See `{skillSectionsData}` for full schema and the canonical list of `file_type` values.

### 7. Build evidence-report.md Content

Compilation audit trail: generation date, forge tier, source info, tool versions, extraction summary (files/exports/confidence), warnings. For validation-specific fields (Schema, Frontmatter, Body, Security, Description angle brackets, Tessl Review, Metadata, Provenance labels, Provenance lines), insert the placeholder text `[PENDING: populated by step 6]`. Step-06 will replace these placeholders with actual results. See `{skillSectionsData}` for full template. Use the same `{skf_version}` value resolved in section 4 when populating the Tool Versions block.

**Frontmatter, pinned fields:** emit YAML frontmatter at the top of `evidence-report.md` with at minimum `skill_name`, `generated`, `forge_tier`, and `t2_future_count`. Take `t2_future_count` from `{inventory_counts}.t2_future` (§1): the T2 annotations step 4 classified `T2-future`, counted by the helper. **Emit `t2_future_count: 0` when no T2-future annotations exist**: omission is indistinguishable from "no data" for downstream consumers and would silently flip the skf-test-skill §2b/§5b migration-section gate into Case 2/3 for a Case-1 skill. This frontmatter is the authoritative detection contract: `migration-section-rules.md` Case Rules parse it deterministically rather than grepping prose.

**Auto-Decisions section (render from the run sink):** render the `## Auto-Decisions` section into `evidence-report.md` from `{run_dir}/headless-decisions.jsonl`, the run's one decision trail: one row per line, in file order, in the table format below. Every decision the run took without asking is there, written the moment it was taken (step 1 tier-override, step 3 tag-choice, step 3's deferred authoritative files, step 3 review-gate, step 3 and step 3c zero-exports, step 3d component-extraction gates, step 5 manual-carry-forward), however much of the run context compacted since. No gate records a decision after this step. When the file is missing or empty, emit the section with the single line `No auto-decisions: the workflow ran interactively, or no gate had to resolve on its own.`

```
## Auto-Decisions

| Step | Gate | Decision | Rationale | Timestamp |
|------|------|----------|-----------|-----------|
| {step} | {gate} | {decision}{value?} | {rationale} | {timestamp} |
```

Also write the inventory's `authoritative_files_scan` record into the evidence report. When the inventory's `intent_mapping` is not empty (a free-text `scripts_intent` or `assets_intent`, step 3 §4c), write one line per kind into the evidence report, so a reader sees which detected files the intent left out: `{kind} intent "{intent}": kept {each kept source file, or none}; left out {each left_out source file, or none}`. When the inventory marks exports `public: false`, list each one the inventory `summary` call (§1's, or the same call run again) gives in its `not_public` in the evidence report, one line each as `{name} ({file})`, under the line `Off the public surface (left out of the provenance map, SKILL.md, references/, the context snippet and metadata.json's exports[]):`. This step is the first point `evidence-report.md` is written to disk (staging dir, §8 below).

### 8. Auto-Proceed

No user interaction. Once all content is written to the staging directory `_bmad-output/.skf-stage/{skill-name}/` (no final files in `skills/` or `forge-data/` yet), load `{nextStepFile}`, read it fully, then execute it. `extraction-rules.yaml` is generated by step 7 from the inventory's `extraction_rules`: do not create it here.

