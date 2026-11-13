---
signatureRulesFile: 'references/signature-comparison-rules.md'
coherenceAggregationScript: 'scripts/aggregate-coherence.py'
migrationSectionRules: 'references/migration-section-rules.md'
---

# Coherence Check: Contextual Mode

Load this file only from coherence-check.md §1, in contextual mode, and follow it. `{run_dir}`, the `{scanSkillMdStructureHelper}` coherence-check.md §1 resolved (a command of it that exits non-zero halts as that section says) and coherence-check.md's **Halt envelope** apply here. A bare §1 or §6 is coherence-check.md's, any other bare § this file's. coherence-check.md §6 records what this file finds in the gap ledger under stage `coherence-check`, as `broken-reference`, `inaccurate-reference`, `reference-escape`, `scripts-assets`, `integration-pattern` and `migration-section` gaps.

## Sections

### 3. Contextual Mode: Extract References

SKILL.md's cross-references come in two kinds, and each has one owner:

- **File-path and script/asset references**: every markdown link to a file (`[types](src/types.ts)`, `[guide](references/guide.md)`) and every `references/`, `scripts/` or `assets/` path mentioned in prose or inline code (`references/{file}.md`, `scripts/{file}`, `assets/{file}`), by the scanner's Reference extraction rules. Whether the target exists, and where it really lives, has one right answer, so the scanner extracts them and checks them. Any other path written outside a link (`../shared/types.ts` in inline code, an import specifier) is not checked: it usually names a file in the reader's project or a module, not one the skill ships:

  ```bash
  uv run {scanSkillMdStructureHelper} reference-check "{resolved_skill_package}/SKILL.md" [--source-root "{source_path}"] [--skills-root "{skills_output_folder}"] > "{run_dir}/references.json"
  ```

  Pass `--source-root` when metadata.json records the extraction tree (`{source_path}`), and `--skills-root` for a stack skill: a stack's constituent cross-references legitimately resolve to `skills/{name}/active` under `{skills_output_folder}`, which lies outside `{skillDir}`, and a stack's metadata.json records no `source_root` to anchor them. The scanner resolves symlinks before its root check. Do not check these targets again by hand or through subagents, and do not validate an escaping target's contents: the escape itself is the finding.
- **Skill references, type imports and integration-pattern references** (`See SKILL.md for {other-skill}`, `Integrates with {package}`, `import { Type } from './module'`, middleware chains, plugin hooks, shared state): whether one is accurate takes judgment. Delegate to a subagent that reads SKILL.md and returns only this JSON shape (no prose, no commentary, no markdown fences): `{"references_found": [{"line": N, "type": "skill|type-import|integration-pattern", "target": "..."}]}`. Parent strips wrapping markdown fences (if present) before parsing. If subagent unavailable, scan in main thread.

### 4. Contextual Mode: Validate Each Reference

The scanned references need no further check: `{run_dir}/references.json` holds their statuses.

Delegate the references §3's subagent found, in one batch, to a subagent given the absolute path of `{signatureRulesFile}` (under `{skill-root}`), that, for each one:

1. Checks if the target exists (the skill exists in the skills output folder, the type is declared, the integration point is in the code)
2. If the target exists, validates the reference is accurate:
   - Type imports: type is actually exported from the referenced module
   - Skill references: referenced skill exists in skills output folder
   - Integration patterns: documented pattern matches actual implementation
   - Signatures: a documented signature matches its declaration by the rules of `{signatureRulesFile}` (`signature_match`)
3. Returns only a JSON array, one object per reference, with no prose, no commentary and no markdown fences: `{"reference": "...", "type": "<its §3 type>", "line": N, "target_exists": <bool>, "type_match": <bool>, "signature_match": <bool>, "issues": ["..."]}`

Save its response, as it came back, to `{run_dir}/judged-references.json` with the Write tool (no file when §3 found no such reference). If subagent unavailable, load `{signatureRulesFile}`, validate each reference in main thread by it and save the same array. §5c counts the valid references from both files, and classifies the invalid ones.

When `scripts_assets.missing` in `{run_dir}/references.json` is true (a `scripts/` or `assets/` folder beside SKILL.md, and no Scripts & Assets section), it is a Medium `scripts-assets` gap, as in coherence-naive.md §2.7; §6 records it from that file.

### 5. Contextual Mode: Check Integration Pattern Completeness

For stack skills, verify integration patterns are complete:

- **All documented integration points carry the wiring evidence of the stack's mode** (defined below; a fenced code example is not required)
- **Shared types are consistently used across referenced components**
- **Middleware/plugin chains show complete flow, not fragments**
- **Event handlers reference valid event types**

**Integration points.** Each Cross-Cutting Patterns entry and each Library Pair Integrations entry in the stack's Integration Patterns section is one integration point, and `patterns_documented` counts them. The Hub Library Connections list that create-stack-skill adds after them only summarizes each hub library's partners, so its bullets are not integration points: this section does not score them and `patterns_documented` does not count them.

**Wiring evidence (first criterion).** create-stack-skill gives an integration entry no slot for a code example: the entry records a type, the wiring evidence of the stack's mode and a confidence label, so the first criterion reads that evidence. Take the stack's mode from the Confidence labels of its integration entries: the stack is compose-mode when any of them carries the `[composed]` marker (alone or extended, as in `[composed, +T2 annotations]`) or `[inferred from shared domain]`, the markers create-stack-skill puts on every compose-mode integration; otherwise it is code-mode. An integration point meets the first criterion when its entry carries the evidence of its stack's mode:

- **Code mode:** at least one `file:line` citation (a source file path with a line number) where the libraries connect in the codebase, and, for a library-pair entry, a `**Key files:**` line that names at least one file.
- **Compose mode:** one `[from skill: {skill name}]` line for each constituent skill the entry joins, citing something that skill exports. For a skill that exports functions, that is an exported function signature, the `[from skill: {skill name}] {exported_function_signature}` line of the Integration Evidence Format in `skf-create-stack-skill/references/compose-mode-rules.md`. For any other constituent (a skill whose `scope_type` is `reference-app` or `docs-only`, or whose exports are not functions), it is the export, pattern surface or documented contract the line quotes. A `[from skill: …]` line that cites nothing the skill exports does not count.

A fenced code block is not required in either mode: an entry that carries its mode's evidence meets the criterion without one, and a code block does not stand in for missing evidence. When an entry fails the first criterion, name the missing evidence in its `incomplete_patterns` issue, for example `no file:line citation` or `no [from skill: …] line for {skill name}`.

**Run the integration scan.** `{scanSkillMdStructureHelper}` applies the integration-point and wiring-evidence rules above, so the count, the mode and each entry's evidence are never taken by hand:

```bash
uv run {scanSkillMdStructureHelper} integration-scan "{resolved_skill_package}/SKILL.md" > "{run_dir}/integration-scan.json"
```

It gives `patterns_documented`, the stack's `stack_mode` and, in `entries[]`, each integration point with its `name`, `line`, `kind`, `libraries`, `confidence`, `citations`, `key_files` and `from_skill` lines, its `first_criterion` and, in `missing`, the evidence it lacks. You judge each entry against the other three criteria; in compose mode, whether each `from_skill` line cites something its skill exports (a line that cites nothing fails the first criterion); and an entry whose `first_criterion` is null (a compose-mode entry whose name names no libraries), from its `from_skill` lines.

Build the integration completeness findings, and save them to `{run_dir}/integration.json` with the Write tool (§5c reads the file): `patterns_documented` as the scan gives it; one `incomplete_patterns` entry for each integration point that fails any criterion, its `pattern` the entry's `name`, its `line` the entry's `line` and its `issue` the entry's `missing` joined by `; ` and the criterion it fails, as they apply; and `patterns_complete` the documented count less their number:

```json
{
  "patterns_documented": 5,
  "patterns_complete": 4,
  "incomplete_patterns": [
    {
      "pattern": "Auth middleware chain",
      "issue": "Shows middleware registration but not the handler function signature",
      "line": 95
    }
  ]
}
```

Each `incomplete_patterns` entry is an incomplete integration pattern, a Medium `integration-pattern` gap, with its Source at `SKILL.md:{line}` and the missing evidence as its Issue; §5c copies the list into `{run_dir}/coherence.json`, and §6 records each from there.

**Zero integration patterns:** If the scan's `patterns_documented` is 0 (e.g., a contextual-mode skill that uses shared types but has no middleware chains, plugin hooks, or event flows): record `patterns_documented: 0`, `patterns_complete: 0`, `incomplete_patterns: []`. The coherence score then uses reference validity alone: with no integration patterns, §5c's script makes combined coherence equal reference validity.

### 5b. Migration/Deprecation Verification (Contextual Path)

Apply rules from `{migrationSectionRules}`, the single source of truth for the gate, scope and case rules. Append findings to the coherence analysis results.

### 5c. Calculate Coherence Scores

**Contextual mode only.** The reference-validity ratio, the integration-completeness ratio, and their weighted mean are pure arithmetic: the judgment (which references are valid in §4, which patterns are complete in §5) has already happened. Do not compute these percentages by hand; `{coherenceAggregationScript}` aggregates them and is the one home of the formula and its weights.

The script counts the references itself, from the per-reference files of §3 and §4, and reads the pattern counts from the §5 file:

```bash
uv run {coherenceAggregationScript} --references "{run_dir}/references.json" [--judged "{run_dir}/judged-references.json"] --integration "{run_dir}/integration.json" --output "{run_dir}/coherence.json"
```

Exit 2 (`INVALID_INPUT`): a file does not hold the shape §3 to §5 describe; correct it (re-dispatch the §4 subagent once for its file) and run the command again. Exit 1: a file is missing or is not JSON; write it again. A second failure: HALT with its `error` (`halt_reason: "helper-failed"`, phase `coherence-check:aggregate`).

`--output` also writes the result to the run folder, where step 5 hands it to the scoring script. Parse its output and read:
- `referenceValidity`: reference-validity percentage
- `integrationCompleteness`: integration-completeness percentage (`null` when no patterns are documented)
- `combinedCoherence`: the combined coherence percentage, the `coherence` score step 5 reads from `{run_dir}/coherence.json`

§6's render writes these values into the Coherence Score list. `{run_dir}/coherence.json` lists each invalid reference with its `status` in `invalidReferences[]`, which §6 records from that file; stdout gives only their number. It also copies `integration.json`'s `incomplete_patterns` into `incompletePatterns[]`, which §6 records the same way.

When this file is done, continue at coherence-check.md §6.
