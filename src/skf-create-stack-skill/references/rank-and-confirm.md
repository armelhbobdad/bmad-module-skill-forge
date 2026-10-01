---
nextStepFile: 'parallel-extract.md'
countImportsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-count-imports.py'
  - '{project-root}/src/shared/scripts/skf-count-imports.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 3: Rank and Confirm Scope

## STEP GOAL:

Count the files under `{scan_root}` that import each dependency, rank by usage, and present for user confirmation of which libraries to include in the stack skill.

## Rules

- Focus on counting imports, ranking, and getting user confirmation — do not extract documentation (Step 04)
- Take every count from `skf-count-imports.py`; never count imports by hand

## MANDATORY SEQUENCE

### 1. Count Import Frequency

**If `compose_mode` is true:**

Skip import counting entirely. All skills are included by default.

Set `confirmed_dependencies` = all `raw_dependencies` (the list already stored as workflow state from Step 02).

**Apply scope_overrides:** If `scope_overrides` were provided in step 01, apply them now — force-include or force-exclude skills as specified. Log any overrides applied.

**Validate override keys (S4):** Every key in `scope_overrides` MUST be present in `raw_dependencies`. For any unknown key, emit `"scope_override: unknown dependency '{key}' — skipping"` and drop that override entry (do not fail the run). Known-key overrides still apply.

Present skills sorted by architectural layer (from architecture doc if available):
- If `architecture_doc_path` is not null: **wrap the architecture-doc parse in try/except (S5)**. On any parse error (file unreadable, malformed markdown, no H2 structure), fall back to alphabetical ordering and log a warning `"architecture-doc parse failed: {error} — falling back to alphabetical"`. Otherwise parse section headers to determine layer grouping.
- If `architecture_doc_path` is null or layers not detectable: present alphabetically.

Display skills as a table:

| # | Skill | Language | Tier | Architecture Layer |
|---|-------|----------|------|--------------------|
| 1 | {name} | {language} | {confidence_tier} | {layer or 'Unclassified'} |

User confirms inclusion/exclusion at the gate (same [C] menu as code-mode).

Skip to [Present MENU OPTIONS](#5-present-menu-options).

**If not compose_mode:**

Count, for each dependency, the files under `{scan_root}` that import it, with the shared helper that holds the counting rules (its `--help` states them). **Resolve `{countImportsHelper}`** from `{countImportsProbeOrder}`; first existing path wins. If no candidate exists, HALT with "**Cannot proceed.** `skf-count-imports.py` is missing, so no import can be counted. Re-install SKF, then re-run.", then emit the result envelope on stderr per the Result Contract in SKILL.md with `exit_code` 3 and `halt_reason` `resolution-failure`, and STOP.

```bash
uv run {countImportsHelper} count {scan_root} --deps - --relative-to {project_root}
```

Pipe `raw_dependencies` on stdin: step 2's scan JSON as it stands, or, when step 2 took `explicit_deps`, those names as a JSON array (use a temp file under `{forge_data_folder}/` if stdin piping is unavailable). `{project_root}` is `project_root` from step 1: the helper scans only `{scan_root}` and writes each path relative to the project root, the base every path this run records shares. Keep its JSON as `{import_counts}`: step 4 reads each library's files from it, and step 5 §1 pipes it to the pair helper as it stands. Each `dependencies[]` entry gives `file_count`, `files[]` (`path`, and `line`, the first line that imports it) and `above_threshold` (2 or more files); a dependency only the dev sections list carries `scope: "dev"`.

**Unresolved names.** `unresolved[]` lists, each with its `reason`, the dependencies the helper cannot count with confidence: a guessed import name that matched no file, no import name, or an ecosystem with no import rules; the helper never counts them as 0. For a runtime entry whose import name you know (`python-dateutil` is imported as `dateutil`), run the call again with that name, piping `[{"name": "<name>", "ecosystem": "<its ecosystem>", "modules": ["<import name>"]}]`, add the `dependencies[]` entry it returns to `{import_counts}`, drop the entry from `unresolved[]`, and keep `dependencies[]` sorted by `file_count` (highest first), then name, so the library ranks and pairs like the others. Every other unresolved entry goes below the threshold with its `reason`.

### 2. Rank and Filter

`dependencies[]` comes ranked: by `file_count`, highest first, then by name.

Apply filtering:
- **Include by default:** the runtime libraries with `above_threshold` true
- **Below threshold:** every other library: under 2 files, a dev-only dependency, or an unresolved one
- **Apply scope_overrides** from step 01 if provided (force include/exclude)

### 3. Present Ranked List

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

**Total:** {total} dependencies detected, {above_threshold} recommended for inclusion

---

**Please confirm your scope:**
- Type **C** to accept the recommended scope (the runtime libraries above the threshold)
- Type library names to **add** from the below-threshold list
- Type **-library_name** to **exclude** a recommended library
- Type a custom list to override entirely"

### 4. Process User Response

**If C (accept recommended):**
Store the recommended libraries (§2's include-by-default set, with scope_overrides applied) as `confirmed_dependencies`.

**If modifications requested:**
Apply additions/exclusions, display updated list, and ask for final confirmation.

**If custom list provided:**
Use the custom list as `confirmed_dependencies`.

Display the resolved scope:

"**Scope confirmed:** {count} libraries selected for stack skill extraction.

{List confirmed libraries}"

The extraction itself begins only once the user clears the gate below.

### 5. Present MENU OPTIONS

Display: **Select:** [C] Continue to Extraction | [X] Cancel and exit

#### EXECUTION RULES:

- This is a confirmation gate — advancing without the user's `C` would extract and ship a stack scope they never approved. Halt and wait for input after presenting scope.
- **GATE [default: C]**: If `{headless_mode}`: auto-proceed with [C] Continue, keeping the scope §4 stores for C (the recommended libraries in code mode, every skill in compose mode), log: "headless: auto-confirm library scope"
- Proceed to the next step only once the user confirms scope by selecting `C`.

#### Menu Handling Logic:

- IF C: Store current `confirmed_dependencies` (including any modifications made since initial presentation), then load, read entire file, then execute {nextStepFile}
- IF X: Invoke the rollback contract (purge any `{forge_data_folder}/{stack_name}/{version}/*-tmp` and `*.skf-tmp` staging artifacts under the forge workspace, leave any existing committed stack package untouched), emit the `SKF_STACK_RESULT_JSON` envelope on stderr with `status: "error"`, `halt_reason: "user-cancelled"`, `exit_code: 6`, and exit with code 6
- IF Any other: Process as scope modification (add/remove skills from `confirmed_dependencies`), update the in-memory `confirmed_dependencies` list accordingly, redisplay the updated skills table, then [Redisplay Menu Options](#5-present-menu-options)

