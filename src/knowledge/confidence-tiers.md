# Confidence Tiers

## Principle

Every extracted claim carries a confidence tier label — T1, T1-low, T2, or T3 — that tells consuming agents how much to trust the information. The tier determines citation format, affects scoring weights, and governs how claims interact during updates and audits.

## Rationale

Not all extracted information has equal reliability. An AST-parsed function signature is structurally verified; a type inferred from pattern matching might be wrong; a QMD-enriched usage note adds context but not structural proof; an external doc reference is only as current as its source.

Without confidence tiers:
- All claims appear equally trustworthy regardless of extraction method
- Agents cannot distinguish verified signatures from inferred patterns
- Audit and update workflows have no basis for prioritizing drift findings

With confidence tiers:
- Each claim transparently declares its evidence strength
- Scoring weights adjust based on the distribution of tiers
- Update workflows know which claims to re-verify first

## Tier Definitions

| Tier | Label | Source | Extraction Method | Available At |
| --- | --- | --- | --- | --- |
| T1 | AST-verified | Source code | ast-grep structural parsing | Forge, Forge+, Deep |
| T1-low | Source-read | Source code | Pattern matching, file reading | Quick, Forge, Forge+, Deep |
| T2 | QMD-enriched | Knowledge base | QMD semantic search + synthesis | Deep |
| T3 | External reference | Docs, URLs | External documentation lookup | All tiers |

## T2 Sub-Types

T2 enrichment content maps to temporal scopes that control where annotations surface:

| Sub-type | Content | Surface Level |
| --- | --- | --- |
| T2-past | Closed issues, merged PRs, changelogs — historical context explaining why the API looks the way it does | `references/` (full temporal context) |
| T2-future | Open PRs, deprecation warnings, RFCs — forward-looking context about upcoming changes | `SKILL.md` Section 4b (Migration & Deprecation Warnings) + `references/` |

The T2-past/T2-future distinction is operationally significant: T2-future annotations trigger the presence of a Migration & Deprecation Warnings section in SKILL.md, while T2-past annotations live in progressive disclosure reference files only.

## Citation Formats

Each tier has a defined citation format used consistently across all skill output:

```
T1:     [AST:filepath:Lnn]          — AST-verified, line-level precision
T1-low: [SRC:filepath:Lnn]          — source-read, line-level but unverified structure
T2:     [QMD:collection:document]   — QMD knowledge enrichment
T3:     [EXT:url-or-reference]      — external documentation reference
```

## Pattern Examples

### Example 1: T1 — AST-Verified Export

**Context:** ast-grep parses a TypeScript file and extracts a function export with full signature.

**Implementation:**
```markdown
## `createServer(options: ServerOptions): Server`

Creates and configures an HTTP server instance.

**Parameters:**
| Name | Type | Required | Default |
| --- | --- | --- | --- |
| options | `ServerOptions` | yes | — |

[AST:src/server.ts:L23]
```

**Key Points:**
- Signature extracted by AST — structurally guaranteed to match source
- Line number is exact, not approximate
- Only available when ast-grep is present (Forge/Deep tier)

### Example 2: T1-low — Source-Read Extraction

**Context:** Quick tier extraction reads source files without AST parsing.

**Implementation:**
```markdown
## `createServer(options)`

Creates and configures an HTTP server instance.

**Parameters:**
| Name | Type | Required | Default |
| --- | --- | --- | --- |
| options | `object` | yes | — |

[SRC:src/server.ts:L23] — type inferred from usage, not structurally verified
```

**Key Points:**
- Same function, but parameter type is `object` not `ServerOptions` — pattern matching missed the type alias
- Citation explicitly notes the inference limitation
- Still useful — location is correct, signature is close

### Example 3: T2 — QMD Enrichment

**Context:** Deep tier enriches an extracted API with usage patterns from QMD knowledge base.

**Implementation:**
```markdown
### Usage Context

`createServer` is typically used with `loadMiddleware()` in application bootstrap.
Common pattern: create server first, then attach middleware chain before calling `.listen()`.

[QMD:project-docs:architecture-overview]
```

**Key Points:**
- Enrichment adds context, not structural claims
- QMD citations reference collection and document, not line numbers
- T2 content appears in enrichment sections, not in API signatures

### Example 4: Tier Interaction During Updates

**Context:** An update-skill workflow detects that a T1-low claim now contradicts fresh T1 extraction.

**Implementation:** The merge algorithm applies tier precedence:
1. T1 always overrides T1-low for the same export
2. T2 enrichments are preserved unless the underlying T1/T1-low claim changed
3. T3 references are flagged for manual review if the API they describe changed

**Key Points:**
- Higher confidence tiers take precedence in merge conflicts
- T2 enrichments are additive — they don't conflict with structural claims
- T3 references may go stale and are flagged, not auto-removed

## Confidence Distribution in Metadata

Every generated skill includes a confidence distribution in `metadata.json`:

```json
{
  "confidence_distribution": {
    "t1": 42,
    "t1_low": 5,
    "t2": 12,
    "t3": 3
  },
  "confidence_tier": "Deep"  // valid values: "Quick", "Forge", "Forge+", "Deep"
}
```

This distribution feeds into test-skill scoring — skills with higher T1 ratios score better on signature accuracy.

## Anti-Patterns

- Omitting the confidence tier from a citation — every citation must declare its level
- Using T1 format (`[AST:...]`) when ast-grep was not actually used for that extraction
- Treating T1-low and T1 as equivalent during scoring — they have different weight impacts
- Adding T2 enrichment without a QMD citation — enrichment without provenance is hallucination

## Related Fragments

- [zero-hallucination.md](zero-hallucination.md) — the principle that motivates tiered confidence
- [provenance-tracking.md](provenance-tracking.md) — how citations are recorded in provenance-map.json
- [progressive-capability.md](progressive-capability.md) — how forge tier determines available confidence levels

_Source: consolidated from extraction-patterns.md, create-skill steps 03/05, and scoring-rules.md_
