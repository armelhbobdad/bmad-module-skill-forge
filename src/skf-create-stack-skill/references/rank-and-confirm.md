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
---

<!-- Config: communicate in {communication_language}. -->

# Step 3: Rank and Confirm Scope

## STEP GOAL:

Count the files under `{scan_root}` that import each dependency, rank by usage, and confirm at one gate which libraries the stack skill includes.

## Rules

- Focus on counting imports, ranking, and getting user confirmation — do not extract documentation (Step 04)
- Take every count from `skf-count-imports.py`; never count imports by hand

## MANDATORY SEQUENCE

**Halt envelope.** Every HALT in this step names its exit code, `halt_reason` and phase. Stage `{run_dir}/halt.json` as `{"phase": "<phase>", "halt_reason": "<halt_reason>", "reason": "<the halt message, one line>", "skill_name": "{stack_name}", "mode": "<code|compose>"}`, then run:

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-create-stack-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
```

Display the line it prints, then stop with the halt's exit code (`references/invocation-contract.md` lists every halt). If `{emitEnvelopeHelper}` is not bound, resolve it from `{emitEnvelopeProbeOrder}`; if no path exists, or the emitter exits non-zero or prints no line, display the halt message alone.

### 1. Count Import Frequency

**If `compose_mode` is true:** `references/compose-scope.md` set `confirmed_dependencies` and showed the skills table. Skip to [Confirm the Scope](#3-confirm-the-scope).

Count, for each dependency, the files under `{scan_root}` that import it, with the shared helper that holds the counting rules (its `--help` states them). **Resolve `{countImportsHelper}`** from `{countImportsProbeOrder}`; first existing path wins. If no candidate exists, HALT (exit 3, `halt_reason: "helper-missing"`, phase `rank-and-confirm:count`) with "**Cannot proceed.** `skf-count-imports.py` is missing, so no import can be counted. Re-install SKF, then re-run."

```bash
uv run {countImportsHelper} count {scan_root} --deps - --relative-to {project_root} > "{importCountsFile}"
```

Pipe `raw_dependencies` on stdin: step 2's scan JSON as it stands, or, when step 2 took `explicit_deps`, those names as a JSON array (if stdin piping is unavailable, write it to `{run_dir}/dependencies.json` and pass that path to `--deps`). `{project_root}` is `project_root` from step 1: the helper scans only `{scan_root}` and writes each path relative to the project root, the base every path this run records shares. Its JSON goes to `{importCountsFile}`, the run's import counts, which this step ranks from: step 4 reads each library's files from it, and step 5 §1 passes it to the pair helper as it stands. Each `dependencies[]` entry gives `file_count`, `files[]` (`path`, and `line`, the first line that imports it) and `above_threshold` (2 or more files); a dependency only the dev sections list carries `scope: "dev"`.

**Unresolved names.** `unresolved[]` lists, each with its `reason`, the dependencies the helper cannot count with confidence: a guessed import name that matched no file, no import name, or an ecosystem with no import rules; the helper never counts them as 0. For a runtime entry whose import name you know (`python-dateutil` is imported as `dateutil`), run the call again with that name and without the `>` redirect, which would replace the file, piping `[{"name": "<name>", "ecosystem": "<its ecosystem>", "modules": ["<import name>"]}]`, add the `dependencies[]` entry it returns to `{importCountsFile}`, drop the entry from `unresolved[]`, keep `dependencies[]` sorted by `file_count` (highest first), then name, and write the file back, so the library ranks and pairs like the others. Every other unresolved entry goes below the threshold with its `reason`.

### 2. Rank and Filter

`dependencies[]` comes ranked: by `file_count`, highest first, then by name.

Apply filtering:
- **Include by default:** the runtime libraries with `above_threshold` true and, on a rerun (`{prior_libraries}` set; read it from `{runFile}` if lost), every `{prior_libraries}` entry whose `dependencies[]` entry has `file_count` 1 or more, a dev-only one too: the published stack keeps each library the counts still find
- **Below threshold:** every other library: under 2 files, a dev-only dependency, or an unresolved one
- **Apply scope_overrides** from step 01 if provided (force include/exclude)

Set `confirmed_dependencies` ← the recommended scope: the libraries included by default, with the overrides applied. The gate below keeps it, or the user's edits change it.

### 3. Confirm the Scope

**Empty scope.** Check `confirmed_dependencies` before presenting the gate and after each scope change. While it is empty the gate offers no [C]: an interactive run says "**No library is in scope.**", shows each library left out with its reason (the below-threshold table, then each library `scope_overrides` or the user excluded; compose mode: the skills `scope_overrides` or the user excluded) and takes only names to add, a custom list or [X]; a headless run records no scope decision and HALTs (exit 2, `halt_reason: "empty-scope"`, phase `rank-and-confirm:scope`) with "**Cannot proceed.** No library is in scope: {each library left out, with its reason}. Pass `scope_overrides` with `<name>: include` for each library the stack should cover, then re-run."

**A rerun.** When `{prior_libraries}` is set (from `{runFile}` if lost), the scope is marked against the published stack: the table's Published column says `kept` for a library of `{prior_libraries}` and `new` for any other, and after the Total line the gate lists each `{prior_libraries}` entry `confirmed_dependencies` leaves out, with its reason: `no importing file` for one the counts hold at 0 files, `removed at the scope gate` for one the user took out, `not among this run's dependencies` for one the counts no longer hold, else its below-threshold reason or `excluded by scope_overrides`; the line reads `none` when it leaves none out. Each scope change recomputes the marks and the Dropped line. A new stack shows no Published column and no Dropped line.

Present the scope and the one gate, with the Published column and the Dropped line only on a rerun. **In code mode:**

"**Dependency ranking complete.** Here are your project's libraries ranked by usage:

| # | Library | Files | Category | Published |
|---|---------|-------|----------|-----------|
| 1 | {name} | {file_count} | {runtime, or dev for a `scope: "dev"` dependency} | {kept or new} |
| 2 | {name} | {file_count} | {runtime, or dev for a `scope: "dev"` dependency} | {kept or new} |
| ... | ... | ... | ... | ... |

**Below threshold** (excluded by default):
| Library | Files | Category |
|---------|-------|----------|
| {name} | {file_count, or the unresolved `reason`} | {runtime, or dev for a `scope: "dev"` dependency} |

**Total:** {total} dependencies detected, {count of confirmed_dependencies} recommended for inclusion

**Dropped from v{prior_stack_version}:** {name} ({its reason}), ..."

**In compose mode** the skills table `references/compose-scope.md` showed is the scope, with its Published column on a rerun, followed by the same Dropped line (`not among this run's dependencies` for a published skill step 2 no longer picked).

Display: **Select:** [C] Continue to extraction with this scope (not offered while the scope is empty) | [X] Cancel and exit, or type library names to **add** from the below-threshold list, **-library_name** to **exclude** one, or a custom list to replace the scope.

#### EXECUTION RULES:

- This is a confirmation gate: advancing without the user's `C` would extract and ship a stack scope they never approved. Halt and wait for input after presenting the scope.
- **GATE [default: C]**: If `{headless_mode}` (an empty scope has halted above): auto-proceed with [C] Continue, keeping `confirmed_dependencies` as §2 set it (the recommended libraries in code mode, every skill in compose mode), and record the auto-decision, which names each library the default left out (a published library's `reason` reads `in v{prior_stack_version}: ` and then its reason, and `prior_kept` lists the libraries §2 kept only because the published stack holds them: `[]` on a new stack and in compose mode): stage `{"gate": "rank-and-confirm.scope", "default_action": "C", "taken_action": "C", "reason": "headless: kept the recommended scope", "evidence": {"scope": ["<confirmed library>", ...], "dropped": [{"library": "<name>", "reason": "<under 2 files, no importing file, dev only, its unresolved reason, excluded by scope_overrides, or not among this run's dependencies, led by in v{prior_stack_version}: for a published library>"}, ...], "prior_kept": ["<published library kept below the threshold>", ...]}}` as `{run_dir}/decision.json` and run:

  ```bash
  uv run {emitEnvelopeHelper} record --workflow skf-create-stack-skill --run-dir "{run_dir}" --decision < "{run_dir}/decision.json"
  ```

- Proceed to the next step only once the user approves the scope by selecting `C`.

#### Menu Handling Logic:

- IF C: While `confirmed_dependencies` is empty, refuse it with "**No library is in scope.** Add a library, give a custom list or type X." and show the gate again. Otherwise display "**Scope confirmed:** {count} libraries selected for stack skill extraction." with the list, then load, read entire file, then execute `{composeNextStepFile}` when `compose_mode` is true, else {nextStepFile}
- IF X: HALT (exit 6, `halt_reason: "user-cancelled"`, phase `rank-and-confirm:scope`): leave any existing committed stack package untouched, emit the envelope, then delete the run folder (`rm -rf "{run_dir}"`)
- IF Any other: Process it as a scope change (add or remove libraries from `confirmed_dependencies`, or replace them with a custom list), check the scope again as **Empty scope** says, on a rerun recompute the marks and the Dropped line as **A rerun** says, redisplay the updated table, then [Redisplay the gate](#3-confirm-the-scope)
