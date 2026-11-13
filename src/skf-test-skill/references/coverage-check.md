---
nextStepFile: 'coherence-check.md'
outputFile: '{report_file}'
scoringRulesFile: 'references/scoring-rules.md'
signatureRulesFile: 'references/signature-comparison-rules.md'
inventoryContractFile: 'references/inventory-contract.md'
sourceAccessProtocol: 'references/source-access-protocol.md'
coverageTiersFile: 'references/coverage-check-tiers.md'
coverageBranchesFile: 'references/coverage-check-branches.md'
validateInventoryScript: 'scripts/validate-inventory.py'
coverageInputsScript: 'scripts/load-coverage-inputs.py'
scoreSignaturesScript: 'scripts/score-signatures.py'
reconcileScript: 'scripts/reconcile-coverage.py'
coherenceScript: 'scripts/check-metadata-coherence.py'
numeratorVerifyScript: 'scripts/verify-declared-numerator.py'
stageHelperPayloadScript: 'scripts/stage-helper-payload.py'
ledgerFile: '{forge_version}/test-findings-{run_id}.json'
gapLedgerScript: 'scripts/gap-ledger.py'
# Each `<name>ProbeOrder` resolves `{<name>Helper}` to its first existing path:
# the installed SKF module first, the src/ dev checkout second.
verifyProvenanceCompletenessProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-verify-provenance-completeness.py'
  - '{project-root}/src/shared/scripts/skf-verify-provenance-completeness.py'
extractPublicApiProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-extract-public-api.py'
  - '{project-root}/src/shared/scripts/skf-extract-public-api.py'
detectWorkspacesProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-detect-workspaces.py'
  - '{project-root}/src/shared/scripts/skf-detect-workspaces.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 3: Coverage Check

## STEP GOAL:

Compare what SKILL.md documents (exports, functions, classes, types, interfaces) with the source API surface: missing documentation, undocumented exports, signature mismatches, at the forge tier's depth.

**Halt envelope.** Every HALT in this step names its `halt_reason` and phase and carries exit code 1. It releases the run lock first, whatever the release prints: from `{project-root}`, run `uv run {runLockHelper} release --lock "{forge_version}/.test-skill.lock" --owner "{run_owner}"` (SKILL.md Workflow Rules). In headless mode it then writes `{"phase": "<phase>", "reason": "<the halt message>", "halt_reason": "<halt_reason>", "skill_name": "{skill_name}", "report_path": "{report_file}"}`, adding `"path"` when the halt names one, to `{run_dir}/halt.json` and runs:

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-test-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
```

Display the line it prints, as the run's last line, then stop. If the emitter exits non-zero or prints no line, display the halt message alone. An interactive HALT displays its message and emits nothing.

**Run files.** Every script below writes its result into the run folder `{run_dir}` that init.md §6b created, where the next one reads it by path. A subagent's response is saved there exactly as it came back, fence and all (the subagent writes it to the path it is given, or the parent saves it, with the Write tool), and passed by path, so a quote or an apostrophe in it never meets a shell. Every count, name list and score a script computes is read from the file it wrote, never re-derived by hand or copied between commands. Each command runs from `{project-root}`; a `{...Script}` path resolves relative to the skill root.

### 0. Check for Docs-Only Mode

A skill is docs-only when every citation it writes is `[EXT:...]`, none local (`[AST:...]`, `[SRC:...]`, or a stack's `[from skill: ...]`). The citation census decides it:

```bash
uv run {coverageInputsScript} census --skill-dir "{resolved_skill_package}" --output "{run_dir}/census.json"
```

Bind `{docs_only_mode}` ← `docsOnly` and write it to the `{outputFile}` frontmatter as `docsOnly: true` or `false`, bare. Exit 1 printed its error on stderr: HALT with it (`halt_reason: "helper-failed"`, phase `coverage-check:census`). §0b sets `{docs_only_mode}` too when source access reaches State 5.

**A docs-only run**: load `{coverageBranchesFile}` and follow its **Docs-Only Run** section.

### 0b. Load Source Access Protocol

Read the source access from the files, leaving out `--metadata` when init.md §2 found no metadata.json (its `metadata-missing` warning), `--provenance` when it bound no `{forge_provenance_map}` and `--source-root` when `{source_path}` is null:

```bash
uv run {coverageInputsScript} access [--metadata "{resolved_skill_package}/metadata.json"] [--provenance "{forge_provenance_map}"] [--source-root "{source_path}"] --output "{run_dir}/access.json"
```

Exit 1 printed its error on stderr: HALT with it (`halt_reason: "helper-failed"`, phase `coverage-check:access`). Then load `{sourceAccessProtocol}` and follow its **Source API Surface Definition** (the denominator clause §2b picks) and **Source Access Resolution** (the 5-state waterfall that sets `analysis_confidence`; State 5 makes the run docs-only).

**Workspace layout.** The Source API Surface Definition's monorepo tests read `{source_is_monorepo}`. At State 1 (local source), resolve `{detectWorkspacesHelper}` ← first existing path in `{detectWorkspacesProbeOrder}` and run (`{stageHelperPayloadScript}` pipes it the tree and root manifests from disk; leave `--brief` out with no brief):

```bash
uv run {stageHelperPayloadScript} detect-workspaces --source-root "{source_path}" --brief "{forge_data_folder}/{skill_name}/skill-brief.yaml" | uv run {detectWorkspacesHelper}
```

A workspace whose members `scope.exclude` drops is no workspace. Bind `{source_is_monorepo}` ← `is_monorepo` and `{source_workspace_kind}` ← `manifest_kind`. At States 2 to 5, or when the helper does not resolve or the command exits non-zero, the layout is unknown: bind `{source_is_monorepo}` ← false. §5 records the layout.

**Clause flags.** Every `surface` command, in §2 or in a branch file it loads, takes `--monorepo` when `{source_is_monorepo}` is true, and the flags the Source API Surface Definition leaves to you.

### 1. Extract Documented Exports from SKILL.md

First write the inventory's floor, the names the skill documents in a fixed form, which the inventory must keep:

```bash
uv run {coverageInputsScript} floor --skill-dir "{resolved_skill_package}" --output "{run_dir}/inventory-floor.json"
```

Exit 1 printed its error on stderr: HALT with it (`halt_reason: "helper-failed"`, phase `coverage-check:inventory`).

Delegate the reading of the skill under test to a subagent, given `{run_dir}` and the path to SKILL.md and to its `references/` directory when one exists: it reads SKILL.md, and every `references/*.md` file too when SKILL.md's `## Full` headings are absent or stubs. It is given `{run_dir}/inventory-floor.json` too, and lists each name there with an origin in a file it reads, choosing its kind from the name's `kindLabel`, the skill's own label, when it has one. An origin's `signature` is that place's entry, at that place, its non-blank fields kept as given; a blank one is the reader's. For each export two or more of the files it reads document, it compares the SKILL.md body with each reference file, and two reference files with each other only when the body does not settle them (it does not document the export, or agrees with both), by the rules of `{signatureRulesFile}`, whose absolute path (under `{skill-root}`) it is given: parameters, the return type, and descriptions that contradict (brief against detailed is fine). That file alone says what a form may leave out. It writes only this JSON, with no prose and no commentary, to `{run_dir}/inventory-response.txt` with the Write tool, never a shell, and returns that path, or returns the JSON itself when it cannot write files. The JSON's shape and the contract the validator checks are in `{inventoryContractFile}`, whose absolute path (under `{skill-root}`) the subagent is given.

When the subagent returned the JSON rather than the path, or the file is absent or empty afterwards, save its response, as it came back, to `{run_dir}/inventory-response.txt` with the Write tool. The documented inventory is the one §1a validates: do not load SKILL.md or the reference files into the parent context. Without subagents, the parent loads `{inventoryContractFile}` and builds the same JSON from the same files and `inventory-floor.json` and saves it to that file; §1a's checks still run on it.

#### 1a. Parent-Side Schema Validation + Spot-Check

Before anything consumes the inventory, `{validateInventoryScript}` checks it against the §1 contract (a wrapping fence stripped), spot-checks sampled names against SKILL.md and the subagent's listed reference files, and refuses it when it leaves out a floor name those files write, or an origin's `signature`. The look-up is the script's, never a grep: an export named `$state` or `a.b` is neither a shell variable nor a regex.

```bash
uv run {validateInventoryScript} --input "{run_dir}/inventory-response.txt" --skill-package "{resolved_skill_package}" --output "{run_dir}/inventory.json" --floor "{run_dir}/inventory-floor.json"
```

- `valid` true (exit 0): every later command reads `{run_dir}/inventory.json`. Each of its `warnings` that says "the form is compared as one whose citations name no declaration" names a form whose place (`at`) is missing or bad, dropped so §2 binds it to no declaration: list their count and names in §5's notes, the forms left unbound for want of a place.
- `valid` false (exit 2), or exit 1: load `{coverageBranchesFile}` and follow its **Inventory Failures** section. Invalid a second time: HALT (`halt_reason: "inventory-invalid"`, phase `coverage-check:inventory`): "coverage-check: the subagent inventory failed {schema validation | the ground-truth spot-check | the floor check} twice: {the violations joined}."

### 1b. Cross-Check Split-Body Consistency

Only when the validated inventory's `references` is non-empty. Each `cross_check_mismatches` entry is a High `split-body-mismatch` gap. §5b records it titled `Split-body mismatch: {export} ({reference_file})`, with its `export` and its Source at the side the source contradicts (`{reference_file}` when no source settles it): update-skill makes the edits its remediation names, reading no source. An entry for two references the body does not settle is titled `Split-body mismatch: {export} ({other_file}, {reference_file})`.

### 2. Analyze Source Code (Tier-Dependent)

Identify the public API surface from the package entry points (0b), as deep as the tier allows; whichever branch runs, `{coverageInputsScript} surface` writes it to `{run_dir}/surface.json`. Names read by eye reach it as per-file results, `{"file": "<path>", "exports_found": [<each name>], "signature_mismatches": []}` for each file, saved to `{run_dir}/per-file-<n>.json` with the Write tool and given to `surface` with one `--per-file` each. An `export * from` or `export type * from` another package adds no name: list `<line>: <statement>` in `unresolved_stars` and Coverage Analysis.

**Exits.** Every `{coverageInputsScript}` and `{scoreSignaturesScript}` command in §2 and §2b exits 0, or exits 1 with its error on stderr: HALT with it (`halt_reason: "helper-failed"`, phase `coverage-check:surface`). `surface` with a `--per-file`, and `score`, also exit 2 when a subagent response breaks the schema or leaves out a file its batch was given: re-dispatch each judge a violation names (for a left-out file, its batch's) once with its `violations[]` appended (or correct a result the main thread wrote, or the response files passed: one per batch, in batch order), save each new response over the old one and run the command again; a second failure HALTs the same way.

**Quick Tier (no AST tools):** load `{coverageTiersFile}` and follow its **Quick Tier** section. Signatures cannot be verified at this tier (§5's render marks them unverified).

**Forge Tier (ast-grep available):**

At State 1, run the recipe runner once over the source. Resolve `{extractPublicApiHelper}` ← first existing path in `{extractPublicApiProbeOrder}` and run it (leave `--brief` out when the skill has no brief; `--head-cap 0` keeps every match, so no export is cut and read as missing):

```bash
uv run {extractPublicApiHelper} --mode full --source-root "{source_path}" --brief "{forge_data_folder}/{skill_name}/skill-brief.yaml" --tier {detected_tier} --head-cap 0 --output "{run_dir}/extract-full.json"
```

Exit 2 is an input error (a brief the runner cannot read, say) or a failure the runner did not foresee, named in one line on stderr with no JSON: HALT with that line (`halt_reason: "helper-failed"`, phase `coverage-check:surface`). No Fallback Per-File Scan stands in for it.

Build the surface from it, with the metadata, the brief when the skill has one and, when init.md §2 bound one, the provenance map (the baselines of the §2b candidates and guards; they add no name):

```bash
uv run {coverageInputsScript} surface --extraction "{run_dir}/extract-full.json" --metadata "{resolved_skill_package}/metadata.json" [--provenance "{forge_provenance_map}"] [--brief "{forge_data_folder}/{skill_name}/skill-brief.yaml"] [--monorepo] [--pattern-reference-intent] [--curated-subset] --output "{run_dir}/surface.json"
```

The surface holds what `{sourceAccessProtocol}` **What the Surface Holds** says. §5's render lists `excluded.outsideScope`, `excluded.nestedEntries`, the restored names and `extractionGaps`. Decide what to do from the JSON, not from the exit code:

- `extraction.fallback.needed` is true, or the runner printed no JSON on an exit other than 2: load `{coverageTiersFile}` and run its **Fallback Per-File Scan** in place of the rest of this tier.
- `extraction.readByEye` is non-empty (a file the run could not parse or decode, or a failed call left unread): keep the surface, read by eye only the files it names, save a per-file result for each, and run `surface` again with them, once (the second call starts no new pass).
- In the Coverage Analysis section, list each `readByEye` file as read by eye, each `extraction.unread` file as unread.
- `extractionGaps[]` names exports no recipe found: on the surface, judged below when documented and located; read none by eye.

**Compare the signatures.** A script plans (pass `--doc-errors` at the Deep tier, below); subagents judge:

```bash
uv run {scoreSignaturesScript} plan --inventory "{run_dir}/inventory.json" --surface "{run_dir}/surface.json" --skill-dir "{resolved_skill_package}" [--doc-errors] --output "{run_dir}/signature-plan.json"
```

For each `batches[]` entry, delegate one subagent with the `files[]` entries it names, their checks and the absolute path of `{signatureRulesFile}` (under `{skill-root}`). For each check it reads the full declaration at `{file}:{line}` (all of it, not only `signatureLine`'s one physical line; with `line` null, find it in `{file}` and give its mismatch that line), compares it with the check's `documented` signature by the rules of that file, and returns only a JSON array, one object per `files[]` entry it was given, with no prose and no markdown fences:

```json
[{"file": "src/utils.ts", "signature_mismatches": [{"name": "formatDate", "line": 42, "source_sig": "(date: Date, format?: string) => string", "documented_sig": "(date: Date) => string", "issue": "missing optional parameter 'format'", "difference": "omitted-optional"}], "undecided": []}]
```

Tag a mismatch's `difference` as `{signatureRulesFile}` says: `score` (§2b) checks the facts. One tagged `annotation-contradicted` also gives `evidence_line`, the body line that returns the documented type.

A check with `candidates` reads each as above and reports a mismatch only when the documented signature matches none: one, at the closest candidate, its `file` and `line` on the mismatch object (the result's `file` stays its `files[]` entry) and its `difference` tagged against it.

A check with `alternatives` (the other forms the skill documents for the name) is compared with each of them too, as `{signatureRulesFile}` says, each mismatch naming its form as `form`.

A check's `bound` lists each form (its `form` index) whose own citations name one declaration of the name: one of its surface records, or of its `surface.json` `otherDeclarations` (a same-named declaration no entry point exports). Its own citations are the `[AST:]` and `[SRC:]` citations `{validateInventoryScript}` reads at the inventory's `at`: on that line, after it unless it is a table row, and around its fenced block, as its `form_citations` says. A citation names a declaration when it cites the declaration's file at a line or in an `L` range that holds its line or a later one before the next declaration the surface records in its file; one with no line names every declaration in its file. The `files[]` entry `""` names no file: its judge compares only bound forms, `imports` and `members`, and gives its result the first check's first `bound` `file` as `file`. Compare a bound form with its bound declaration alone, read in full at its `file` and `line` as above, whatever the check's `candidates`, and report its mismatch there, `file` and `line` on the mismatch object.

A check with `member` is a `method`'s, named `{owner}.{member}`: its `file`, `line`, `candidates` and `bound` entries are its owner's declarations. Compare its forms with its owner's `member`, as `{signatureRulesFile}` says, and report each mismatch under the check's `name`, at the member's `file` and `line`, a bound form's and a candidate's too.

Save each batch's response to `{run_dir}/signatures-<n>.txt` with the Write tool, `<n>` counting the batches from 1. Without subagents, load `{signatureRulesFile}`, compare in the main thread by its rules and save the same JSON, one array per batch in its own `signatures-<n>.txt`.

**Deep Tier (ast-grep + gh + QMD):** the Forge tier checks: init.md §5b's drift guard checks the local tree against the pinned commit, at any tier, when both exist; the recipe runner traces each re-export to the file that defines it when it runs (the fallback per-file scan does not); and the Forge tier's signature check compares each documented signature with its declaration. Run its plan with `--doc-errors`: each check also carries the skill's import lines of its name (`imports`) and its documented members (`members`), and a located documented name with no form but with either gets a check with no `documented`. Its judge compares them with the source by `{signatureRulesFile}` and adds each that differs to the JSON above as `doc_errors`, which `score` records as an Info `Not checked by script: {name}` observation at the documenting line.

**States 2 to 4 (no local source):** the surface is what the skill recorded, so there is no signature to score: load `{coverageBranchesFile}` and follow its **States 2 to 4** section.

### 2b. Resolve the Denominator and Guard Zero Exports

Load the metadata and provenance-map counts once (pass `--provenance` when init.md §2 bound `{forge_provenance_map}`):

```bash
uv run {coverageInputsScript} metadata --metadata "{resolved_skill_package}/metadata.json" [--provenance "{forge_provenance_map}"] --output "{run_dir}/coverage-inputs.json"
```

**Pick the denominator.** `surface.json` `denominator` holds the Source API Surface Definition clause (§0b) `surface` picked: its §2c `branch` (`barrel`, `scalar` or `stack`), `surfaceSet` (the set the barrel branch counts, as the scalar one does when `setCounted` is true, and the signature score reads) and `ladderStep`. When `absentSet` names a set the surface lacks, `surfaceSet` is `all`, and §5's render says so on the `Denominator:` line. When `rebuild` is `provenance-fold`, load `{coverageBranchesFile}` and rerun State 2's command from its **States 2 to 4** section without `--metadata` and with `--fold` and `--pattern-reference-intent`, running nothing else from that section, and read the `denominator` it writes.

- **A stack skill** (`branch` `stack`): `coverage-inputs.json` `stack.denominator`. Its own barrel is empty by design, and its `[from skill: …]` citations never make it docs-only. **If `stack.denominator` is 0**: HALT (`halt_reason: "indeterminate-surface"`, phase `coverage-check:denominator`) with `Error: stack composition surface empty: {skill_name} cites no contracts, libraries, or integration pairs, so Export Coverage is undefined. Verify the stack was compiled from at least one constituent skill.` Do not write the Coverage Analysis section; this is an indeterminate state, not a FAIL.
- **A docs-only skill**: the `docsOnly` branch, over the inventory.

**Numerator ground truth.** A declared count equal to the denominator (`stats.exports_documented == stats.effective_denominator`, the inflation signature) may be padded to a tautological 100%. A declared name is `verified` only when the validated inventory gives it an entry and the skill's text writes it: one the skill writes only where the inventory contract gives it none (such as a mention in running text, a bullet list or a description cell, a type position in another name's signature, a sentence saying the skill does not cover it, a local import alias, a name it says the source does not export, a form marked removed or from an earlier version) is `absent`. A name a module path qualifies has the entry of its last segment (`cognee.add` that of `add`), and one the provenance map types `module` or `package`, which the inventory has no kind for, is `verified` when the text writes it. Run it on every source-based skill (without the signature it reports `skipped`):

```bash
uv run {numeratorVerifyScript} --inputs "{run_dir}/coverage-inputs.json" --skill-dir "{resolved_skill_package}" --inventory "{run_dir}/inventory.json" --output "{run_dir}/numerator.json"
```

Unless §2c's scalar branch counts its set, it takes the `verified` count as the numerator when `inflated` is true; §4b records the gap. Exit 1 or 2: HALT with its message (`halt_reason: "helper-failed"`, phase `coverage-check:numerator`).

**If the chosen denominator is 0 AND `docs_only_mode == false` AND `metadata.json.skill_type != "stack"`:** HALT (`halt_reason: "indeterminate-surface"`, phase `coverage-check:denominator`) with:

```
Error: indeterminate API surface: 0 exports discovered in source for {skill_name}.

Export Coverage is undefined, and scoring would yield a vacuous PASS. Fix one of:
  - Set `scope.include` in the brief to point at the package's entry point(s)
  - Add `[EXT:]` citations if this is actually a docs-only skill
  - Verify the skill's source_root / source_ref resolve to the intended tree
```

Do not write the Coverage Analysis section or attach a score: this is an indeterminate state, not a FAIL. **If `docs_only_mode == true` and the validated inventory documents no item:** HALT the same way with "docs-only skill declares zero items: no API surface to test".

**Score the signatures** (Forge, Forge+ and Deep tier at State 1, once §2 compared them). Give `{scoreSignaturesScript}` `denominator.surfaceSet` as `--surface-set`. Give it one `--results` per batch, in batch order (the fallback scan's `per-file-<n>.txt`, else the `signatures-<n>.txt`), and `--source-root` whenever the source is local (State 1, Forge tier or above), under a drift override too, since the judges read that tree:

```bash
uv run {scoreSignaturesScript} score --inventory "{run_dir}/inventory.json" --surface "{run_dir}/surface.json" --surface-set <set> --plan "{run_dir}/signature-plan.json" [--source-root "{source_path}"] --results "{run_dir}/signatures-<n>.txt" --output "{run_dir}/signatures.json" --gaps-output "{run_dir}/signature-gaps.json"
```

It grades each mismatch of a compared name by facts it checks, never a `difference` alone, into `signature-gaps.json`, which §5b appends to the ledger. A bound form's mismatch is recorded at its bound declaration, a judge that names another file listed in `warnings`; a bound declaration joins no name, set or count. §5's render lists its `warnings`.

### 2c. Reconcile Documented vs Source Surface (Deterministic Intersection)

`{reconcileScript}` reconciles the §1 inventory with the source surface into `{run_dir}/coverage.json`, whose `exportCoverage` step 5 hands to the scoring script. Run the branch §2b picked:

1. **Barrel**, with the name set §2b picked as `--surface-set`:

   ```bash
   uv run {reconcileScript} --denominator-source barrel --inventory "{run_dir}/inventory.json" --surface "{run_dir}/surface.json" --surface-set <set> --output "{run_dir}/coverage.json"
   ```

2. **Scalar or stack**: load `{coverageBranchesFile}` and follow its **Scalar and Stack Branches** section, which runs the branch's command.

3. **Docs-only**: the command in the Docs-Only Run section of coverage-check-branches.md.

Exit 2 printed an `INVALID_INPUT` envelope: correct the input it names and run it again. Exit 1: HALT with its stderr (`halt_reason: "helper-failed"`, phase `coverage-check:reconcile`).

**Classify what the script found.** §5b records each of these gaps from the run files:

- **Missing names** (`missing`, barrel or scalar).
- **Stale names** (`stale` when `staleApplicable` is true): each is a documented name the enumerated source surface lacks. Where ast-grep read the source at the pinned commit (Forge, Forge+ or Deep tier, `analysis_confidence` `full`, `workspaceDrift` not `overridden` in the `{outputFile}` frontmatter) and init.md §2 bound `{forge_provenance_map}`, resolve `{verifyProvenanceCompletenessHelper}` ← first existing path in `{verifyProvenanceCompletenessProbeOrder}` and run once (leave `--brief` out with no brief):

  ```bash
  uv run {verifyProvenanceCompletenessHelper} classify-stale --names "{run_dir}/coverage.json" --provenance "{forge_provenance_map}" --source-root "{source_path}" --inventory "{run_dir}/inventory.json" [--brief "{forge_data_folder}/{skill_name}/skill-brief.yaml"] -o "{run_dir}/stale.json"
  ```

  A helper that does not resolve or exits non-zero writes no `stale.json`, and §5b's call leaves `--stale` out.

### 4. The Denominator Record

§5's render writes the denominator record (the `Denominator:` line, the fold summary and the Denominator Candidates block) from `surface.json`, `coverage.json` and `coverage-inputs.json`.

The guards that fire raise coverage gaps too, which §5b records from `surface.json`.

### 4b. Metadata Export-Count Coherence Cross-Check

Load `{coverageBranchesFile}` and follow its **Metadata Count Cross-Check** section.

**The numerator ground truth §2b ran.** §5b records its finding from `numerator.json`.

### 4c. Provenance Line Check

Check that the provenance map records each export at its definition line (not a decorator or blank line above it). Run this section only when `analysis_confidence` is `full`, `{forge_version}/provenance-map.json` exists, and the `{outputFile}` frontmatter's `workspaceDrift` is not `overridden` (init.md §5b: the drifted tree is not the pinned commit). Otherwise skip to section 5.

Resolve `{verifyProvenanceCompletenessHelper}` ← first existing path in `{verifyProvenanceCompletenessProbeOrder}`. If neither path exists, skip to section 5: the check is advisory. Otherwise run:

```bash
uv run {verifyProvenanceCompletenessHelper} verify \
    --metadata {resolved_skill_package}/metadata.json \
    --provenance {forge_version}/provenance-map.json \
    --source-root {source_path} \
    -o "{run_dir}/provenance-verify.json"
```

Rely on the file, not the exit code (exit 1 means findings); on exit 2 the helper writes no file: skip to section 5. §5b records each `stale[]` item from that file.

This section reports none of the helper's `missing`, `orphaned` or `citations` findings, and no gap it records blocks the gate.

### 5. Write the Coverage Analysis Section

Write the **Coverage Analysis** section in place of the template's `## Coverage Analysis` heading and the placeholder comment under it, in `{outputFile}`. `{reconcileScript}` renders its counts, per-export table and category scores from the run files (leave out `--surface` on a docs-only run, `--signatures` when §2b scored none and `--coverage-inputs` when §2b wrote none):

```bash
uv run {reconcileScript} render --coverage "{run_dir}/coverage.json" [--surface "{run_dir}/surface.json"] [--signatures "{run_dir}/signatures.json"] [--coverage-inputs "{run_dir}/coverage-inputs.json"]
```

Exit 0: write its output unchanged where the section below places it. Exit 2 is a usage error: correct the command and run it again. Exit 1 printed its error on stderr: HALT with it (`halt_reason: "helper-failed"`, phase `coverage-check:render`).

```markdown
## Coverage Analysis

**Tier:** {detected_tier}
**Source Access:** {analysis_confidence}
**Source Path:** {source_path}
**Workspace Layout:** {source_workspace_kind | single package | unknown (no local source, or the §0b helper failed)}
{the render output}

{the notes §1a to §4b add to this section}
```

### 5b. Record the Coverage Gaps

Record every gap this step found in the gap ledger `{ledgerFile}`, which the hard gate decides from and the report step renders. `{gapLedgerScript}` writes each gap a script found from that script's file, with the severity and category of its row in the Gap Severity table of `{scoringRulesFile}` and a fixed title, Source, `export` and Remediation. Run each command whose `--input` file this run wrote, leaving out a bracketed flag whose file does not exist: a run file this run did not write, or `--provenance` when init.md §2 bound no `{forge_provenance_map}`:

```bash
uv run {gapLedgerScript} append --ledger "{ledgerFile}" --stage coverage-check --input "{run_dir}/signature-gaps.json"
uv run {gapLedgerScript} append --ledger "{ledgerFile}" --stage coverage-check --from coverage --input "{run_dir}/coverage.json" [--surface "{run_dir}/surface.json"] [--signatures "{run_dir}/signatures.json"] [--numerator "{run_dir}/numerator.json"] [--stale "{run_dir}/stale.json"] [--provenance "{forge_provenance_map}"] --inventory "{run_dir}/inventory.json" --skill-dir "{resolved_skill_package}" --metadata "{resolved_skill_package}/metadata.json"
uv run {gapLedgerScript} append --ledger "{ledgerFile}" --stage coverage-check --from guards --input "{run_dir}/surface.json" --metadata "{resolved_skill_package}/metadata.json"
uv run {gapLedgerScript} append --ledger "{ledgerFile}" --stage coverage-check --from numerator --input "{run_dir}/numerator.json" --metadata "{resolved_skill_package}/metadata.json"
uv run {gapLedgerScript} append --ledger "{ledgerFile}" --stage coverage-check --from metadata-coherence --input "{run_dir}/metadata-coherence.json" --metadata "{resolved_skill_package}/metadata.json"
uv run {gapLedgerScript} append --ledger "{ledgerFile}" --stage coverage-check --from provenance-line --input "{run_dir}/provenance-verify.json" [--stale "{run_dir}/stale.json"]
```

**A split-body mismatch's Source** is a line inside the skill package: when §1b found one, load `{coverageBranchesFile}` and follow its **Split-Body Sources** section.

Save each §1b entry's settlement, in `cross_check_mismatches` order, to `{run_dir}/split-body-settlements.json` with the Write tool: one JSON array of `{"export", "reference_file", "source", "remediation"}`, the entry's `export` and `reference_file`, `source` `reference` when its Source is `{reference_file}:{reference_line}` and `other` when it is the other side, and the remediation that section gives it. The script builds each record's title, Source and `export` from the inventory entry. Run the command even when §1b found none, leaving out `--settlements`: the hard gate refuses to decide until every stage before it has recorded.

```bash
uv run {gapLedgerScript} append --ledger "{ledgerFile}" --stage coverage-check --from split-body --input "{run_dir}/inventory.json" [--settlements "{run_dir}/split-body-settlements.json"]
```

Rely on the JSON of each command:

- Exit 0: the records are in the ledger.
- Exit 2 (`INVALID_RECORD` or `INVALID_INPUT`): nothing was written. Correct each record `errors[]` names (its `index` counts from 0), or the file or flag the `error` names, and run the command again.
- Exit 1: HALT with the script's `error` (`halt_reason: "helper-failed"`, phase `coverage-check:ledger`).

### 6. Report Coverage Results

Report to the user from §5's render: the {detected_tier} tier, the **Files Analyzed** count, the three category scores and the issue count.

Append `'coverage-check'` to `stepsCompleted` in the `{outputFile}` frontmatter, then load and execute {nextStepFile}.
