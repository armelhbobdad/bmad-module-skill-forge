---
nextStepFile: 'compile.md'
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

**Ref-aware source reading:** When `source_ref` is set from tag resolution (see step 1), append `?ref={source_ref}` to all GitHub API content and tree requests (e.g., `gh api repos/{owner}/{repo}/contents/{path}?ref={source_ref}`) to read from the tagged version. When using web browsing, use the tagged URL format (e.g., `github.com/{owner}/{repo}/blob/{source_ref}/{path}`). This ensures extraction reads from the same source version resolved during tag resolution.

**Parallel-fetch directive:** §1 (README), §2 (manifest), and §3 (entry-point exports) read independent files from the same `?ref={source_ref}` and are safe to issue as one batched tool-call message rather than three sequential round trips. For multi-module Maven (`<modules>`) and multi-project Gradle (`include(...)`) builds, also fetch all submodule `pom.xml` / `build.gradle[.kts]` files in parallel rather than serially per module — N module fetches collapse to O(1) wall-clock time.

### 1. Read README

Read `README.md` from the repository root via web browsing.

Extract:
- **Description:** What the package does (first paragraph or tagline)
- **Features:** Key features or capabilities listed
- **Usage patterns:** Code examples showing common usage
- **Installation:** Package manager install command (confirms package name)

If README is unavailable, note and continue.

### 1.5. Repo-Shape Sniff

After the README has loaded, classify the repo shape from the available signals before committing further effort to extraction. Quick-skill is designed to wrap a library; non-library repos sail through silently today and produce low-quality skills the user only notices via the description field after compilation.

The signals are the README and one filtered listing of the repository tree: every root-level file, and every `SKILL.md`, `module.yaml` and `module-help.csv` at any depth.

```bash
gh api "repos/{owner}/{repo}/git/trees/{source_ref or HEAD}?recursive=1" \
  --jq '.tree[] | select(.type == "blob") | .path | select((contains("/") | not) or test("(^|/)(SKILL\\.md|module\\.yaml|module-help\\.csv)$"))'
```

**Classify as one of:**

- **skills-module**: the repository ships agent skills rather than code. Skill folders alone qualify (a plain Agent Skills package), and a `module-help.csv` adds menu codes. The shape is library-like: record `repo_shape: skills-module` and `skills_root` in the extraction inventory, proceed with no gate, and follow the skills-module branch of §2 and §3. Find the skills root in the listing:
  - A skill folder holds its own `SKILL.md`. A module root is a folder that directly holds `module.yaml` or `module-help.csv`: the listing shows `<folder>/module.yaml` or `<folder>/module-help.csv` (the bare name at the repository root). A copy that sits in a skill folder, such as a skill's `assets/module.yaml`, makes no module root.
  - The skill folders of a module root are all the folders below it that hold a `SKILL.md` and sit in no other skill folder. The skill folders of any other folder are its direct subfolders that hold one (`<folder>/<name>/SKILL.md`).
  - When `scope_hint` is set, it is the only candidate, and it counts whenever it has skill folders. Otherwise the candidates are the repository root and each top-level folder that has skill folders, and a candidate counts only when it is a module root or the root ships no code. The root ships no code when it has no package manifest (one from the §2 table, or another such as `setup.cfg` or `Gemfile`), or when its only one is a `package.json` that declares no `main` (or an empty one), `exports`, `bin` or `workspaces` and has no `index.js` or `index.ts` beside it. Fetch that `package.json` when the check needs it; §2 reuses it. So a library with a manifest and one `skill/SKILL.md` stays a library.
  - When several candidates count, prefer a module root, then the one with the most skill folders.
- **library** (default) — README has installation / usage / API content; manifest at root with publishable metadata. Proceed normally.
- **awesome-list** — README H1 contains "awesome" (case-insensitive) or `awesome-` is in the repo name; README body is dominated by curated bullet links of the form `- [name](url) — desc`; no manifest at root.
- **docs-site / website** — README is short (under ~50 non-empty lines) and primarily points elsewhere ("See https://… for docs"); root has no manifest, or only a docs-framework manifest (e.g. `docusaurus.config.js`, `astro.config.mjs`, `mkdocs.yml`).
- **examples-only / tutorial** — README explicitly labels the repo as examples or a tutorial ("Code examples for…", "Tutorial: …", "Learn X by building Y"); typically no published package; many small standalone files instead of a single API surface.

**If an awesome-list, docs-site or examples-only shape is detected**, soft-warn and gate before continuing:

"**Heads up — `{repo_name}` looks like a `{shape}` repo, not a library.**

Quick-skill is designed to wrap a library's public API. The compiled SKILL.md will likely have a thin Description and an empty Key Exports list. You can continue anyway, or abort and pick a target library.

Select: [C] Continue anyway · [A] Abort"

- **IF C**: log "user accepted `{shape}` shape" and proceed to §2. Set `extraction_inventory.repo_shape` to the detected shape, `awesome-list`, `docs-site` or `examples-only`, so the result contract carries the signal for automators.
- **IF A**: HARD HALT with **exit code 3 (resolution-failure)**: "Aborted. `{shape}` repos are best wrapped manually with `/skf-create-skill` from a brief, not auto-extracted." Stage `{"phase": "quick-extract", "halt_reason": "resolution-failure", "reason": "Aborted: a {shape} repo, not a library.", "skill_package": null, "error": {"code": "resolution-failure", "message": "Aborted: a {shape} repo, not a library.", "details": {"repo_shape": "{shape}"}}}` as `{run_dir}/halt.json` and run `uv run {emitEnvelopeHelper} emit-halt --workflow skf-quick-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"` (`references/halt-contract.md`).

**GATE [default: C]**: in headless mode, log "headless: detected `{shape}` repo, continuing anyway", set `extraction_inventory.repo_shape` as [C] does, record the decision (stage `{"gate": "quick-extract.repo-shape", "default_action": "C", "taken_action": "C", "reason": "headless: continued with a {shape} repo"}` as `{run_dir}/decision.json` and run `uv run {emitEnvelopeHelper} record --workflow skf-quick-skill --run-dir "{run_dir}" --decision < "{run_dir}/decision.json"`) and proceed; the result contract's `summary.repo_shape` carries the signal so automators can flag low-quality outputs without re-parsing logs.

### 2. Fetch Source Files

Fetch the manifest file and the top-level entry-point file(s) for the detected language. The helper invoked in §3 does pure parsing — no I/O — so this step does the fetch work using `gh api` (preferred when source_ref is set) or web browsing.

| Language | Manifest | Entry-point files (quick mode) |
| --- | --- | --- |
| JavaScript / TypeScript | `package.json` | `index.{js,ts}`, `src/index.{ts,js}`, or the file pointed to by the `main` field |
| Python | `pyproject.toml` or `setup.py` | `__init__.py`, `src/{package}/__init__.py` |
| Rust | `Cargo.toml` | `src/lib.rs` |
| Go | `go.mod` | top-level `*.go` files (3–5 best-effort) |
| Java (Maven) | `pom.xml` | top-level `*.java` files under `src/main/java/<groupId-as-path>/` (3–5 best-effort) |
| Kotlin (Gradle) | `build.gradle.kts` or `build.gradle` | top-level `*.kt` files under `src/main/kotlin/` (3–5 best-effort); also fetch `settings.gradle[.kts]` for `include(...)` entries when present |

**If `scope_hint` provided:** focus the entry-point fetch on the specified directories instead of repo root.

For multi-module Maven (`<modules>`) and multi-project Gradle (`include(...)`) builds, fetch the parent manifest first, then loop §2+§3 per module. Batch the sub-module fetches per the parallel-fetch directive at the top of this step.

**Skills module** (`repo_shape: skills-module`): fetch no entry-point files. In one batched tool-call message, fetch the manifest from the table when the root has one and §1.5 did not fetch it, the `module-help.csv` directly in the skills root (`<skills root>/module-help.csv`) when the listing shows one, and the frontmatter of the `SKILL.md` in every skill folder of the skills root. One loop prints each frontmatter under a `=== <folder>` line and leaves the bodies out, so a module with many skills stays small:

```bash
for dir in <each skill folder path §1.5 found, e.g. skills/bmad-agent-builder or src/workflows/testarch/bmad-testarch-atdd>; do
  printf '=== %s\n' "$dir"
  gh api -H "Accept: application/vnd.github.raw" "repos/{owner}/{repo}/contents/$dir/SKILL.md?ref={source_ref}" \
    | awk '{ sub(/\r$/, "") } NR == 1 { if ($0 != "---") exit; next } $0 == "---" { exit } { print }'
done
```

Fetch `module-help.csv` whole, with the same `gh api -H "Accept: application/vnd.github.raw"` call on its path. Drop `?ref={source_ref}` when `source_ref` is unset.

### 3. Parse Manifest and Scan Exports

Run the shared extractor against the contents fetched in §2. The helper does manifest parse + export scan in one invocation and emits a structured envelope ready to feed §4's inventory.

**Resolve `{publicApiExtractor}`** from `{publicApiExtractorProbeOrder}`; first existing path wins. If no candidate exists, fall back to in-prompt per-language regex parsing of the manifest and entry-point files.

Build the input payload from §2's fetched files and pipe it to the helper:

```bash
echo '{"language":"<lang>","manifest":{"path":"<rel>","content":"<...>"},"entries":[{"path":"<rel>","content":"<...>"},...],"mode":"quick"}' \
  | python3 {publicApiExtractor} --mode quick
```

Where `<lang>` is one of `js`, `ts`, `javascript`, `typescript`, `python`, `rust`, `go`, `java`, `kotlin`. The helper accepts arbitrarily many `entries` items and aggregates exports across them.

The helper emits JSON on stdout with:

- `package_name`, `version`, `description` — parsed from the manifest
- `exports[]` — `{name, type, source_file}` per discovered top-level public symbol
- `dependencies[]` — declared direct dependencies
- `modules[]` — for Maven `<modules>` and Gradle `include(...)`, the names of sub-modules to iterate (loop §2+§3 per entry)
- `extra` — language-specific extras (e.g. `group_id` for Maven)
- `warnings[]` — manifest parse failures or scanner errors (advisory only; the envelope is still valid)

Capture the helper's output into the extraction context. The shape of the envelope is the same for every language; §4 builds the inventory from it without per-language branching.

**Multi-module loop:** when `modules[]` is non-empty, fetch each sub-module's manifest + entry-point files (§2) and re-invoke the helper per module (§3), aggregating `exports[]` across all module envelopes. The aggregated `exports[]`, `dependencies[]`, and a single resolved `package_name` (from the parent manifest) feed §4.

**Skills module** (`repo_shape: skills-module`): when §2 fetched a manifest, run the helper as above with `"entries": []`. It still reads `package_name`, `version`, `description` and `dependencies`, and returns no exports. With no manifest, skip the helper and take `{repo_name}` as `package_name`. Then build `exports[]` from the skills root, reading each frontmatter as YAML and `module-help.csv` by its header names:

- One `{name, type: "skill", brief_description}` per skill folder, in listing order: `name` from the frontmatter `name` (the folder name when it has none), `brief_description` from its `description`.
- Then one `{name, type: "menu-code", brief_description}` per `module-help.csv` row that has a `menu-code`, in file order: `name` is the code, and `brief_description` is the row's `description`, followed by its `display-name` and the `skill` it runs, with the row's `action` when set.

Skip the rows whose `skill` is empty or starts with `_` (the `_meta` row). Every other row also gives §4 a usage pattern: its menu code, display name and `description`, the skill and action it runs, its `args`, and its `preceded-by` and `followed-by` entries when set.

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
  usage_patterns: [{pattern from README examples, or from the module-help.csv rows of a skills module}]
  dependencies: [{key deps from manifest}]
  confidence: {high/medium/low based on data quality}
```

For a skills module, confidence is `high` when every skill folder's frontmatter gave a `name` and a `description`, else `medium`.

**If no exports found:**
- Set confidence to `low`
- Use README description and features as fallback content
- Note: "No exports detected — SKILL.md will be based on README content only"
- If a folder below the repository root has skill folders (as §1.5 defines them), add to the note: "`{folder}` holds skill folders: re-run with `scope={folder}` to document them as a skills module." Name the module root with the most skill folders or, when the listing shows no module root, the folder with the most.

### 4.5. Zero-Exports Soft Gate (rescue mode)

Run this gate **only when** `extraction_inventory.exports.length == 0` and `extraction_inventory.description` is empty (no usable README content either). When either is non-empty, the README-fallback in §4 produces a usable skill and this section is skipped.

When both are empty, the compiled SKILL.md would be effectively empty — no API surface to document and no description to fall back on. Offer the user a chance to retry with hints before producing a degenerate output:

"**Extraction yielded zero exports and no README description.**

The compiled SKILL.md would be effectively empty — no API surface to document and no description to fall back on.

Common causes:
- Wrong scope (extraction read the repo root, but the public API lives in a subdir)
- Wrong language (manifest probe picked the test/build language, not the lib language)
- Repo lays out exports unconventionally (e.g., not in `src/index.*` or `lib.rs`)

Select: [R] Retry with new hints · [P] Proceed anyway (low-confidence skill) · [A] Abort"

- **IF R** — prompt for new `scope_hint` ("New scope hint (e.g. `src/server/`):") and optional new `language_hint` ("New language hint (or empty to keep `{language}`):"). Update the extraction context with the new hints, then **re-execute step 3 from §1** with the new values. Discards the prior empty inventory.
- **IF P**: log "user accepted zero-exports outcome" and proceed to §5. The compiled skill will be README-content-only with confidence `low`. Record `zero_exports_rescue: "user-accepted"` in the inventory so the result contract summary surfaces it.
- **IF A**: HARD HALT with **exit code 3 (resolution-failure)**: "Aborted. Run `/skf-create-skill` from a brief if you want a guided extraction with provenance tracking." Stage `{"phase": "quick-extract", "halt_reason": "resolution-failure", "reason": "Aborted: zero exports and no README description.", "skill_package": null, "error": {"code": "resolution-failure", "message": "Aborted: zero exports and no README description.", "details": {"exports_found": 0, "description_empty": true, "language": "{language}", "scope": "{scope_hint or 'entire repo'}"}}}` as `{run_dir}/halt.json` and run `uv run {emitEnvelopeHelper} emit-halt --workflow skf-quick-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"`.

**GATE [default: P]**: in headless mode, log "headless: zero exports + empty description, proceeding with low-confidence skill", record `zero_exports_rescue: "auto-proceeded"` in the inventory so the result contract summary lets batch automators re-queue these targets with stricter hints, record the decision (stage `{"gate": "quick-extract.zero-exports", "default_action": "P", "taken_action": "P", "reason": "headless: compiled a low-confidence skill"}` as `{run_dir}/decision.json` and run `uv run {emitEnvelopeHelper} record --workflow skf-quick-skill --run-dir "{run_dir}" --decision < "{run_dir}/decision.json"`) and proceed. [P] preserves the pre-rescue behaviour for unattended pipelines.

### 5. Report Extraction Summary

"**Extraction complete:**

- **Package:** {package_name} v{version}
- **Language:** {language}
{If `repo_shape` was recorded, add:} - **Repo shape:** {repo_shape} (for `skills-module`: {skill count} skills and {menu code count} menu codes in `{skills_root}`)
- **Exports found:** {count}
- **Confidence:** {confidence}
- **Source files read:** {count}

**Proceeding to compilation...**"

### 6. Auto-Proceed to Compilation

Once extraction_inventory is assembled (even if minimal or low-confidence), load and execute {nextStepFile} to compile; when `{headless_mode}` is true, print this step's `done` event and step 4's `start` event first (`references/halt-contract.md`).

