# Zero Hallucination Principle

## Principle

Every instruction, signature, parameter, and behavioral claim in a generated skill must trace to a verifiable source location. Content that cannot be cited from source code, documentation, or verified external references is excluded — never guessed, inferred, or fabricated.

## Rationale

Agent skills direct other AI agents to use libraries and APIs. A hallucinated parameter name, an invented default value, or a fabricated usage pattern will cause the consuming agent to generate broken code. Unlike documentation aimed at humans who can cross-reference, skills are consumed by agents that treat every statement as ground truth.

Without zero hallucination enforcement:
- Agents follow fabricated instructions and produce broken code
- Confidence in the entire skill degrades when any claim proves false
- Users lose trust in the forge pipeline and revert to manual documentation

With zero hallucination enforcement:
- Every claim is backed by a source citation with file, line number, and confidence tier
- Gaps in knowledge produce explicit "not extracted" markers rather than guesses
- Skills become machine-verifiable evidence documents, not prose summaries

## Pattern Examples

### Example 1: Export Signature Extraction

**Context:** Creating a skill for a TypeScript library with exported functions.

**Implementation:** The extraction step reads source files and records each export with its exact signature, parameters, return type, and source location. If a parameter has no explicit type annotation, the skill records it as `unknown` with a T1-low citation rather than inferring the type from usage patterns.

```
## `parseConfig(input: string): Config`
[AST:src/parser.ts:L42]

## `validate(data: unknown): boolean`
[SRC:src/validator.ts:L18] — parameter type not annotated in source
```

**Key Points:**
- Exact signatures from source, not from README examples
- Missing type information acknowledged, not filled in
- Citation format includes file path and line number

### Example 2: Handling Undocumented Behavior

**Context:** Source code contains a function with side effects not described in JSDoc.

**Implementation:** The skill documents only what can be structurally verified. Observable side effects (file writes, network calls) are noted only if they appear in the function body with verifiable call sites. Behavioral nuances described nowhere in source are omitted with a coverage gap note.

```
### Coverage Gaps
- `initializeCache()` — internal caching behavior not fully traceable;
  implementation references external service not available for inspection
```

**Key Points:**
- Absence is documented as a gap, not filled with speculation
- Coverage gaps inform the test-skill scoring (reduces coverage score, not coherence)
- Gaps are actionable — they tell the user what to add via \[MANUAL\] sections

### Example 3: Quick Tier Without AST

**Context:** Operating at Quick tier where ast-grep is unavailable.

**Implementation:** Extraction relies on source reading and pattern matching. All citations use `[SRC:file:Lnn]` format (T1-low confidence). The skill clearly states its extraction tier so consuming agents understand the confidence level.

```json
// metadata.json (excerpt)
{
  "confidence_tier": "Quick",
  "confidence_distribution": {
    "t1": 0,
    "t1_low": 47,
    "t2": 0,
    "t3": 3
  }
}
```

**Key Points:**
- Quick tier skills are legitimate — lower confidence, not lower integrity
- T1-low citations still reference real source locations
- Metadata makes the confidence distribution transparent

## Anti-Patterns

- Inferring return types from variable names or function names — use `unknown` if not annotated
- Copying usage examples from README without verifying they match current source signatures
- Describing "typical usage patterns" from training data rather than from the actual codebase
- Omitting the confidence tier from citations — every citation must declare its trust level

## Checklist

- [ ] Every API signature extracted from source, not from memory or documentation alone
- [ ] Missing information produces gaps, not guesses
- [ ] All citations include source file, line number, and confidence tier
- [ ] metadata.json reflects actual confidence distribution
- [ ] Quick tier skills clearly labeled as T1-low extraction

## Related Fragments

- [confidence-tiers.md](confidence-tiers.md) — defines the T1/T1-low/T2/T3 trust model
- [provenance-tracking.md](provenance-tracking.md) — the mechanism for recording and verifying citations
- [progressive-capability.md](progressive-capability.md) — how tier affects extraction without compromising integrity

_Source: distilled from agent principles, create-skill extraction logic, and update-skill merge rules_
