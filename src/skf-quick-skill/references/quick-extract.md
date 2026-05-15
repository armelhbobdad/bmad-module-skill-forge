---
nextStepFile: 'compile.md'
publicApiExtractorProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-extract-public-api.py'
  - '{project-root}/src/shared/scripts/skf-extract-public-api.py'
---

# Step 3: Quick Extract

Communicate with the user in `{communication_language}`.

## STEP GOAL:

To read the resolved GitHub repository source and extract the public API surface using surface-level source reading (no AST). Produces an extraction inventory of exports, descriptions, and manifest data for compilation.

## Rules

- Best-effort extraction — completeness is not required; surface-level reading only, no AST
- Do not begin compilation or write output files
- If no exports found, use README content as fallback

## MANDATORY SEQUENCE

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

**Classify as one of:**

- **library** (default) — README has installation / usage / API content; manifest at root with publishable metadata. Proceed normally.
- **awesome-list** — README H1 contains "awesome" (case-insensitive) or `awesome-` is in the repo name; README body is dominated by curated bullet links of the form `- [name](url) — desc`; no manifest at root.
- **docs-site / website** — README is short (under ~50 non-empty lines) and primarily points elsewhere ("See https://… for docs"); root has no manifest, or only a docs-framework manifest (e.g. `docusaurus.config.js`, `astro.config.mjs`, `mkdocs.yml`).
- **examples-only / tutorial** — README explicitly labels the repo as examples or a tutorial ("Code examples for…", "Tutorial: …", "Learn X by building Y"); typically no published package; many small standalone files instead of a single API surface.

**If a non-library shape is detected** — soft-warn and gate before continuing:

"**Heads up — `{repo_name}` looks like a `{shape}` repo, not a library.**

Quick-skill is designed to wrap a library's public API. The compiled SKILL.md will likely have a thin Description and an empty Key Exports list. You can continue anyway, or abort and pick a target library.

Select: [C] Continue anyway · [A] Abort"

- **IF C** — log "user accepted `{shape}` shape" and proceed to §2. Set `extraction_inventory.repo_shape` to the detected shape so the result contract carries the signal for automators.
- **IF A** — HARD HALT with **exit code 3 (resolution-failure)** per the SKILL.md exit-code map: "Aborted. `{shape}` repos are best wrapped manually with `/skf-create-skill` from a brief, not auto-extracted." Before exiting, emit the error result contract per SKILL.md "Result Contract on HARD HALT" (`phase: "quick-extract"`, `error.code: "resolution-failure"`, `error.details: {repo_shape: "{shape}"}`, `skill_package: null`).

**GATE [default: C]** — In headless mode, log "headless: detected `{shape}` repo, continuing anyway" and proceed; the result contract's `summary.repo_shape` carries the signal so automators can flag low-quality outputs without re-parsing logs.

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

For multi-module Maven (`<modules>`) and multi-project Gradle (`include(...)`) builds, fetch the parent manifest first, then loop §2+§3 per module. Sub-module fetches are safe to issue as one batched tool-call message — N module fetches collapse to O(1) wall-clock time.

### 3. Parse Manifest and Scan Exports

Run the shared extractor against the contents fetched in §2. The helper does manifest parse + export scan in one invocation and emits a structured envelope ready to feed §4's inventory.

**Resolve `{publicApiExtractor}`** from `{publicApiExtractorProbeOrder}`; first existing path wins. If no candidate exists, fall back to in-prompt parsing (the legacy per-language regex tables that this section replaces).

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

### 4. Build Extraction Inventory

Assemble the extraction inventory from collected data:

```
extraction_inventory:
  description: {from README or manifest}
  package_name: {from manifest}
  version: {from manifest}
  language: {detected}
  exports: [{name, type, brief_description}]
  usage_patterns: [{pattern from README examples}]
  dependencies: [{key deps from manifest}]
  confidence: {high/medium/low based on data quality}
```

**If no exports found:**
- Set confidence to `low`
- Use README description and features as fallback content
- Note: "No exports detected — SKILL.md will be based on README content only"

### 4.5. Zero-Exports Soft Gate (rescue mode)

Run this gate **only when** `extraction_inventory.exports.length == 0` AND `extraction_inventory.description` is empty (no usable README content either). When either is non-empty, the README-fallback in §4 produces a usable skill and this section is skipped.

When both are empty, the compiled SKILL.md would be effectively empty — no API surface to document and no description to fall back on. Offer the user a chance to retry with hints before producing a degenerate output:

"**Extraction yielded zero exports and no README description.**

The compiled SKILL.md would be effectively empty — no API surface to document and no description to fall back on.

Common causes:
- Wrong scope (extraction read the repo root, but the public API lives in a subdir)
- Wrong language (manifest probe picked the test/build language, not the lib language)
- Repo lays out exports unconventionally (e.g., not in `src/index.*` or `lib.rs`)

Select: [R] Retry with new hints · [P] Proceed anyway (low-confidence skill) · [A] Abort"

- **IF R** — prompt for new `scope_hint` ("New scope hint (e.g. `src/server/`):") and optional new `language_hint` ("New language hint (or empty to keep `{language}`):"). Update the extraction context with the new hints, then **re-execute step 3 from §1** with the new values. Discards the prior empty inventory.
- **IF P** — log "user accepted zero-exports outcome" and proceed to §5. The compiled skill will be README-content-only with confidence `low`. Record `zero_exports_rescue: "user-accepted"` in the inventory so the result contract summary surfaces it.
- **IF A** — HARD HALT with **exit code 3 (resolution-failure)**: "Aborted. Run `/skf-create-skill` from a brief if you want a guided extraction with provenance tracking." Before exiting, emit the error result contract per SKILL.md "Result Contract on HARD HALT" (`phase: "quick-extract"`, `error.code: "resolution-failure"`, `error.details: {exports_found: 0, description_empty: true, language: "{language}", scope: "{scope_hint or 'entire repo'}"}`, `skill_package: null`).

**GATE [default: P]** — In headless mode, log "headless: zero exports + empty description, proceeding with low-confidence skill" and proceed; record `zero_exports_rescue: "auto-proceeded"` in the result contract summary so batch automators can re-queue these targets with stricter hints downstream. [P] preserves the pre-rescue behaviour for unattended pipelines.

### 5. Report Extraction Summary

"**Extraction complete:**

- **Package:** {package_name} v{version}
- **Language:** {language}
- **Exports found:** {count}
- **Confidence:** {confidence}
- **Source files read:** {count}

**Proceeding to compilation...**"

### 6. Auto-Proceed to Compilation

#### Menu Handling Logic:

- After extraction summary, immediately load, read entire file, then execute {nextStepFile}

#### EXECUTION RULES:

- This is an auto-proceed step — extraction results flow directly to compilation
- Proceed directly to next step after summary

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN extraction is complete and extraction_inventory is assembled (even if minimal/low-confidence) will you load and read fully `{nextStepFile}` to execute compilation.

