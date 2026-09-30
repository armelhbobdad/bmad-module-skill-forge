---
nextStepFile: 'ecosystem-check.md'
registryResolutionData: '{registryResolutionPath}'
packageResolverProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-resolve-package.py'
  - '{project-root}/src/shared/scripts/skf-resolve-package.py'
githubProbeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-github-probe.py'
  - '{project-root}/src/shared/scripts/skf-github-probe.py'
detectLanguageProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-detect-language.py'
  - '{project-root}/src/shared/scripts/skf-detect-language.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 1: Resolve Target

## STEP GOAL:

To accept a GitHub URL or package name from the user, resolve it to a GitHub repository, detect the primary language, and prepare state for source extraction.

## Rules

- Focus only on resolving the target to a GitHub repository — do not begin extraction or compilation
- If resolution fails, hard halt with actionable guidance

## Steps

### 1. Accept User Input

**Batch mode:** if `--batch` is active (see SKILL.md "Batch Mode"), the current target was already resolved by On Activation step 5 from the next batch line and placed into the workflow context as `target`, with optional `language_hint` and `scope_hint` per-line modifiers. Skip the prompt below — emit `{"batch":<n>,"target":"<target>","status":"start"}` to stderr and proceed directly to §1b with the batch-supplied values.

**Single-target mode** (default):

"**Quick Skill — fastest path to a skill.**

Provide a **GitHub URL**, a **package name** or its **npm, PyPI or crates.io page** and I'll resolve it to source and compile a best-effort SKILL.md.

**Target:** (GitHub URL, package name or registry page URL)

Examples: `cocoindex`, `@tanstack/react-query`, `requests==2.31.0`, `https://github.com/tursodatabase/limbo`, `cognee@0.5.0`

**Optional:**
- **Language hint:** (if the repo is multi-language)
- **Scope hint:** (specific directories to focus on)

Or type `cancel` / `exit` / `:q` / `[X]` to leave without writing anything."

Wait for user input. **Cancel branch**: if the user types `cancel`, `exit`, `:q`, `[X]`, or selects `[X] Cancel and exit`, display "Cancelled. No files were written." and HARD HALT with **exit code 6 (user-cancelled)** per the exit-code map in `references/halt-contract.md`. Before exiting, emit the error result contract per `references/halt-contract.md` (`phase: "resolve-target"`, `error.code: "user-cancelled"`, `skill_package: null`). Cancellation here is non-destructive: no files have been written yet.

**GATE [default: use args]** — If `{headless_mode}` and a target (URL or package name) was provided as argument: use it as the target input and auto-proceed, log: "headless: using provided target". If no target provided in headless mode, HALT with: "headless mode requires a target argument."

### 1b. Parse the Target

**Resolve `{packageResolver}`** from `{packageResolverProbeOrder}`; first existing path wins. If no candidate exists, or a call to it prints no JSON on stdout, read {registryResolutionData} and apply its target shapes and registry chain by hand for §1b to §3.

Parse the target. Write it exactly as given on the line between the two markers: the quoted marker hands it to the parser unchanged, quotes, backticks and `$` included.

```bash
uv run {packageResolver} parse-target <<'SKF_TARGET'
{target}
SKF_TARGET
```

When the parser's `target_version` is not `null`, store it as `target_version` in the extraction context; a batch line's own `target_version` otherwise stays. A `target_version` overrides auto-detection (same behavior as `target_version` in the skill-brief schema). A `dist_tag` (an npm dist-tag such as `latest` or `canary`) pins no version: log "`{dist_tag}` pins no version; auto-detecting it". Without a `target_version`, the version is auto-detected.

### 2. Route by Kind

- **`github`**: set `resolved_url` ← `url`, `owner` ← `owner`, `repo` ← `repo` and `repo_name` ← `skill_name`, the name the skill is written under. A `/tree/<ref>/<folder>` URL also gives `ref` and `subdir`: set `source_ref` ← `ref`, and `scope_hint` ← `subdir` when no scope hint was given. Skip to §3a (Verify Target Version Tag), then §4 (Detect Language).
- **`package`** or **`registry-page`**: proceed to §3 (Registry Resolution) with `package_name`, and with `registry` when it is set.
- **`other-host`**, **`local-path`** or **`unparsed`**: quick-skill cannot resolve the input to a GitHub repository. Instead of a registry lookup that can only fail, show the redirect for its kind, then, in interactive mode, wait for new input and go back to §1b:

  - **`other-host`**: "**Quick Skill reads GitHub repositories only.** `{url}` is on `{host}`. Paste the project's GitHub URL if it has one, or clone it and run `/skf-brief-skill` on the local clone, then `/skf-create-skill`."
  - **`local-path`**: "**Quick Skill reads GitHub repositories, not local folders.** To make a skill from `{path}`, run `/skf-brief-skill` with that path, then `/skf-create-skill`. Or paste the GitHub URL of its repository."
  - **`unparsed`**: the user typed something like "I want a skill that helps with onboarding" or "build me a brainstorming workflow", or text that is no package name or URL. Redirect with a sibling-skill suggestion:

    "**This input looks like a description, not a package or URL.** Quick Skill needs a package name (e.g. `lodash`, `@vercel/og`, `requests==2.31.0`) or a GitHub URL (e.g. `https://github.com/lodash/lodash`).

    If you are describing a skill you want to **create from scratch** rather than compile from existing source:

    - Run `/skf-create-skill` with a skill brief: the full pipeline, with provenance tracking and AST-verified exports
    - Or use `bmad-agent-builder` for an interactive skill design session

    Otherwise, paste the package name or GitHub URL of the library you want to wrap, and quick-skill will resolve it."

**GATE [default: HALT]**: in headless mode, emit the redirect for the kind and HALT with **exit code 3 (resolution-failure)** per the exit-code map in `references/halt-contract.md`. Before exiting, emit the error result contract per `references/halt-contract.md` (`phase: "resolve-target"`, `error.code: "resolution-failure"`, `error.details: {kind: "<kind>"}`, `skill_package: null`).

### 3. Registry Resolution

Run the shared resolver (resolved in §1b) against the deterministic registries (npm → PyPI → crates.io):

```bash
uv run {packageResolver} resolve {package_name} --timeout 10 [--registry {registry}] [--language "{language_hint}"]
```

Pass `--registry` when §2 set `registry`, and `--language` when a language hint was given: a JavaScript, TypeScript, Python or Rust hint makes the resolver ask that language's registry alone. It prints JSON whose `status` is `ok`, `ambiguous` or `fallthrough` (exit 0, 3 or 1).

- **On `status: "ok"`**: set, from the JSON, `resolved_url`, `owner` ← `repo_owner`, `repo` ← `repo_name`, `repo_name` ← `skill_name` and `registry_used`; when `source_subdir` is set and no scope hint was given, set `scope_hint` ← `source_subdir`. Proceed to §3a.
- **On `status: "ambiguous"`**: a registry earlier in the chain answered for the name before `registry_used` resolved it, so the name may belong to two projects and the resolved repository may be the wrong one. Run the ambiguous-name gate below.
- **On `status: "fallthrough"`**: no registry gave a GitHub URL. Fall back to the web-search step from {registryResolutionData} §4: search `"{package_name} github repository"` with a 15s timeout and look for a GitHub URL in the top results. If found, take that URL as the target and go back to §1b. If web search also returns nothing, HARD HALT below.

**Ambiguous-name gate** (on `status: "ambiguous"` only). `{answers}` names each registry of `name_found_in` with its `registry_outcomes` value in words: `ok` resolved the name, `no-github-link` knows the name but gives no GitHub repository, `error` could not be read.

"**`{package_name}` may name more than one project.** {answers}. The registry chain would compile {resolved_url}, from `{registry_used}`, but an earlier registry knows the name or could not be read.

Select: [C] Continue with {resolved_url} · [U] Use another GitHub URL · [X] Cancel and exit"

- **IF C**: log "user accepted the `{registry_used}` resolution of `{package_name}`" and continue as on `status: "ok"`.
- **IF U**: ask for the GitHub URL of the project the user means, take it as the target and go back to §1b.
- **IF X**: display "Cancelled. No files were written." and HARD HALT with **exit code 6 (user-cancelled)**. Before exiting, emit the error result contract per `references/halt-contract.md` (`phase: "resolve-target"`, `error.code: "user-cancelled"`, `skill_package: null`).
- **GATE [default: HALT]**: in headless mode, never pick one of the projects. HARD HALT with **exit code 3 (resolution-failure)**: "**`{package_name}` is ambiguous:** {answers}. The registry chain would compile {resolved_url}, from `{registry_used}`. Pass the GitHub URL of the project you mean, or its npm, PyPI or crates.io page URL, instead of the package name." Before exiting, emit the error result contract per `references/halt-contract.md` (`phase: "resolve-target"`, `error.code: "resolution-failure"`, `error.details: {status: "ambiguous", package_name, name_found_in, registry_outcomes, registry_used, resolved_url}`, `skill_package: null`).

**If all methods fail — HARD HALT (exit code 3, resolution-failure):**

"**Resolution failed.** Could not resolve `{package_name}` to a GitHub repository.

Check:
- Is the package name spelled correctly?
- Is it a private package?
- Is the source hosted on a non-GitHub platform?

**Provide the GitHub URL directly to continue.**"

In interactive mode, wait for corrected input and loop back to §1b. In headless mode, emit the error result contract per `references/halt-contract.md` (`phase: "resolve-target"`, `error.code: "resolution-failure"`, `skill_package: null`) and exit 3.

### 3a. Verify Target Version Tag (when applicable)

Skip this section if `target_version` is null (auto-detect path: the version comes from the manifest read in step 3).

When the target carried a version (§1b), verify the tag exists in the resolved repo before extraction. Otherwise step 3 silently reads from the default branch while metadata records the requested version: a quiet provenance bug where the SKILL.md claims version 0.5.0 but the exports actually came from main.

**Resolve `{githubProbe}`** from `{githubProbeProbeOrder}`; first existing path wins. If no candidate exists, halt as when no probe could read the tags (below).

List the repository's tags once, looking for every form a tag gives the version: `0.5.0`, `v0.5.0`, or a monorepo package's `<name>@0.5.0`:

```bash
uv run {githubProbe} tags --repo {owner}/{repo} --version {target_version} --name {package_name or repo_name} --limit 5
```

- **`status: "ok"` with `match` set**: set `source_ref` ← `match`, which replaces a `/tree/` URL's ref. Step 3's ref-aware source reading uses this value to fetch from the tagged commit. Proceed to §4.
- **`status: "ok"` with `match` null**: the listing lacks the tag. HARD HALT with **exit code 3 (resolution-failure)**:

  "**Tag `{target_version}` not found in `{owner}/{repo}`.**

  The version was parsed from your target but no tag of the resolved repository names it. Quick-skill cannot extract from a version with no commit pointer: the result would be sourced from the default branch but labelled `{target_version}` in metadata.

  Tags near this version:
  {the probe's `nearest`, else its `tags`, or "(none: the repo has no tags)"}

  Re-run with one of these tags, or omit the version to auto-detect from the default branch."

  Before exiting, emit the error result contract per `references/halt-contract.md` (`phase: "resolve-target"`, `error.code: "resolution-failure"`, `error.details: {requested_version: "{target_version}", available_tags: [the tags shown]}`, `skill_package: null`).
- **`status: "unavailable"`, any other exit, or no `{githubProbe}` candidate**: nothing could read the repository's tags, so the tag may exist. Do not report it missing. HARD HALT with **exit code 3 (resolution-failure)**: "**Could not check tag `{target_version}` in `{owner}/{repo}`.** {the probe's `message` (on stderr after another exit), or with no candidate: SKF's GitHub probe (`skf-github-probe.py`) is missing from `{project-root}/_bmad/skf/shared/scripts/`, so re-install SKF.} Re-run once GitHub can be read, or omit the version to auto-detect from the default branch." Before exiting, emit the error result contract per `references/halt-contract.md` (`phase: "resolve-target"`, `error.code: "resolution-failure"`, `error.details: {requested_version: "{target_version}", cause: "<the probe's cause, probe-error after another exit, or github-probe-missing>"}`, `skill_package: null`).

In headless mode, exit immediately on either halt; do not loop.

### 4. Detect Language

**Resolve `{detectLanguageHelper}`** from `{detectLanguageProbeOrder}`; first existing path wins. If no candidate exists (e.g. Python/`uv` unavailable), fall back to the manifest-priority walk documented in the helper's `--help` — `package.json` → JavaScript/TypeScript (TypeScript when a `tsconfig.json` is also present), `Cargo.toml` → Rust, `pyproject.toml`/`setup.py`/`setup.cfg` → Python, `go.mod` → Go, `pom.xml` → Java, `build.gradle.kts` → Kotlin, `build.gradle` → Kotlin when `src/main/kotlin/` exists else Java, `*.csproj`/`*.sln` → C#, `Gemfile` → Ruby, then extension frequency — applied by hand.

Determine primary language:

1. **User-provided language hint** (overrides detection) — set `language` to the hint and skip straight to §5. The disambiguation gate below does not run.

2. **Delegate the rule walk to `{detectLanguageHelper}`** — it is the single source of truth for the manifest → language rule table (including the `package.json` JS-vs-TS disambiguation); do not restate or re-derive it here. Fetch the repo file listing once (`gh api repos/{owner}/{repo}/git/trees/{source_ref or default branch}?recursive=1`, reading the `path` values), then hand the flat list to the script:

   ```bash
   echo '{"tree": [<flat list of repo-relative file paths>]}' | uv run {detectLanguageHelper}
   ```

   The script returns `{language, confidence, detection_source, detected_languages}` after walking the deterministic rule table (manifest presence first, then extension-frequency fallback). `detected_languages` is the ordered, deduplicated set of every manifest-level match in priority order, with `detected_languages[0]` equal to the winning `language`.

3. **Auto-pick** — set `language` to the returned `language`. If `detected_languages` is empty (the script recognized no manifest and no source extensions — `language` is `"unknown"`), treat it as a zero-match resolution and HALT with the step 1 §3 resolution-failure guidance so the user can supply a language hint or a different target.

4. **Multi-language gate** (`len(detected_languages) > 1`) — the script found manifests for more than one language. Surface the choice rather than silently keeping the first match. Multi-language repos (Python + JS bindings, or monorepos with mixed manifests) otherwise produce a skill for whichever manifest sorts first in priority order, with no signal that the user might have wanted the other one.

   "**`{repo_name}` has manifests for multiple languages:** {detected_languages}.

   Primary guess: **{language}** (`detected_languages[0]`, manifest-priority order). If you wanted a different language, abort and re-run with `--language-hint <lang>` or with the optional language hint at step 1 §1.

   Select: [C] Continue with `{language}` · [A] Abort"

   - **IF C** — log "user accepted multi-manifest pick: `{language}`" and keep `language`.
   - **IF A** — HARD HALT with **exit code 3 (resolution-failure)**: "Aborted to disambiguate language. Re-run with a `language_hint`." Before exiting, emit the error result contract per `references/halt-contract.md` (`phase: "resolve-target"`, `error.code: "resolution-failure"`, `error.details: {detected_languages: [...], auto_pick: "{language}"}`, `skill_package: null`).
   - **GATE [default: C]** — Headless mode auto-proceeds with the manifest-priority pick; record `detected_languages` and `language_resolution: "auto-picked-first"` in the extraction context so the result contract surfaces the ambiguity downstream.

### 5. Confirm Resolution

"**Target resolved:**

- **Repository:** {resolved_url}
- **Name:** {repo_name}
- **Registry:** {registry_used} (omit this line when no registry resolved the target)
- **Ref:** {source_ref} (omit this line when `source_ref` is not set)
- **Language:** {language}
- **Scope:** {scope_hint or 'entire repo'}

**Proceeding to ecosystem check...**"

### 6. Proceed to Next Step

Once the target is resolved to a GitHub repository with confirmed URL, name, and detected language, load and execute {nextStepFile} for the ecosystem check.

