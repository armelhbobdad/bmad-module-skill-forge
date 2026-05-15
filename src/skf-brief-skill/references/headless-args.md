# Headless Argument Table

Loaded by step 1 §8 only when `{headless_mode}` is true. Canonical operator-facing documentation for the argument set consumed at step 1's GATE; the `{validateBriefInputsScript}` enforces these rules deterministically (its `KNOWN_FIELDS` set must stay in sync with this table).

| Argument | Required | Default | Notes |
|----------|----------|---------|-------|
| `target_repo` | yes | — | HALT (exit 2, `halt_reason: "input-missing"`) if absent |
| `skill_name` | yes | — | HALT (exit 2, `halt_reason: "input-missing"`) if absent; HALT (exit 2, `halt_reason: "input-invalid"`) if non-kebab |
| `source_type` | no | `source` | If `docs-only`, `doc_urls` becomes required |
| `doc_urls` | conditional | — | Required when `source_type=docs-only` (HALT exit 2, `halt_reason: "input-missing"` if empty). List of `url` or `url,label` |
| `source_authority` | no | detected | `official` / `community` / `internal`. When absent and `target_repo` is a GitHub URL, step 1 §8 GATE probes `gh api user` and compares its login to the URL owner — match → `official`, otherwise → `community`. Local-path or `gh api user` failure → `community`. Forced to `community` when `source_type=docs-only` |
| `target_version` | no | — | Auto-detected in step 2 if absent. Full X.Y.Z semver required (HALT exit 2, `halt_reason: "input-invalid"` on partial forms like `1`, `1.2`, `v2`) |
| `scope_hint` | no | — | Free-text steering for §5 |
| `language_hint` | no | — | Overrides language detection in step 2/03 |
| `scope_type` | no | heuristic | `full-library` / `specific-modules` / `public-api` / `component-library` / `reference-app` / `docs-only`. When absent and `source_type=source`, step 3 §2c runs five signal-driven heuristics (component-registry presence, reference-app keywords, specific-module intent, narrow public API) and uses the first match; falls back to `full-library` only if no heuristic fires. `source_type=docs-only` always short-circuits to `docs-only` |
| `include` | no | — | Comma-separated globs (used by step 3 §3) |
| `exclude` | no | — | Comma-separated globs (used by step 3 §3) |
| `scripts_intent` | no | `detect` | `detect` / `none` / free-text |
| `assets_intent` | no | `detect` | `detect` / `none` / free-text |
| `intent` | no | — | Free-text used to derive `description` in §7b |
| `force` | no | — | Overwrite existing brief without prompting (consumed in step 5 §2b) |
| `preset` | no | — | Name of a preset YAML file at `{sidecar_path}/brief-presets/{preset}.yaml`. Loaded at step 1 §8 GATE and merged as defaults; explicit args override preset values. Useful for repeated patterns (e.g. briefing 5 SaaS API SDKs with the same `source_authority`/`scope_type`/`scripts_intent`). The preset file is YAML containing any subset of the headless args above; unknown fields are ignored with a warning |
