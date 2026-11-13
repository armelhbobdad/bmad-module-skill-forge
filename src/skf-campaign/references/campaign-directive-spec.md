# Campaign Directive Specification

Canonical contract for the campaign directive (`_campaign-directive.md`) — a
file-based standing directive holding campaign-wide policy. When a step loads
`campaign.directive_path` it re-reads the file fresh from disk at stage entry
(no caching, so operator edits between stages are picked up) and applies the
sections below as campaign-wide context. UTF-8 markdown; frontmatter not
required; default filename `_campaign-directive.md`.

## Recognized Sections

All optional — the directive may hold any combination of these, or none:

- **`## Quality Overrides`**: operator adjustments to the quality gate, one list item each. `- soft_target: 85` and `- soft_fallback: 75` set the campaign-wide values, and `- <skill>: soft_target 80, soft_fallback 70` sets one skill's (either key alone is fine). A skill's line beats a campaign-wide line, and both beat the campaign brief and customize.toml. The hard gate cannot be overridden. They apply to each skill's test threshold (skill loop) and to the export classification (Capstone and Export).
- **`## Skip List`**: skills to skip during processing, one list item each: `- <skill>: <reason>`, the reason optional. The skill loop and the Tier B batch mark a listed skill `skipped` before it runs and log the reason.

`scripts/campaign-quality-gate.py` reads the Quality Overrides and Skip List sections (a section runs to the next `#` or `##` heading; backticks around a name are dropped), so their effect never depends on how a step reads the prose. A list item in them it cannot read is reported and logged, never applied, and a name that is no skill in the campaign is logged as a warning.

Any heading not listed above, such as `## Notes`, is treated as general
guidance: read it and apply judgment based on the content. This lets operators
add ad-hoc context without modifying this specification. Such guidance never
changes a sub-skill's flags or inputs: the stages pass fixed flags and the
inputs their scripts resolve. Only the two sections above are parsed by a
script; the kickoff script copies the whole directive into each Tier A kickoff
as context.

## Absence Behavior

An unset `campaign.directive_path` or a missing file is no error: the campaign proceeds with defaults.
