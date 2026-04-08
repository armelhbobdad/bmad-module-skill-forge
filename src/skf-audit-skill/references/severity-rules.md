# Severity Classification Rules

## Severity Levels

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
- **Impact:** Skill is incomplete or contains outdated guidance

### MEDIUM — Moderate Drift
- Implementation changes behind a stable public API
- New optional parameters with defaults on documented functions
- New public exports not in skill (1-3 new exports)
- Moved functions between files (same API, different location)
- Changed internal implementation patterns documented in skill conventions
- **Impact:** Skill is functional but not fully current

### LOW — Minor Drift
- Style or convention changes (formatting, naming patterns)
- Comment or documentation changes in source
- Whitespace or structural reorganization
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

| Label  | Source                           | Reliability                             |
|--------|----------------------------------|-----------------------------------------|
| T1     | AST extraction (ast-grep)        | High — structural truth                 |
| T1-low | Text pattern matching (no AST)   | Moderate — pattern-based                |
| T2     | QMD semantic context             | High — evidence-backed temporal context |
| T3     | External documentation reference | Variable — secondary source             |
