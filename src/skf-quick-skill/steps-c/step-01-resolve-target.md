---
nextStepFile: './step-02-ecosystem-check.md'
registryResolutionData: 'references/registry-resolution.md'
packageResolverProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-resolve-package.py'
  - '{project-root}/src/shared/scripts/skf-resolve-package.py'
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
- Skip to step 3a (Verify Target Version Tag), then step 4 (Detect Language)

**If input is a package-name-like token** (no whitespace, matches `[@a-zA-Z0-9._/-]+(@<semver>)?`, e.g. `lodash`, `@scope/name`, `requests==2.31`, `cognee@0.5.0`):
- Proceed to step 3 (Registry Resolution)

**Otherwise — input looks like free-form prose, not a target:**

The user typed something like "I want a skill that helps with onboarding" or "build me a brainstorming workflow" — quick-skill cannot resolve that to a GitHub repository. Instead of falling through to a registry-failure HARD HALT, redirect with a sibling-skill suggestion:

"**This input looks like a description, not a package or URL.** Quick Skill needs a package name (e.g. `lodash`, `@vercel/og`, `requests`) or a GitHub URL (e.g. `https://github.com/lodash/lodash`).

If you are describing a skill you want to **create from scratch** rather than compile from existing source:

- Run `/skf-create-skill` with a skill brief — full pipeline with provenance tracking and AST-verified exports
- Or use `bmad-agent-builder` for an interactive skill design session

Otherwise, paste the package name or GitHub URL of the library you want to wrap, and quick-skill will resolve it."

**GATE [default: HALT]** — In headless mode, emit the same redirect message and HALT with **exit code 3 (resolution-failure)** per the SKILL.md exit-code map. Before exiting, emit the error result contract per SKILL.md "Result Contract on HARD HALT" (`phase: "resolve-target"`, `error.code: "resolution-failure"`, `skill_package: null`). Do not attempt registry lookups against prose input; that wastes ~3-4 round trips and produces a less actionable error message than the redirect above.

### 3. Registry Resolution

Run the shared resolver against the deterministic registries (npm → PyPI → crates.io). The resolver does the HTTP+JSON+GitHub-URL-extraction work; the LLM only handles the web-search fallback below when needed.

**Resolve `{packageResolver}`** from `{packageResolverProbeOrder}`; first existing path wins. If no candidate exists, fall back to the LLM walk of {registryResolutionData} for the full chain.

```bash
python3 {packageResolver} {package_name} --timeout 10
```

The resolver emits JSON with `status` (`"ok"` or `"fallthrough"`), `resolved_url`, `repo_owner`, `repo_name`, `registry_used`, `registries_tried`, and a per-registry `registry_outcomes` map. Exit 0 means ok; exit 1 means fallthrough.

- **On `status: "ok"`** — capture `resolved_url`, `repo_name`, and `registry_used` from the JSON. Proceed to §3a.
- **On `status: "fallthrough"`** — the deterministic chain returned no GitHub URL (every registry replied with 404 / no-github-link / timeout). Fall back to the web-search step from {registryResolutionData} §4: search `"{package_name} github repository"` with a 15s timeout and look for a GitHub URL in the top results. If found, set `resolved_url` and proceed. If web search also returns nothing, HARD HALT below.

**If all methods fail — HARD HALT (exit code 3, resolution-failure):**

"**Resolution failed.** Could not resolve `{package_name}` to a GitHub repository.

Check:
- Is the package name spelled correctly?
- Is it a private package?
- Is the source hosted on a non-GitHub platform?

**Provide the GitHub URL directly to continue.**"

In interactive mode, wait for corrected input and loop back to step 2. In headless mode, emit the error result contract per SKILL.md "Result Contract on HARD HALT" (`phase: "resolve-target"`, `error.code: "resolution-failure"`, `skill_package: null`) and exit 3.

### 3a. Verify Target Version Tag (when applicable)

Skip this section if `target_version` is null (auto-detect path — version comes from manifest read in step-03).

When the user explicitly supplied `@version` in §1b, verify the tag exists in the resolved repo before extraction. Otherwise step-03 silently reads from the default branch while metadata records the requested version — a quiet provenance bug where the SKILL.md claims version 0.5.0 but the exports actually came from main.

Probe both with-and-without v-prefix (the v-prefix is conventional but not universal across ecosystems):

```bash
gh api repos/{owner}/{repo}/git/ref/tags/{target_version} --silent \
  || gh api repos/{owner}/{repo}/git/ref/tags/v{target_version} --silent
```

**If a matching tag is found** — set `source_ref` to the matching ref (with v-prefix when that variant matched). Step-03's ref-aware source reading uses this value to fetch from the tagged commit. Proceed to §4.

**If no tag matches** — HARD HALT with **exit code 3 (resolution-failure)**:

"**Tag `{target_version}` not found in `{owner}/{repo}`.**

The version was parsed from your `@version` suffix but does not exist as a tag in the resolved repository. Quick-skill cannot extract from a version with no commit pointer — the result would be sourced from the default branch but labelled `{target_version}` in metadata.

Recent tags in this repo:
{list top 5 from `gh api repos/{owner}/{repo}/tags --paginate=false`, or "(none — repo has no tags; omit @version to auto-detect from default branch)"}

Re-run with one of these tags, or omit the `@version` suffix to auto-detect from the default branch."

Before exiting, emit the error result contract per SKILL.md "Result Contract on HARD HALT" (`phase: "resolve-target"`, `error.code: "resolution-failure"`, `error.details: {requested_version: "{target_version}", available_tags: [...top 5]}`, `skill_package: null`). In headless mode, exit immediately; do not loop.

### 4. Detect Language

Determine primary language from:

1. **User-provided language hint** (overrides detection — skip the ambiguity gate below).
2. **Manifest-presence scan** — check the repo root for ALL of these (priority order = first hit wins on auto-pick):
   - `package.json` → JavaScript/TypeScript
   - `pyproject.toml` or `setup.py` → Python
   - `Cargo.toml` → Rust
   - `go.mod` → Go
   - `pom.xml` → Java (or Kotlin if `src/main/kotlin/` is present)
   - `build.gradle.kts` or `build.gradle` → Kotlin (or Java if only `src/main/java/` is present)

   Collect every match into `detected_languages`.

3. **Single-language case** (`len(detected_languages) <= 1`) — set `language` to the detected value (or HALT in step-01 §3 if zero matches).

4. **Multi-language case** (`len(detected_languages) > 1`) — surface the choice rather than silently picking the first match. Multi-language repos (Python + JS bindings, or monorepos with mixed manifests) otherwise produce a skill for whichever manifest probe hits first, with no signal that the user might have wanted the other one.

   "**`{repo_name}` has manifests for multiple languages:** {detected_languages}.

   Primary guess: **{first_match}** (manifest-priority order). If you wanted a different language, abort and re-run with `--language-hint <lang>` or with the optional language hint at step-01 §1.

   Select: [C] Continue with `{first_match}` · [A] Abort"

   - **IF C** — log "user accepted multi-manifest pick: `{first_match}`" and set `language` to the first match.
   - **IF A** — HARD HALT with **exit code 3 (resolution-failure)**: "Aborted to disambiguate language. Re-run with a `language_hint`." Before exiting, emit the error result contract per SKILL.md "Result Contract on HARD HALT" (`phase: "resolve-target"`, `error.code: "resolution-failure"`, `error.details: {detected_languages: [...], auto_pick: "{first_match}"}`, `skill_package: null`).
   - **GATE [default: C]** — Headless mode auto-proceeds with the manifest-priority pick; record `detected_languages` and `language_resolution: "auto-picked-first"` in the extraction context so the result contract surfaces the ambiguity downstream.

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

