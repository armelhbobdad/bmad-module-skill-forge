<!-- House style: the finding types and tiers Steps 02-05 classify with. Step 01 checks it, and `workflow.refinement_rules_path` can swap it for a team's copy. -->

# Architecture Refinement Rules

## What a Copy Can Change

`workflow.refinement_rules_path` replaces this whole file with a team's copy, so a copy starts from this file. It can add, rename, drop or redefine the gap, issue and improvement types, name its own severity and value tiers and say when each applies, and decide which tier each [VS] verdict raises. It keeps the six tables below under their headings, since the steps read them by name: Step 01 halts on a copy that lacks one.

What each step looks for is fixed: the types label what a step finds, so a type a copy drops does not stop the step finding it, and a finding no type fits takes the closest type.

Each tier becomes a count of the Refinement Summary, `{<tier>_count}` (the name in lower case, spaces as `_`), so Step 01 also halts on a copy whose tiers break these rules: a tier name starts with a letter and holds only the letters A to Z, digits and spaces; no two tiers share a name, ignoring case, in one table or across the two (so High, Medium and Low cannot name both severity and value); no tier is named Gap, Issue, Improvement, Unverified or Skill, whose counts the summary already holds; and each VS Report Integration row raises a tier of the Issue Severity table, or no issue.

Everything else is fixed, whatever a copy says. The step files decide which skills and pairs are analyzed (the document scope of Step 02 §2b), `references/finding-storage.md` decides how Steps 02-04 store their findings, and the refined document's headings, callouts, RA markers, placement and preservation check are set by Step 05: compile.md and `scripts/skf-check-preservation.py` own them, so an override of this file cannot change them.

---

## Gap Classification

A gap is an undocumented integration path: two in-scope skills whose APIs could connect while the architecture never describes how they interact.

| Gap Type                     | Description                                                            | Example                                                                              |
|------------------------------|------------------------------------------------------------------------|--------------------------------------------------------------------------------------|
| **Missing Integration Path** | Two libraries can connect but the architecture never describes how     | Skill A exports JSON producer, Skill B accepts JSON input, no mention of A-to-B flow |
| **Undocumented Data Flow**   | Data moves between libraries but the flow is not described             | Architecture mentions both libraries but not their data exchange mechanism           |
| **Absent Bridge Layer**      | Cross-language or cross-protocol libraries need a bridge not mentioned | Rust library and TypeScript library with no IPC/FFI description                      |

---

## Issue Classification

An issue is a contradiction between an architecture claim and the API evidence of the skills: an API that does not exist, an assumed compatibility that breaks, a bridge layer that is missing.

| Issue Type                    | Description                                                    | Example                                                                      |
|-------------------------------|----------------------------------------------------------------|------------------------------------------------------------------------------|
| **API Mismatch**              | Architecture describes an API that does not exist in the skill | "Library X exposes a streaming API" but skill shows only batch APIs          |
| **Protocol Contradiction**    | Architecture assumes a protocol the library does not support   | "Communicates via gRPC" but skill shows HTTP-only exports                    |
| **Language Boundary Ignored** | Architecture assumes direct calls across language boundaries   | "Calls Rust functions from TypeScript" with no FFI/IPC mechanism described   |
| **Type Incompatibility**      | Architecture assumes type compatibility that does not hold     | "Passes CRDT documents directly" but types are incompatible across libraries |

## Issue Severity

Each issue takes one severity tier. The tiers are listed most severe first: Step 05 orders issues by them and counts each one in the Refinement Summary.

| Severity     | When                                                                             |
|--------------|----------------------------------------------------------------------------------|
| **Critical** | The architecture needs a redesign: a fundamental language barrier with no bridge |
| **Major**    | A protocol mismatch or a missing bridge layer                                    |
| **Minor**    | A minor type difference with an easy conversion                                  |

## VS Report Integration

When the run uses a [VS] feasibility report, each in-scope pair verdict raises the issue this table maps its token to, citing the verdict and its rationale as additional evidence. The tokens are the feasibility-report schema's and are case-sensitive, and each rule keys on the token alone, never on phrases in the rationale text. A copy maps all four tokens, each to a severity tier of the table above or to no issue. A Raises cell raises what it bolds (a tier, or No issue or None), else what its text names; when that is more than one tier, or a tier and also No issue or None, Step 01 halts: bold only the one it raises.

| Verdict     | Raises                                                                                                     |
|-------------|------------------------------------------------------------------------------------------------------------|
| `Blocked`   | A **Critical** issue: the architecture needs a redesign                                                    |
| `Risky`     | A **Major** issue, confirmed by the VS evidence                                                            |
| `Plausible` | A **Minor**, potential issue: every compatibility check passed but neither skill cites the other literally |
| `Verified`  | No issue                                                                                                   |

---

## Improvement Classification

An improvement is a capability expansion, looked for in each in-scope skill (Step 02 §2b): a feature the skill documents that the architecture does not use, or two in-scope skills whose features combine in a way the architecture does not.

| Improvement Type          | Description                                                             | Example                                                                        |
|---------------------------|-------------------------------------------------------------------------|--------------------------------------------------------------------------------|
| **Unused Capability**     | Library has a feature the architecture does not mention                 | "Loro supports document CRDTs but architecture only uses data sync"            |
| **Cross-Library Synergy** | Two libraries have complementary features not combined in architecture  | "Library A's event system could feed Library B's stream processor"             |
| **Alternative Pattern**   | Skill documents a better pattern than the one described in architecture | "Skill shows batch API is more efficient than the per-item approach described" |

## Improvement Value

Each improvement takes one value tier. The tiers are listed most valuable first: Step 05 orders improvements by them and counts each one in the Refinement Summary.

| Value      | When                                                                                 |
|------------|--------------------------------------------------------------------------------------|
| **High**   | Addresses a known architectural concern or significantly expands functionality       |
| **Medium** | Adds convenience or efficiency                                                       |
| **Low**    | Nice to have, not impactful                                                          |
