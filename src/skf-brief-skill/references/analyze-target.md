---
nextStepFile: 'scope-definition.md'
versionResolutionFile: 'references/version-resolution.md'
extractPublicApiProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-extract-public-api.py'
  - '{project-root}/src/shared/scripts/skf-extract-public-api.py'
detectWorkspacesProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-detect-workspaces.py'
  - '{project-root}/src/shared/scripts/skf-detect-workspaces.py'
detectLanguageProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-detect-language.py'
  - '{project-root}/src/shared/scripts/skf-detect-language.py'
githubProbeProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-github-probe.py'
  - '{project-root}/src/shared/scripts/skf-github-probe.py'
githubFetchProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-github-fetch.py'
  - '{project-root}/src/shared/scripts/skf-github-fetch.py'
validatePinsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-validate-pins.py'
  - '{project-root}/src/shared/scripts/skf-validate-pins.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 2: Analyze Target

## Rules

- Do not make scoping decisions or recommendations
- Do not hallucinate or guess about repository contents
- **One display.** The §5 summary is this step's one display of the analysis. Before it, §2 to §4.3 show one progress line each, besides any warning, the truncation choice (§1), the monorepo pick (§1b) and §4.4's semantic signals; the values they compute stay in context for §5.
- **Staged inputs.** The helpers of this step read the repository from files in the run folder `{run_dir}` that step 1 §1 created, never from a list or a file's text typed into a command: `{run_dir}/tree.json` (the file list, §1), `{run_dir}/files/` (manifests and entry points fetched at `{analysis_ref}`, laid out like the repository), `{run_dir}/snapshot.json` (the tree's counts and module candidates, §2) and `{run_dir}/extract.json` (the exports, §4). Step 3 reads the same files.
- **Ratify run (`ratify_mode: true`):** this step runs only from step 4 `[R] Revise Scope`, to give step 3 an analysis of the brief's repository, and never replaces the hydrated `name`, `version` or `language`. §1 treats the hydrated `target_ref` and `target_version` as set in step 01, and a hydrated `version` without either as an implicit `target_version`: §1 resolves it to a tag the same way, and with no match analyzes `HEAD` without the zero-match warning. §1b selects, without asking, the workspace whose path begins the hydrated `scope.include` globs (the repo root when none does). §3 runs only to choose §4's path: the brief keeps the hydrated `language`, which the §5 summary shows with the hydrated `version`. Skip §4b. At §5, set `ratify_analyzed: true` in workflow context, so a later `[R]` goes straight to step 3.

## Sequence

### 0. Docs-Only Target

**If `source_type` is `docs-only`:** there is no repository to read, so skip §1 to §5 (no tree, manifests, extraction or version detection). Set `{language}` to the `language_hint` argument when one was supplied, else `documentation` (the language skf-analyze-source writes for a docs-only brief). Leave `detected_version` unset: the brief's version is `target_version` when step 1 collected one, else the `1.0.0` default (step 5's writer applies that precedence). Display:

"**Docs-only target: no repository to analyze.**
**Language:** {language}
**Version:** {target_version, or 1.0.0 (default)}"

Then load, read entire file, then execute {nextStepFile}.

**If `source_type` is `source`:** continue to §1.

### 1. Resolve Target Location

Display: "**Resolving target...**"

**For GitHub URLs:**

**Resolve the analysis ref first.** `{analysis_ref}` is the git ref every GitHub-API fetch in this step (tree, manifests, contents) reads from: resolve it before fetching anything so the analyzed structure matches the version being skilled.
- If neither `target_ref` nor `target_version` was set in step 01: `{analysis_ref}` = `HEAD` (default branch). This is the common case: skip straight to the listing below with no extra call.
- If `target_ref` is set (an explicit ref the user stated verbatim, highest priority): use it directly as `{analysis_ref}`, with no tag lookup.
- If `target_version` is set: resolve it to a tag with `{validatePinsHelper}` (resolve it from `{validatePinsProbeOrder}`; first existing path wins), which tries every form a tag writes a version in and prints one JSON line:

  ```bash
  uv run {validatePinsHelper} --repo-url "https://github.com/{owner}/{repo}" --pin "{target_version}" --format tag
  ```

  - Exit 0: set `{analysis_ref}` to its `resolved_ref`.
  - Exit 1 (`status: "invalid"`) with tags in `suggestions`: no tag matches. Warn `"No git tag matches version {target_version}; analyzing the default branch (HEAD) instead: structure and exports may not match the pinned version."`, naming those nearest tags.
  - Exit 1 with an empty `suggestions`: the repository has no tag, or its tags could not be listed. Warn `"Could not find or list the tags of {owner}/{repo}; analyzing the default branch (HEAD) instead: structure and exports may not match the pinned version."`
  - Exit 2 (`gh` missing, or a URL it does not accept), or no candidate path: warn `"Could not check the tags of {owner}/{repo} ({the error it printed}); analyzing the default branch (HEAD) instead: structure and exports may not match the pinned version."`
  - On any of these warnings, add it to `workflow_warnings[]`, set `{analysis_ref}` = `HEAD`, and record the fallback in the §5 analysis summary.

**List the repository.** Resolve `{githubProbeHelper}` from `{githubProbeProbeOrder}`; first existing path wins. Write its listing to the run folder in one call:

```bash
uv run {githubProbeHelper} tree --repo "{owner}/{repo}" --ref "{analysis_ref}" --out "{run_dir}/tree.json"
```

`--out` writes the listing to `{run_dir}/tree.json`, where the helpers read it, and the call prints the rest as one JSON line: `status`, `cause`, `message`, `gh`, `count` and `truncated`. Branch on that line. Every branch below that halts emits its halt envelope first, per the SKILL.md Halt Contract:

- **`status: "unavailable"`** (exit 3): the repository or the ref cannot be read, and `message` names the cause and the fix.
  - `cause` `gh-missing` or `gh-unauthenticated`: emit the halt envelope first, `uv run {emitBriefEnvelopeHelper} emit --target stderr` with `halt_reason: "gh-auth-failed"`, then HALT (exit code 3): "**Error:** {message}"
  - `cause` `repo-not-found`, `no-access` or `ref-not-found` (or `unreachable`, `invalid-repo`): emit the halt envelope first, `uv run {emitBriefEnvelopeHelper} emit --target stderr` with `halt_reason: "target-inaccessible"`, then HALT (exit code 3): "**Error:** {message}"
- **No candidate path, or no JSON** (the helper exits 1 or 2): emit the halt envelope first, `uv run {emitBriefEnvelopeHelper} emit --target stderr` with `halt_reason: "target-inaccessible"`, then HALT (exit code 3): "**Error:** Cannot list `{url}`: {the first line of its stderr, or `skf-github-probe.py not found`}."

**Fetching files.** Every file this step and step 3 read from a GitHub source is fetched into `{run_dir}/files` at `{analysis_ref}`, laid out like the repository, by `{githubFetchHelper}` (resolve it from `{githubFetchProbeOrder}`; first existing path wins; HALT if no candidate exists), which §4.1's `--follow` runs too. It reads each file from `raw.githubusercontent.com`, which needs no `gh`, and through `gh` only when that fails (a private repository). A path the listing does not hold costs no request and is reported in `unmatched`, so each call names every candidate. On exit 3, its `failed` names each file it could not read: go on without them, and add `files not fetched: <their paths>` to `workflow_warnings[]`.

**Truncation.** When `truncated` is true, GitHub cut the listing short:
- Display: "Note: GitHub returned a truncated tree ({count} files). Full analysis may require a local clone." and add `tree listing truncated by GitHub ({count} files listed)` to `workflow_warnings[]`.
- Interactive: present
  ```
  Tree is truncated. How would you like to proceed?
    [L] Clone locally and re-analyze (slower but complete)
    [P] Proceed with the partial tree (faster, may miss exports under deeper paths)
  ```
  On `[L]`: shallow-clone the repository into the run folder at `{analysis_ref}`:

  ```bash
  git clone --depth 1 --branch "{analysis_ref}" "https://github.com/{owner}/{repo}.git" "{run_dir}/clone"
  ```

  Leave `--branch` out when `{analysis_ref}` is `HEAD`. A commit SHA is no `--branch` value: clone it with `git clone --filter=blob:none --no-checkout "https://github.com/{owner}/{repo}.git" "{run_dir}/clone"`, then `git -C "{run_dir}/clone" checkout --quiet "{analysis_ref}"`. Set `{source_path}` ← `{run_dir}/clone` and restart this section for that local path: its listing replaces `{run_dir}/tree.json`, and every later `{source_path}`, in this step and in step 3, is the clone. Before any later HALT, remove the clone (`rm -rf "{run_dir}/clone"`): a halt keeps the files the run staged, never a copy of the repository. If a clone or checkout command fails, remove what it left (`rm -rf "{run_dir}/clone"`), warn `"Could not clone {owner}/{repo} at {analysis_ref} ({the first line of its stderr}); proceeding with the partial tree."`, add the warning to `workflow_warnings[]` and continue as `[P]`.
  **GATE [default: P]**: on `[P]`, and under headless: record `tree_truncated: true` in the analysis summary and continue without HALT.

**For local paths:** `{source_path}` is the path.
- If the directory does not exist (`test -d "{source_path}"` fails): emit the halt envelope first, `uv run {emitBriefEnvelopeHelper} emit --target stderr` with `halt_reason: "target-inaccessible"` (the failure class of a GitHub target the CLI cannot read), then HALT (exit code 3): "**Error:** Directory not found at {path}. Verify the path is correct."
- List its files into the run folder, the files git tracks and the untracked ones it does not ignore:

  ```bash
  git -C "{source_path}" -c core.quotePath=false ls-files --cached --others --exclude-standard -- . ':(exclude,glob)**/.skf-run/**' > "{run_dir}/tree.json"
  ```

  Outside a git work tree (the command fails): `(cd "{source_path}" && find . -type f -not -path './.git/*' -not -path '*/node_modules/*' -not -path '*/.skf-run/*') > "{run_dir}/tree.json"`. Both leave out SKF's run folders (`.skf-run`), which a listing of the project root would otherwise hold.

### 1b. Detect Monorepo / Workspace Layout

**Resolve `{detectWorkspacesHelper}`** from `{detectWorkspacesProbeOrder}`; first existing path wins. HALT if no candidate exists.

Delegate workspace detection to `{detectWorkspacesHelper}`: it reads the file list from `{run_dir}/tree.json` and the root manifests from a folder laid out like the repository. For a GitHub source, `--manifest-files` lists the root manifests the detectors read that the listing holds (`rush.json` among them; Nx needs only the tree), the fetch writes them into `{run_dir}/files`, and the last line runs the detection:

```bash
uv run {detectWorkspacesHelper} --tree-file "{run_dir}/tree.json" --manifest-files > "{run_dir}/manifests.txt"
uv run {githubFetchHelper} --repo "{owner}/{repo}" --ref "{analysis_ref}" --tree-file "{run_dir}/tree.json" --dest "{run_dir}/files" --patterns-file "{run_dir}/manifests.txt"
uv run {detectWorkspacesHelper} --tree-file "{run_dir}/tree.json" --manifest-dir "{run_dir}/files"
```

For a local source (or the `[L]` clone), drop the first two lines and pass the folder itself: `--manifest-dir "{source_path}"`. The manifest folder of this section is the one §2 and §4 pass again.

The script returns a JSON envelope: `{is_monorepo, manifest_kind, workspaces[], warnings[]}`. Apply the result deterministically — see `src/shared/scripts/schemas/workspace-detection.v1.json` for the full contract.

**If `is_monorepo: false`** — skip this section silently and continue to §2.

**If `is_monorepo: true`** — present the discovered workspaces and prompt:

```
This looks like a monorepo ({manifest_kind}) with these workspaces:
  1. {workspaces[0].name} ({workspaces[0].path})
  2. {workspaces[1].name} ({workspaces[1].path})
  ...
Which one should the skill cover? Pick a number, or type 'all' to scope at the repo root.
```

Interactive: wait for the user choice. On a numbered choice, store `monorepo_workspace: {path}` and rebase §2-§4b against that path. On `'all'`, leave `monorepo_workspace` unset and proceed at the repo root with a note in the analysis summary that scope is unfiltered.

**GATE [default: the workspace an `include` glob names, else the repo root]**: headless, if the input contract supplied an `include` glob that begins with one of the workspace paths, auto-select that workspace (log `"headless: auto-selected workspace {name} from include glob"`). Otherwise default to repo root and log `"warn: monorepo detected ({manifest_kind}) but no workspace pre-selected; analyzing at repo root"`.

Log each non-empty `warnings[]` entry from the script and add it to `workflow_warnings[]`, so a malformed or unfetched root manifest is debuggable; the workflow does not HALT, because falling back to repo-root analysis is always safe.

**`cross-ecosystem workspace ignored` warning:** when a root workspace manifest from a different language ecosystem co-exists with the surfaced one (e.g. a root `Cargo.toml [workspace]` alongside a pnpm workspace), the script surfaces only the higher-priority kind and emits this warning naming the ignored kind and its member count. The ignored ecosystem's workspaces are **not** in `workspaces[]`, so the numbered menu above will not list them. When this warning is present, tell the operator both ecosystems exist and ask which the skill should cover; if they pick the ignored ecosystem, scope §2-§4b at its root (or the relevant member) rather than the surfaced workspace, and carry the ignored kind into §3 (see the `workspace_signal` note there).

### 2. Read Repository Structure

Display `Reading the repository structure...`, then take the structure from the tree snapshot `{detectWorkspacesHelper}` computes, never from a count of the listing by hand. Add `--root "{monorepo_workspace}"` when §1b picked a workspace:

```bash
uv run {detectWorkspacesHelper} --tree-file "{run_dir}/tree.json" --manifest-dir "<§1b's manifest folder>" --snapshot > "{run_dir}/snapshot.json"
```

It holds `file_count`, `source_file_count`, `dir_count`, `top_level_files`, `top_level_dirs`, `truncated` (the counts are then lower bounds), the `workspaces` detection found, and the module candidates §4.3 picks from.

### 3. Detect Primary Language

Display `Detecting the language...`. **Resolve `{detectLanguageHelper}`** from `{detectLanguageProbeOrder}`; first existing path wins. HALT if no candidate exists.

Delegate the rule walk to `{detectLanguageHelper}` instead of evaluating manifest presence and extension frequency in prose:

```bash
uv run {detectLanguageHelper} --tree-file "{run_dir}/tree.json" [--workspace-signal "<§1b manifest_kind>"]
```

Pass the §1b `manifest_kind` as `--workspace-signal` (leave the flag out when it is `null` / not a monorepo). This gives the workspace root precedence: for a `cargo-workspace` or `python-multi-package` root, the script returns the root language (rust/python) instead of being misled into `typescript` by a nested `package.json` + `tsconfig.json` in a non-workspace subdirectory (e.g. a `docs/` or `website/` site). JS-family workspace kinds (`npm-workspaces`/`pnpm-workspaces`/`lerna`/`rush`/`nx`) carry no override: their root `package.json` resolves js/ts normally.

**When §1b surfaced a `cross-ecosystem workspace ignored` warning and the operator chose the ignored ecosystem:** pass that ignored kind as `--workspace-signal` (not the surfaced kind), so a co-located `cargo-workspace`/`python-multi-package` root resolves to rust/python instead of being pinned to the surfaced ecosystem's language by the workspace that won detection priority.

The script returns `{language, confidence, detection_source, fallback_to_extension_frequency, source_language, detected_languages}` after walking the documented rule table: the `workspace_signal` precedence above first, then the manifests nearest the tree's root, by folder depth and then rule order (package.json with tsconfig.json disambiguation, Cargo.toml, pyproject.toml/setup.py/setup.cfg, go.mod, pom.xml, build.gradle.kts, Package.swift, Gemfile, build.gradle Groovy with Java/Kotlin disambiguation, *.csproj/*.sln), where a manifest in a docs, examples, tests or other non-core folder, or in a hidden one, decides only when no other exists, then extension-frequency fallback. With no manifest at the root, the nearest one decides at `medium` confidence and `source_language` names the language most source files are in. Use the returned values directly: §5 shows them.

**Headless language override.** If `language_hint` was supplied as a headless argument, use it as the confirmed `{language}` (overriding the detected value) and carry it forward to §4 and step 03. The detector still runs so §5's Detected-language line reflects what the source signals, but the explicit hint wins and the step 03 §4 low-confidence override does not fire. When `language_hint` is absent, carry the detected `{language}` forward.

If `confidence` is `low` (or `unknown` is returned for `language`) and no `language_hint` was supplied: flag for user override in step 03 §4.

### 4. List Top-Level Modules and Exports

**Resolve `{extractPublicApiHelper}`** from `{extractPublicApiProbeOrder}`; first existing path wins. HALT if no candidate exists.

Identify the public API surface. **Delegate the parsing to `{extractPublicApiHelper}` whenever the detected language is supported:** it finds the entry files, parses the manifest and reads the exports and the version, so none of them is derived in prose.

**Script-supported languages** (use the script): `js`, `ts`, `javascript`, `typescript`, `python`, `rust`, `go`, `java`, `kotlin`.

Display `Listing the exports...`. This section runs exactly one of §4.1 (script path) or §4.2 (fallback path) based on the detected language, then always §4.3 (the modules and exports §5 shows) and conditionally §4.4 (semantic signals).

#### 4.1 Procedure — script-supported languages

`<source root>` is `{run_dir}/files` for a GitHub source. For a local source, or the `[L]` clone, it is `{source_path}`, whose files need no fetch: leave the `{githubFetchHelper}` lines and step 2's `--repo` and `--ref` out. When §1b picked a workspace, prefix each manifest candidate with `{monorepo_workspace}/` and pass `--scope "{monorepo_workspace}"`.

1. **Find the entry files.** Fetch the manifest candidates (the listing decides which exist), let the extractor find the entry files in the listing by full mode's rules, and fetch the files it lists:

   ```bash
   uv run {githubFetchHelper} --repo "{owner}/{repo}" --ref "{analysis_ref}" --tree-file "{run_dir}/tree.json" --dest "{run_dir}/files" package.json pyproject.toml setup.py setup.cfg Cargo.toml go.mod pom.xml build.gradle.kts build.gradle
   uv run {extractPublicApiHelper} --mode entries --language "<language>" --tree-file "{run_dir}/tree.json" --source-root "<source root>" [--scope "{monorepo_workspace}"] --fetch-list "{run_dir}/entries.txt" > "{run_dir}/entries.json"
   uv run {githubFetchHelper} --repo "{owner}/{repo}" --ref "{analysis_ref}" --tree-file "{run_dir}/tree.json" --dest "{run_dir}/files" --patterns-file "{run_dir}/entries.txt"
   ```

   `{run_dir}/entries.json` names the `manifest` the extractor read and its `entry_files`: never pick an entry file yourself. Its `unresolved` and `warnings` join the extraction warnings §5 shows. When the entries call exits non-zero, or it names neither a manifest nor an entry file, there is nothing to parse: skip the rest of §4.1 and take §4.2.

2. **Parse them and follow their re-exports** by path: the `manifest` (no `--manifest-file` when it is null) and one `--entry-file` per entry file (for a GitHub source, each one the fetch `fetched`):

   ```bash
   uv run {extractPublicApiHelper} --mode quick --language "<language>" --source-root "<source root>" --tree-file "{run_dir}/tree.json" --manifest-file "<manifest path>" --entry-file "<entry path>" --follow [--repo "{owner}/{repo}" --ref "{analysis_ref}"] > "{run_dir}/extract.json"
   ```

   `--follow` reads each module an `export *` or a star import passes names on from, round after round, so a chain is read to its end, and lists them in `followed`; for a GitHub source, `--repo` and `--ref` fetch each into `{run_dir}/files` first. A module it could not read stays in `unlisted[]`, and a warning names it.

3. On a non-zero exit of the extractor (codes 1 or 2 per its docstring), log its stderr and fall through to §4.2 (the prose-fallback path), which writes over `{run_dir}/extract.json`: never HALT just because the script choked on an unusual manifest.

4. Keep `{run_dir}/extract.json`'s `package_name`, `exports` (each entry's `name`/`type`/`source_file`), `dependencies` and `warnings` for §5, which shows the package, its dependency count, the exports and the warnings. Its `version` feeds §4b instead of being derived again, and step 3 counts its exports.

#### 4.2 Procedure — fallback (not script-supported)

Languages outside the script coverage (Ruby / C# / Swift / etc.) take this path. The §4.1 fall-through on script error also lands here.

Fall back to ad-hoc inspection of `Gemfile` / `*.csproj` / `*.sln` / `Package.swift` / file extension frequency. Read the files you inspect from `{run_dir}/files` (fetched with §4.1's fetch line, naming them) or the local folder. Note any obvious entry points, and flag the limitation in the analysis summary so the user knows scoping is on coarser signals. Then stage an extraction with no export, so step 3 reads `{run_dir}/extract.json` on either path: `printf '{"exports": []}' > "{run_dir}/extract.json"`.

#### 4.3 Output format (both paths)

Display `Picking the top-level modules...`. The snapshot lists candidates and names no module on purpose: a folder-name rule misreads `LICENSES`, `ci`, `web` or lodash's `lib/`. **Pick the Top-Level Modules from `{run_dir}/snapshot.json`** (Maven and Gradle aside: there the §4.1 script's `modules` array is the list):
- The snapshot's `workspaces`, when it lists some.
- Else the `module_candidates` that hold the library's own code: not a folder with no source file (`source_file_count` 0), nor one of tests, docs, examples, scripts, build tooling or CI.
- When one candidate holds most of the source files, it is the package itself (`pandas/` at the root of pandas): run the snapshot again for that folder, `uv run {detectWorkspacesHelper} --tree-file "{run_dir}/tree.json" --snapshot --root "<that folder>" > "{run_dir}/package-snapshot.json"`, and pick among its candidates.

The number of modules picked is `module_count`, which step 3 §2c passes the scope-type recommender (0 when none qualifies). Give each picked module a one-line description. The exports are the §4.1 script's `exports`, or the entry points §4.2 found.

#### 4.4 Semantic Signals (Forge+/Deep with ccc only)

**Remote source guard:** If the target source was resolved via GitHub API (remote URL, not a local file path), skip this CCC subsection — CCC requires a local source index and cannot operate on remote-only sources. Note: "CCC semantic discovery skipped — target is remote. CCC discovery will run automatically during create-skill after the source is cloned."

If `tools.ccc` is true in forge-tier.yaml, supplement the module listing with a semantic discovery pass:

**CCC Semantic Discovery:**
- **Claude Code:** Use `/ccc search "{repo_name} public API exports modules"` from `{source_path}` — the query is variadic, so a trailing path is swallowed into the search string rather than selecting a project
- **Cursor:** Use `ccc` MCP server `search` tool with query `"{repo_name} public API exports modules"` and path `{source_path}`
- **CLI fallback:** `cd {source_path} && ccc search --limit 10 "{repo_name} public API exports modules"` — `ccc search` reads the index in the current working directory and has no project-selector flag (`--path` is a file-path glob filter *within* the index)

See `knowledge/tool-resolution.md` for full bridge-to-tool mapping.

If results are returned, display:

"**Semantic Signals (ccc):**
{numbered list of file:snippet pairs from CCC results — top 5 most relevant}"

This supplements, and never replaces, the module list §4.3 picked. CCC may surface non-obvious entry points (dynamically constructed exports, re-export chains) that static directory analysis misses.

If CCC is unavailable or returns no results: skip this subsection silently.

### 4b. Detect Source Version

**When the language was script-supported (§4 took the script path):** the `version` field returned by `{extractPublicApiHelper}` IS the detected version — do not re-derive it and do not load `{versionResolutionFile}`. The script already implements the language-specific lookups documented in that reference, so loading the reference here only burns context.

**When the language was not script-supported:** load `{versionResolutionFile}` and follow the prose Detection Algorithm directly (Ruby / C# / Swift / etc. fall outside the script's coverage).

Whichever path produced it, keep the detected version for §5, which shows it beside `target_version`. The actual write happens in step 05.

### 5. Report Analysis Summary

Present the complete analysis, the counts and notable files read from `{run_dir}/snapshot.json`:

"**Analysis Complete**

---

**Target:** {repo URL or path}
{If §4.1 returned a `package_name`:}
**Package:** {package_name} ({the number of its `dependencies`} dependencies)
**Detected language:** {the detector's language} ({confidence}, {detection_source})
{If a `language_hint` or a ratified brief set the language:}
**Language:** {language} (kept over the detected one)
**Structure:** {file_count} files ({source_file_count} source files) across {dir_count} directories

**Key Modules ({module_count}):**
{bulleted list of the §4.3 modules, each with its one-line description}

**Public Exports/Entry Points ({count}):**
{bulleted list of the §4.3 exports}

**Version:** {on a ratify run, the hydrated `version`; otherwise:}
- Detected version: {the §4b version, or `not detected: defaulting to 1.0.0, which you can change when you confirm the brief` when detection failed or returned a non-semver value}
{If `target_version` was provided in step 01:}
- Target version: {target_version} (user-specified)
{If `target_version` was provided AND the detected version differs:}
- Note: the detected version ({detected_version}) differs from your target version ({target_version}). Using target version (per `references/version-resolution.md` precedence rules).

{If §4.1 returned `warnings`:}
**Extraction warnings:**
{one bullet per warning}

**Notable Files:**
- README: {a README file in `top_level_files`, or not found}
- Tests: {a tests folder in `top_level_dirs` (`test`, `tests`, `__tests__`, `spec`), or not found}
- Docs: {a docs folder in `top_level_dirs` (`docs`, `doc`, `documentation`), or not found}
- Config: {the configuration files in `top_level_files`}
{If the target was a GitHub URL:}
- Analysis ref: {analysis_ref} {append " (resolved from target_version {target_version})" when a tag was matched, or " (no tag matched {target_version} — analyzed default branch)" on the zero-match fallback}

Store `{analysis_ref}` and `module_count` in workflow context: step 03 (`scope-definition.md`) reuses them, with `{run_dir}/tree.json`, the fetched files and `{run_dir}/extract.json`, so scope analysis reads the same ref as this step.

---

{If language confidence is low:}
**Note:** Language detection confidence is low. You'll be able to override this in the next step.

Moving to scope definition where you'll choose what to include and exclude."

### 6. Proceed to Scope Definition

In the same turn as the §5 summary, load, read entire file, then execute {nextStepFile}: step 3 §1 asks whether anything in this analysis is wrong, and applies a correction before a scope decision relies on it.
