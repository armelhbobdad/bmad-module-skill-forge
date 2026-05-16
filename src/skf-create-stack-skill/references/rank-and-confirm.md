---
nextStepFile: 'parallel-extract.md'
---

<!-- Config: communicate in {communication_language}. -->

# Step 3: Rank and Confirm Scope

## STEP GOAL:

Count import frequency for each dependency across the codebase, rank by usage, and present for user confirmation of which libraries to include in the stack skill.

## Rules

- Focus on counting imports, ranking, and getting user confirmation — do not extract documentation (Step 04)
- Use subprocess Pattern 1 (grep/search) when available

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

For each dependency in `raw_dependencies`:

**Launch a subprocess** that runs grep across all source files in the project to count import statements for each library. Return only the counts, not file contents.

**Subprocess resolution:** Use the Grep tool (Claude Code), built-in search (Cursor), or `grep`/`rg` (CLI). See `knowledge/tool-resolution.md`.

Use ecosystem-appropriate import patterns:
- JavaScript/TypeScript: `import .* from ['"]library`, `require\(['"]library`
- Python: `import library`, `from library import`
- Rust: `use library::`, `extern crate library`
- Go: `"library"` in import blocks
- (Match patterns from manifest-patterns.md)

**Subprocess returns:** `{library_name: import_count, files: [file_paths]}` for each dependency.

**If subprocess unavailable:** Perform grep operations in main thread sequentially.

Exclude from counting:
- Test files (*/test/*, *_test.*, *.spec.*, *.test.*)
- Config files (*.config.*, .eslintrc, etc.)
- Build artifacts (dist/, build/, node_modules/, target/, __pycache__/)

### 2. Rank and Filter

Sort dependencies by import count (descending).

Apply filtering:
- **Include by default:** Libraries with 2+ import files
- **Flag as trivial:** Libraries with 0-1 import files
- **Apply scope_overrides** from step 01 if provided (force include/exclude)

### 3. Present Ranked List

"**Dependency ranking complete.** Here are your project's libraries ranked by usage:

| # | Library | Imports | Files | Category |
|---|---------|---------|-------|----------|
| 1 | {name} | {count} | {file_count} | runtime |
| 2 | {name} | {count} | {file_count} | runtime |
| ... | ... | ... | ... | ... |

**Below threshold** (0-1 imports — excluded by default):
| Library | Imports | Category |
|---------|---------|----------|
| {name} | {count} | {category} |

**Total:** {total} dependencies detected, {above_threshold} recommended for inclusion

---

**Please confirm your scope:**
- Type **C** to accept the recommended scope (all above-threshold libraries)
- Type library names to **add** from the below-threshold list
- Type **-library_name** to **exclude** a recommended library
- Type a custom list to override entirely"

### 4. Process User Response

**If C (accept recommended):**
Store all above-threshold libraries as `confirmed_dependencies`.

**If modifications requested:**
Apply additions/exclusions, display updated list, and ask for final confirmation.

**If custom list provided:**
Use the custom list as `confirmed_dependencies`.

Display final confirmation:

"**Scope confirmed:** {count} libraries selected for stack skill extraction.

{List confirmed libraries}

**Proceeding to parallel extraction...**"

### 5. Present MENU OPTIONS

Display: **Select:** [C] Continue to Extraction | [X] Cancel and exit

#### EXECUTION RULES:

- ALWAYS halt and wait for user input after presenting scope
- **GATE [default: C]** — If `{headless_mode}`: auto-proceed with [C] Continue (accept all ranked libraries), log: "headless: auto-confirm library scope"
- ONLY proceed to next step when user confirms scope and selects 'C'

#### Menu Handling Logic:

- IF C: Store current `confirmed_dependencies` (including any modifications made since initial presentation), then load, read entire file, then execute {nextStepFile}
- IF X: Invoke the rollback contract (purge any `{forge_data_folder}/{project_name}-stack/{version}/*-tmp` and `*.skf-tmp` staging artifacts under the forge workspace, leave any existing committed stack package untouched), emit the `SKF_STACK_RESULT_JSON` envelope on stderr with `status: "error"`, `halt_reason: "user-cancelled"`, `exit_code: 6`, and exit with code 6
- IF Any other: Process as scope modification (add/remove skills from `confirmed_dependencies`), update the in-memory `confirmed_dependencies` list accordingly, redisplay the updated skills table, then [Redisplay Menu Options](#5-present-menu-options)

