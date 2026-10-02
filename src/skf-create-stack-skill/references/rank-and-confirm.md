---
nextStepFile: 'parallel-extract.md'
countImportsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-count-imports.py'
  - '{project-root}/src/shared/scripts/skf-count-imports.py'
emitEnvelopeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py'
  - '{project-root}/src/shared/scripts/skf-emit-result-envelope.py'
importCountsFile: '{run_dir}/import-counts.json'
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

**Warnings.** Each `workflow_warnings[]` entry this step appends is recorded at once: write its `[{step}/{severity}] {code}: {message}` line to `{run_dir}/warning.txt` with a file write, then run `uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning "$(cat "{run_dir}/warning.txt")"`.

### 1. Count Import Frequency

**If `compose_mode` is true:**

Skip import counting entirely. All skills are included by default: the recommended scope is every `raw_dependencies` entry (the list step 2 stored).

**Apply scope_overrides:** If `scope_overrides` were provided in step 01, apply them now — force-include or force-exclude skills as specified. Log any overrides applied.

**Validate override keys (S4):** Every key in `scope_overrides` MUST be present in `raw_dependencies`. For any unknown key, append a `workflow_warnings[]` entry (`step: "step-03"`, `severity: "warn"`, `code: "scope-override-unknown"`, `message`: "scope_override: unknown dependency '{key}', skipped") and drop that override entry (do not fail the run). Known-key overrides still apply.

Present skills sorted by architectural layer (from architecture doc if available):
- If `architecture_doc_path` is not null: **wrap the architecture-doc parse in try/except (S5)**. On any parse error (file unreadable, malformed markdown, no H2 structure), fall back to alphabetical ordering and log a warning `"architecture-doc parse failed: {error} — falling back to alphabetical"`. Otherwise parse section headers to determine layer grouping.
- If `architecture_doc_path` is null or layers not detectable: present alphabetically.

Display skills as a table:

| # | Skill | Language | Tier | Architecture Layer |
|---|-------|----------|------|--------------------|
| 1 | {name} | {language} | {confidence_tier} | {layer or 'Unclassified'} |

Set `confirmed_dependencies` ← that scope, with the overrides applied, and skip to [Confirm the Scope](#3-confirm-the-scope).

**If not compose_mode:**

Count, for each dependency, the files under `{scan_root}` that import it, with the shared helper that holds the counting rules (its `--help` states them). **Resolve `{countImportsHelper}`** from `{countImportsProbeOrder}`; first existing path wins. If no candidate exists, HALT (exit 3, `halt_reason: "helper-missing"`, phase `rank-and-confirm:count`) with "**Cannot proceed.** `skf-count-imports.py` is missing, so no import can be counted. Re-install SKF, then re-run."

```bash
uv run {countImportsHelper} count {scan_root} --deps - --relative-to {project_root} > "{importCountsFile}"
```

Pipe `raw_dependencies` on stdin: step 2's scan JSON as it stands, or, when step 2 took `explicit_deps`, those names as a JSON array (if stdin piping is unavailable, write it to `{run_dir}/dependencies.json` and pass that path to `--deps`). `{project_root}` is `project_root` from step 1: the helper scans only `{scan_root}` and writes each path relative to the project root, the base every path this run records shares. Its JSON goes to `{importCountsFile}`, the run's import counts, which this step ranks from: step 4 reads each library's files from it, and step 5 §1 passes it to the pair helper as it stands. Each `dependencies[]` entry gives `file_count`, `files[]` (`path`, and `line`, the first line that imports it) and `above_threshold` (2 or more files); a dependency only the dev sections list carries `scope: "dev"`.

**Unresolved names.** `unresolved[]` lists, each with its `reason`, the dependencies the helper cannot count with confidence: a guessed import name that matched no file, no import name, or an ecosystem with no import rules; the helper never counts them as 0. For a runtime entry whose import name you know (`python-dateutil` is imported as `dateutil`), run the call again with that name and without the `>` redirect, which would replace the file, piping `[{"name": "<name>", "ecosystem": "<its ecosystem>", "modules": ["<import name>"]}]`, add the `dependencies[]` entry it returns to `{importCountsFile}`, drop the entry from `unresolved[]`, keep `dependencies[]` sorted by `file_count` (highest first), then name, and write the file back, so the library ranks and pairs like the others. Every other unresolved entry goes below the threshold with its `reason`.

### 2. Rank and Filter

`dependencies[]` comes ranked: by `file_count`, highest first, then by name.

Apply filtering:
- **Include by default:** the runtime libraries with `above_threshold` true
- **Below threshold:** every other library: under 2 files, a dev-only dependency, or an unresolved one
- **Apply scope_overrides** from step 01 if provided (force include/exclude)

Set `confirmed_dependencies` ← the recommended scope: the libraries included by default, with the overrides applied. The gate below keeps it, or the user's edits change it.

### 3. Confirm the Scope

Present the scope and the one gate. **In code mode:**

"**Dependency ranking complete.** Here are your project's libraries ranked by usage:

| # | Library | Files | Category |
|---|---------|-------|----------|
| 1 | {name} | {file_count} | runtime |
| 2 | {name} | {file_count} | runtime |
| ... | ... | ... | ... |

**Below threshold** (excluded by default):
| Library | Files | Category |
|---------|-------|----------|
| {name} | {file_count, or the unresolved `reason`} | {runtime, or dev for a `scope: "dev"` dependency} |

**Total:** {total} dependencies detected, {above_threshold} recommended for inclusion"

**In compose mode** the skills table of §1 is the scope.

Display: **Select:** [C] Continue to extraction with this scope | [X] Cancel and exit, or type library names to **add** from the below-threshold list, **-library_name** to **exclude** one, or a custom list to replace the scope.

#### EXECUTION RULES:

- This is a confirmation gate: advancing without the user's `C` would extract and ship a stack scope they never approved. Halt and wait for input after presenting the scope.
- **GATE [default: C]**: If `{headless_mode}`: auto-proceed with [C] Continue, keeping `confirmed_dependencies` as §2 set it (the recommended libraries in code mode, every skill in compose mode), and record the auto-decision, which names each library the default left out: stage `{"gate": "rank-and-confirm.scope", "default_action": "C", "taken_action": "C", "reason": "headless: kept the recommended scope", "evidence": {"scope": ["<confirmed library>", ...], "dropped": [{"library": "<name>", "reason": "<under 2 files, dev only, its unresolved reason, or excluded by scope_overrides>"}, ...]}}` as `{run_dir}/decision.json` and run:

  ```bash
  uv run {emitEnvelopeHelper} record --workflow skf-create-stack-skill --run-dir "{run_dir}" --decision < "{run_dir}/decision.json"
  ```

- Proceed to the next step only once the user approves the scope by selecting `C`.

#### Menu Handling Logic:

- IF C: Display "**Scope confirmed:** {count} libraries selected for stack skill extraction." with the list, then load, read entire file, then execute {nextStepFile}
- IF X: HALT (exit 6, `halt_reason: "user-cancelled"`, phase `rank-and-confirm:scope`): leave any existing committed stack package untouched, emit the envelope, then delete the run folder (`rm -rf "{run_dir}"`)
- IF Any other: Process it as a scope change (add or remove libraries from `confirmed_dependencies`, or replace them with a custom list), redisplay the updated table, then [Redisplay the gate](#3-confirm-the-scope)
