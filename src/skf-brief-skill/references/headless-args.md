# Headless Argument Table

Loaded by step 1 §8 only when `{headless_mode}` is true. Canonical operator-facing documentation for the argument set consumed at step 1's GATE; the `{validateBriefInputsHelper}` enforces these rules deterministically (its `KNOWN_FIELDS` set must stay in sync with this table).

| Argument | Required | Default | Notes |
|----------|----------|---------|-------|
| `target_repo` | yes¹ | — | HALT (exit 2, `halt_reason: "input-missing"`) if absent. ¹Not required when `from_brief` is supplied — the ratify route derives the target from the brief and ignores `target_repo` (with a warning) if also passed |
| `skill_name` | yes¹ | — | HALT (exit 2, `halt_reason: "input-missing"`) if absent; HALT (exit 2, `halt_reason: "input-invalid"`) if non-kebab. ¹Not required when `from_brief` is supplied — the ratify route derives the name from the brief and ignores `skill_name` (with a warning) if also passed |
| `from_brief` | no | — | Path to a pre-authored `skill-brief.yaml` (a file, or a directory containing one) to **ratify** instead of deriving a brief. When present it is the source of truth and routes the step 1 §8 GATE to the headless ratify path — the mirror of the interactive §3.1a `[R]` branch: schema-validate the brief → skip analyze-target / scope-definition (no re-derivation) → write through the canonical writer, overwriting in place (no `force` needed). `target_repo` / `skill_name` become optional and are ignored if also passed. HALT (exit 2, `halt_reason: "input-missing"`) if the value is empty or the resolved path does not exist; HALT (exit 2, `halt_reason: "input-invalid"`) if the brief fails schema validation |
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
