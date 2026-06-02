---
stateFile: 'forge-data/_campaign/_campaign-state.yaml'
directiveFile: '_campaign-directive.md'
---

# Campaign Directive Specification

## Purpose

The campaign directive (`_campaign-directive.md`) is a file-based standing directive that provides campaign-wide policy persisting across context boundaries. It is:

- **Human-readable** — plain markdown, editable with any text editor
- **Auditable** — version-controllable alongside campaign artifacts
- **Context-boundary safe** — re-read from disk at each stage transition, with no dependency on LLM memory (NFR-2)

The directive allows the operator to adjust campaign-wide policy without editing the state file or relying on LLM memory.

## File Format

- **Encoding:** UTF-8 markdown
- **Frontmatter:** not required (plain content is sufficient)
- **Location:** the path specified by `campaign.directive_path` in the campaign state file
- **Default filename:** `_campaign-directive.md` (configured in `manifest.yaml` as `config.directive_file`)

## Recognized Sections

All sections are optional. The directive may contain any combination of these, or none at all.

### `## Quality Overrides`

Operator adjustments to quality gates for specific skills or the entire campaign.

Example:
```markdown
## Quality Overrides

- Accept 85% for library-x due to incomplete upstream docs
- Lower soft gate to 70% for experimental-sdk (early-stage repo)
```

### `## Skip List`

Skills to skip during processing, with rationale.

Example:
```markdown
## Skip List

- Skip library-y — upstream repo is in maintenance mode
- Skip legacy-tool — will be removed in next sprint
```

### `## Pipeline Flags`

Per-skill or campaign-wide pipeline modifiers.

Example:
```markdown
## Pipeline Flags

- Use `--pin main` for all unpinned skills
- Force forge-auto mode for large-repo-z
```

### `## Notes`

Free-form operator context for the LLM agent processing the campaign.

Example:
```markdown
## Notes

Focus on documentation quality this run — the team is preparing for an external audit.
Prioritize skills that feed into the public API layer.
```

## Unrecognized Sections

Any section heading not listed above is treated as general guidance. The LLM agent reads and applies judgment based on the content. This allows operators to add ad-hoc context without modifying the specification.

## Read Contract

The directive is read from the path stored in `campaign.directive_path` (in the campaign state file) at stage entry. Every step that loads state and performs actionable processing checks for and applies the directive.

Steps that read the directive:
- **step-02-strategy** — operator may influence execution order presentation or add notes visible in strategy review
- **step-05-skill-loop** — directive populates `{{directive_content}}` in kickoff template and provides campaign-wide context for all skill processing
- **step-06-batch** — operator may want skip/quality overrides for Tier B batch processing
- **step-08-verify** — operator may want to influence verification focus areas
- **step-09-refine** — operator may want to guide refinement priorities
- **step-10-export** — operator may want to exclude specific skills from export

Steps that do NOT read the directive:
- **step-01-setup** — creates the state file; `directive_path` is collected as input, not read
- **step-03-pins** — pin validation is deterministic (Python script); directive cannot influence gh API calls
- **step-04-provenance** — repo access verification is deterministic; directive cannot influence commit SHA recording
- **step-07-capstone** — SS compose-mode is mechanical aggregation; no operator policy applies
- **step-11-maintenance** — report generation is templated; health check is autonomous
- **step-resume** — routing step, not a processing step

## Absence Behavior

- If `campaign.directive_path` is not set in the state file: no error, proceed with defaults
- If `campaign.directive_path` is set but the file does not exist at that path: no error, proceed with defaults
- The directive is always optional — a campaign runs identically without one

## Modification Contract

The operator may edit the directive file at any time between stages. The next stage that reads the directive will pick up the updated version. There is no caching — the directive is always read fresh from disk at stage entry.

## Lifecycle

1. **Created:** before or during Stage 0 (setup) — the operator provides the file path, or it defaults to `_campaign-directive.md`
2. **Read:** at each stage entry by applicable steps (see Read Contract above)
3. **Modified:** at any time between stages by the operator
4. **Consumed:** by the LLM agent as campaign-wide context influencing processing decisions
