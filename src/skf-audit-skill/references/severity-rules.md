<!-- Config: communicate in {communication_language}. -->

# Severity Classification Rules

## Severity Levels

Each line below is one rule of `skf-severity-classify.py`, which grades a finding by its type and category: `--rules` prints the pairs each line accepts.

### CRITICAL — Breaking Changes
- Removed or renamed public exports (functions, classes, types)
- Changed function signatures (parameter count, parameter types, return type)
- Removed or renamed modules/files referenced in skill
- Changed class inheritance or interface contracts
- **Impact:** Skill instructions will produce incorrect code if followed

### HIGH — Significant Drift
- New public API exports not documented in skill (>3 new exports)
- Removed internal helpers that are referenced in documented patterns
- Changed default parameter values that affect documented behavior
- New required parameters added to documented functions
- Deprecated APIs still documented as current in skill
- Constituent skills changed since the stack was composed (compose-mode stacks)
- Changed documentation sources of a docs-only skill (doc drift)
- **Impact:** Skill is incomplete or contains outdated guidance

### MEDIUM — Moderate Drift
- Implementation changes behind a stable public API
- New optional parameters with defaults on documented functions
- New public exports not in skill (1-3 new exports)
- Moved functions between files (same API, different location)
- Changed internal implementation patterns documented in skill conventions
- Added or changed script, asset or doc files (Script/Asset Drift)
- Constituent skills that can no longer be found (compose-mode stacks)
- **Impact:** Skill is functional but not fully current

### LOW — Minor Drift
- Style or convention changes (formatting, naming patterns)
- Comment or documentation changes in source
- Whitespace or structural reorganization
- Line-only changes (same export and file, only the line number changed)
- New private/internal functions not affecting public API
- Test file changes
- **Impact:** Cosmetic — skill remains accurate for practical use

## Overall Drift Score

| Score       | Criteria                                 |
|-------------|------------------------------------------|
| CLEAN       | 0 findings at any level                  |
| MINOR       | LOW findings only, no MEDIUM+            |
| SIGNIFICANT | Any MEDIUM or HIGH findings, no CRITICAL |
| CRITICAL    | Any CRITICAL findings present            |

## Confidence Tier Labels

| Label  | Source                                                         | Reliability                             |
|--------|----------------------------------------------------------------|-----------------------------------------|
| T1     | An ast-grep match (`extraction_method: ast-grep`), at any tier | High: structural truth                  |
| T1-low | Read by eye (`extraction_method: source-read`), at any tier    | Moderate: read, not matched by ast-grep |
| T2     | Deep-tier semantic diff: a skill claim checked in the source   | High: cites the current source line     |
| T3     | External documentation reference                               | Variable: secondary source              |

A label names the tool that produced an export, not the forge tier: Quick tier reads every export by eye, and at Forge, Forge+ and Deep an export is read by eye when ast-grep cannot parse its file, a rule misses it, or its file is read instead of matched. A difference between the provenance map's label and the re-index label is not drift and has no severity.
