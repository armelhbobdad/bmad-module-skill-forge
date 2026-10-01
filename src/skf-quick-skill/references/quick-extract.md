---
nextStepFile: 'compile.md'
githubFetchProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-github-fetch.py'
  - '{project-root}/src/shared/scripts/skf-github-fetch.py'
skillsModuleProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-skills-module.py'
  - '{project-root}/src/shared/scripts/skf-skills-module.py'
publicApiExtractorProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-extract-public-api.py'
  - '{project-root}/src/shared/scripts/skf-extract-public-api.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 3: Quick Extract

## STEP GOAL:

To read the resolved GitHub repository source and extract the public API surface using surface-level source reading (no AST). Produces an extraction inventory of exports, descriptions, and manifest data for compilation.

## Rules

- Best-effort extraction — completeness is not required; surface-level reading only, no AST
- Do not begin compilation or write output files
- If no exports found, use README content as fallback
- A HARD HALT prints, after its envelope, this step's `halt` event when `{headless_mode}` is true. Under `--batch` it ends only this target: then return to `references/batch-mode.md` §3, even when the halt reads as the end of the run (`references/halt-contract.md`).

## Steps

**Reading the repository.** Step 1 §4 wrote the repository's file listing, at the ref this step reads (`source_ref`, or the default branch when it is unset), to `{run_dir}/tree.json`. Every file this step reads is fetched from that listing into `{run_dir}/src/`, laid out as in the repository, and the helpers read it there by path: no file's text passes through a shell string, and none is read by web browsing, which gives a rendered page rather than the file's bytes. Resolve `{githubFetch}` from `{githubFetchProbeOrder}`; first existing path wins. One call fetches every file a step names:

```bash
uv run {githubFetch} --repo {owner}/{repo} --ref {source_ref or HEAD} --tree-file "{run_dir}/tree.json" --dest "{run_dir}/src" [--limit <n>] [--exclude <glob>]... <path or glob>...
```

It reads each file from `raw.githubusercontent.com` at the ref, which needs no gh, and through `gh api` when that fails (a private repository). A path or glob the listing does not hold is reported in `unmatched` and costs no request, so name every candidate a step lists and use the ones it `fetched`. When the listing is `truncated` (GitHub cut a very large tree short), a path with no `*` or `?` that the listing lacks is read anyway, one request, and stays in `unmatched` when it cannot be read. On `status` `partial` or `unavailable` (exit 3), `failed` names each file it could not read: go on without them and say so in §5. If no `{githubFetch}` candidate exists, fetch each file the same way by hand: `gh api -H "Accept: application/vnd.github.raw" "repos/{owner}/{repo}/contents/<path>?ref={source_ref or HEAD}" > "{run_dir}/src/<path>"`, creating its folder first.

### 1. Read the Listing and README

Clear the extraction files an earlier attempt of this step left first (§4.5 [R] and step 4's [S] run this step again under a new scope, and step 4 passes the files it finds), so no export, package name or version of the old scope reaches `metadata.json`:

```bash
rm -f "{run_dir}"/extract*.json
```

Fetch the root `package.json` (the sniff below reads it; nothing is fetched when the listing has none), then sniff the listing, which §1.5 classifies from. Resolve `{skillsModuleHelper}` from `{skillsModuleProbeOrder}`; first existing path wins:

```bash
uv run {githubFetch} --repo {owner}/{repo} --ref {source_ref or HEAD} --tree-file "{run_dir}/tree.json" --dest "{run_dir}/src" package.json
uv run {skillsModuleHelper} sniff --tree-file "{run_dir}/tree.json" --package-json "{run_dir}/src/package.json" [--scope-hint "{scope_hint}"] --fetch-list "{run_dir}/skills-fetch.txt" > "{run_dir}/sniff.json"
```

Pass `--scope-hint` when `scope_hint` is set. Then fetch the README that `{run_dir}/sniff.json` names in `readme` with the same fetch call (`README.md`, or another root `README` file), and read it from `{run_dir}/src/`. If no `{skillsModuleHelper}` candidate exists (an incomplete install), fetch `README.md` instead, and §1.5 classifies from the README alone, never as a skills module.

Extract:
- **Description:** What the package does (first paragraph or tagline)
- **Features:** Key features or capabilities listed
- **Usage patterns:** Code examples showing common usage
- **Installation:** Package manager install command (confirms package name)

If `readme` is null or the README could not be fetched, note and continue.

### 1.5. Repo-Shape Sniff

Quick-skill wraps a library: classify the repo shape before spending effort on extraction.

The signals are the README and `{run_dir}/sniff.json`, which `{skillsModuleHelper}` computed from the whole listing: `root_files` (the files at the repository root), `skills_module` with its `skills_root`, `module_root` and `skill_folders`, the `candidates` it weighed, `suggested_scope`, and `asset_dirs` with `asset_dir_count`. It applies the skills-module rules: a skill folder holds its own `SKILL.md`; a folder that directly holds `module.yaml` or `module-help.csv` (not a copy inside a skill folder) is a module root, whose skill folders sit at any depth below it; when `scope_hint` is set it is the only candidate; and a top-level folder of skill folders counts only when it is a module root or the root ships no code. Read its answer; do not re-derive it from the listing.

**Classify as one of:**

- **skills-module**: `skills_module` is true: the repository ships agent skills rather than code, in the skill folders of `skills_root`. Skill folders alone qualify (a plain Agent Skills package), and a `module-help.csv` adds menu codes. The shape is library-like: record `repo_shape: skills-module` and `skills_root` in the extraction inventory, proceed with no gate, and follow the skills-module branch of §2 and §3. A library with a manifest and one `skill/SKILL.md` stays a library: the helper gives it `skills_module: false`.
- **library** (default) — README has installation / usage / API content; manifest at root with publishable metadata. Proceed normally.
- **awesome-list** — README H1 contains "awesome" (case-insensitive) or `awesome-` is in the repo name; README body is dominated by curated bullet links of the form `- [name](url) — desc`; no manifest at root.
- **docs-site / website** — README is short (under ~50 non-empty lines) and primarily points elsewhere ("See https://… for docs"); root has no manifest, or only a docs-framework manifest (e.g. `docusaurus.config.js`, `astro.config.mjs`, `mkdocs.yml`).
- **examples-only / tutorial** — README explicitly labels the repo as examples or a tutorial ("Code examples for…", "Tutorial: …", "Learn X by building Y"); typically no published package; many small standalone files instead of a single API surface.

**If an awesome-list, docs-site or examples-only shape is detected**, soft-warn and gate before continuing:

"**Heads up — `{repo_name}` looks like a `{shape}` repo, not a library.**

Quick-skill is designed to wrap a library's public API. The compiled SKILL.md will likely have a thin Description and an empty Key Exports list. You can continue anyway, or abort and pick a target library.

Select: [C] Continue anyway · [A] Abort"

- **IF C**: log "user accepted `{shape}` shape" and proceed to §2. Set `extraction_inventory.repo_shape` to the detected shape, `awesome-list`, `docs-site` or `examples-only`.
- **IF A**: HARD HALT with **exit code 3 (resolution-failure)**: "Aborted. `{shape}` repos are best wrapped manually with `/skf-create-skill` from a brief, not auto-extracted." Stage `{"phase": "quick-extract", "halt_reason": "resolution-failure", "reason": "Aborted: a {shape} repo, not a library.", "skill_package": null, "details": {"repo_shape": "{shape}"}}` as `{run_dir}/halt.json` and run `uv run {emitEnvelopeHelper} emit-halt --workflow skf-quick-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"` (`references/halt-contract.md`).

**GATE [default: C]**: in headless mode, log "headless: detected `{shape}` repo, continuing anyway", set `extraction_inventory.repo_shape` as [C] does, record the decision (stage `{"gate": "quick-extract.repo-shape", "default_action": "C", "taken_action": "C", "reason": "headless: continued with a {shape} repo"}` as `{run_dir}/decision.json` and run `uv run {emitEnvelopeHelper} record --workflow skf-quick-skill --run-dir "{run_dir}" --decision < "{run_dir}/decision.json"`) and proceed.

### 2. Fetch Source Files

Fetch the manifest file and the top-level entry-point file(s) for the detected language with the fetch call above: the manifest first (§1 already fetched a root `package.json`), then the entry points, whose candidates are patterns for the same call. Name every candidate the row lists; the listing decides which exist.

| Language | Manifest | Entry-point patterns (quick mode) |
| --- | --- | --- |
| JavaScript / TypeScript | `package.json` | `index.js` `index.ts` `src/index.ts` `src/index.js`, and the file the `main` field names |
| Python | `pyproject.toml` or `setup.py` | `__init__.py` `{package}/__init__.py` `src/{package}/__init__.py` |
| Rust | `Cargo.toml` | `src/lib.rs` |
| Go | `go.mod` | `'*.go'` with `--limit 5 --exclude '*_test.go'` |
| Java (Maven) | `pom.xml` | `'src/main/java/<groupId-as-path>/*.java'` with `--limit 5` |
| Kotlin (Gradle) | `build.gradle.kts` or `build.gradle` | `'src/main/kotlin/**/*.kt'` with `--limit 5`; also fetch `settings.gradle` or `settings.gradle.kts` for `include(...)` entries when present |

**If `scope_hint` provided:** put `{scope_hint}/` before each entry-point pattern, and fetch the manifest there too when the listing holds one, so extraction reads the scoped folder instead of the repo root.

For multi-module Maven (`<modules>`) and multi-project Gradle (`include(...)`) builds, fetch the parent manifest first: §3's multi-module loop fetches the modules.

**Skills module** (`repo_shape: skills-module`): fetch no entry-point files. Fetch the manifest from the table when the root has one and §1 did not fetch it, and the files the sniff listed in `{run_dir}/skills-fetch.txt`, each skill folder's `SKILL.md` and then the `module-help.csv` directly in the skills root (`<skills root>/module-help.csv`) when the listing shows one:

```bash
uv run {githubFetch} --repo {owner}/{repo} --ref {source_ref or HEAD} --tree-file "{run_dir}/tree.json" --dest "{run_dir}/src" --patterns-file "{run_dir}/skills-fetch.txt"
```

### 3. Parse Manifest and Scan Exports

Run the shared extractor on the files §2 staged. The helper does manifest parse + export scan in one invocation, reads each file from `{run_dir}/src/` by its repo-relative path, and writes a structured envelope ready to feed §4's inventory.

**Resolve `{publicApiExtractor}`** from `{publicApiExtractorProbeOrder}`; first existing path wins. If no candidate exists, fall back to in-prompt per-language regex parsing of the manifest and entry-point files, and stage what it finds as `{run_dir}/extract.json` through a quoted heredoc, in the shape of the empty envelope below with its fields filled in, so step 4's renderer reads it as it reads the helper's output.

```bash
uv run {publicApiExtractor} --mode quick --language <lang> --source-root "{run_dir}/src" --manifest-file <manifest path> --entry-file <entry path> [--entry-file <entry path>]... > "{run_dir}/extract.json"
```

Where `<lang>` is one of `js`, `ts`, `javascript`, `typescript`, `python`, `rust`, `go`, `java`, `kotlin`. Pass the manifest and each entry point §2 `fetched`, by its path in the repository: one `--entry-file` per entry point, and no `--manifest-file` when §2 fetched no manifest. The helper aggregates exports across every entry.

**When §2 fetched neither a manifest nor an entry point** (the listing holds no candidate, the language has no row in §2's table, or the fetch read none of them), do not run the extractor: it needs at least one file. Stage the empty envelope instead, so §4 builds an inventory with no exports and §4.5 decides what follows:

```bash
cat > "{run_dir}/extract.json" <<'SKF_JSON'
{"language": "{language}", "package_name": null, "version": null, "description": null, "exports": [], "dependencies": [], "modules": [], "warnings": ["no source file was fetched"]}
SKF_JSON
```

Stage it the same way when the extractor exits non-zero, which leaves `{run_dir}/extract.json` empty, with its error line in place of `no source file was fetched` (a JSON string, any `"` or `\` escaped).

The helper writes JSON to `{run_dir}/extract.json` with:

- `package_name`, `version`, `description`: parsed from the manifest
- `exports[]`: `{name, type, source_file}` per discovered top-level public symbol
- `dependencies[]`: declared direct dependencies
- `modules[]`: for Maven `<modules>` and Gradle `include(...)`, the names of sub-modules to iterate
- `extra`: language-specific extras (e.g. `group_id` for Maven)
- `warnings[]`: manifest parse failures and scanner errors (advisory only; the envelope is still valid), and each statement whose names the entry file alone cannot give: `export * from`, a star import from the package, an `__all__` built from another module, `pub use x::*`, `module.exports = require(...)`, or an anonymous or conditional export. Each names its file, line and statement.

Read `{run_dir}/extract.json` into the extraction context. The shape of the envelope is the same for every language; §4 builds the inventory from it without per-language branching.

**Act on the statements a warning names** before §4. When the module such a statement names is in the listing (resolve the relative specifier the way the language does: `./core` is `core.ts`, `core/index.ts` and the like beside the entry file, `.mod` is `mod.py` or `mod/__init__.py`), fetch it with §2's call and run the extractor again with it as one more `--entry-file`, writing over `{run_dir}/extract.json`. Otherwise read the statement by eye, from the README's API section or the module's documentation, and list the names it adds: stage them through a quoted heredoc as `{run_dir}/extract-added.json`, `{"exports": [{"name": "<name>", "type": "re-export", "source_file": "<the warning's file>"}]}`, which step 4 §4 passes with the other extraction files. Leave the other warnings for §5.

**Multi-module loop:** when `modules[]` is non-empty, fetch every sub-module's manifest and entry-point patterns in one §2 call (each module's patterns under its folder) and run the helper per module (§3), writing each to `{run_dir}/extract-module-<n>.json`, `<n>` counting from 1 in `modules[]` order (a module is a path such as `modules/core` or a Gradle name such as `core:api`, so it never names the file). Step 4 §4 passes `{run_dir}/extract.json` (the parent manifest, which names the `package_name`) first and then each module's file in that order, and the renderer aggregates `exports[]` and `dependencies[]` across them.

**Skills module** (`repo_shape: skills-module`): when §2 fetched a manifest, run the helper as above with that `--manifest-file` and no `--entry-file`, writing `{run_dir}/extract-manifest.json`. It still reads `package_name`, `version`, `description` and `dependencies`, and returns no exports. Then build the module's envelope from the staged `SKILL.md` files and `module-help.csv`:

```bash
uv run {skillsModuleHelper} extract --sniff "{run_dir}/sniff.json" --source-root "{run_dir}/src" [--package "{run_dir}/extract-manifest.json"] --name {repo_name} > "{run_dir}/extract.json"
```

Pass `--package` only when that file exists; without it `package_name` is `{repo_name}`. Read the `exports[]` it lists: one `skill` per skill folder in the sniff's order, named by its frontmatter `name` (the folder name when it has none) with its `description`, then one `menu-code` per `module-help.csv` row that has a menu code, in file order. Its `usage_patterns[]` give §4 one usage pattern per `module-help.csv` row (the `_meta` row and rows with no skill left out), and its `confidence` is the module's. Do not read the `SKILL.md` files or the CSV yourself: the helper parses them.

### 4. Build Extraction Inventory

Assemble the extraction inventory from collected data:

```
extraction_inventory:
  description: {from README or manifest}
  package_name: {from manifest}
  version: {from manifest}
  language: {detected}
  repo_shape: {the §1.5 shape, when one was recorded}
  skills_root: {skills-module only: the folder that holds the skill folders}
  exports: [{name, type, brief_description}]
  usage_patterns: [{pattern from README examples, or the skills-module helper's usage_patterns}]
  dependencies: [{key deps from manifest}]
  confidence: {high/medium/low based on data quality}
```

For a skills module, confidence is the helper's `confidence`: `high` when every skill folder's frontmatter gave a `name` and a `description`, else `medium`.

**If no exports found:**
- Set confidence to `low`
- Use README description and features as fallback content
- Note: "No exports detected: SKILL.md will be based on README content only"
- If the sniff's `suggested_scope` is set (a folder below the repository root holds skill folders), add to the note: "`{suggested_scope}` holds skill folders: re-run with `--scope-hint {suggested_scope}` (a batch line's `scope={suggested_scope}`) to document them as a skills module." The helper names the module root with the most skill folders or, when the listing shows no module root, the folder with the most.

### 4.5. Zero-Exports Soft Gate (rescue mode)

Run this gate **only when** `extraction_inventory.exports.length == 0` and `extraction_inventory.description` is empty (no usable README content either). When either is non-empty, the README-fallback in §4 produces a usable skill and this section is skipped.

Offer the user a chance to retry with hints before producing a degenerate output:

"**Extraction yielded zero exports and no README description.**

The compiled SKILL.md would be effectively empty — no API surface to document and no description to fall back on.

Common causes:
- Wrong scope (extraction read the repo root, but the public API lives in a subdir)
- Wrong language (manifest probe picked the test/build language, not the lib language)
- Repo lays out exports unconventionally (e.g., not in `src/index.*` or `lib.rs`)

Select: [R] Retry with new hints · [P] Proceed anyway (low-confidence skill) · [A] Abort"

- **IF R**: prompt for new `scope_hint` ("New scope hint (e.g. `src/server/`):") and optional new `language_hint` ("New language hint (or empty to keep `{language}`):"). A non-empty new language hint sets `language` to it, `language_resolution` to `hint` and `detected_languages` to `[]`, as step 1 §4 does for a hint, so the result contract reports where the language came from. Update the extraction context with the new hints, then **re-execute step 3 from §1** with the new values: §1 sniffs the same `{run_dir}/tree.json` again under the new scope. Discards the prior empty inventory.
- **IF P**: log "user accepted zero-exports outcome" and proceed to §5. The compiled skill will be README-content-only with confidence `low`. Record `zero_exports_rescue: "user-accepted"` in the inventory so the result contract summary surfaces it.
- **IF A**: HARD HALT with **exit code 3 (resolution-failure)**: "Aborted. Run `/skf-create-skill` from a brief if you want a guided extraction with provenance tracking." Stage `{"phase": "quick-extract", "halt_reason": "resolution-failure", "reason": "Aborted: zero exports and no README description.", "skill_package": null, "details": {"exports_found": 0, "description_empty": true, "language": "{language}", "scope": "{scope_hint or 'entire repo'}"}}` as `{run_dir}/halt.json` and run `uv run {emitEnvelopeHelper} emit-halt --workflow skf-quick-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"`.

**GATE [default: P]**: in headless mode, log "headless: zero exports + empty description, proceeding with low-confidence skill", record `zero_exports_rescue: "auto-proceeded"` in the inventory so the result contract summary lets automators re-run these targets with stricter hints (`--scope-hint` or `--language-hint`, or a batch line's `scope=` or `language=`), record the decision (stage `{"gate": "quick-extract.zero-exports", "default_action": "P", "taken_action": "P", "reason": "headless: compiled a low-confidence skill"}` as `{run_dir}/decision.json` and run `uv run {emitEnvelopeHelper} record --workflow skf-quick-skill --run-dir "{run_dir}" --decision < "{run_dir}/decision.json"`) and proceed.

### 5. Report Extraction Summary

"**Extraction complete:**

- **Package:** {package_name} v{version}
- **Language:** {language}
{If `repo_shape` was recorded, add:} - **Repo shape:** {repo_shape} (for `skills-module`: {skill count} skills and {menu code count} menu codes in `{skills_root}`)
- **Exports found:** {count}
- **Confidence:** {confidence}
- **Source files read:** {count} (the files §1 to §3 fetched; name each one the fetch could not read)
{If the fetch output's `truncated` was true, add:} - **Listing:** truncated by GitHub (a very large tree), so a file a glob names may have been missed

**Proceeding to compilation...**"

### 6. Auto-Proceed to Compilation

Once extraction_inventory is assembled (even if minimal or low-confidence), load and execute {nextStepFile} to compile; when `{headless_mode}` is true, print this step's `done` event and step 4's `start` event first (`references/halt-contract.md`).

