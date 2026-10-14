# Version Resolution

Single source of truth for how brief-skill resolves the `version` field of `skill-brief.yaml`. Loaded by step 2 §4b (auto-detect, when §4.2's fallback read the source) and step 5 §3 (resolve & write) so both operate on the same precedence rules and invariant. Step-01 §3b references this file in prose for human-readable rationale but does not load it: that step only collects `target_version` and checks its shape with `skf-validate-brief-inputs.py --only target_version`.

## Detection Algorithm

Step 2 §4.1's extractor detects the version of the languages it reads, with `--resolve-version`: the manifest's literal version, then a version file or a Cargo workspace root, then the release tag (`skf-extract-public-api.py --help` gives the order). When §4.2 read the source instead, attempt these lookups in order and stop at the first match:

1. The version the manifest or a version file writes as a literal: `package.json`'s `"version"`, `pyproject.toml`'s `[project] version` or a package's `__version__`, a `.gemspec` or `version.rb` `VERSION`, a `.csproj` `<Version>`, `composer.json`'s `"version"`.
2. The tag lookup. For a GitHub source, `uv run {githubProbeHelper} tags --repo "{owner}/{repo}" --ref "{analysis_ref}" --limit 1`: its `release.version` is the version (the newest release tag at `HEAD`, the pinned tag itself at a tag, none at a branch or a commit), and a null `release` or a non-zero exit gives none. For a local source, `git -C "{source_path}" describe --tags --abbrev=0`: a tag whose name is a version gives it, a leading `v` dropped.

For remote GitHub sources, read version-bearing files from `{run_dir}/files/`, where step 2 stages the files it fetches; fetch one that is not there yet with step 2's fetch helper, naming it: `uv run {githubFetchHelper} --repo "{owner}/{repo}" --ref "{analysis_ref}" --tree-file "{run_dir}/tree.json" --dest "{run_dir}/files" "{file}"`. `{analysis_ref}` is the ref resolved in step 02 §1, defaulting to `HEAD` when no `target_ref`/`target_version` was pinned; reading at the pinned ref keeps the "Detected version" consistent with the version being skilled. For local sources, read the file directly.

If every step fails or returns a non-semver value, the detected version is `null` — the resolver below falls back to `"1.0.0"`.

**Pre-release handling:** preserve detected pre-release tags (`1.0.0-beta.0`, `2.0.0-rc.1`) verbatim. Do not strip them.

## Precedence — Resolving the `version` Field

The brief's `version` field is resolved from three candidate sources, in priority order:

1. **`target_version`** — collected interactively in step 1 §3b or supplied as a headless argument. When present, this value wins outright. The auto-detection above still runs for informational purposes (the user sees both "Target version" and "Detected version" side-by-side at the analysis summary), but the brief's `version` field is set from `target_version`.
2. **Auto-detected version** — from §"Detection Algorithm" above. Used when `target_version` is absent.
3. **Default** — `"1.0.0"` when both of the above fail or yield a non-semver value.

## Invariant

When `target_version` is set, the written brief must satisfy:

```
brief.target_version == brief.version
```

Step-05 §3 enforces this by setting both fields to the same string when `target_version` is present. Downstream tooling (e.g. `skf-create-skill`) can distinguish "user-requested" from "auto-detected" by the presence of `target_version` without re-deriving provenance — but the values themselves are identical. Different values are a contract violation and a bug.

## Step-Level Responsibilities

| Step | Responsibility |
|------|----------------|
| 01 §3b | Collect `target_version` (interactive prompt, or headless arg). Do not auto-detect — that is step 02's job. |
| 02 §1 | Resolve `target_version` to the git tag step 2 reads, through `skf-validate-pins.py`. With no match, analyze `HEAD` and warn. |
| 02 §4b | Detect the version (§4.1's extractor, or the detection algorithm after §4.2) regardless of whether `target_version` is set. If `target_version` is set and the detected version differs, surface the disagreement to the user; the precedence above is unchanged, so `target_version` wins. |
| 05 §3 | Apply the precedence rules and write `version`. If `target_version` is set, also write the `target_version` field with the identical value. Enforce the invariant. |
