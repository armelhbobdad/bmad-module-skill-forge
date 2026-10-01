---
nextStepFile: 'coherence-check.md'
outputFile: '{forge_version}/test-report-{skill_name}-{run_id}.md'
scoringRulesFile: 'references/scoring-rules.md'
sourceAccessProtocol: 'references/source-access-protocol.md'
validateInventoryScript: 'scripts/validate-inventory.py'
coverageInputsScript: 'scripts/load-coverage-inputs.py'
scoreSignaturesScript: 'scripts/score-signatures.py'
reconcileScript: 'scripts/reconcile-coverage.py'
coherenceScript: 'scripts/check-metadata-coherence.py'
numeratorVerifyScript: 'scripts/verify-declared-numerator.py'
stageHelperPayloadScript: 'scripts/stage-helper-payload.py'
outputFormatsFile: 'assets/output-section-formats.md'
# §5b records every gap this step finds in the run's gap ledger, which the
# hard gate (step 4c) reads and the Gap Report is rendered from.
ledgerFile: '{forge_version}/test-findings-{run_id}.json'
gapLedgerScript: 'scripts/gap-ledger.py'
# Resolve `{verifyProvenanceCompletenessHelper}` by probing
# `{verifyProvenanceCompletenessProbeOrder}` in order (installed SKF module
# path first, src/ dev-checkout fallback); first existing path wins. §2c runs
# it on the line the skill cites for a stale name, and §4c to check that each
# provenance `source_line` is the line that defines its export. Advisory: if
# neither path resolves, §2c records stale names as stale documentation and
# §4c is skipped.
verifyProvenanceCompletenessProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-verify-provenance-completeness.py'
  - '{project-root}/src/shared/scripts/skf-verify-provenance-completeness.py'
# Resolve `{extractPublicApiHelper}` to the first existing path. §2 runs its
# `--mode full` recipe runner at Forge, Forge+ and Deep tier, and at Quick
# tier parses a skill quick-skill built with its `--mode quick` parser, the
# parser that built the skill's export list.
extractPublicApiProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-extract-public-api.py'
  - '{project-root}/src/shared/scripts/skf-extract-public-api.py'
# Resolve `{detectWorkspacesHelper}` to the first existing path. §0b runs it
# to tell whether a local source is a monorepo.
detectWorkspacesProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-detect-workspaces.py'
  - '{project-root}/src/shared/scripts/skf-detect-workspaces.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 3: Coverage Check

## STEP GOAL:

Compare the exports, functions, classes, types, and interfaces documented in SKILL.md against the actual source code API surface. Identify missing documentation, undocumented exports, and signature mismatches. Analysis depth scales with forge tier.

Every HALT in this step releases the run lock first (SKILL.md Workflow Rules).

**Run files.** Every script below writes its result into the run folder `{run_dir}` that init.md §6b created, and the next one reads it from there by path: no list, count or score is copied from one command into another. A subagent's response is saved there with the Write tool exactly as it came back, fence and all, and passed by path, so a quote or an apostrophe in it never meets a shell. Each command runs from `{project-root}`; a `{...Script}` path resolves relative to the skill root.

### 0. Check for Docs-Only Mode

A skill is docs-only when every citation it writes is `[EXT:...]`, with no local source citation (`[AST:...]`, `[SRC:...]`, or a stack's `[from skill: ...]`). The citation census counts them, not a reading by eye:

```bash
uv run {coverageInputsScript} census --skill-dir "{resolved_skill_package}" --output "{run_dir}/census.json"
```

Bind `{docs_only_mode}` ← `docsOnly`. Exit 1 printed its error on stderr: HALT with it. §0b sets `{docs_only_mode}` too when source access reaches State 5 (no source access at all).

**A docs-only run** has no source to compare against, so Export Coverage measures documentation completeness instead, and `analysis_confidence` is `docs-only`. It runs §1, §1a and §1b, the docs-only guard of §2b, §2c's `docsOnly` branch, §3, §4's Export Coverage line and its `Denominator: docs-only completeness` annotation, §5, §5b and §6, and skips the rest of §0b, §2, §2b, §4, §4b and §4c. Step 5 passes `docsOnly: true` to the scoring script, which skips Signature Accuracy and Type Coverage and redistributes their weights at any tier.

"**Docs-only skill detected.** Coverage check evaluates documentation completeness rather than source code coverage."

**If source-based skill:** Continue with standard coverage check below.

### 0b. Load Source Access Protocol

Load `{sourceAccessProtocol}` and follow both sections:
1. **Source API Surface Definition**: which clause decides the coverage denominator, read in §2b
2. **Source Access Resolution**: the 5-state waterfall that decides how source files will be read and sets `analysis_confidence`; State 5 makes the run docs-only (§0)

**Workspace layout.** Whether the source is a monorepo decides which Source API Surface Definition clause applies, and `{detectWorkspacesHelper}` decides it, not a check of folder and manifest names by eye. When Source Access Resolution reached State 1 (local source), resolve `{detectWorkspacesHelper}` ← first existing path in `{detectWorkspacesProbeOrder}` and, from `{project-root}`, run the command below. `{stageHelperPayloadScript}` (it resolves relative to the skill root) reads the source tree and the root manifests from disk and pipes them to the helper, so no file text is copied by hand:

```bash
uv run {stageHelperPayloadScript} detect-workspaces --source-root "{source_path}" | uv run {detectWorkspacesHelper}
```

Bind `{source_is_monorepo}` ← `is_monorepo` and `{source_workspace_kind}` ← `manifest_kind`; the Source API Surface Definition's monorepo tests read `{source_is_monorepo}`. At States 2 to 5 there is no tree to read, and a helper that does not resolve or a command that exits non-zero leaves the layout unknown: bind `{source_is_monorepo}` ← false in both cases. §5 records the layout.

### 1. Extract Documented Exports from SKILL.md

<!-- Subagent delegation: read SKILL.md + references/*.md, return compact JSON inventory -->

Delegate reading of the skill under test to a subagent. The subagent receives the path to SKILL.md (and the `references/` directory path if it exists) and must:
1. Read SKILL.md
2. If a `references/` directory exists alongside SKILL.md and SKILL.md's `## Full` headings are absent or stubs, also read all `references/*.md` files
3. only return this compact JSON inventory, with no prose and no extra commentary:

```json
{
  "exports": [
    {"name": "functionName", "kind": "function", "params": "...", "return_type": "...", "description": "..."},
    {"name": "ClassName", "kind": "class", "methods": ["..."], "properties": ["..."], "description": "..."},
    {"name": "TypeName", "kind": "type", "fields": ["..."], "description": "..."},
    {"name": "CONST_NAME", "kind": "constant", "values": ["..."], "description": "..."},
    {"name": "useHook", "kind": "hook", "usage_signature": "...", "description": "..."}
  ],
  "capabilities": ["brief capability descriptions from the skill overview"],
  "references": ["references/api-reference.md", "references/type-definitions.md"],
  "cross_check_mismatches": [
    {
      "export": "functionName",
      "skill_md_line": 42,
      "reference_file": "references/api-reference.md",
      "reference_line": 18,
      "issue": "description of the signature mismatch"
    }
  ]
}
```

Tell the subagent the contract the validator checks: each `kind` is one of `function`, `class`, `type`, `constant`, `hook`, `interface`, `method`, `struct`, `enum`, `trait`, `macro` or `adapter`; every entry carries the `description` the skill gives it (an empty string when it gives none); a function or method carries `params` (`""` or `[]` when it takes none) and `return_type` as the skill documents them, and leaves a key out when the skill documents nothing for it.

Save the subagent's response, as it came back, to `{run_dir}/inventory-response.txt` with the Write tool. **Parent uses the validated inventory §1a writes as the documented inventory.** Do not load SKILL.md or references file contents into parent context.

**If subagent delegation is unavailable:** the parent performs the read itself in the main thread: read SKILL.md (and, per step 2 above, all `references/*.md` when a `references/` directory exists and SKILL.md's `## Full` headings are absent or stubs), assemble the same compact JSON inventory and save it to the same file. The §1a schema validation and ground-truth spot-check still run on the parent-built inventory: a quality gate does not skip its own hallucination guards just because the extraction ran in-thread. This mirrors the §2 fallback (the per-file scan in the main thread) so §1 degrades gracefully instead of stalling.

#### 1a. Parent-Side Schema Validation + Spot-Check

test-skill is a quality gate: it must not trust subagent output blindly. Before any downstream step consumes the inventory, the parent runs a schema validator and a spot-check.

**Schema validation, by `{validateInventoryScript}`.** It strips a wrapping markdown fence, parses the JSON and checks the contract §1 gave the subagent: `exports` and `cross_check_mismatches` are lists, each export has a non-empty `name` and one of the 12 kinds, and each cross-check mismatch carries its five fields. It also counts each documented item's completeness for a docs-only run (§2c):

```bash
uv run {validateInventoryScript} --input "{run_dir}/inventory-response.txt" --output "{run_dir}/inventory.json"
```

`valid` true (exit 0): the script wrote the validated inventory to `{run_dir}/inventory.json`, which every later command reads by path; do not re-parse the raw response by hand. `valid` false (exit 2): re-dispatch the §1 subagent once, with the script's `violations[]` appended to its instructions, save the new response over the old one and run the command again. Exit 1 (no input, or a file that cannot be read): correct the file and run it again.

**Spot-check (ground-truth verification, zero-hallucination guard):** operate on the validated inventory.

1. If `exportsCount` is 0: skip the spot-check (no names to verify). Zero-exports policy is handled in the §2b zero-exports guard.
2. Otherwise, sample `min(3, exportsCount)` exports deterministically: by default take indices `[0, len//2, len-1]` (first, middle, last) from the inventory's `exports` after a stable sort by `name`.
3. For each sampled export, grep for the name across SKILL.md **and every reference file the subagent listed in its `references`** (the documented surface of a split-body skill spans both): `grep -n "{export.name}" {resolved_skill_package}/SKILL.md {resolved_skill_package}/{each references[] path}` in the parent context. The name must appear at least once somewhere in that file set. Grepping SKILL.md alone would false-HALT a split-body skill whose sampled export is documented only in a `references/*.md` file (a legitimate placement per §1 step 2 and the split-body note below).
4. If a sampled name returns zero matches across SKILL.md **and** all listed reference files, re-dispatch the §1 subagent once, with the absent names appended to its instructions as names the skill does not write, and validate and spot-check its new response.

These checks catch two hallucination classes: schema-shape drift (subagent paraphrased or dropped the contract) and fabricated exports (subagent invented names not in the document). Both are disqualifying for a grader skill, so neither is downgraded to a warning: when the re-dispatched response fails the schema validation or the spot-check again, HALT with `halt_reason: "inventory-invalid"`: "coverage-check: the subagent inventory failed {schema validation: the violations joined | the ground-truth spot-check: `{name}` claimed as export but absent from SKILL.md and the listed reference files} twice." In `{headless_mode}`, emit to **stderr** before halting:

```
SKF_TEST_RESULT_JSON: {"status":"error","skill_name":"{skill_name}","verdict":null,"score":null,"threshold":null,"report_path":"{outputFile}","next_workflow":null,"exit_code":1,"halt_reason":"inventory-invalid"}
```

**Split-body traversal** is handled inside the subagent: if `references/` exists and `## Full` headings are absent or stubs in SKILL.md, the subagent extends its scan to all `references/*.md` files and includes them in the `exports` array. After split-body, Tier 2 content (Full API Reference, Full Type Definitions) lives in reference files: the inventory must reflect the full skill content regardless of where it resides.

### 1b. Cross-Check Split-Body Consistency

**Only execute if the subagent's `references` array is non-empty** (detected during split-body traversal in Section 1). Skip silently otherwise.

The subagent has already read both SKILL.md body and `references/*.md` files. For each function, class, type, or interface that appears in both the SKILL.md body AND any `references/*.md` file, instruct the subagent (or perform in the same subagent call from Section 1) to compare the documented signatures and include mismatches in its JSON output as a `cross_check_mismatches` array:

- **Parameters:** name, type, order, optionality
- **Return types:** exact type match
- **Description:** no contradictions (brief vs detailed is acceptable; conflicting semantics is not)

**SKILL.md body is authoritative.** When a mismatch is found, the reference file is the one that needs updating.

Parent reads `cross_check_mismatches` from the validated inventory. Build the split-body consistency findings list:

```json
{
  "cross_check_mismatches": [
    {
      "export": "formatDate",
      "skill_md_line": 42,
      "reference_file": "references/api-reference.md",
      "reference_line": 18,
      "issue": "SKILL.md shows (date: Date) => string, reference shows (date: Date, format?: string) => string"
    }
  ],
  "exports_cross_checked": 12,
  "mismatches_found": 1
}
```

Each mismatch is a High `split-body-mismatch` gap: a signature inconsistency between the SKILL.md body and a reference file undermines agent trust. §5b records it titled `Split-body mismatch: {export}`, with its `export` and its Source at the reference file's line (`{reference_file}:{reference_line}`), inside the skill package: the reference file is the one to update, and update-skill repairs it without reading the source.

### 2. Analyze Source Code (Tier-Dependent)

Start from the package entry point (see 0b) and identify the public API surface. Then analyze those exports at the appropriate tier depth. However the surface is found, `{coverageInputsScript} surface` writes it to `{run_dir}/surface.json`: its `exports[]` (each name with its kind, file and line when known) and its name `sets` (`all`; `scope.include` and `tier_a_include` when the brief has those globs and the names carry their files; `subpaths` and `root` from an extraction only), which §2b, §2c, §4 and step 5 read.

**Exits.** Every `{coverageInputsScript}` and `{scoreSignaturesScript}` command in §2 and §2b prints its JSON and exits 0, or exits 1 with its error on stderr: HALT with it. `surface` with a `--per-file` and `score` also exit 2 when a subagent response breaks the schema: their `violations[]` name the response, so re-dispatch that subagent once with the violations appended (or correct a result the main thread wrote), save its new response over the old one and run the command again; a second failure HALTs with the violations.

**Quick Tier (no AST tools):**
- **A skill quick-skill built** (`metadata.json` `generated_by` is `quick-skill`), **from local source** (State 1): quick-skill built its export list with `{extractPublicApiHelper}` `--mode quick`, so parse the entry points with the same parser and both sides count one surface. Resolve it ← first existing path in `{extractPublicApiProbeOrder}` and run it once per package in scope, with its manifest and one `--entry-file` for each entry-point file the Source API Surface Definition (§0b) makes its surface, each path relative to `{source_path}`, saving its output to `{run_dir}/quick-<n>.json` (`<n>` counts the packages from 1):

  ```bash
  uv run {extractPublicApiHelper} --mode quick --language <language> --source-root "{source_path}" --manifest-file <manifest path> --entry-file <entry path> > "{run_dir}/quick-<n>.json"
  ```

- The parser reads the re-exports (a Python `from ... import`, a Rust `pub use`, a JS/TS `export * as`), the `async` declarations (`export async function`, `async def`, `pub async fn`) and CommonJS `module.exports` itself. Its `warnings` name each statement whose names the entry file alone cannot give: `export * from`, a star import, a non-literal `__all__` part, `pub use x::*` and `module.exports = require(...)`. Read by eye only the statements its warnings name, save the names they give as a per-file result for the entry file that holds the statement, `{"file": "<entry path>", "exports_found": [<each name>], "signature_mismatches": []}`, to `{run_dir}/per-file-<n>.json` with the Write tool, and list those names in the Coverage Analysis section as read by eye. Give `surface` one `--quick` per package and one `--per-file` per saved result, with the brief when the skill has one (its scope globs give the `scope.include` and `tier_a_include` sets), the metadata and, when init.md §2 bound one, the provenance map (the baselines of the §2b candidates and guards; they add no name here):

  ```bash
  uv run {coverageInputsScript} surface --quick "{run_dir}/quick-<n>.json" [--per-file "{run_dir}/per-file-<n>.json"] [--brief "{forge_data_folder}/{skill_name}/skill-brief.yaml"] --metadata "{resolved_skill_package}/metadata.json" [--provenance "{forge_provenance_map}"] --output "{run_dir}/surface.json"
  ```

- **Any other skill** (create-skill's Quick tier reads the entry points as source text), a source that is not local, or a helper that does not resolve or exits non-zero (it exits 1 on a language it does not parse): identify the exports by reading the entry points per the Source API Surface Definition, save one per-file result per entry file, `{"file": "<entry path>", "exports_found": [<each exported name>], "signature_mismatches": []}`, to `{run_dir}/per-file-<n>.json` with the Write tool, run the `surface` command above with one `--per-file` for each and no `--quick`, and note in the Coverage Analysis section that the Quick-tier scan read them by eye. §2c's script works out which names are documented, missing and stale.
- Signatures cannot be verified at this tier: note them as "unverified" in the report.

**Forge Tier (ast-grep available):**

At State 1, run the recipe runner once over the source, as create-skill extracts it. Resolve `{extractPublicApiHelper}` ← first existing path in `{extractPublicApiProbeOrder}` and run (leave `--brief` out when the skill has no brief):

```bash
uv run {extractPublicApiHelper} --mode full --source-root "{source_path}" --brief "{forge_data_folder}/{skill_name}/skill-brief.yaml" --tier {detected_tier} --head-cap 0 --output "{run_dir}/extract-full.json"
```

`--head-cap 0` keeps every match: a recipe cut at its default cap would drop exports, which would read as missing documentation. Then build the surface from it, with the metadata and, when init.md §2 bound one, the provenance map as the baselines of the §2b guards (they add no name here):

```bash
uv run {coverageInputsScript} surface --extraction "{run_dir}/extract-full.json" --metadata "{resolved_skill_package}/metadata.json" [--provenance "{forge_provenance_map}"] --output "{run_dir}/surface.json"
```

The surface holds the names the package's entry points export (`entry_point_diff.public`), less those defined in a file the brief scopes out (`excluded.outsideScope`, listed in the report); the recipes' internal matches are never part of it. Decide what to do from the JSON, not from the exit code:

- `extraction.fallback.needed` is true (no ast-grep, no file in scope, files only in languages no recipe reads, or files in scope that no recipe reads while the skill's language is one no recipe reads), the runner exited 2, or it printed no JSON: run the **fallback per-file scan** below instead.
- `extraction.status` is `incomplete` (exit 1): keep the surface, and read by eye only the files `extraction.readByEye` names; save the exports each holds as a per-file result for that file, as at Quick tier, and run `surface` again with a `--per-file` for each.
- `extractionGaps[]` lists the names an entry point exports that no recipe found: they are on the surface, and their signature is read by eye at their `file` and `line`.

**Compare the signatures.** The judgment of whether a documented signature matches the source stays with subagents; the list of comparisons comes from a script:

```bash
uv run {scoreSignaturesScript} plan --inventory "{run_dir}/inventory.json" --surface "{run_dir}/surface.json" --output "{run_dir}/signature-plan.json"
```

For each `files[]` entry, delegate one subagent with its checks. For each check it reads the full declaration at `{file}:{line}` (all of it, as create-skill's extraction reads a signature: `signatureLine` is one physical line, and a multi-line signature cut there would read as a mismatch), compares it with the check's `documented` signature (params: name, type, order, optionality; and the return type), and returns only this JSON, with no prose, no commentary and no markdown fences:

```json
{
  "file": "src/utils.ts",
  "signature_mismatches": [
    {
      "name": "formatDate",
      "line": 42,
      "source_sig": "(date: Date, format?: string) => string",
      "documented_sig": "(date: Date) => string",
      "issue": "missing optional parameter 'format'"
    }
  ]
}
```

Save each response to `{run_dir}/signatures-<n>.txt` with the Write tool. If subagents are unavailable, compare in the main thread and save the same JSON.

**Fallback per-file scan.** When the recipe runner cannot be used, run `plan` without `--surface`: its `documentedSignatures` is the map of every documented signature. For EACH source file that defines public API exports, delegate to a subagent that gets that map with the file, uses ast-grep to extract its exported symbols with their full signatures (or reads the file when `extraction.fallback.reason` says no ast-grep can run, and lists those files in the Coverage Analysis section as read by eye), compares each with the map's entry (params, return type), gives each mismatch the `line` that defines the export, and returns only `{"file", "exports_found": [...], "types_found": [<the exported interfaces, type aliases, enums and classes>], "signature_mismatches": [...]}` in the shape above. Save each response to `{run_dir}/per-file-<n>.txt` and build the surface from them, one `--per-file` each, with the same baselines as at Quick tier:

```bash
uv run {coverageInputsScript} surface --per-file "{run_dir}/per-file-<n>.txt" [--brief "{forge_data_folder}/{skill_name}/skill-brief.yaml"] --metadata "{resolved_skill_package}/metadata.json" [--provenance "{forge_provenance_map}"] --output "{run_dir}/surface.json"
```

§2b scores the saved responses once it has picked the denominator set.

**Deep Tier (ast-grep + gh + QMD):**
- All Forge tier checks, plus:
- Use gh CLI to verify source repository matches documented version
- Cross-check type definitions against their source declarations
- Verify re-exported symbols trace to their original source

**States 2 to 4 (no local source):** the surface comes from what the skill recorded, so there is no signature to score:
- **State 2** (`{forge_provenance_map}`, the provenance map init.md §2 bound): the union of its named exports and the `metadata.json` `exports[]` names. Pass `--fold` when the Source API Surface Definition's canonicalization applies, with one `--keep` for each variant the skill documents as an export of its own and one `--fold-prefix` for each renderer prefix the library uses:

  ```bash
  uv run {coverageInputsScript} surface --provenance "{forge_provenance_map}" --metadata "{resolved_skill_package}/metadata.json" [--brief "{forge_data_folder}/{skill_name}/skill-brief.yaml"] [--fold] [--keep <variant>] [--fold-prefix <prefix>] --output "{run_dir}/surface.json"
  ```

  `--fold` folds the variants among both lists, so one the map folds never returns through `metadata.json`. Its `state2` counts go to step 5, whose scoring script decides the State 2 undercount deduction, and `canonical.summary` is the fold summary the report records.
- **State 3**: the `metadata.json` `exports[]` names: `surface --metadata "{resolved_skill_package}/metadata.json" --output "{run_dir}/surface.json"`.
- **State 4**: the names read remotely by eye, saved as per-file results and passed with `--per-file`, with the brief and the metadata, as at Quick tier.

### 2b. Resolve the Denominator and Guard Zero Exports

Load the metadata and provenance-map counts once; §2c's stack branch, §4b and the numerator check below read them. Pass `--provenance` when init.md §2 bound `{forge_provenance_map}`:

```bash
uv run {coverageInputsScript} metadata --metadata "{resolved_skill_package}/metadata.json" [--provenance "{forge_provenance_map}"] --output "{run_dir}/coverage-inputs.json"
```

**Pick the denominator.** Which clause of the Source API Surface Definition (§0b) matches this skill is a judgment; the counts each clause names are the script's, in `surface.json` `candidates` and `guards`. The clause gives §2c its branch:

- **Standard barrel**, **multi-entry**, **specific-modules**, **pattern-reference**, State 2 or a priority-2/3 **stratified-scope** denominator: an enumerated name set, §2c's barrel branch, with the `surface.json` set the clause names (`all`, `subpaths`, `tier_a_include` or `scope.include`). A set is there only when its inputs are: `scope.include` and `tier_a_include` need the brief's globs and names that carry their files (State 3's metadata names carry none), `subpaths` and `root` an extraction. Without an extraction the entry files read are the ones the clause names, so when its set is absent the denominator is the `all` set, and the `Denominator:` line (§4) adds `({set} set absent: all set used)`.
- **Stratified-scope priority 1**: the scalar `stats.effective_denominator` (`candidates.statsEffectiveDenominator`), §2c's scalar branch, unless the deflation guard fires (`guards.deflation.fires`), when the re-derived `scope.include` set (`all` when the brief has no `scope.include`) is the denominator instead.
- **A stack skill** (`metadata.json.skill_type == "stack"`): its own barrel is empty by design (it composes constituent skills rather than exporting a proprietary surface), and its `[from skill: …]` citations never make it docs-only. Its denominator is `coverage-inputs.json` `stack.denominator`: the distinct provenance-map named exports (`::` impl-block methods left out) when init.md §2 bound a map with entries, else its libraries and integration pairs (`stack.basis` says which). §2c's stack branch reads it. **If `stack.denominator` is 0**: HALT with `Error: stack composition surface empty: {skill_name} cites no contracts, libraries, or integration pairs, so Export Coverage is undefined. Verify the stack was compiled from at least one constituent skill.` Do not write the Coverage Analysis section; this is an indeterminate state, not a FAIL.
- **A docs-only skill**: §2c's `docsOnly` branch, over the inventory.

**Numerator ground truth.** A documented count padded to equal the denominator (`stats.exports_documented == stats.effective_denominator`, the inflation signature) would give a tautological 100%. Run the check on every source-based skill: without the signature (a stack and a reference app carry none) it reports `skipped`:

```bash
uv run {numeratorVerifyScript} --inputs "{run_dir}/coverage-inputs.json" --skill-dir "{resolved_skill_package}" --output "{run_dir}/numerator.json"
```

On the signature it looks every declared name up in `SKILL.md ∪ references/*.md` and reports `inflated`, `verified` and the `absent[]` names; §2c's scalar branch reads `verified` as its numerator when `inflated` is true, and §4b records the gap. Exit 1 or 2 (an input it cannot read, or one it refuses): HALT with its message.

**If the chosen denominator is 0 AND `docs_only_mode == false` AND `metadata.json.skill_type != "stack"`:** HALT with:

```
Error: indeterminate API surface — 0 exports discovered in source for {skill_name}.

A source-based skill with zero exports cannot be meaningfully tested:
Export Coverage is undefined (division by zero) and downstream scoring
would yield a vacuous PASS.

Fix one of:
  - Set `scope.include` in the brief to point at the package's entry point(s)
  - Add `[EXT:]` citations if this is actually a docs-only skill
  - Verify the skill's source_path / source_ref resolve to the intended tree
```

Do not write the Coverage Analysis section. Do not proceed to scoring. This is a true indeterminate state, not a FAIL: no score should be attached.

**If `docs_only_mode == true` and the validated inventory documents no item:** HALT with the analogous docs-only message ("docs-only skill declares zero items: no API surface to test").

**Score the signatures** (Forge, Forge+ and Deep tier at State 1, once §2 compared them). `{scoreSignaturesScript}` schema-checks every saved response and computes both categories: Signature Accuracy compares every documented signature on the whole surface, since a wrong signature is wrong whatever the denominator counts, and Type Coverage counts the types of the set the denominator counts (`totalTypes`), so a type the clause leaves out (a stratified skill's deferred Tier B) lowers neither Export Coverage nor Type Coverage. Give it that set as `--surface-set`: the set §2c's barrel branch reads, or for the scalar branch the set the scalar counts (`tier_a_include` when `surface.json` has it, else `scope.include`, else `all`). Give it one `--results` per saved response (the fallback scan's `per-file-<n>.txt` responses, else the `signatures-<n>.txt` ones):

```bash
uv run {scoreSignaturesScript} score --inventory "{run_dir}/inventory.json" --surface "{run_dir}/surface.json" --surface-set <set> --results "{run_dir}/signatures-<n>.txt" --output "{run_dir}/signatures.json" --gaps-output "{run_dir}/signature-gaps.json"
```

Each `signature_mismatches[]` entry of a compared name is a wrong signature, a Critical `signature-mismatch` gap: the script writes it to `signature-gaps.json` titled `Signature mismatch: {name}`, with `export` `{name}`, its Source at `{file}:{line}` and both signatures in its Issue, and §5b appends that file to the ledger. A mismatch a response reports for any other name, and a category with nothing to compare, are `warnings`, which §5 writes in the Coverage Analysis section.

### 2c. Reconcile Documented vs Source Surface (Deterministic Intersection)

On a split-body skill the §1 inventory (documented surface) and the §2 source surface are two independent lists, so the `Documented` count must be their **intersection**, not a parent estimate. That reconciliation is deterministic arithmetic with one correct answer per input, so `{reconcileScript}` does it. It derives `documented_set` from the inventory's `exports[]` itself, de-duplicated and with `kind: "method"` excluded: methods are members of an already-counted class or type, not top-level barrel exports. Run the branch §2b picked:

1. **Enumerated path (barrel)**: Documented := |documented_set ∩ barrel_set|, Missing := barrel_set − documented_set (in source, not documented), Stale := documented_set − barrel_set (documented, not in source), and Export Coverage = |Documented| / |barrel_set| * 100, with the name set §2b picked as `--surface-set`:

   ```bash
   uv run {reconcileScript} --denominator-source barrel --inventory "{run_dir}/inventory.json" --surface "{run_dir}/surface.json" --surface-set <set> --output "{run_dir}/coverage.json"
   ```

2. **Scalar branch**: the resolved denominator is a count with **no enumerated name set**, so the script looks each documented name up in `SKILL.md ∪ references/*.md` (as a whole name, case-sensitive: `get` is not found in `target` or `getAll`) and counts the hits, sets `Missing := max(0, denominator − Documented)` and returns an empty `Stale`. It reads the scalar, `stats.effective_denominator`, from `coverage-inputs.json`. When §2b's numerator check found the count inflated, `--verified` makes its `verified` count the numerator instead:

   ```bash
   uv run {reconcileScript} --denominator-source scalar --coverage-inputs "{run_dir}/coverage-inputs.json" --inventory "{run_dir}/inventory.json" --skill-dir "{resolved_skill_package}" --verified "{run_dir}/numerator.json" --output "{run_dir}/coverage.json"
   ```

3. **Stack branch** (`metadata.json.skill_type == "stack"`): the script looks each composition name up in `SKILL.md ∪ references/*.md`, sets `Missing := max(0, stack_denominator − Documented)` and omits `Stale` (no source barrel to enumerate against):

   ```bash
   uv run {reconcileScript} --denominator-source stack --coverage-inputs "{run_dir}/coverage-inputs.json" --skill-dir "{resolved_skill_package}" --output "{run_dir}/coverage.json"
   ```

4. **Docs-only branch**: Export Coverage is the completeness ratio, complete items over documented items, one item per name and kind of the inventory. An item is complete when it has a non-empty description and, for a function or a method, its params and its return type; a missing description makes it incomplete. `incomplete[]` lists each incomplete item with the fields it lacks:

   ```bash
   uv run {reconcileScript} --denominator-source docsOnly --inventory "{run_dir}/inventory.json" --output "{run_dir}/coverage.json"
   ```

The script returns (read these, **do not re-derive them by hand**):

- `documented`: the numerator (`|documented_set ∩ barrel_set|` for barrel; the looked-up or verified count for scalar and stack; the complete items for docs-only). This is always the true count, never capped.
- `missing` / `missingCount`: source names not documented (barrel enumerates the names; scalar and stack give only the residual count; docs-only counts the incomplete items). Never negative.
- `stale` / `staleCount`: documented names not in source (barrel only; empty with `staleApplicable: false` for the other branches)
- `denominator`: `|barrel_set|` (barrel), the resolved scalar or stack denominator, or the documented items (docs-only)
- `exportCoverage`: `documented / denominator * 100`, already rounded; capped at 100 on the scalar and stack branches
- `numeratorSurplus` / `coverageUncapped` / `coverageCapped`: scalar and stack only; see the surplus note below

Exit 2 printed an `INVALID_INPUT` envelope: correct the input it names and run it again. Exit 1: HALT with its stderr.

**Surplus on the lookup branches.** The scalar and stack branches look a name set up in the skill body, so their numerator and denominator measure independent sets and `documented` can exceed `denominator`: a consumer-surface denominator counts one surface while the documented body may also name migration aliases or re-exported sibling symbols. When that happens the script reports `numeratorSurplus > 0` and `coverageCapped: true`, holds `exportCoverage` at 100, floors `missingCount` at 0, and preserves the raw ratio in `coverageUncapped`. **A surplus is a signal, not a pass:** it means the two sets disagree, so state it in the Coverage Analysis section (§5) alongside both counts. A large surplus on a skill whose brief carries no `scope.tier_a_include` is the deflated-denominator signature the deflation guard looks for: check `guards.deflation` before accepting the 100.

`{run_dir}/coverage.json` is the file step 5 hands to the scoring script: its `exportCoverage` is the Export Coverage score. Carry the counts into §3's summary and record them in the Coverage Analysis section (§5) so the numerator is auditable.

**Classify what the script found.** §5b records each of these gaps:

- **Missing names** (barrel branch: `missing`): each is a Medium `missing-export` gap titled `Missing export: {name}`, or a Medium `missing-type` gap titled `Missing type: {name}` when `signatures.json` lists it in `missingTypes`, with `export` `{name}`. Its Source is the file `surface.json` `exports[]` records for it (`{file}:{line}` when the line is known), and its Remediation names that file, so update-skill can re-extract the export from it. A missing export does not block: it lowers Export Coverage, and the threshold decides.
- **Missing count** (scalar or stack branch, `missingCount` above 0): these branches do not enumerate the names, so record one Medium `missing-export` gap for the count, titled `{missingCount} of {denominator} exports not documented`, with the source of the denominator as its Source. When §4b's numerator ground-truth arm finds the count inflated, its `absent[]` names replace this gap (§4b).
- **Stale names** (barrel branch: `stale`): each is a documented name the enumerated source surface lacks. Where ast-grep read the source at the pinned commit (Forge, Forge+ or Deep tier, `analysis_confidence` `full`, `allow_workspace_drift` not true) and `{forge_provenance_map}` holds entries whose `export_name` is the name, check the line the skill cites for it. Resolve `{verifyProvenanceCompletenessHelper}` ← first existing path in `{verifyProvenanceCompletenessProbeOrder}` and run once per such entry, with `--export-type` when the entry records one:

  ```bash
  uv run {verifyProvenanceCompletenessHelper} definition-lines --source-root "{source_path}" --file "{source_file}" --name "{name}" --line {source_line} [--export-type "{export_type}"]
  ```

  Rely on its JSON. When every entry's `line_check` is `file-missing`, or `checked` with an empty `definition_lines`, neither the surface ast-grep enumerated nor the file the skill cites has the export: a Critical `fabricated-signature` gap titled `Fabricated signature: {name}`, with `export` `{name}` and the entry's `source_file:source_line` (the first, when there are several) as its Source. Any other stale name (no entry, another tier or source access, the drift override, a helper that does not resolve or prints no JSON, a `skipped-export-type` or `skipped-language` result, or a cited file that defines the name) is a Medium `stale-documentation` gap titled `Stale documentation: {name}`, with `export` `{name}` and the SKILL.md or `references/` line that documents it as its Source.

### 3. Build Coverage Results

Aggregate findings across all source files:

**Per-export status table:**

| Export | Type | Documented | Signature Match | File:Line | Status |
|--------|------|-----------|-----------------|-----------|--------|
| {name} | function/class/type | yes/no | yes/no/unverified | src/file.ts:42 | PASS/FAIL/WARN |

**Summary counts** (read from `{run_dir}/coverage.json` and `{run_dir}/signatures.json`, not re-estimated here):
- Total exports in source: `denominator` (docs-only: documented items)
- Documented in SKILL.md: `documented` (docs-only: complete items)
- Missing documentation: `missingCount` (docs-only: incomplete items, each with the fields it lacks)
- Signature mismatches: the length of `signatures.json` `mismatches`
- Undocumented in SKILL.md but not in source (stale docs): `staleCount`

When the script reports `coverageCapped: true`, add the surplus to the summary (`Documented (surplus over denominator): {numeratorSurplus}` and `Uncapped coverage: {coverageUncapped}%`) so the reader can see that `Missing documentation: 0` is a floored residual rather than a verified-complete surface.

### 4. Category Scores and the Denominator Record

Each category score is a script's output, read from its file and never re-computed here; step 5 hands the same files to the scoring script:

- **Export Coverage:** `coverage.json` `exportCoverage`
- **Signature Accuracy:** `signatures.json` `signatureAccuracy` (Forge, Forge+ and Deep tier at State 1; "N/A" otherwise)
- **Type Coverage:** `signatures.json` `typeCoverage`: `documentedTypes` over `totalTypes`, the types of the set §2b scored; "N/A" where Signature Accuracy is

Record the denominator source in the Coverage Analysis section with the annotation string the matching clause of `{sourceAccessProtocol}` specifies: `Denominator: {barrel | stratified (…) | multi-entry (…) | specific-modules (…) | pattern-reference (…) | stack composition (…) | pattern-surface (…) | docs-only completeness}`. When `surface.json` has a `canonical` fold, record its `summary` line too.

**Record the candidates beside the chosen one.** Stratified-scope and multi-entry resolution pick one denominator candidate; to make the choice auditable, append a `Denominator Candidates` block immediately after the `Denominator:` line with every count from `surface.json` `candidates`, the chosen one marked and the others as observed (`absent` when a candidate is null):

```markdown
**Denominator Candidates** (stratified-scope audit trail):
- `stats.effective_denominator`: {statsEffectiveDenominator | absent}  {← chosen if priority (1) applied}
- `scope.tier_a_include` union: {tierAIncludeUnion | absent}    {← chosen if priority (2) applied}
- `scope.include` union: {scopeIncludeUnion | absent}           {← chosen if priority (3) applied}
- exports-map subpath union: {subpathUnion | absent}        {← chosen if the multi-entry clause applied}
- root barrel: {rootBarrel | absent}                               {secondary candidate: root-barrel-vs-subpath-union audit}
```

Readers can then spot-check the chosen denominator against the others without re-running the extraction, and a reviewer who suspects denominator gaming has the evidence inline.

A gap the guards raise is a coverage gap too: `guards.deflation.fires` is a Medium `metadata-drift` gap titled `denominator deflation: effective_denominator below source public surface without tier_a_include`, and `guards.inflation.fires` a Medium `denominator-inflation` gap titled `denominator inflation: coarse scope.include union exceeds authored surface`, each with the two counts and the percentage the guard reports in its Issue and `{resolved_skill_package}/metadata.json` (deflation) or the skill brief (inflation) as its Source. When `guards.umbrella.umbrella` is true, the inflation gap's Remediation recommends `stats.effective_denominator` rather than `scope.tier_a_include`. §5b records them.

### 4b. Metadata Export-Count Coherence Cross-Check

Counts authored to measure the same surface should agree. `{coherenceScript}` bins the `coverage-inputs.json` counts into the barrel and documented-surface clusters and owns every comparison and every skip: the stack and reference-app skips, a cluster with fewer than two counts, and drift within its threshold. Run it on the file §2b wrote:

```bash
uv run {coherenceScript} --inputs "{run_dir}/coverage-inputs.json"
```

Read `findings[]` and record each entry as a gap (§5b); **do not re-derive the percentages by hand.** A Medium entry is a Medium `metadata-drift` gap and an Info entry an Info `multi-denominator` gap, titled with the entry's `title`, with its `detail` as the Issue and `{resolved_skill_package}/metadata.json` as the Source. Record the denominator of a stack (`Denominator: stack composition ({N} cited contracts)` or `({N} libraries + integration pairs)`, from `stack.basis`) and of a reference app (`Denominator: pattern-surface ({pattern_surfaces_documented})`).

**The numerator ground truth §2b ran.** When `numerator.json` reports `inflated: true` (`verified < declared`): a High `numerator-inflation` gap titled `numerator inflation: {declared − verified} of {declared} declared exports absent from SKILL.md/references`, whose Issue lists the script's `absent[]` names and whose Source is `{resolved_skill_package}/metadata.json`. When §2c recorded a missing-count gap (the scalar branch), record each `absent[]` name in its place, as a Medium `missing-export` gap titled `Missing export: {name}` with `export` `{name}` and the name's provenance `source_file:source_line` as its Source (`{resolved_skill_package}/metadata.json` when the map holds none): update-skill documents a named export, not a count. `inflated: false` or `skipped: true` is no finding.

§5b records these findings (the Medium gaps, the Info note and the High numerator-inflation gap) in the gap ledger beside the coverage and signature gaps, so the hard gate and the Gap Report see them. The count-coherence findings are informational about data quality and do not change the denominator; the numerator ground truth is the one exception, and §2c already used it.

### 4c. Provenance Line Check

Check that the provenance map records each export at the line that defines it (the `def` or declaration line itself, not a decorator or blank line above it), so update-skill can move a wrong line. Run this section only when `analysis_confidence` is `full`, `{forge_version}/provenance-map.json` exists, and `allow_workspace_drift` is not true (init.md §5b): under the drift override the tree at `{source_path}` is not the pinned commit, so its lines prove nothing about the map. Otherwise skip to section 5.

Resolve `{verifyProvenanceCompletenessHelper}` ← first existing path in `{verifyProvenanceCompletenessProbeOrder}`. If neither path exists, skip to section 5: the check is advisory. Otherwise run:

```bash
uv run {verifyProvenanceCompletenessHelper} verify \
    --metadata {resolved_skill_package}/metadata.json \
    --provenance {forge_version}/provenance-map.json \
    --source-root {source_path}
```

Rely on the JSON, not the exit code, and do not re-check the lines by eye. On exit 2 the helper prints no JSON: skip to section 5. For each `stale[]` item whose `reason` is `line-not-definition` and whose `definition_lines` holds one or more lines, §5b records one Low `provenance-line` gap. Its Source is exactly the `file:line` the map records, with nothing after it, because update-skill's rule R5 reads that pair as the gap's citation:

- **Title:** `Provenance line is not the definition of {export_name}`
- **Category:** `provenance-line`
- **Source:** `{source_file}:{source_line}`
- **Export:** `{export_name}`
- **Issue:** the provenance map records `{export_name}` at `{source_file}:{source_line}`, which is not the line that defines it; the lines that define it are {definition_lines}.
- **Remediation:** "Set the provenance `source_line` of `{export_name}` in `{source_file}` to its definition line ({definition_lines}) and move its citations to that line; update-skill `--from-test-report` applies this when the file defines it on one line."

A `line-not-definition` item whose `definition_lines` is empty means the rules found no line that defines the export, which may be a shape they do not cover: the export is unverified, not gone. Record one Info `provenance-unverified` gap for it instead, titled `Provenance line not verified for {export_name}`, with the same Source and `export`, the Issue "the line-check rules found no definition line for `{export_name}` in `{source_file}`; check by hand" and the Remediation "Open `{source_file}` and confirm that line {source_line} defines `{export_name}`; if another line does, set the provenance `source_line` to it." Never say the file no longer defines the export. update-skill does not route this Info gap.

The helper's other findings (`missing`, `orphaned` and the other `stale` reasons) are not reported by this section, and neither gap blocks the gate.

### 5. Write the Coverage Analysis Section

Write the **Coverage Analysis** section in place of the template's `## Coverage Analysis` heading and the placeholder comment under it, in `{outputFile}`:

```markdown
## Coverage Analysis

**Tier:** {forge_tier}
**Source Access:** {analysis_confidence} (full | provenance-map | metadata-only | remote-only | docs-only)
**Source Path:** {source_path}
**Workspace Layout:** {source_workspace_kind | single package | unknown (no local source, or the §0b helper failed)}
**Files Analyzed:** {count}
**Denominator:** {the §4 annotation}

### Export Coverage

| Export | Type | Documented | Signature | Source Location | Status |
|--------|------|-----------|-----------|-----------------|--------|
| ... per-export rows ... |

### Coverage Summary

- **Exports Found:** {N}
- **Documented:** {N} ({percentage}%)
- **Missing Documentation:** {N}
- **Signature Mismatches:** {N}
- **Stale Documentation:** {N}
- **Scoring Warnings:** each entry of `signatures.json` `warnings` (a category with nothing to compare scores 100, a mismatch no check asked about); omit this row when there is none
- **Numerator Surplus:** {N} — omit this row unless `coverageCapped: true`; when present, also give the uncapped percentage

### Category Scores

| Category | Score |
|----------|-------|
| Export Coverage | {N}% |
| Signature Accuracy | {N}% or N/A |
| Type Coverage | {N}% or N/A |

Note: Weight application is deferred to step 5 where all category weights are calculated after external validation availability is known.
```

### 5b. Record the Coverage Gaps

Record every gap this step found in the gap ledger `{ledgerFile}`: the hard gate (step 4c) decides from it, and the report step renders the Gap Report from it. Load the Ledger Record Format from `{outputFormatsFile}`: each gap is one JSON record whose severity and category are those of its row in the Gap Severity table of `{scoringRulesFile}`, and whose Source and Remediation follow the remediation quality rules in `{outputFormatsFile}`. The gaps, from the sections above:

- §1b: each split-body mismatch.
- §2b: each signature mismatch, which `{scoreSignaturesScript}` already wrote to `{run_dir}/signature-gaps.json`.
- §2c: each missing name, or the missing count, and each stale name.
- §4 and §4b: the denominator deflation or inflation gap, each finding of the count cross-check, and the numerator-inflation gap with the absent names it records.
- §4c: each provenance line gap.

When §2b scored the signatures, append the records the script wrote first, as they are:

```bash
uv run {gapLedgerScript} append --ledger "{ledgerFile}" --stage coverage-check --input "{run_dir}/signature-gaps.json"
```

A record about one export (`missing-export`, `missing-type`, `signature-mismatch`, `fabricated-signature`, `stale-documentation`, `split-body-mismatch`, `provenance-line`, `provenance-unverified`) names it in `export` and in its title, as the sections above say: the ledger tells two gaps apart by their title, Source and `export`, and update-skill takes the export's name from `export`.

Then write the other records as one JSON array on the lines between the two markers, exactly as they are: the quoted marker hands them to the script unchanged, quotes, apostrophes and `$` included. Run the command even when the array is empty (`[]`): the hard gate refuses to decide until every stage before it has recorded, with gaps or without (`{gapLedgerScript}` resolves relative to the skill root).

```bash
uv run {gapLedgerScript} append --ledger "{ledgerFile}" --stage coverage-check <<'SKF_GAPS'
<the records, one JSON array>
SKF_GAPS
```

Rely on its JSON:

- Exit 0: the records are in the ledger. `appended` names the id each new record received, and `duplicates` the ones a rerun of this step had already recorded.
- Exit 2 (`INVALID_RECORD` or `INVALID_INPUT`): nothing was written. Correct each record `errors[]` names (its `index` counts from 0) and run the command again.
- Exit 1: HALT with the script's `error`.

### 6. Report Coverage Results

Report the coverage result to the user: the {forge_tier}-tier analysis of {file_count} source files, the documented ratios for exports / signatures / types (signatures and types are N/A for Quick tier), and the issue count. Full details are in the Coverage Analysis section. Then proceed to the coherence check.

Append `'coverage-check'` to `stepsCompleted` in the `{outputFile}` frontmatter, then load and execute {nextStepFile}.
