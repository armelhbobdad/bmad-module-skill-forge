# Headless Argument Table

Loaded by step-01 §8 only when `{headless_mode}` is true. Canonical operator-facing documentation for the argument set consumed at step-01's GATE; the `{validateBriefInputsScript}` enforces these rules deterministically (its `KNOWN_FIELDS` set must stay in sync with this table).

| Argument | Required | Default | Notes |
|----------|----------|---------|-------|
| `target_repo` | yes | — | HALT (exit 2, `halt_reason: "input-missing"`) if absent |
| `skill_name` | yes | — | HALT (exit 2, `halt_reason: "input-missing"`) if absent; HALT (exit 2, `halt_reason: "input-invalid"`) if non-kebab |
| `source_type` | no | `source` | If `docs-only`, `doc_urls` becomes required |
| `doc_urls` | conditional | — | Required when `source_type=docs-only` (HALT exit 2, `halt_reason: "input-missing"` if empty). List of `url` or `url,label` |
| `source_authority` | no | `community` | `official` / `community` / `internal`; forced to `community` when `source_type=docs-only` |
| `target_version` | no | — | Auto-detected in step-02 if absent. Full X.Y.Z semver required (HALT exit 2, `halt_reason: "input-invalid"` on partial forms like `1`, `1.2`, `v2`) |
| `scope_hint` | no | — | Free-text steering for §5 |
| `language_hint` | no | — | Overrides language detection in step-02/03 |
| `scope_type` | no | — | `full-library` / `specific-modules` / `public-api` / `component-library` / `reference-app` / `docs-only` |
| `include` | no | — | Comma-separated globs (used by step-03 §3) |
| `exclude` | no | — | Comma-separated globs (used by step-03 §3) |
| `scripts_intent` | no | `detect` | `detect` / `none` / free-text |
| `assets_intent` | no | `detect` | `detect` / `none` / free-text |
| `intent` | no | — | Free-text used to derive `description` in §7b |
| `force` | no | — | Overwrite existing brief without prompting (consumed in step-05 §2b) |
