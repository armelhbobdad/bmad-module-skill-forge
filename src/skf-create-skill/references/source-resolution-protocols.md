# Source Resolution Protocols

## Shell Path Quoting

Every shell snippet in this document and in step 3 §2b uses `{...}` placeholders for paths. **Always wrap path interpolations in double quotes** when emitting the actual command: `uv run {sourceTreeHelper} resolve --source-repo "{source_repo}"`, `cd "{remote_clone_path}"`, `cd "{project-root}"`. Home folders on macOS often contain spaces, which break unquoted shell, and WSL2 and Windows paths do too, so the quoting convention applies on every platform.

## Tag Resolution

Tag resolution maps a declared version in the brief onto a concrete git ref, so the skill is built from code matching its declared version. Three signals can drive it, in priority order: an explicit `brief.target_ref` (a ref the user states verbatim, highest priority), an **explicit** `brief.target_version` (deliberate user intent), or an **implicit** `brief.version` (auto-populated hint from `brief-skill`). They apply only to a remote source read at Forge tier or above: step 3 §2b hands them to the `resolve` subcommand of `{sourceTreeHelper}` as flags (its command shows which), and resolve lists the remote's tags and does the matching. A Quick-tier remote source reads `HEAD`.

| The brief sets | What resolve reads |
|---|---|
| `target_ref` (it takes priority) | that ref as given: a tag (a tag wins over a branch of the same name), a branch, `HEAD` or a full commit |
| `target_version` | the first of seven tag forms that exists (Explicit Tag Resolution) |
| only `version` | the first of two tag forms that exists (Implicit Tag Resolution) |
| none of them | `HEAD`, the default branch |

`target_ref` is the escape hatch for ref conventions the tag forms do not cover, notably monorepo crate tags whose prefix differs from the skill name (skill `livekit-rust` built from tag `livekit/v0.7.42`). When the brief sets it and a version too, resolve gets both: a `target_ref` the remote does not have adds the warning "target_ref ({target_ref}) does not resolve in {source_repo}; falling back to version matching", and resolve matches the version instead.

### Explicit Tag Resolution (when target_version is set)

resolve tries these forms of `{target_version}` against the remote's tags, in priority order (every form but the first drops a leading `v` of the version):

- **Exact match:** `{target_version}` (e.g., `0.5.0`)
- **With `v` prefix:** `v{target_version}` (e.g., `v0.5.0`)
- **With package scope (monorepos):** `{brief.name}@{target_version}` or `@{scope}/{brief.name}@{target_version}`
- **With crate/package-directory prefix (monorepos):** `{brief.name}/v{target_version}`, `{brief.name}/{target_version}`, or `{brief.name}-v{target_version}` (e.g. `tokio/v1.0.0`). These cover monorepos whose tags are prefixed by the crate or package directory **when that directory equals the skill name**. When it differs (crate `livekit` for skill `livekit-rust`, tag `livekit/v0.7.42`), no form can infer it: set `target_ref` instead.

Outcomes, from `tag_resolution.status`:

- **`matched`:** one form matched. resolve read that tag, and it is `source_ref`.
- **`ambiguous`:** several tags matched, and nothing was read yet: see Several Matching Tags below.
- **`fallback-head`:** no tag matched, and resolve read `HEAD`; the warning it printed names the nearest tags. ⚠️ Add: "**Extracted code may not match target version {target_version}.**"

`source_ref` is written to metadata.json and provenance-map.json for downstream workflows (update-skill, audit-skill) to read the same ref again.

### Implicit Tag Resolution (when only brief.version is set)

When `brief.target_version` is absent but `brief.version` is present, `brief.version` is an **implicit** target version. This matches `brief-skill`'s behavior, which fills `brief.version` from the source's manifest or version files or, when they hold none, its latest release tag, so a tag matching `brief.version` is the common case, and silently reading HEAD would produce a skill labeled with `brief.version` but built from an unrelated default-branch commit.

With `--implicit`, resolve tries only two forms, in this order:

- **Exact match:** `{brief.version}` (e.g., `0.3.37`)
- **With `v` prefix:** `v{brief.version}` (e.g., `v0.3.37`)

Package-scoped monorepo forms are **not** tried: they need deliberate user intent through `target_version`, since implicit matching against a monorepo tag like `{brief.name}@{version}` could silently select a sibling package's ref.

Outcomes, from `tag_resolution.status`:

- **`matched`:** no warning; this is the expected path.
- **`ambiguous`:** see Several Matching Tags below, where `HEAD` is one of the choices.
- **`fallback-head`:** no tag matched, and resolve read `HEAD`; the warning it printed names the nearest tags. ⚠️ Add: "**Extracted code may not match the declared version {brief.version}.** If you intended to pin a specific version, set `target_version` explicitly in the brief." Keep the `tag_resolution` record resolve printed (`status: "fallback-head"`, `requested`, `reason: "no-matching-tag"`) in the in-context evidence-report payload so step 5 §7 surfaces the fallback in the evidence report: a persistent audit trail a reviewer can grep later, not just a one-shot warning.

**Do not halt on zero matches.** Implicit resolution never blocks compilation: `brief.version` is an auto-populated hint, and some repositories simply do not tag releases. The warning is sufficient notice; the evidence report in step 8 will surface the HEAD fallback for reviewers.

**Interaction with Version Reconciliation (below):** When implicit tag resolution matches a tag, the tree's version file should carry `brief.version`, unless it holds a release-time placeholder, which the extractor reports as no version, so the Version Reconciliation section's source-vs-brief mismatch warning will not fire. When implicit resolution falls back to HEAD, Version Reconciliation runs normally against the default branch's version file and may produce its own mismatch warning.

### Several Matching Tags

When resolve prints `ambiguous`, it read nothing, and `tag_resolution.candidates` lists the matching tags in the priority order above. This is the one choice tag resolution leaves to you:

- Ask: "Multiple tags match version {tag_resolution.requested}: {candidates}. Which one should I use?", adding "or should I fall back to HEAD?" for an implicit version, and "Setting `target_ref` in the brief skips this question next time." Wait for the selection.
- **GATE [default: first candidate]**: under `{headless_mode}`, take the first candidate, log "headless: tag {tag} chosen from {candidates} for version {tag_resolution.requested}", and record the auto-decision per the Workflow Rules (step `extract`, gate `tag-choice`, decision `{tag}`): stage `{"step": "extract", "gate": "tag-choice", "decision": "{tag}", "rationale": "headless mode: first matching tag in priority order", "timestamp": "{ISO}"}` as `{run_dir}/decision.json` and run `uv run {emitEnvelopeHelper} record --workflow skf-create-skill --run-dir "{run_dir}" --decision < "{run_dir}/decision.json"`.

Step 3 §2b then runs resolve again with the chosen tag (or `HEAD`) as `--target-ref`.

### Local Source Warning

When `brief.target_version` is set AND `source_repo` is a local path:

⚠️ "**Local source may not match target version {target_version}.** Ensure you've checked out the correct version locally, or use a remote GitHub URL so SKF can clone from the git tag automatically."

Proceed with local files as-is. Set `source_ref` to `"local"`.

Implicit resolution via `brief.version` is **not applied to local sources** — local paths reflect whatever the user has checked out, and rewriting them from a tag would be out of scope for a local-source workflow.

---

## Remote Source Resolution

**Note:** Quick-tier remote sources are never read into a tree. Quick tier accesses remote files via the `gh_bridge.read_file` path described in step 3 section 4.

A remote source (a GitHub URL, an `owner/repo` shorthand or another git URL) read at Forge, Forge+ or Deep tier goes through one `resolve` call of `{sourceTreeHelper}` (step 3 §2b). It reads the commit Tag Resolution picks into a private tree of this run's own, which no other run can move, and with `--update-clone` moves SKF's workspace clone to the same commit in the same call, under the clone's `.skf-workspace.lock` and after running `{cccGitHygieneHelper}` there, never forcing a checkout (the `resolve` section of `skf-source-tree.py` has the details). The tree is removed with the helper's `close` subcommand at the end of step 7, or before any HALT after step 3 §2b.

**Compute workspace path:** SKF's workspace clone of a repository is `{workspace_root}/repos/{host}/{owner}/{repo}/`, where `{workspace_root}` is the environment variable `SKF_WORKSPACE` when set, otherwise `~/.skf/workspace/` (where `~` is the user's home directory on all platforms). resolve prints it as `workspace_path`.

**Scope filtering:** the tree is a full checkout (no sparse-checkout), so apply `include_patterns` and `exclude_patterns` from the brief as **file-level filters** when building the extraction file list. Always-included root files (`pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod`, `pom.xml`, `build.gradle`, `build.gradle.kts`, `Package.swift`, `setup.py`, `setup.cfg`, `VERSION`) are exempt from pattern filtering.

**When no tree can be read** (resolve prints `unavailable`, or does not finish), step 3 §2b warns the user and degrades this run to source reading (T1-low), with the Quick tier extraction strategy.

---

## Source Commit Capture (all tiers, source mode only)

**If `source_type: "docs-only"`:** skip — set `source_commit: null`.

After the source path is accessible, capture the current commit hash for provenance tracking:

- **Local path:** `git -C "{source_root}" rev-parse HEAD` — if the path is a git repo
- **Remote source at Forge tier or above:** the `source_commit` resolve printed in step 3 §2b, the commit the tree holds
- **Quick tier (remote, no clone):** `gh api repos/{owner}/{repo}/commits/{source_ref} --jq '.sha'`

Store the result as `source_commit` in context. If capture fails (not a git repo, API unavailable), set `source_commit: null` — this is not an error.

Also store `source_ref` in context (from tag resolution above, or `HEAD` if no tag was resolved, or `"local"` for local sources). This value is persisted to metadata.json and provenance-map.json so downstream workflows (update-skill, audit-skill) can re-access the same source ref.

**The `source_root` metadata.json records** is `{resolved-source-path}` (`assets/skill-sections.md`): the local path for a local source; the remote URL for a remote source read without a tree (Quick tier, or a run degraded to source reading) or one whose workspace path holds a folder that is not SKF's clone; SKF's workspace clone (resolve's `clone`) for a remote source read from a private tree; null for a docs-only skill. Never the tree itself: step 7 removes it, while update-skill, test-skill and audit-skill read the skill's source from the workspace clone.

---

## Version Reconciliation (all tiers, source mode only)

**Target version override:** If `brief.target_version` is present, use it as the authoritative version for the skill. Do not warn about a brief-vs-source version mismatch — the user intentionally specified this version. Set the working version to `brief.target_version` and skip the rest of this reconciliation section. The `target_version` field indicates deliberate user intent (e.g., targeting an older version, or providing the version for a docs-only skill).

**If `source_type: "docs-only"`:** skip this section — no source files exist to reconcile.

After the source path is accessible (local path from step 1, or the private tree from above), read the source's version with `{extractPublicApiHelper}` (resolve it ← first existing path in `{extractPublicApiProbeOrder}`), never from a version file by eye: it reports a release-time placeholder such as `0.0.0-development`, and a value that is not a string, as no version. The version file is, in the source root, `pyproject.toml`, else `setup.py`, else `setup.cfg` for Python and `Cargo.toml` for Rust; for JavaScript or TypeScript, the `package.json` whose `name` matches `brief.name`, else one with a `bin` field, else the root one. Any other language, or a source that holds none of them, keeps `brief.version`: skip the rest of this section. From `{project-root}`, run:

```bash
uv run {extractPublicApiHelper} --mode quick --language "{brief.language}" --source-root "{source_root}" --manifest-file "<version file>" --resolve-version
```

**A remote source with no local tree** (Quick tier, or one §2b could not read into a tree): first stage the version file with `{githubFetchHelper}` (resolve it ← the first existing path of `{project-root}/_bmad/skf/shared/scripts/skf-github-fetch.py` and `{project-root}/src/shared/scripts/skf-github-fetch.py`), then run the call above with `--source-root "{run_dir}/files"`:

```bash
gh api "repos/{owner}/{repo}/git/trees/{source_ref}?recursive=1" --jq '.tree[] | select(.type == "blob") | .path' | uv run {githubFetchHelper} --repo "{owner}/{repo}" --ref "{source_ref}" --tree-file - --dest "{run_dir}/files" "<version file>"
```

**The source version** is the JSON's `version` when its `version_source` is `manifest` or starts with `file:`. Keep `brief.version`, with no mismatch warning, when `version` is null or `version_source` starts with `tag:` (no file of the source states that version), and when a call exits non-zero, prints no JSON or resolves no path. Record the JSON's `warnings` in context for the evidence report (step 8).

**If the source version differs from `brief.version`:** ⚠️ Warn the user: "Brief version ({brief.version}) differs from source version ({source_version}). Using source version ({source_version})." Update the working version in context to the source version, and record the mismatch in context for the evidence report (step 8).
