# Architecture Verification

## Principle

A tech stack is only as strong as its weakest integration point. Architecture verification cross-references generated skills against architecture documents to produce evidence-backed feasibility verdicts — before a single line of application code is written. Every verdict must cite specific APIs, types, or function signatures from the generated skills. Speculation is labeled; evidence is cited.

## Rationale

Architects commonly evaluate tech stacks by reading documentation, building proof-of-concepts, or asking on forums. This process is slow, incomplete, and leaves integration risks undiscovered until implementation. SKF's pre-code verification pipeline replaces guesswork with systematic cross-referencing:

1. Generate skills for each candidate library (CS/QS) — producing T1/T2 extraction data
2. Run Verify Stack (VS) — cross-reference extracted APIs against architecture integration claims
3. Run Refine Architecture (RA) — improve the architecture doc with verified API evidence
4. Run Stack Skill compose mode (SS) — synthesize a consolidated integration playbook

Without architecture verification:
- Integration risks surface during implementation (costly, late)
- Architecture documents describe intent without evidence
- Library selection is based on feature lists, not API compatibility

With architecture verification:
- Integration feasibility is validated pre-code with API-level evidence
- Architecture documents become evidence-backed engineering artifacts
- Library swaps happen in minutes (regenerate skill, re-run VS) not days

## Verification Passes

### Pass 1: Coverage Verification

Check that a generated skill exists for every technology referenced in the architecture document. Coverage gaps mean unverified assumptions about library capabilities.

- **Covered**: Skill exists — APIs are known
- **Missing**: Referenced but no skill — capabilities are assumed, not verified

### Pass 2: Integration Verification

For each integration claim in the architecture document, cross-reference the API surfaces of both libraries:

- **Verified**: APIs demonstrably connect — matching types, documented bridge, or shared protocol
- **Plausible**: Compatible types or protocols but no documented integration path
- **Risky**: Type mismatch, protocol gap, or language boundary requiring a bridge
- **Blocked**: Fundamental incompatibility — no feasible integration path

Cross-reference protocol:
1. Language boundary check (same language → direct calls; TypeScript↔Rust → needs FFI/IPC)
2. Protocol compatibility (in-process, HTTP, WebSocket, shared filesystem)
3. Type compatibility (does A export something B accepts?)
4. Documentation cross-reference (does either library mention the other?)

### Pass 3: Requirements Verification

If a PRD/vision document is provided, verify the stack covers stated capability requirements:

- **Fulfilled**: Stack capabilities demonstrably address the requirement
- **Partially Fulfilled**: Some aspects covered, gaps remain
- **Not Addressed**: No library in the stack covers this requirement

## Iteration Loop

The core value of architecture verification is the iteration loop:

1. VS produces verdicts → user reads RISKY/BLOCKED items
2. User swaps a library → generates new skill via CS/QS
3. User re-runs VS → sees delta: "Previously RISKY, now VERIFIED"
4. Repeat until FEASIBLE

Each VS run should produce a diff from the previous run when a prior feasibility report exists. This makes the iteration cycle visible and measurable.

## Evidence Citation Format

All verdicts cite evidence from generated skills:

```
Library A exports: `function_name(params) → return_type` [from skill: skill-name]
Library B accepts: `function_name(params)` [from skill: skill-name]
Compatibility: {explanation}
```

## Lifecycle Position

Architecture verification sits between individual skill generation and stack skill synthesis:

```
(CS|QS)×N → VS → RA → SS (compose) → TS → EX → Implementation → SS (code-mode)
```

VS and RA are pre-code workflows. SS compose-mode synthesizes the implementation playbook. After the codebase grows, SS code-mode (the standard stack-skill mode that analyzes manifests and source) captures actual usage patterns — completing the lifecycle.

## Anti-Patterns

- Treating VS verdicts as absolute — they are evidence-based assessments, not guarantees
- Running VS without generating skills first — VS reads skills, it does not create them
- Skipping the iteration loop — the first VS run often reveals gaps that require library swaps
- Using VS output as a SKILL.md — VS produces a feasibility report, not a skill; use SS compose-mode for the stack skill

## Related Fragments

- [confidence-tiers.md](confidence-tiers.md) — T1/T2/T3 trust model for verdict evidence
- [skill-lifecycle.md](skill-lifecycle.md) — end-to-end pipeline and workflow connections
- [progressive-capability.md](progressive-capability.md) — tier philosophy for skill generation

_Source: synthesized from skf-verify-stack/SKILL.md, skf-refine-architecture/SKILL.md, and skf-create-stack-skill/references/compose-mode-rules.md_
