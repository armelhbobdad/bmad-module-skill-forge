# Version Resolution

Loaded by step 2 §4b when §4.2's fallback read the source.

## Detection Algorithm

Step 2 §4.1's extractor detects the version of the languages it reads, with `--resolve-version`: the manifest's literal version, then a version file or a Cargo workspace root, then the release tag (`skf-extract-public-api.py --help` gives the order). When §4.2 read the source instead, attempt these lookups in order and stop at the first match:

1. The version the manifest or a version file writes as a literal: `package.json`'s `"version"`, `pyproject.toml`'s `[project] version` or a package's `__version__`, a `.gemspec` or `version.rb` `VERSION`, a `.csproj` `<Version>`, `composer.json`'s `"version"`.
2. The tag lookup. For a GitHub source, `uv run {githubProbeHelper} tags --repo "{owner}/{repo}" --ref "{analysis_ref}" --limit 1`: its `release.version` is the version (the newest release tag at `HEAD`, the pinned tag itself at a tag, none at a branch or a commit), and a null `release` or a non-zero exit gives none. For a local source, `git -C "{source_path}" describe --tags --abbrev=0`: a tag whose name is a version gives it, a leading `v` dropped.

For remote GitHub sources, read version-bearing files from `{run_dir}/files/`, where step 2 stages the files it fetches; fetch one that is not there yet with step 2's fetch helper, naming it: `uv run {githubFetchHelper} --repo "{owner}/{repo}" --ref "{analysis_ref}" --tree-file "{run_dir}/tree.json" --dest "{run_dir}/files" "{file}"`. `{analysis_ref}` is the ref resolved in step 02 §1, defaulting to `HEAD` when no `target_ref`/`target_version` was pinned; reading at the pinned ref keeps the "Detected version" consistent with the version being skilled. For local sources, read the file directly.

If every step fails or returns a non-semver value, the detected version is `null` — the resolver below falls back to `"1.0.0"`.

**Pre-release handling:** preserve detected pre-release tags (`1.0.0-beta.0`, `2.0.0-rc.1`) verbatim. Do not strip them.

## Precedence

`target_version`, else the detected version, else 1.0.0: `skf-write-skill-brief.py` applies it and keeps `target_version == version`.
