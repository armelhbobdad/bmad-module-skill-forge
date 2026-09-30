# Integration Verification Rules

## Purpose

Rules for cross-referencing API surfaces between two skills to determine integration feasibility.

---

## Verdict Definitions

Token set is defined canonically in the SKF shared feasibility report schema (`_bmad/skf/shared/references/feasibility-report-schema.md` in installed mode; `src/shared/references/feasibility-report-schema.md` in a dev checkout) — the table below restates the same set with this skill's evidence obligations. Tokens are case-sensitive (`Verified`, `Plausible`, `Risky`, `Blocked`); emitting any other token is a schema violation.

| Verdict | Meaning | Required Evidence |
|---|---|---|
| **Verified** | APIs demonstrably connect and at least one skill cites the other | Check 1 (language) passes with declared evidence; Check 2 (protocol) flags no risk; Check 3 (types) passes from cited `exports` signatures; **Check 4 (docs cross-reference) passes with a literal substring/name citation** |
| **Plausible** | The checks pass, but neither skill cites the other | Checks 1 to 3 pass as for `Verified`; Check 4 finds no literal citation, so the Plausible cap below applies |
| **Risky** | Type mismatch, protocol gap, or language boundary requiring a bridge | A clear gap exists (e.g., TypeScript↔Rust FFI needed) but a workaround is architecturally feasible: cite a named workaround in the recommendation |
| **Blocked** | Fundamental incompatibility: no feasible integration path even with a bridge or adapter layer | The two libraries cannot exchange data in any documented way; requires replacing one of the libraries |

**Plausible cap:** when Check 4 finds no literal citation in either direction, cap the pair at `Plausible`: it can be `Plausible`, `Risky` or `Blocked`, never `Verified`. This is the only cap. Check 2 reads protocol and data-format tokens inferred from each skill's prose, so it can flag a risk, but it never promotes a pair to `Verified` and never caps one at `Plausible`. A pair whose Checks 1 to 3 pass and whose Check 4 finds a literal citation is `Verified`. This is the producer obligation the shared schema declares.

---

## Cross-Reference Protocol

For each integration pair (Library A ↔ Library B):

### 1. Language Boundary Check

- Same language on both sides → no boundary, direct API calls. Different languages → the integration needs a bridge (FFI, IPC, or a network protocol; the mechanism follows from the pair — e.g. C/C++ exposes FFI most languages can bind).
- The load-bearing nudge: **check whether a bridge library already exists in the stack** before assuming one must be built (e.g., Tauri provides JS↔Rust IPC).

### 2. Protocol Compatibility Check

- Input: each skill's `protocols_inferred` and `data_formats_inferred` tokens, inferred from its SKILL.md prose. Conflicting transports or formats with no adapter in the stack flag a risk. A shared or complementary token (e.g. "HTTP client" and "HTTP server"), or no token on either side, flags none: the tokens are too weak to prove compatibility, and a library pair that names no transport usually calls in-process.
- Matching transports are compatible modulo format alignment: both in-process → direct calls; both HTTP/REST → compatible if endpoints match; both WebSocket → check message-format compatibility; both shared-filesystem → async, check format.
- The load-bearing nudge: **two embedded databases may conflict on lock files — check for multi-writer support** before treating them as compatible.

### 3. Type Compatibility Check

- Extract the primary data types each library produces/consumes from the skill's export list
- Check: does Library A export a type that Library B accepts as input?
- Common patterns: JSON serialization (universal bridge), binary formats (check codec), shared schemas (strong compatibility)

### 4. Documentation Cross-Reference (required for `Verified`)

- Search Skill A's SKILL.md for a literal substring/name citation of Library B
- Search Skill B's SKILL.md for the reciprocal citation
- Accept literal names or aliases declared in that skill's metadata; a paraphrase or fuzzy match does not satisfy Check 4
- A pass requires at least one literal citation in at least one direction; record the exact substring and location in the evidence block. A fail brings the Plausible cap above into play.

---

## Verdict Evidence Format

Each verdict includes:

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
