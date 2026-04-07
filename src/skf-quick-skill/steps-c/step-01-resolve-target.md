---
nextStepFile: './step-02-ecosystem-check.md'
registryResolutionData: '../data/registry-resolution.md'
---

# Step 1: Resolve Target

## STEP GOAL:

To accept a GitHub URL or package name from the user, resolve it to a GitHub repository, detect the primary language, and prepare state for source extraction.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 🛑 NEVER generate content without user input
- 📖 CRITICAL: Read the complete step file before taking any action
- 🔄 CRITICAL: When loading next step with 'C', ensure entire file is read
- 📋 YOU ARE A FACILITATOR, not a content generator
- ✅ YOU MUST ALWAYS SPEAK OUTPUT In your Agent communication style with the config `{communication_language}`

### Role Reinforcement:

- ✅ You are a rapid skill compiler resolving a target package to its source
- ✅ If you already have been given a name, communication_style and identity, continue to use those while playing this new role
- ✅ Speed is the priority — resolve quickly, fail fast if unresolvable
- ✅ You bring package ecosystem knowledge, user brings their target

### Step-Specific Rules:

- 🎯 Focus only on resolving the target to a GitHub repository
- 🚫 FORBIDDEN to begin source extraction or compilation
- 💬 Approach: Accept input, resolve, confirm, proceed
- 📋 If resolution fails, hard halt with actionable guidance

## EXECUTION PROTOCOLS:

- 🎯 Follow the MANDATORY SEQUENCE exactly
- 💾 Set state: resolved_url, repo_name, language, scope_hint
- 📖 Load {registryResolutionData} for resolution patterns
- 🚫 Do not proceed without a confirmed resolved repository

## CONTEXT BOUNDARIES:

- This is the first step — no prior context exists
- User provides a GitHub URL or package name (npm/PyPI/crates.io)
- Optional: language hint, scope hint
- Web browsing required for registry API lookups
- Focus: resolution only, not extraction

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

### 1. Accept User Input

"**Quick Skill — fastest path to a skill.**

Provide a **GitHub URL** or **package name** and I'll resolve it to source and compile a best-effort SKILL.md.

**Target:** (GitHub URL or package name)

**Optional:**
- **Language hint:** (if the repo is multi-language)
- **Scope hint:** (specific directories to focus on)"

Wait for user input.

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

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- User input accepted (URL or package name)
- Target resolved to a valid GitHub repository URL
- Language detected or provided
- State set: resolved_url, repo_name, language, scope_hint
- Auto-proceeding to ecosystem check

### ❌ SYSTEM FAILURE:

- Proceeding without a resolved repository
- Skipping registry resolution fallback chain
- Not providing actionable guidance on resolution failure
- Beginning extraction or compilation in this step

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
