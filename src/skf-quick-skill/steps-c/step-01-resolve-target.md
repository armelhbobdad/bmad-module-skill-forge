---
nextStepFile: './step-02-ecosystem-check.md'
registryResolutionData: 'references/registry-resolution.md'
---

# Step 1: Resolve Target

Communicate with the user in `{communication_language}`.

## STEP GOAL:

To accept a GitHub URL or package name from the user, resolve it to a GitHub repository, detect the primary language, and prepare state for source extraction.

## Rules

- Focus only on resolving the target to a GitHub repository — do not begin extraction or compilation
- If resolution fails, hard halt with actionable guidance

## MANDATORY SEQUENCE

### 1. Accept User Input

"**Quick Skill — fastest path to a skill.**

Provide a **GitHub URL** or **package name** and I'll resolve it to source and compile a best-effort SKILL.md.

**Target:** (GitHub URL or package name)

Examples: `cocoindex`, `@tanstack/query`, `https://github.com/tursodatabase/limbo`, `cognee@0.5.0`

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

**If input is a package-name-like token** (no whitespace, matches `[@a-zA-Z0-9._/-]+(@<semver>)?`, e.g. `lodash`, `@scope/name`, `requests==2.31`, `cognee@0.5.0`):
- Proceed to step 3 (Registry Resolution)

**Otherwise — input looks like free-form prose, not a target:**

The user typed something like "I want a skill that helps with onboarding" or "build me a brainstorming workflow" — quick-skill cannot resolve that to a GitHub repository. Instead of falling through to a registry-failure HARD HALT, redirect with a sibling-skill suggestion:

"**This input looks like a description, not a package or URL.** Quick Skill needs a package name (e.g. `lodash`, `@vercel/og`, `requests`) or a GitHub URL (e.g. `https://github.com/lodash/lodash`).

If you are describing a skill you want to **create from scratch** rather than compile from existing source:

- Run `/skf-create-skill` with a skill brief — full pipeline with provenance tracking and AST-verified exports
- Or use `bmad-agent-builder` for an interactive skill design session

Otherwise, paste the package name or GitHub URL of the library you want to wrap, and quick-skill will resolve it."

**GATE [default: HALT]** — In headless mode, emit the same redirect message and HALT with **exit code 3 (resolution-failure)** per the SKILL.md exit-code map. Do not attempt registry lookups against prose input; that wastes ~3-4 round trips and produces a less actionable error message than the redirect above.

### 3. Registry Resolution

Load {registryResolutionData} and execute its fallback chain in order — stop at first success. The reference is canonical for the chain order (npm → PyPI → crates.io → web search), the per-registry URL templates and response-field paths, the per-call timeouts (10s per registry, 15s for web search), and the timeout-as-soft-failure semantics.

**If all methods fail — HARD HALT (exit code 3, resolution-failure):**

"**Resolution failed.** Could not resolve `{package_name}` to a GitHub repository.

Check:
- Is the package name spelled correctly?
- Is it a private package?
- Is the source hosted on a non-GitHub platform?

**Provide the GitHub URL directly to continue.**"

In interactive mode, wait for corrected input and loop back to step 2. In headless mode, exit 3.

### 4. Detect Language

Determine primary language from:

1. **User-provided language hint** (overrides detection)
2. **Manifest file presence** (check via GitHub API or web browsing):
   - `package.json` → JavaScript/TypeScript
   - `pyproject.toml` or `setup.py` → Python
   - `Cargo.toml` → Rust
   - `go.mod` → Go
   - `pom.xml` → Java (or Kotlin if `src/main/kotlin/` is present)
   - `build.gradle.kts` or `build.gradle` → Kotlin (or Java if only `src/main/java/` is present)

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

