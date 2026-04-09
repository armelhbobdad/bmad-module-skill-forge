---
nextStepFile: './step-02-ecosystem-check.md'
registryResolutionData: 'references/registry-resolution.md'
---

# Step 1: Resolve Target

## STEP GOAL:

To accept a GitHub URL or package name from the user, resolve it to a GitHub repository, detect the primary language, and prepare state for source extraction.

## Rules

- Focus only on resolving the target to a GitHub repository — do not begin extraction or compilation
- If resolution fails, hard halt with actionable guidance

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

### 1. Accept User Input

"**Quick Skill — fastest path to a skill.**

Provide a **GitHub URL** or **package name** and I'll resolve it to source and compile a best-effort SKILL.md.

**Target:** (GitHub URL or package name)

Examples: `lodash`, `@tanstack/query`, `https://github.com/tursodatabase/limbo`, `cognee@0.5.0`

**Optional:**
- **Language hint:** (if the repo is multi-language)
- **Scope hint:** (specific directories to focus on)"

Wait for user input. **GATE [default: use args]** — If `{headless_mode}` and a target (URL or package name) was provided as argument: use it as the target input and auto-proceed, log: "headless: using provided target". If no target provided in headless mode, HALT with: "headless mode requires a target argument."

### 1b. Parse Version Targeting

**Version targeting:** If the user input contains `@` followed by a semver-like string (e.g., `cognee@0.5.0`, `https://github.com/org/repo@2.1.0-beta`), parse it as:
- **Package/URL:** everything before the last `@`
- **Target version:** everything after the last `@`

Store the target version as `target_version` in the extraction context. When present, this version overrides auto-detection (same behavior as `target_version` in the skill-brief schema).

If no `@version` suffix is present, proceed as today — version will be auto-detected.

### 2. Classify Input Type

**If input starts with `https://github.com/` or `github.com/`:**
- Extract org/repo from URL
- Set `resolved_url` to the GitHub URL
- Set `repo_name` to the repo name (last path segment)
- Skip to step 4 (Detect Language)

**If input is a package name:**
- Proceed to step 3 (Registry Resolution)

### 3. Registry Resolution

Load {registryResolutionData} for resolution patterns.

**Execute the fallback chain in order — stop at first success:**

1. **npm registry:** Fetch `https://registry.npmjs.org/{package_name}` — extract `repository.url`
2. **PyPI registry:** Fetch `https://pypi.org/pypi/{package_name}/json` — extract `info.project_urls.Source` or `info.home_page`
3. **crates.io registry:** Fetch `https://crates.io/api/v1/crates/{package_name}` — extract `crate.repository`
4. **Web search fallback:** Search `"{package_name} github repository"` — look for GitHub URL

**If all methods fail — HARD HALT:**

"**Resolution failed.** Could not resolve `{package_name}` to a GitHub repository.

Please check:
- Is the package name spelled correctly?
- Is it a private package?
- Is the source hosted on a non-GitHub platform?

**Provide the GitHub URL directly to continue.**"

Wait for corrected input. Loop back to step 2.

### 4. Detect Language

Determine primary language from:

1. **User-provided language hint** (overrides detection)
2. **Manifest file presence** (check via GitHub API or web browsing):
   - `package.json` → JavaScript/TypeScript
   - `pyproject.toml` or `setup.py` → Python
   - `Cargo.toml` → Rust
   - `go.mod` → Go

Set `language` to detected language.

### 5. Confirm Resolution

"**Target resolved:**

- **Repository:** {resolved_url}
- **Name:** {repo_name}
- **Language:** {language}
- **Scope:** {scope_hint or 'entire repo'}

**Proceeding to ecosystem check...**"

### 6. Proceed to Next Step

#### Menu Handling Logic:

- After successful resolution confirmation, immediately load, read entire file, then execute {nextStepFile}

#### EXECUTION RULES:

- This is an init step with auto-proceed after successful resolution
- Proceed directly to next step after confirmation

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN the target has been successfully resolved to a GitHub repository with confirmed URL, name, and detected language will you load and read fully `{nextStepFile}` to execute the ecosystem check.

