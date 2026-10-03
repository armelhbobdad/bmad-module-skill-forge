---
nextStepFile: 'analyze-target.md'
ratifyFile: 'references/gather-intent-ratify.md'
validateBriefInputsProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-validate-brief-inputs.py'
  - '{project-root}/src/shared/scripts/skf-validate-brief-inputs.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 1 (Headless): Input Gate

Step 1 §1b loads this file when `{headless_mode}` is true outside `[auto]` mode, in place of step 1's interactive §2 to §8. The arguments are merged and validated here, before any section uses them, and every later value the run takes from an argument comes from the validated `normalized` object.

## Arguments

`{validateBriefInputsHelper}` enforces this table.

| Argument | Required | Default | Notes |
|----------|----------|---------|-------|
| `target_repo` | yes¹ | none | HALT (exit 2, `halt_reason: "input-missing"`) if absent. ¹Not required when `from_brief` is supplied: the ratify route takes the target from the brief and ignores `target_repo` (with a warning) if also passed |
| `skill_name` | yes¹ | none | HALT (exit 2, `halt_reason: "input-missing"`) if absent; HALT (exit 2, `halt_reason: "input-invalid"`) if not kebab-case. ¹Not required when `from_brief` is supplied: the ratify route takes the name from the brief and ignores `skill_name` (with a warning) if also passed |
| `from_brief` | no | none | Path to a pre-authored `skill-brief.yaml` (a file, or a folder holding one) to **ratify** instead of deriving a brief (§3): schema-validate it, skip steps 2 and 3, write through the canonical writer to `{forge_data_folder}/{name}/skill-brief.yaml` (no `force` needed when the brief already lives at that path; otherwise `force` applies as on the derive route). `target_repo` and `skill_name` become optional and are ignored if also passed. HALT (exit 2, `halt_reason: "input-missing"`) if the value is empty or the path does not exist; HALT (exit 2, `halt_reason: "input-invalid"`) if the brief fails schema validation |
| `source_type` | no | `source` | If `docs-only`, `doc_urls` becomes required |
| `doc_urls` | conditional | none | Required when `source_type=docs-only` (HALT exit 2, `halt_reason: "input-missing"` if empty). List of `url` or `url,label` |
| `source_authority` | no | detected | `official` / `community` / `internal`. When absent and `target_repo` is a GitHub URL, §4 compares the `gh api user` login with the URL owner: a match is `official`, anything else `community`. A local path, or a failed `gh api user`, is `community`. Forced to `community` when `source_type=docs-only` |
| `target_version` | no | none | Auto-detected in step 2 if absent. Full X.Y.Z semver required (HALT exit 2, `halt_reason: "input-invalid"` on partial forms like `1`, `1.2`, `v2`) |
| `scope_hint` | no | none | Free-text scope steering, classified with `intent` into the scope-type signals at step 3 §2c |
| `language_hint` | no | none | Overrides language detection, consumed at step 2 §3: the detector still runs for the informational Detected-language line, but the hint becomes the confirmed language and the step 3 §4 low-confidence override does not fire |
| `scope_type` | no | heuristic | `full-library` / `specific-modules` / `public-api` / `component-library` / `reference-app` / `docs-only`. When absent and `source_type=source`, step 3 §2c recommends one from the `intent` and `scope_hint` arguments and step 2's analysis; `source_type=docs-only` always short-circuits to `docs-only` |
| `include` | no | the scope type's default | Comma-separated globs, used by step 3 §3 as given. When absent, step 3 §3 takes the scope type's headless default and names it in the envelope's `warnings`; a `scope_type=reference-app` argument halts here instead (§2), and a `reference-app` type the recommender picked, or a `specific-modules` `scope_type` argument whose `intent` and `scope_hint` name no module, halts at step 3 §3, each with `input-missing` (exit 2) |
| `exclude` | no | see Notes | Comma-separated globs. With an `include`, step 3 §3 uses them as given; without one, it adds them to the exclusions of the scope type's headless default and names them in its `warn:` line. When absent: none beside a given `include`, else the default's exclusions |
| `scripts_intent` | no | `detect` | `detect` / `none` / free-text |
| `assets_intent` | no | `detect` | `detect` / `none` / free-text |
| `intent` | no | none | Free text the description is composed from (§5) |
| `force` | no | none | Overwrite an existing brief without prompting (consumed in step 5 §2b) |
| `preset` | no | none | Name of a preset YAML file at `{sidecar_path}/brief-presets/{preset}.yaml`, merged as defaults by §1: explicit arguments override preset values. Useful for repeated patterns (e.g. briefing 5 SaaS API SDKs with the same `source_authority`/`scope_type`/`scripts_intent`). The preset file is YAML holding any subset of the arguments above; unknown fields are ignored with a warning |

## Sequence

**GATE [default: use args]**: consume the arguments in the order below and auto-proceed; nothing here prompts.

### 1. Preset Merge

Skip this merge when a `from_brief` argument is present: a preset seeds a derived brief and means nothing on the ratify route. Otherwise, when the arguments hold a `preset`, load `{sidecar_path}/brief-presets/{preset}.yaml` and merge its keys as defaults, an explicit argument winning key by key. When the file does not exist, log `"warn: preset '{name}' not found at {path}; proceeding without preset"`, add it to `workflow_warnings[]` and continue. An unknown field the preset holds passes through: the validator warns about it in §2. Drop the `preset` key itself before validation: it is not a brief field.

### 2. Validate the Arguments

Resolve `{validateBriefInputsHelper}` from `{validateBriefInputsProbeOrder}` (first existing path wins; HALT if no candidate exists). Stage the merged arguments as one JSON object in the run folder, then run the helper on the file:

```bash
cat > "{run_dir}/headless-args.json" <<'SKF_JSON'
<the merged headless arguments, as one JSON object>
SKF_JSON
uv run {validateBriefInputsHelper} < "{run_dir}/headless-args.json"
```

It returns `{valid, errors[], warnings[], normalized, halt_reason}`:

- **`valid: false`**: emit the halt envelope first, `uv run {emitBriefEnvelopeHelper} emit --target stderr` with the script's `halt_reason` (`input-missing` for an absent required argument, docs-only without `doc_urls`, or a `reference-app` `scope_type` without `include`; `input-invalid` for an enum violation, malformed semver or a `skill_name` that is not kebab-case) (SKILL.md Halt Contract), surface `errors[]` to the operator log, then HALT (exit code 2).
- **`valid: true`**: `normalized`, the arguments with the table's defaults applied, is the source of truth for the rest of the run. Log each `warnings[]` entry and add it to `workflow_warnings[]` as `<field>: <message>`.

### 3. Ratify Route (`from_brief`)

When `normalized.from_brief` is set, this run ratifies a pre-authored brief instead of deriving one: load, read entirely, and execute `{ratifyFile}` with that path. It validates the brief and hands the run to step 4, so nothing below runs.

### 4. Source Authority

When `normalized.source_authority` is absent, `source_type` is `source` and `target_repo` is a GitHub URL (`https://github.com/<owner>/<repo>`), probe the operator's login:

```bash
gh api user --jq .login
```

Compare it with `<owner>`, both lower-cased (GitHub owners match case-insensitively, but the API keeps the case): a match sets `source_authority: "official"`, another login `community`. When the call fails (`gh` missing or not logged in, no network), set `community`, log `"warn: source-authority detection skipped: gh api user failed"` and add it to `workflow_warnings[]`. In every other case `source_authority` is the value given, else `community`.

### 5. Derive the Brief Fields

From `normalized`, before step 2 runs:

- **Version:** a `target_version` sets `version` too; without one, step 2 detects the version.
- **Doc URLs:** HEAD-check every `doc_urls` entry in parallel, all calls in one message, each `curl -sI --max-time 5 {url}`. Keep a URL that fails, log `"warn: could not reach {url} ({status or error})"` and add it to `workflow_warnings[]`: the failure shows now instead of in skf-create-skill.
- **Name collision:** when `{forge_data_folder}/{skill_name}/skill-brief.yaml` exists, log `"warn: skill name '{skill_name}' collides with existing brief at {path}"`, add it to `workflow_warnings[]` and proceed: step 5 §2b halts with `overwrite-cancelled` unless `force` was supplied.
- **Description:** compose 1-3 sentences in `{document_output_language}` that say what the skill is and contain a literal `Use when` clause, in the spirit of `{descriptionVoiceExamplesPath}` (load it), from the first seed available:
  1. `intent`.
  2. The repository's own description, when `target_repo` is a GitHub URL: `gh api repos/{owner}/{repo} --jq .description` (5-second timeout). When it is not empty, log `"info: description seeded from GitHub repo description"`.
  3. None (a local path, an empty description, a failed call): write `"Use the {skill_name} skill to work with code or content from {target_repo}."`, log `"warn: description synthesized without intent or repo description: narrow registry text."` and add it to `workflow_warnings[]`.

### 6. Continue

Load, read entire file, then execute `{nextStepFile}` (step 2).
