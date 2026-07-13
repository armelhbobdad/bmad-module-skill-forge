<!-- Static reference loaded by gap-analysis.md, issue-detection.md, and improvements.md. -->

# Architecture Refinement Rules

## Purpose

Rules for detecting gaps, issues, and improvements in an architecture document using generated skill data as the evidence source.

---

## Gap Detection Rules

Gaps are undocumented integration paths — library pairs that have compatible APIs but no architecture description.

### Detection Method

1. Read the pre-computed unique library pairs from `skill_inventory.pairs` (emitted by the enumerate helper's `--pairs` flag) — do not re-derive them in-context
2. For each pair, check if both skills export APIs that could connect (compatible types, shared protocols, complementary producer/consumer patterns)
3. Cross-reference against the architecture document: does the document describe how these two libraries interact?
4. If compatible APIs exist but NO architecture description exists, this is a **gap**

### Gap Classification

| Gap Type                     | Description                                                            | Example                                                                              |
|------------------------------|------------------------------------------------------------------------|--------------------------------------------------------------------------------------|
| **Missing Integration Path** | Two libraries can connect but the architecture never describes how     | Skill A exports JSON producer, Skill B accepts JSON input, no mention of A-to-B flow |
| **Undocumented Data Flow**   | Data moves between libraries but the flow is not described             | Architecture mentions both libraries but not their data exchange mechanism           |
| **Absent Bridge Layer**      | Cross-language or cross-protocol libraries need a bridge not mentioned | Rust library and TypeScript library with no IPC/FFI description                      |

---

## Issue Detection Rules

Issues are contradictions between architecture claims and verified API reality from the skills.

### Detection Method

1. Extract every integration claim from the architecture document (prose co-mention analysis)
2. For each claim, verify against the actual API surfaces in the skills
3. Flag contradictions: claimed APIs that do not exist, assumed compatibility that breaks, missing bridge layers

### Issue Classification

| Issue Type                    | Description                                                    | Example                                                                      |
|-------------------------------|----------------------------------------------------------------|------------------------------------------------------------------------------|
| **API Mismatch**              | Architecture describes an API that does not exist in the skill | "Library X exposes a streaming API" but skill shows only batch APIs          |
| **Protocol Contradiction**    | Architecture assumes a protocol the library does not support   | "Communicates via gRPC" but skill shows HTTP-only exports                    |
| **Language Boundary Ignored** | Architecture assumes direct calls across language boundaries   | "Calls Rust functions from TypeScript" with no FFI/IPC mechanism described   |
| **Type Incompatibility**      | Architecture assumes type compatibility that does not hold     | "Passes CRDT documents directly" but types are incompatible across libraries |

### VS Report Integration

When a VS feasibility report is available:
- RISKY verdicts become **confirmed issues** with the VS evidence as additional citation
- BLOCKED verdicts become **critical issues** requiring architecture redesign
- Plausible verdicts become potential issues **only if** the VS rationale text explicitly states "no direct API evidence" or "weak evidence" — otherwise they are informational only

---

## Improvement Detection Rules

Improvements are capability expansions — library features documented in skills but not leveraged in the architecture.

### Detection Method

1. For each skill, enumerate its full API surface (all exports, types, protocols)
2. Compare against how the architecture uses that library
3. Identify capabilities present in the skill but absent from the architecture

### Improvement Classification

| Improvement Type          | Description                                                             | Example                                                                        |
|---------------------------|-------------------------------------------------------------------------|--------------------------------------------------------------------------------|
| **Unused Capability**     | Library has a feature the architecture does not mention                 | "Loro supports document CRDTs but architecture only uses data sync"            |
| **Cross-Library Synergy** | Two libraries have complementary features not combined in architecture  | "Library A's event system could feed Library B's stream processor"             |
| **Alternative Pattern**   | Skill documents a better pattern than the one described in architecture | "Skill shows batch API is more efficient than the per-item approach described" |

---

## Finding Storage (Steps 02-04)

Each analysis step stores its findings two ways: as workflow state for Step 05, and appended to `{forge_data_folder}/ra-state-{project_name}.md` as a labeled `<!-- [RA-...] ... -->` block holding the **complete formatted findings** — full citation blocks with evidence and suggestions, not just counts — so Step 05 can recover them if context degrades on a long run. The refined document itself is written once, in Step 05; Steps 02-04 never write to it.

---

## Preservation Rules

1. **Never delete original content** — only add annotations and subsections
2. **Follow original section layout** — add refinement subsections within existing sections
3. **Use callout blocks** for issues: `> [!WARNING]` or `> [!NOTE]` format
4. **Mark additions clearly** — prefix added subsections with "RA:" or use a refinement marker
5. **Maintain original heading hierarchy** — refinement subsections are one level deeper than the parent
