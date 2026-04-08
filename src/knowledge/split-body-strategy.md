# Split-Body Strategy

## Principle

Selective split is the recommended strategy when `split-body` is needed. Extract only the largest Tier 2 section(s) to stay under the 500-line body guideline — keep all actionable Tier 1 content inline. Full split-body reduces agent accuracy because on-demand retrieval underperforms inline passive context.

## Rationale

Vercel research shows inline passive context achieves 100% task accuracy vs 79% for on-demand retrieval. Full split-body moves all Tier 2 content to `references/`, forcing agents to retrieve it on demand. Selective split preserves the most-used content inline while still satisfying the body size constraint.

Without selective split awareness:
- `skill-check split-body --write` extracts everything, reducing agent effectiveness
- tessl content scores drop dramatically (65% → 38%) because only SKILL.md body is evaluated
- Context snippet anchors (`#quick-start`, `#key-types`) may break if those sections move to references

With selective split awareness:
- Only the largest Tier 2 section(s) are extracted (usually Full API Reference or Full Type Definitions)
- Quick Start, Key API Summary, Key Types, Migration Warnings stay inline
- Agent accuracy remains high for common tasks
- tessl scores reflect actual inline content quality

## Split-Body Detection Pattern

A split-body skill is identified by:
1. A `references/` directory exists alongside SKILL.md
2. SKILL.md Tier 2 sections (headings starting with `## Full`) contain only stubs or are absent — their content lives in `references/*.md`
3. The skill's full documented content spans SKILL.md + `references/*.md`

When processing a split-body skill, any workflow step that reads SKILL.md content must also traverse `references/*.md` to get the complete picture.

## Anti-Patterns

- Running `skill-check split-body --write` without first attempting selective split
- Moving Tier 1 sections (Quick Start, Key API Summary) to references/ — these must stay inline
- Splitting before checking whether context snippet anchors will break

## Recommended Approach

When the 500-line body guideline is exceeded:
1. Identify which Tier 2 section(s) are largest (usually `## Full API Reference`)
2. Extract only those specific sections to `references/`
3. Keep all Tier 1 sections and smaller Tier 2 sections inline
4. Verify context snippet anchors still resolve after extraction

## Scripts and Assets Interaction

Split-body affects only SKILL.md content movement to `references/`. The `scripts/` and `assets/` directories are unaffected — they remain as top-level siblings of SKILL.md regardless of split-body decisions. They do not count toward the body line limit.

## Related Fragments

- [agentskills-spec.md](agentskills-spec.md) — 500-line guideline for SKILL.md body size and the `references/` directory structure
- [skill-lifecycle.md](skill-lifecycle.md) — where split-body decisions fit in the compilation pipeline
- `test-skill/references/scoring-rules.md` — tessl/split-body interaction and the pre-split baseline recommendation during test reporting

_Source: derived from agentskills.io split-body guidance and Vercel agent accuracy research (inline vs on-demand retrieval)_
