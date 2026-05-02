# Version Resolution

Single source of truth for how brief-skill resolves the `version` field of `skill-brief.yaml`. Loaded by step-02 §4b (auto-detect, fallback path only when the language is not script-supported) and step-05 §3 (resolve & write) so both operate on the same precedence rules and invariant. Step-01 §3b references this file in prose for human-readable rationale but does not load it — that step only collects `target_version` and validates its shape with an inline regex.

**Aligned with** `assets/skill-brief-schema.md` "Version Detection" section. If you change one, change the other.

## Detection Algorithm

For the detected source language, attempt the lookups in order. Stop at the first match.

- **Python:** `pyproject.toml` `[project] version` (static) → if `dynamic = ["version"]`, check `__init__.py` for `__version__` → `_version.py` if exists → `setup.py` `version=` → `git describe --tags --abbrev=0`
- **JavaScript / TypeScript:** root `package.json` (`"version"`). If the root has `"private": true` with a `"workspaces"` array or lacks a `"version"` field, fall back to a primary workspace package's `package.json` (e.g. `code/core/package.json`, or the first matching `packages/*/package.json`). For GitHub sources, prefer `gh api repos/{owner}/{repo}/releases/latest` → `tag_name` when a non-pre-release tag exists, over a default-branch pre-release. Treat a version containing `-alpha`, `-beta`, `-rc`, `-next`, or `-canary` as a pre-release.
- **Rust:** `Cargo.toml` `[package] version` (static). If `version = { workspace = true }`, resolve from workspace root `Cargo.toml` → `git describe --tags --abbrev=0`.
- **Go:** version tag from `go.mod`, or `git describe --tags --abbrev=0`.

For remote GitHub sources, fetch version-bearing files via `gh api repos/{owner}/{repo}/contents/{file}` (decode base64). For local sources, read the file directly.

If every step fails or returns a non-semver value, the detected version is `null` — the resolver below falls back to `"1.0.0"`.

**Pre-release handling:** preserve detected pre-release tags (`1.0.0-beta.0`, `2.0.0-rc.1`) verbatim. Do not strip them.

## Precedence — Resolving the `version` Field

The brief's `version` field is resolved from three candidate sources, in priority order:

1. **`target_version`** — collected interactively in step-01 §3b or supplied as a headless argument. When present, this value wins outright. The auto-detection above still runs for informational purposes (the user sees both "Target version" and "Detected version" side-by-side at the analysis summary), but the brief's `version` field is set from `target_version`.
2. **Auto-detected version** — from §"Detection Algorithm" above. Used when `target_version` is absent.
3. **Default** — `"1.0.0"` when both of the above fail or yield a non-semver value.

## Invariant

When `target_version` is set, the written brief MUST satisfy:

```
brief.target_version == brief.version
```

Step-05 §3 enforces this by setting both fields to the same string when `target_version` is present. Downstream tooling (e.g. `skf-create-skill`) can distinguish "user-requested" from "auto-detected" by the presence of `target_version` without re-deriving provenance — but the values themselves are identical. Different values are a contract violation and a bug.

## Step-Level Responsibilities

| Step | Responsibility |
|------|----------------|
| 01 §3b | Collect `target_version` (interactive prompt, or headless arg). Do not auto-detect — that is step 02's job. |
| 02 §4b | Run the detection algorithm regardless of whether `target_version` is set. If `target_version` is set and the detected version differs, surface the disagreement to the user — but the precedence above is unchanged: `target_version` wins. |
| 05 §3 | Apply the precedence rules and write `version`. If `target_version` is set, also write the `target_version` field with the identical value. Enforce the invariant. |
