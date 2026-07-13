---
stateFile: '{campaignWorkspacePath}/_campaign-state.yaml'
directiveFile: '_campaign-directive.md'
---

# Campaign Directive Specification

Canonical contract for the campaign directive (`_campaign-directive.md`) — a
file-based standing directive holding campaign-wide policy. When a step loads
`campaign.directive_path` it re-reads the file fresh from disk at stage entry
(no caching, so operator edits between stages are picked up) and applies the
sections below as campaign-wide context. UTF-8 markdown; frontmatter not
required; default filename `_campaign-directive.md`.

## Recognized Sections

All optional — the directive may hold any combination of these, or none:

- **`## Quality Overrides`** — operator adjustments to quality gates for specific skills or the whole campaign.
- **`## Skip List`** — skills to skip during processing, with rationale.
- **`## Pipeline Flags`** — per-skill or campaign-wide pipeline modifiers.
- **`## Notes`** — free-form operator context for the agent processing the campaign.

Any heading not listed above is treated as general guidance: read it and apply
judgment based on the content. This lets operators add ad-hoc context without
modifying this specification.

## Absence Behavior

- If `campaign.directive_path` is not set in the state file: no error, proceed with defaults
- If `campaign.directive_path` is set but the file does not exist at that path: no error, proceed with defaults
- The directive is always optional — a campaign runs identically without one
