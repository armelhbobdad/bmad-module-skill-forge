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
outputFormatsFile: 'assets/output-section-formats.md'
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

Bind `{docs_only_mode}` ← `docsOnly`. Exit 1 printed its error on stderr: HALT with it (`halt_reason: "helper-failed"`, phase `coverage-check:census`). §0b sets `{docs_only_mode}` too when source access reaches State 5.

**A docs-only run**: load `{coverageBranchesFile}` and follow its **Docs-Only Run** section.

A source-based skill continues with §0b.

### 0b. Load Source Access Protocol

Load `{sourceAccessProtocol}` and follow both sections: **Source API Surface Definition** (the denominator clause §2b picks) and **Source Access Resolution** (the 5-state waterfall that decides how the source is read and sets `analysis_confidence`; State 5 makes the run docs-only).

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

Delegate the reading of the skill under test to a subagent, given `{run_dir}` and the path to SKILL.md and to its `references/` directory when one exists: it reads SKILL.md, and every `references/*.md` file too when SKILL.md's `## Full` headings are absent or stubs. It is given `{run_dir}/inventory-floor.json` too, and lists each name there with an origin in a file it reads, choosing its kind from the name's `kindLabel`, the skill's own label, when it has one. An origin's `signature` is that place's entry, at that place, its non-blank `params` and `return_type` kept as given; a blank one is the reader's. For each export two or more of the files it reads document, it compares the SKILL.md body with each reference file, and two reference files with each other only when the body does not settle them (it does not document the export, or agrees with both), by the rules of `{signatureRulesFile}`, whose absolute path (under `{skill-root}`) it is given: parameters, the return type, and descriptions that contradict (brief against detailed is fine). That file alone says what a form may leave out. It writes only this JSON, with no prose and no commentary, to `{run_dir}/inventory-response.txt` with the Write tool, never a shell, and returns that path, or returns the JSON itself when it cannot write files. The JSON's shape and the contract the validator checks are in `{inventoryContractFile}`, whose absolute path (under `{skill-root}`) the subagent is given.

When the subagent returned the JSON rather than the path, or the file is absent or empty afterwards, save its response, as it came back, to `{run_dir}/inventory-response.txt` with the Write tool. The documented inventory is the one §1a validates: do not load SKILL.md or the reference files into the parent context. Without subagents, the parent loads `{inventoryContractFile}` and builds the same JSON from the same files and `inventory-floor.json` and saves it to that file; §1a's checks still run on it.

#### 1a. Parent-Side Schema Validation + Spot-Check

Before anything consumes the inventory, `{validateInventoryScript}` checks it against the §1 contract (a wrapping fence stripped), spot-checks sampled names against SKILL.md and the subagent's listed reference files, and refuses it when it leaves out a floor name those files write, or an origin's `signature` at its origin, or when an entry's `at` is missing or is no line of those files that writes its name. The look-up is the script's, never a grep: an export named `$state` or `a.b` is neither a shell variable nor a regex.

```bash
uv run {validateInventoryScript} --input "{run_dir}/inventory-response.txt" --skill-package "{resolved_skill_package}" --output "{run_dir}/inventory.json" --floor "{run_dir}/inventory-floor.json"
```

- `valid` true (exit 0): every later command reads `{run_dir}/inventory.json`.
- `valid` false (exit 2), or exit 1: load `{coverageBranchesFile}` and follow its **Inventory Failures** section. Invalid a second time: HALT (`halt_reason: "inventory-invalid"`, phase `coverage-check:inventory`): "coverage-check: the subagent inventory failed {schema validation | the ground-truth spot-check | the place (`at`) check | the floor check} twice: {the violations joined}."

### 1b. Cross-Check Split-Body Consistency

Only when the validated inventory's `references` is non-empty. Each `cross_check_mismatches` entry is a High `split-body-mismatch` gap. §5b records it titled `Split-body mismatch: {export} ({reference_file})`, with its `export` and its Source at the side the source contradicts (`{reference_file}` when no source settles it): update-skill edits that file to match the other without reading the source. An entry for two references the body does not settle is titled `Split-body mismatch: {export} ({other_file}, {reference_file})`.

### 2. Analyze Source Code (Tier-Dependent)

Identify the public API surface from the package entry points (0b), as deep as the tier allows. Whichever branch runs, `{coverageInputsScript} surface` writes it to `{run_dir}/surface.json`, which §2b, §2c, §4 and step 5 read. Names read by eye reach it as per-file results, `{"file": "<path>", "exports_found": [<each name>], "signature_mismatches": []}` for each file, saved to `{run_dir}/per-file-<n>.json` with the Write tool and given to `surface` with one `--per-file` each. An `export * from` or `export type * from` another package adds no name: list `<line>: <statement>` in `unresolved_stars` and Coverage Analysis.

**Exits.** Every `{coverageInputsScript}` and `{scoreSignaturesScript}` command in §2 and §2b exits 0, or exits 1 with its error on stderr: HALT with it (`halt_reason: "helper-failed"`, phase `coverage-check:surface`). `surface` with a `--per-file`, and `score`, also exit 2 when a subagent response breaks the schema: re-dispatch that subagent once with its `violations[]` appended (or correct a result the main thread wrote), save the new response over the old one and run the command again; a second failure HALTs the same way.

**Quick Tier (no AST tools):** load `{coverageTiersFile}` and follow its **Quick Tier** section. Signatures cannot be verified at this tier (§5's render marks them unverified).

**Forge Tier (ast-grep available):**

At State 1, run the recipe runner once over the source. Resolve `{extractPublicApiHelper}` ← first existing path in `{extractPublicApiProbeOrder}` and run it (leave `--brief` out when the skill has no brief; `--head-cap 0` keeps every match, so no export is cut and read as missing):

```bash
uv run {extractPublicApiHelper} --mode full --source-root "{source_path}" --brief "{forge_data_folder}/{skill_name}/skill-brief.yaml" --tier {detected_tier} --head-cap 0 --output "{run_dir}/extract-full.json"
```

Exit 2 is an input error (a brief the runner cannot read, say) or a failure the runner did not foresee, named in one line on stderr with no JSON: HALT with that line (`halt_reason: "helper-failed"`, phase `coverage-check:surface`). No Fallback Per-File Scan stands in for it: every flag here is fixed, so the error is a defect to surface.

Build the surface from it, with the metadata, the brief when the skill has one and, when init.md §2 bound one, the provenance map (the baselines of the §2b candidates and guards; they add no name):

```bash
uv run {coverageInputsScript} surface --extraction "{run_dir}/extract-full.json" --metadata "{resolved_skill_package}/metadata.json" [--provenance "{forge_provenance_map}"] [--brief "{forge_data_folder}/{skill_name}/skill-brief.yaml"] [--monorepo] [--pattern-reference-intent] [--curated-subset] --output "{run_dir}/surface.json"
```

The surface holds what `{sourceAccessProtocol}` **What the Surface Holds** says (its exclusions and the stale-scope guard). §5's render lists `excluded.outsideScope`, `excluded.nestedEntries` and the restored names. Decide what to do from the JSON, not from the exit code:

- `extraction.fallback.needed` is true, or the runner printed no JSON on an exit other than 2: load `{coverageTiersFile}` and run its **Fallback Per-File Scan** in place of the rest of this tier.
- `extraction.readByEye` is non-empty (a file the run could not parse or decode, or a failed call left unread): keep the surface, read by eye only the files it names, save a per-file result for each, and run `surface` again with them, once (the second call starts no new pass).
- In the Coverage Analysis section, list each `readByEye` file as read by eye, each `extraction.unread` file as unread.
- `extractionGaps[]` names exports no recipe found: they are on the surface; read their signature by eye at their `file` and `line`.

**Compare the signatures.** A script lists the comparisons; subagents judge them:

```bash
uv run {scoreSignaturesScript} plan --inventory "{run_dir}/inventory.json" --surface "{run_dir}/surface.json" --skill-dir "{resolved_skill_package}" --output "{run_dir}/signature-plan.json"
```

For each `files[]` entry, delegate one subagent with its checks and the absolute path of `{signatureRulesFile}` (under `{skill-root}`). For each check it reads the full declaration at `{file}:{line}` (all of it: `signatureLine` is one physical line, and a multi-line signature cut there reads as a mismatch), compares it with the check's `documented` signature by the rules of that file, and returns only this JSON, with no prose and no markdown fences:

```json
{"file": "src/utils.ts", "signature_mismatches": [{"name": "formatDate", "line": 42, "source_sig": "(date: Date, format?: string) => string", "documented_sig": "(date: Date) => string", "issue": "missing optional parameter 'format'", "difference": "omitted-optional"}]}
```

Tag a mismatch's `difference` as `{signatureRulesFile}` says: `score` (§2b) checks the facts. One tagged `annotation-contradicted` also gives `evidence_line`, the body line that returns the documented type.

`plan` gives a check `candidates` when the surface records its name in several files and the skill's citations do not settle one.

A check with `candidates` reads each and reports a mismatch only when the documented signature matches none: one, at the closest candidate, its `file` and `line` on the mismatch object (the result's `file` stays its `files[]` entry) and its `difference` tagged against it.

A check with `alternatives` (the other forms the skill documents for the name) is compared with each of them too, as `{signatureRulesFile}` says, each mismatch naming its form as `form`.

A check's `bound` lists each form (its `form` index) whose own citations name one declaration of the name: one of its surface records, or of its `surface.json` `otherDeclarations` (a same-named declaration no entry point exports, such as one a lazy re-export passes on). Its own citations are the `[AST:]` and `[SRC:]` citations at the inventory's `at`: on that line; on the next non-blank line, unless that line writes the name (another place of it, such as the next table row) or, in a fenced block, is a comment (it heads the next declaration); in a fenced block, on the comment lines just above it; and, when the block holds no other place the inventory gives the name, on the block's first non-blank line when a comment and on the first non-blank line after the block, unless that line writes the name. A citation names a declaration when it cites the declaration's file at its line or in an `L` range that holds that line; one with no line names every declaration in its file. Compare a bound form with its bound declaration alone, read in full at its `file` and `line` as above, whatever the check's `candidates`, and report its mismatch there, `file` and `line` on the mismatch object.

Save each response to `{run_dir}/signatures-<n>.txt` with the Write tool. Without subagents, load `{signatureRulesFile}`, compare in the main thread by its rules and save the same JSON.

**Deep Tier (ast-grep + gh + QMD):** the Forge tier checks, and no coverage check of its own: init.md §5b's drift guard checks the local tree against the pinned commit, at any tier, when both exist; the recipe runner traces each re-export to the file that defines it when it runs (the fallback per-file scan does not); and the Forge tier's signature check compares each documented signature with its declaration. A documentation error you see that no script records (an import path whose module does not export the name, a type member that differs from its declaration) goes in coverage-check §5b's hand-written records as an Info `observation` titled `Not checked by script: {name}`, with `export` `{name}`, its Source at the documenting line and the remediation "Correct the documentation to match the source; no script checks this."

**States 2 to 4 (no local source):** the surface is what the skill recorded, so there is no signature to score: load `{coverageBranchesFile}` and follow its **States 2 to 4** section.

### 2b. Resolve the Denominator and Guard Zero Exports

Load the metadata and provenance-map counts once, for §2c, §4b and the numerator check below (pass `--provenance` when init.md §2 bound `{forge_provenance_map}`):

```bash
uv run {coverageInputsScript} metadata --metadata "{resolved_skill_package}/metadata.json" [--provenance "{forge_provenance_map}"] --output "{run_dir}/coverage-inputs.json"
```

**Pick the denominator.** `surface.json` `denominator` holds the Source API Surface Definition clause (§0b) `surface` picked: its §2c `branch` (`barrel`, `scalar` or `stack`), `surfaceSet` (the set the barrel branch counts, as the scalar one does when `setCounted` is true, and the signature score reads) and `ladderStep`. When `absentSet` names a set the surface lacks (the scope sets need the brief's globs and names that carry their files, `subpaths` and `root` an extraction), `surfaceSet` is `all` and the `Denominator:` line (§4) adds `({absentSet} set absent: all set used)`. When `rebuild` is `provenance-fold`, load `{coverageBranchesFile}` and rerun State 2's command from its **States 2 to 4** section without `--metadata` and with `--fold` and `--pattern-reference-intent`, running nothing else from that section, and read the `denominator` it writes.

- **A stack skill** (`branch` `stack`): `coverage-inputs.json` `stack.denominator`. Its own barrel is empty by design, and its `[from skill: …]` citations never make it docs-only. **If `stack.denominator` is 0**: HALT (`halt_reason: "indeterminate-surface"`, phase `coverage-check:denominator`) with `Error: stack composition surface empty: {skill_name} cites no contracts, libraries, or integration pairs, so Export Coverage is undefined. Verify the stack was compiled from at least one constituent skill.` Do not write the Coverage Analysis section; this is an indeterminate state, not a FAIL.
- **A docs-only skill**: the `docsOnly` branch, over the inventory.

**Numerator ground truth.** A declared count equal to the denominator (`stats.exports_documented == stats.effective_denominator`, the inflation signature) may be padded to a tautological 100%. Run the check on every source-based skill; without the signature (a stack and a reference app carry none) it reports `skipped`:

```bash
uv run {numeratorVerifyScript} --inputs "{run_dir}/coverage-inputs.json" --skill-dir "{resolved_skill_package}" --output "{run_dir}/numerator.json"
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

**Score the signatures** (Forge, Forge+ and Deep tier at State 1, once §2 compared them). Give `{scoreSignaturesScript}` `denominator.surfaceSet` as `--surface-set`. Type Coverage then counts that set's types alone, so a type the clause leaves out (a stratified skill's deferred Tier B) lowers neither Export Coverage nor Type Coverage. Give it one `--results` per saved response (the fallback scan's `per-file-<n>.txt`, else the `signatures-<n>.txt`), and `--source-root` whenever the source is local (State 1, Forge tier or above), under a drift override too, since the judges read that tree:

```bash
uv run {scoreSignaturesScript} score --inventory "{run_dir}/inventory.json" --surface "{run_dir}/surface.json" --surface-set <set> --plan "{run_dir}/signature-plan.json" [--source-root "{source_path}"] --results "{run_dir}/signatures-<n>.txt" --output "{run_dir}/signatures.json" --gaps-output "{run_dir}/signature-gaps.json"
```

It grades each mismatch of a compared name from facts it checks, never a `difference` alone, into `signature-gaps.json`: a Low `signature-mismatch` gap for a `parameter-name` difference in a file the plan offered when it is TS/JS, Go, Rust, Java, C or C++, an Info `observation` titled `Partial signature: {name}` for an `omitted-optional` one on a `partial` form, an Info `observation` titled `Annotation contradicted: {name}` (no change to the skill: report the annotation upstream) for an `annotation-contradicted` one whose facts check (a documented return type, the same parameters on both sides, and an `evidence_line` between the declaration and the next one, whose line returns in the `--source-root` file), a Critical `signature-mismatch` gap otherwise (Python included). A signature gap is titled `Signature mismatch: {name}`, with `export` `{name}`, its Source at `{file}:{line}` and both signatures in its Issue (for a name documented in several forms, each gap's title ends `(form {n} of {m})` and its Issue names that form); §5b appends that file to the ledger. A Low or Info one counts as matching, and §5 renders it so. A bound form's mismatch is recorded at its bound declaration, a judge that names another file listed in `warnings`; a bound declaration joins no name, set or count. §5's render lists its `warnings` (a mismatch for a name never compared, a category with nothing to compare).

### 2c. Reconcile Documented vs Source Surface (Deterministic Intersection)

`{reconcileScript}` reconciles the §1 inventory with the source surface and writes `{run_dir}/coverage.json`, whose `exportCoverage` is the Export Coverage step 5 hands to the scoring script. Run the branch §2b picked:

1. **Barrel**, with the name set §2b picked as `--surface-set`:

   ```bash
   uv run {reconcileScript} --denominator-source barrel --inventory "{run_dir}/inventory.json" --surface "{run_dir}/surface.json" --surface-set <set> --output "{run_dir}/coverage.json"
   ```

2. **Scalar or stack**: load `{coverageBranchesFile}` and follow its **Scalar and Stack Branches** section, which runs the branch's command.

3. **Docs-only**: Export Coverage is the documentation completeness ratio, complete over documented items, and `incomplete[]` lists each incomplete item with the fields it lacks:

   ```bash
   uv run {reconcileScript} --denominator-source docsOnly --inventory "{run_dir}/inventory.json" --output "{run_dir}/coverage.json"
   ```

Exit 2 printed an `INVALID_INPUT` envelope: correct the input it names and run it again. Exit 1: HALT with its stderr (`halt_reason: "helper-failed"`, phase `coverage-check:reconcile`).

**Classify what the script found.** §5b records each of these gaps from the run files:

- **Missing names** (`missing`, barrel or scalar): Medium `missing-export` gaps (Medium `missing-type` for a name `signatures.json` lists in `missingTypes`), each at the file `surface.json` records for it, so update-skill can re-extract the export from it; when `guards.inflation.fires` on a stratified-scope or multi-entry `scope.include` set, one Medium `denominator-inflation` gap beside the guard's at the brief lists them instead. A missing export does not block: it lowers Export Coverage.
- **Stale names** (`stale` when `staleApplicable` is true): each is a documented name the enumerated source surface lacks. Where ast-grep read the source at the pinned commit (Forge, Forge+ or Deep tier, `analysis_confidence` `full`, `workspaceDrift` not `overridden` in the `{outputFile}` frontmatter) and init.md §2 bound `{forge_provenance_map}`, check the lines the skill cites for them: resolve `{verifyProvenanceCompletenessHelper}` ← first existing path in `{verifyProvenanceCompletenessProbeOrder}` and run once:

  ```bash
  uv run {verifyProvenanceCompletenessHelper} classify-stale --names "{run_dir}/coverage.json" --provenance "{forge_provenance_map}" --source-root "{source_path}" --inventory "{run_dir}/inventory.json" -o "{run_dir}/stale.json"
  ```

  A name it marks `fabricated: true` (every map entry of the name cites a missing file or one that does not define it) is a Critical `fabricated-signature` gap at its `source`. A name with a `defined_at` (the source still declares it there, an import never counting, a module so named counting unless the name's inventory kind rules it out), or whose `declared_in` lists several files of which the skill's `[AST:]`/`[SRC:]` citations on lines naming it cite exactly one, is a documented extra: an Info `observation` gap at that declaration, when `surface.json` has an `extraction` and its `excluded.outsideScope` does not list the name (a brief scoped its file out). Any other stale name (no `defined_at` and no single cited declaring file, one scoped out, no `extraction`, a dotted name, the conditions above not met, a helper that does not resolve or exits non-zero) is a Medium `stale-documentation` gap; one the brief's globs scope out says which.

### 4. The Denominator Record

Record the denominator source in the Coverage Analysis section with the annotation `{sourceAccessProtocol}` gives `denominator.clause` (§4b gives a stack's and a reference app's): `Denominator: {barrel | empty barrel (…) | stratified (…) | multi-entry (…) | specific-modules (…) | pattern-reference (…) | stack composition (…) | pattern-surface (…) | docs-only completeness}`, and the `canonical.summary` line when `surface.json` has a fold. When `denominator.clause` is `stratified-scope` or `multi-entry`, load `{coverageBranchesFile}` and append the block of its **Denominator Candidates** section after the `Denominator:` line, with every count from `surface.json` `candidates` (`absent` for a null one).

The guards raise coverage gaps too, which §5b records from `surface.json`: `guards.deflation.fires` is a Medium `metadata-drift` gap (on its `tier_a_include` basis, a stale stored count to recount), `guards.inflation.fires` a Medium `denominator-inflation` gap (with deflation, both name one fix: the brief's tier A list) and `guards.staleScope.fires` a Medium `brief-scope-stale` gap at the brief.

### 4b. Metadata Export-Count Coherence Cross-Check

Load `{coverageBranchesFile}` and follow its **Metadata Count Cross-Check** section.

**The numerator ground truth §2b ran.** `numerator.json` `inflated: true` (`verified < declared`) is a High `numerator-inflation` gap listing its `absent[]` names, which §5b records; on a scalar branch that counts no set those names also replace the missing-count gap in the Scalar and Stack Branches section of coverage-check-branches.md. `inflated: false` or `skipped: true` is no finding.

### 4c. Provenance Line Check

Check that the provenance map records each export at the line that defines it (the `def` or declaration line, not a decorator or blank line above it), so update-skill can move a wrong line. Run this section only when `analysis_confidence` is `full`, `{forge_version}/provenance-map.json` exists, and the `{outputFile}` frontmatter's `workspaceDrift` is not `overridden` (init.md §5b: the drifted tree is not the pinned commit). Otherwise skip to section 5.

Resolve `{verifyProvenanceCompletenessHelper}` ← first existing path in `{verifyProvenanceCompletenessProbeOrder}`. If neither path exists, skip to section 5: the check is advisory. Otherwise run:

```bash
uv run {verifyProvenanceCompletenessHelper} verify \
    --metadata {resolved_skill_package}/metadata.json \
    --provenance {forge_version}/provenance-map.json \
    --source-root {source_path} \
    -o "{run_dir}/provenance-verify.json"
```

Rely on the file, not the exit code (exit 1 means findings); on exit 2 the helper writes no file: skip to section 5. §5b records each `stale[]` item by its `reason`: `line-not-definition` is a Low `provenance-line` gap when its `definition_lines` holds a line, else an Info `provenance-unverified` gap (the rules may not cover its shape: the export is unverified, not gone); `file-missing` (the pinned source lacks the file) and `line-out-of-bounds` (the line is past its end, or below 1) are Low `provenance-line` gaps; `line-invalid` (not a line number) is an Info `provenance-unverified` gap. A bookkeeping variant (`X_def`, `X_exact`, `a11y_X`) the cited file never names is checked against `X`. Its Source is exactly the `file:line` the map records (the file alone for `line-invalid`), the citation update-skill's rule R5 reads. A name §2c's `fabricated-signature` gap covers takes no such gap.

This section reports none of the helper's `missing`, `orphaned` or `citations` findings, and no gap it records blocks the gate.

### 5. Write the Coverage Analysis Section

Write the **Coverage Analysis** section in place of the template's `## Coverage Analysis` heading and the placeholder comment under it, in `{outputFile}`. `{reconcileScript}` renders its counts, per-export table and category scores from the run files (leave out `--surface` on a docs-only run and `--signatures` when §2b scored none):

```bash
uv run {reconcileScript} render --coverage "{run_dir}/coverage.json" [--surface "{run_dir}/surface.json"] [--signatures "{run_dir}/signatures.json"]
```

Exit 0: write its output unchanged where the section below places it. Exit 2 is a usage error: correct the command and run it again. Exit 1 printed its error on stderr: HALT with it (`halt_reason: "helper-failed"`, phase `coverage-check:render`).

```markdown
## Coverage Analysis

**Tier:** {forge_tier}
**Source Access:** {analysis_confidence} (full | provenance-map | metadata-only | remote-only | docs-only)
**Source Path:** {source_path}
**Workspace Layout:** {source_workspace_kind | single package | unknown (no local source, or the §0b helper failed)}
**Denominator:** {the §4 annotation}
{the Denominator Candidates block, when §4 adds one}

{the render output}

{the notes §2 to §4b add to this section}
```

### 5b. Record the Coverage Gaps

Record every gap this step found in the gap ledger `{ledgerFile}`: the hard gate (step 4c) decides from it, and the report step renders the Gap Report from it. `{gapLedgerScript}` writes the record of each gap a script found from that script's file: §2b's signature mismatches, §2c's missing names, missing count and stale names, §4's guard gaps, §4b's count findings and numerator gap, and §4c's provenance line gaps, each with the severity and category of its row in the Gap Severity table of `{scoringRulesFile}` and a fixed title, Source, `export` and Remediation. Run each command whose `--input` file this run wrote, leaving out a bracketed flag whose file does not exist: a run file this run did not write, or `--provenance` when init.md §2 bound no `{forge_provenance_map}`:

```bash
uv run {gapLedgerScript} append --ledger "{ledgerFile}" --stage coverage-check --input "{run_dir}/signature-gaps.json"
uv run {gapLedgerScript} append --ledger "{ledgerFile}" --stage coverage-check --from coverage --input "{run_dir}/coverage.json" [--surface "{run_dir}/surface.json"] [--signatures "{run_dir}/signatures.json"] [--numerator "{run_dir}/numerator.json"] [--stale "{run_dir}/stale.json"] [--provenance "{forge_provenance_map}"] --skill-dir "{resolved_skill_package}" --metadata "{resolved_skill_package}/metadata.json"
uv run {gapLedgerScript} append --ledger "{ledgerFile}" --stage coverage-check --from guards --input "{run_dir}/surface.json" --metadata "{resolved_skill_package}/metadata.json"
uv run {gapLedgerScript} append --ledger "{ledgerFile}" --stage coverage-check --from numerator --input "{run_dir}/numerator.json" --metadata "{resolved_skill_package}/metadata.json"
uv run {gapLedgerScript} append --ledger "{ledgerFile}" --stage coverage-check --from metadata-coherence --input "{run_dir}/metadata-coherence.json" --metadata "{resolved_skill_package}/metadata.json"
uv run {gapLedgerScript} append --ledger "{ledgerFile}" --stage coverage-check --from provenance-line --input "{run_dir}/provenance-verify.json"
```

**A split-body mismatch's Source** is a line inside the skill package: when §1b found one, load `{coverageBranchesFile}` and follow its **Split-Body Sources** section.

Then write the records no script wrote, §1b's split-body mismatches, in the Ledger Record Format of `{outputFormatsFile}` (at the Deep tier, §2's `Not checked by script: {name}` observations too), each naming its export in `export` and in its title: the ledger tells two gaps apart by their title, Source and `export`, and update-skill takes the export's name from `export`. Write them as one JSON array on the lines between the two markers, exactly as they are: the quoted marker hands them to the script unchanged, quotes, apostrophes and `$` included. Run the command even when the array is empty (`[]`): the hard gate refuses to decide until every stage before it has recorded, with gaps or without.

```bash
uv run {gapLedgerScript} append --ledger "{ledgerFile}" --stage coverage-check <<'SKF_GAPS'
<the records, one JSON array>
SKF_GAPS
```

Rely on the JSON of each command:

- Exit 0: the records are in the ledger. `appended` names the id each new record received, and `duplicates` the ones a rerun of this step had already recorded.
- Exit 2 (`INVALID_RECORD` or `INVALID_INPUT`): nothing was written. Correct each record `errors[]` names (its `index` counts from 0), or the file or flag the `error` names, and run the command again.
- Exit 1: HALT with the script's `error` (`halt_reason: "helper-failed"`, phase `coverage-check:ledger`).

### 6. Report Coverage Results

Report to the user from §5's render: the {forge_tier} tier, the **Files Analyzed** count, the three category scores and the issue count; the Coverage Analysis section has the details.

Append `'coverage-check'` to `stepsCompleted` in the `{outputFile}` frontmatter, then load and execute {nextStepFile}.
