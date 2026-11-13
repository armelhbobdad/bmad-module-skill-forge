---
nextStepFile: 'parallel-extract.md'
composeNextStepFile: 'compose-extract.md'
countImportsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-count-imports.py'
  - '{project-root}/src/shared/scripts/skf-count-imports.py'
emitEnvelopeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py'
  - '{project-root}/src/shared/scripts/skf-emit-result-envelope.py'
importCountsFile: '{run_dir}/import-counts.json'
runFile: '{run_dir}/run.json'
scopeFile: '{run_dir}/scope.json'
---

<!-- Config: communicate in {communication_language}. -->

# Step 3: Rank and Confirm Scope

## STEP GOAL:

Count the files under `{scan_root}` that import each dependency, rank by usage, and confirm at one gate which libraries the stack skill includes.

## Rules

- Focus on counting imports, ranking, and getting user confirmation — do not extract documentation (Step 04)
- Take every count and the recommended scope from `skf-count-imports.py`; never count imports or work out the scope by hand

## MANDATORY SEQUENCE

**Halt envelope.** Every HALT in this step names its exit code, `halt_reason` and phase. Stage `{run_dir}/halt.json` as `{"phase": "<phase>", "halt_reason": "<halt_reason>", "reason": "<the halt message, one line>", "skill_name": "{stack_name}", "mode": "<code|compose>"}`, then run:

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-create-stack-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
```

Display the line it prints, then stop with the halt's exit code (`references/invocation-contract.md` lists every halt). If `{emitEnvelopeHelper}` is not bound, resolve it from `{emitEnvelopeProbeOrder}`; if no path exists, or the emitter exits non-zero or prints no line, display the halt message alone.

**Warnings.** Each `workflow_warnings[]` entry this step appends is recorded at once: write its `[{step}/{severity}] {code}: {message}` line to `{run_dir}/warning.txt` with a file write, never an `echo` (a message can quote backticks or `$( )`, which a shell runs), then run `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "$(cat "{run_dir}/warning.txt")"`, resolving `{emitEnvelopeHelper}` from `{emitEnvelopeProbeOrder}` if it is not bound.

### 1. Count Import Frequency

**If `compose_mode` is true:** `references/compose-scope.md` set `confirmed_dependencies` and showed the skills table. Skip to [Confirm the Scope](#3-confirm-the-scope).

Count, for each dependency, the files under `{scan_root}` that import it, with the shared helper that holds the counting rules (its `--help` states them). **Resolve `{countImportsHelper}`** from `{countImportsProbeOrder}`; first existing path wins. If no candidate exists, HALT (exit 3, `halt_reason: "helper-missing"`, phase `rank-and-confirm:count`) with "**Cannot proceed.** `skf-count-imports.py` is missing, so no import can be counted. Re-install SKF, then re-run."

```bash
uv run {countImportsHelper} count {scan_root} --deps - --relative-to {project_root} > "{importCountsFile}"
```

Pipe `raw_dependencies` on stdin: step 2's scan JSON as it stands, or, when step 2 took `explicit_deps`, those names as a JSON array (if stdin piping is unavailable, write it to `{run_dir}/dependencies.json` and pass that path to `--deps`). `{project_root}` is `project_root` from step 1: the helper scans only `{scan_root}` and writes each path relative to the project root, the base every path this run records shares. Its JSON goes to `{importCountsFile}`, the run's import counts, which this step ranks from: step 4 reads each library's files from it, and step 5 §1 passes it to the pair helper as it stands. Each `dependencies[]` entry gives `file_count`, `files[]` (`path`, and `line`, the first line that imports it) and `above_threshold` (2 or more files); a dependency only the dev sections list carries `scope: "dev"`.

**Unresolved names.** `unresolved[]` lists, each with its `reason`, the dependencies the helper cannot count with confidence: a guessed import name that matched no file, no import name, or an ecosystem with no import rules; the helper never counts them as 0. When you know the import name of a runtime entry (a private `acme-client` imported as `acme`), run the command above again, unchanged, redirect included, adding one `--module <name>=<import name>` per such entry (`--module acme-client=acme`): the helper counts and ranks it with the others. A later rerun keeps every `--module` an earlier one passed. The redirect empties `{importCountsFile}` before the helper starts, so on a non-zero exit fix or drop the `--module` its error names and run the command again before §2. §2 leaves every other unresolved entry out with its `reason`.

### 2. Rank and Filter

`dependencies[]` comes ranked: by `file_count`, highest first, then by name.

The same helper works out the recommended scope from those counts, `scope_overrides` and, on a rerun, the published stack, with every rule and reason. Pipe `scope_overrides` from step 1 on stdin as JSON (`null` when none). Pass the bracketed flags only on a rerun (`{prior_libraries}` set; read it and `{prior_stack_version}` from `{runFile}` if lost), with the published libraries comma-separated:

```bash
uv run {countImportsHelper} scope "{importCountsFile}" --overrides - [--prior-version "{prior_stack_version}" --prior-libraries "{prior_libraries}"] > "{scopeFile}"
```

A non-zero exit means the call is malformed: fix it and run it again. `{scopeFile}` holds what §3 shows and records: `scope`, the libraries in, in rank order; `dropped`, each library left out with its `reason` (a published one's led by `in v{prior_stack_version}: `); `prior_kept`, the published libraries kept only because the published stack holds them; and `unknown_overrides`, the `scope_overrides` keys that name no dependency, which the helper skips. Append one `workflow_warnings[]` entry per `unknown_overrides[]` key (`step: "step-03"`, `severity: "warn"`, `code: "scope-override-unknown"`, `message`: "scope_override: unknown dependency '{key}', skipped"); an unknown key never halts the run.

Set `confirmed_dependencies` ← the recommended scope: `{scopeFile}`'s `scope`. The gate below keeps it, or the user's edits change it.

### 3. Confirm the Scope

**Empty scope.** Check `confirmed_dependencies` before presenting the gate and after each scope change. While it is empty the gate offers no [C]: an interactive run says "**No library is in scope.**", shows each library left out with its reason (the Left out table: `{scopeFile}`'s `dropped[]`, then each library the user took out) and takes only names to add, a custom list or [X]; a headless run records no scope decision and HALTs (exit 2, `halt_reason: "empty-scope"`, phase `rank-and-confirm:scope`) with "**Cannot proceed.** No library is in scope: {each library left out, with its reason}. Pass `scope_overrides` with `<name>: include` for each library the stack should cover, then re-run."

**A rerun.** When `{prior_libraries}` is set (from `{runFile}` if lost), the scope is marked against the published stack: the table's Published column says `kept` for a library of `{prior_libraries}` and `new` for any other, and after the Total line the gate lists each `{prior_libraries}` entry `confirmed_dependencies` leaves out, with its reason: each `{scopeFile}` `dropped[]` entry whose `reason` starts `in v{prior_stack_version}: `, with the reason after that lead, and `removed at the scope gate` for one the user took out; the line reads `none` when it leaves none out. Each scope change recomputes the marks and the Dropped line. A new stack shows no Published column and no Dropped line.

Present the scope and the one gate, with the Published column and the Dropped line only on a rerun. The Left out table lists each `{scopeFile}` `dropped[]` entry, its `library` and `reason` as they stand, then each library the user took out, as `removed at the scope gate`; one the user adds leaves it. **In code mode:**

"**Dependency ranking complete.** Here are your project's libraries ranked by usage:

| # | Library | Files | Category | Published |
|---|---------|-------|----------|-----------|
| 1 | {name} | {file_count} | {runtime, or dev for a `scope: "dev"` dependency} | {kept or new} |
| 2 | {name} | {file_count} | {runtime, or dev for a `scope: "dev"` dependency} | {kept or new} |
| ... | ... | ... | ... | ... |

**Left out:**
| Library | Reason |
|---------|--------|
| {library} | {reason} |

**Total:** {total} dependencies detected, {count of confirmed_dependencies} recommended for inclusion

**Dropped from v{prior_stack_version}:** {name} ({its reason}), ..."

**In compose mode** the skills table `references/compose-scope.md` showed is the scope, with its Published column on a rerun, followed by the same Left out table and Dropped line.

Display: **Select:** [C] Continue to extraction with this scope (not offered while the scope is empty) | [X] Cancel and exit, or type library names to **add** from the Left out table, **-library_name** to **exclude** one, or a custom list to replace the scope.

#### EXECUTION RULES:

- This is a confirmation gate: advancing without the user's `C` would extract and ship a stack scope they never approved. Halt and wait for input after presenting the scope.
- **GATE [default: C]**: If `{headless_mode}` (an empty scope has halted above): auto-proceed with [C] Continue, keeping `confirmed_dependencies` as §2 or `references/compose-scope.md` set it from `{scopeFile}` (the recommended libraries in code mode, every skill in compose mode but those `scope_overrides` excludes), and record the auto-decision, whose `evidence` copies `{scopeFile}`'s `scope`, `dropped` and `prior_kept` as they stand, so it names each library the default left out (a published library's `reason` reads `in v{prior_stack_version}: ` and then its reason, and `prior_kept` lists the libraries §2 kept only because the published stack holds them: `[]` on a new stack and in compose mode): stage `{"gate": "rank-and-confirm.scope", "default_action": "C", "taken_action": "C", "reason": "headless: kept the recommended scope", "evidence": {"scope": ["<confirmed library>", ...], "dropped": [{"library": "<name>", "reason": "<under 2 files, no importing file, dev only, its unresolved reason, excluded by scope_overrides, or not among this run's dependencies, led by in v{prior_stack_version}: for a published library>"}, ...], "prior_kept": ["<published library kept below the threshold>", ...]}}` as `{run_dir}/decision.json` and run:

  ```bash
  uv run {emitEnvelopeHelper} record --workflow skf-create-stack-skill --run-dir "{run_dir}" --decision < "{run_dir}/decision.json"
  ```

- Proceed to the next step only once the user approves the scope by selecting `C`.

#### Menu Handling Logic:

- IF C: While `confirmed_dependencies` is empty, refuse it with "**No library is in scope.** Add a library, give a custom list or type X." and show the gate again. Otherwise display "**Scope confirmed:** {count} libraries selected for stack skill extraction." with the list, then load, read entire file, then execute `{composeNextStepFile}` when `compose_mode` is true, else {nextStepFile}
- IF X: HALT (exit 6, `halt_reason: "user-cancelled"`, phase `rank-and-confirm:scope`): leave any existing committed stack package untouched, emit the envelope, then delete the run folder (`rm -rf "{run_dir}"`)
- IF Any other: Process it as a scope change (add or remove libraries from `confirmed_dependencies`, or replace them with a custom list), check the scope again as **Empty scope** says, on a rerun recompute the marks and the Dropped line as **A rerun** says, redisplay the updated tables, then [Redisplay the gate](#3-confirm-the-scope)
