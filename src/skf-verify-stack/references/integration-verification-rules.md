# Integration Verification Rules

## Purpose

Rules for cross-referencing API surfaces between two skills to determine integration feasibility.

---

## Verdict Definitions

Token set is defined canonically in the SKF shared feasibility report schema (`_bmad/skf/shared/references/feasibility-report-schema.md` in installed mode; `src/shared/references/feasibility-report-schema.md` in a dev checkout) — the table below restates the same set with this skill's evidence obligations. Tokens are case-sensitive (`Verified`, `Plausible`, `Risky`, `Blocked`); emitting any other token is a schema violation.

| Verdict       | Meaning                                                                                        | Required Evidence                                                                                                                                                                                                                                                   |
|---------------|------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Verified**  | APIs demonstrably connect AND docs cross-reference each other                                  | Check 1 (language) passes with declared evidence; Check 3 (types) passes from cited `exports` signatures; **Check 4 (docs cross-reference) MUST pass with a literal substring/name citation** — without Check 4 evidence, cap at `Plausible`. Check 2 is best-effort only and cannot by itself promote to `Verified`. |
| **Plausible** | Checks pass but rely on inferred or indirect evidence                                          | Language + type checks pass; Check 2 uses inferred `protocols_inferred`/`data_formats_inferred` (prose scan); Check 4 is weak or missing (no literal cross-reference). This is the mandatory cap whenever Check 4 does not surface a literal citation.             |
| **Risky**     | Type mismatch, protocol gap, or language boundary requiring a bridge                           | A clear gap exists (e.g., TypeScript↔Rust FFI needed) but a workaround is architecturally feasible — a named workaround MUST be cited in the recommendation                                                                                                        |
| **Blocked**   | Fundamental incompatibility — no feasible integration path even with a bridge or adapter layer | The two libraries cannot exchange data in any documented way; requires replacing one of the libraries                                                                                                                                                              |

**Promotion rule:** `Verified` requires Check 4 evidence. If Checks 1 and 3 pass but Check 4 fails (no literal substring/name citation from either skill's SKILL.md), the verdict is capped at `Plausible`. This rule is enforced by step 3 §4 and is the producer obligation declared in the shared schema.

---

## Cross-Reference Protocol

For each integration pair (Library A ↔ Library B):

### 1. Language Boundary Check

| A Language          | B Language                             | Assessment                                                                       |
|---------------------|----------------------------------------|----------------------------------------------------------------------------------|
| Same language       | Same language                          | No boundary — direct API calls possible                                          |
| TypeScript ↔ Rust   | Requires FFI, IPC, or WebSocket bridge | Check if a bridge library exists in the stack (e.g., Tauri provides JS↔Rust IPC) |
| TypeScript ↔ Python | Requires REST/gRPC/WebSocket bridge    | Typically not direct                                                             |
| Any ↔ C/C++         | FFI available in most languages        | Check for bindings                                                               |

### 2. Protocol Compatibility Check

| A Protocol                | B Protocol        | Assessment                                                  |
|---------------------------|-------------------|-------------------------------------------------------------|
| In-process (same runtime) | In-process        | Direct — function calls                                     |
| HTTP/REST                 | HTTP/REST         | Network bridge — compatible if API endpoints match          |
| WebSocket                 | WebSocket         | Real-time bridge — check message format compatibility       |
| Shared filesystem         | Shared filesystem | Async — check format compatibility                          |
| Embedded database         | Embedded database | May conflict on lock files — check for multi-writer support |

### 3. Type Compatibility Check

- Extract the primary data types each library produces/consumes from the skill's export list
- Check: does Library A export a type that Library B accepts as input?
- Common patterns: JSON serialization (universal bridge), binary formats (check codec), shared schemas (strong compatibility)

### 4. Documentation Cross-Reference (required for `Verified`)

- Search Skill A's SKILL.md for a literal substring/name citation of Library B
- Search Skill B's SKILL.md for the reciprocal citation
- Accept literal names or aliases declared in that skill's metadata; do NOT accept paraphrase or fuzzy matches
- A pass requires at least one literal citation in at least one direction; the exact substring and location MUST be recorded in the evidence block
- If neither skill literally cites the other, Check 4 FAILS and the per-pair verdict MUST cap at `Plausible` (not `Verified`)

---

## Verdict Evidence Format

Each verdict MUST include:

```
**{Library A} ↔ {Library B}: {VERDICT}**

Evidence:
- A exports: `{function_name}({params}) → {return_type}` [from skill: {skill_name}]
- B accepts: `{function_name}({params})` [from skill: {skill_name}]
- Compatibility: {explanation}
- Language boundary: {same | bridge required via {mechanism}}

{If RISKY or BLOCKED:}
Recommendation: {actionable next step}
```
