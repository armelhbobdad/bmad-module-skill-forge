---
name: 'step-03-auto-index'
description: 'Smart-index user project directories as QMD collections (Deep tier only)'

nextStepFile: './step-04-report.md'

# Directories ALWAYS excluded regardless of git status — module internals and forge artifacts
alwaysExcluded:
  - _bmad
  - forge-data

# Directory name patterns ALWAYS excluded (glob-style matching)
# _*-learn: module learning material directories (e.g., _skf-learn, _xyz-learn)
alwaysExcludedPatterns:
  - '_*-learn'

# Fallback exclusion list for non-git projects only
# Used ONLY when the project is not a git repository
fallbackExcludedDirs:
  - _bmad
  - forge-data
  - node_modules
  - .git
  - dist
  - build
  - coverage
  - __pycache__
  - target
  - .next
  - .nuxt
  - .cache
  - vendor
  - out
  - .turbo
  - venv
  - .venv
  - .output
---

# Step 3: Smart Auto-Index Project

## STEP GOAL:

If the detected tier is Deep, discover **user project directories** and index each as a targeted QMD collection. Uses `git ls-files` as the authoritative source for what belongs to the project (respects all `.gitignore` rules), with a hardcoded fallback for non-git projects.

Directories in `{alwaysExcluded}` and patterns in `{alwaysExcludedPatterns}` are excluded regardless of git status. Empty directories are skipped. Stale collections from prior runs are cleaned up.

For Quick and Forge tiers, skip silently and proceed.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 📖 CRITICAL: Read the complete step file before taking any action
- 🔄 CRITICAL: When loading next step, ensure entire file is read
- 🎯 Execute all operations autonomously — no user interaction

### Role Reinforcement:

- ✅ You are a system executor performing smart conditional indexing
- ✅ Graceful degradation is paramount — never fail the workflow over indexing
- ✅ No negative messaging — do not mention what non-Deep tiers are missing

### Step-Specific Rules:

- 🎯 Focus only on targeted QMD indexing (Deep tier) or graceful skip (other tiers)
- 🚫 FORBIDDEN to display "missing" or "skipped" messages for non-Deep tiers
- 🚫 FORBIDDEN to fail the workflow if QMD indexing encounters errors
- 🚫 FORBIDDEN to index directories matching `{alwaysExcluded}` or `{alwaysExcludedPatterns}`
- 🚫 FORBIDDEN to index the entire project root as a single collection
- 🚫 FORBIDDEN to create collections for empty directories
- 💬 If indexing fails: log the issue, note that index can be retried, continue

## EXECUTION PROTOCOLS:

- 🎯 Follow the MANDATORY SEQUENCE exactly
- 💾 QMD indexing targets only user project directories — never module internals
- 📖 Use {calculated_tier} from step-01 context
- 🚫 FORBIDDEN to attempt indexing for Quick or Forge tiers
- 🚫 FORBIDDEN to use `**/*.md` as the mask — use `**/*` to capture all file types (source code, docs, configs)

## CONTEXT BOUNDARIES:

- Available: {calculated_tier} from step-01, forge-tier.yaml written in step-02
- Available: {project_name} from workflow config
- Focus: conditional QMD indexing only
- Limits: only index if Deep tier AND user content exists
- Dependencies: step-02 must have completed (forge-tier.yaml exists)

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise.

### 1. Check Tier

Read `{calculated_tier}` from context.

**If tier is NOT Deep:** Proceed directly to section 7 (Auto-Proceed) — no output, no messaging.

**If tier IS Deep:** Continue to section 2.

### 2. Discover User Project Directories

Determine which top-level directories contain user project content that should be indexed.

#### 2a. Check if project is a git repository

Run: `git -C {project-root} rev-parse --is-inside-work-tree 2>/dev/null`

**If git repo (exit code 0):** Use the **git-aware strategy** (section 2b).

**If NOT a git repo:** Use the **fallback strategy** (section 2c).

#### 2b. Git-Aware Strategy (preferred)

Use `git ls-files` to discover which top-level directories contain tracked content. This automatically respects ALL `.gitignore` rules (project-level, nested, global, and `.git/info/exclude`).

Run:
```bash
cd {project-root} && git ls-files | cut -d/ -f1 | sort -u
```

This produces a list of top-level entries (files and directories) that git tracks.

**Filter the results:**
- Keep only **directories** (ignore root-level files — the agent can read those directly)
- Remove all directories matching `{alwaysExcluded}` (exact match)
- Remove all directories matching `{alwaysExcludedPatterns}` (glob match — e.g., `_*-learn` matches `_skf-learn`, `_xyz-learn`)

**Store the result as `{user_dirs}`.**

#### 2c. Fallback Strategy (non-git projects)

List top-level directories in the project root:

Run: `ls -d {project-root}/*/ 2>/dev/null`

**Filter the results:**
- Remove all directories listed in `{fallbackExcludedDirs}` (exact match)
- Remove all directories matching `{alwaysExcludedPatterns}` (glob match)
- Remove all dot-directories (any directory starting with `.`)

**Store the result as `{user_dirs}`.**

### 3. Filter Empty Directories

For each directory in `{user_dirs}`, check if it contains any meaningful files (not just git placeholder files):

Run: `find {dir_path} -type f -maxdepth 3 -not -name '.gitkeep' -not -name '.keep' -not -name '.placeholder' | head -1`

- If output is empty (no meaningful files found within 3 levels): **remove from `{user_dirs}`**
- If output has a result: keep in `{user_dirs}`

This prevents creating QMD collections for directories that only contain placeholder files like `.gitkeep`.

### 4. Evaluate Indexability

**If `{user_dirs}` is empty** (no user content directories with files found):

- Store in context: `{qmd_indexed: false, qmd_skip_reason: "no_project_content"}`
- Note for step-04: "No project source directories found to index. QMD collections will be created automatically on next [SF] run after adding project content."
- Proceed directly to section 7 (Auto-Proceed)

**If `{user_dirs}` has entries:** Continue to section 5.

### 5. Clean Up Stale Collections (Re-run Only)

Check for existing QMD collections that belong to this project but no longer map to a valid directory.

Run: `qmd collection list` and identify collections whose name starts with `{project_name}-`.

For each such collection:
- Extract the directory name from the collection name (the part after `{project_name}-`)
- Check if that directory still exists in `{user_dirs}`
- If NOT found in `{user_dirs}`: remove the stale collection with `qmd collection remove {collection_name}`
- If found: it will be updated in section 6

**Error handling:** If collection listing or removal fails, log and continue — stale cleanup is best-effort.

### 6. Index User Directories with QMD (Deep Tier Only)

For **each directory** in `{user_dirs}`, create a QMD collection:

- **Collection name**: `{project_name}-{sanitized_dirname}`
  - Sanitize the dirname: strip any leading underscores or dots (e.g., `_src` → `src`, `.config` → `config`)
  - Examples: `myapp-src`, `myapp-docs`, `myapp-lib`
- **Path**: the full absolute path to the directory
- **Mask**: `**/*` (captures all file types — source code, markdown, configs, etc.)

**Command per directory:**
```bash
qmd collection add {dir_path} --name {project_name}-{sanitized_dirname} --mask "**/*"
```

**Re-run handling:** If QMD reports "already exists" for a collection:
- Do NOT fail — this means it was indexed on a prior run
- Run `qmd update` once at the end to re-index all existing collections with fresh content
- Note the collection as "updated" rather than "created"

**After all collections are processed:**
- Store in context: `{qmd_indexed: true, qmd_collections: [list of names], qmd_total_files: total}`
- Count total files indexed across all collections from QMD output

**Timeout handling:** If indexing takes excessively long on a large project:
- Log that indexing is in progress but may need more time
- Note in context that index may be incomplete
- Do NOT halt or fail the workflow

**Error handling:** If QMD indexing fails for a specific directory:
- Log the specific error for that directory
- Continue with remaining directories — do not abort the loop
- Note which collections succeeded and which failed

If ALL directories fail:
- Store in context: `{qmd_indexed: false, qmd_skip_reason: "all_indexing_failed"}`
- Note that indexing can be retried by re-running [SF]
- The forge-tier.yaml already records `qmd: true` — the tool is available even if indexing failed

### 7. Auto-Proceed

"**Proceeding to forge status report...**"

#### Menu Handling Logic:

- After indexing completes (or is skipped), immediately load, read entire file, then execute {nextStepFile}

#### EXECUTION RULES:

- This is an auto-proceed step with no user choices
- Proceed directly to next step after indexing or skip

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN the tier check has been performed (and indexing completed or skipped accordingly) will you load and read fully `{nextStepFile}` to execute the report step.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Git repo: `git ls-files` used to discover indexable directories (respects all .gitignore rules)
- Non-git: fallback exclusion list applied correctly
- `{alwaysExcluded}` directories excluded in ALL cases (git or non-git)
- `{alwaysExcludedPatterns}` patterns excluded in ALL cases (e.g., `_skf-learn` matched by `_*-learn`)
- Empty directories skipped — no collections created for dirs with no files
- Stale collections from prior runs detected and removed
- Collection names sanitized (leading `_` and `.` stripped from dirname portion)
- Deep tier with user content: each user directory indexed as its own QMD collection with `**/*` mask
- Deep tier with no user content: skipped with informative note for step-04
- Deep tier re-run: stale collections removed, existing updated via `qmd update`, new directories added
- Quick/Forge tier: skipped silently with no negative messaging
- Workflow continues regardless of indexing outcome
- Auto-proceeded to step-04

### ❌ SYSTEM FAILURE:

- Indexing `_bmad/` or `forge-data/` under any circumstance
- Indexing directories matching `_*-learn` pattern
- Creating collections for empty directories
- Using `**/*.md` mask instead of `**/*` (misses source code files critical for skill generation)
- Indexing the entire project root as a single collection (pollutes results with module internals)
- Not using `git ls-files` when the project IS a git repo
- Leaving stale collections from deleted directories on re-run
- Attempting QMD indexing for Quick or Forge tiers
- Displaying "skipped" or "missing" messages for non-Deep tiers
- Halting the workflow due to QMD indexing failure
- Not proceeding to step-04 after this step

**Master Rule:** This step must NEVER fail the workflow. Use git as the authority for what belongs to the project. Always exclude `{alwaysExcluded}` and `{alwaysExcludedPatterns}`. Skip empty directories. Clean up stale collections. Index only user project directories with `**/*` mask. Non-Deep tiers skip silently.
