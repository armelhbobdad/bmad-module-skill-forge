# Integration Verification Rules

## Purpose

Rules for cross-referencing API surfaces between two skills to determine integration feasibility.

---

## Verdict Definitions

| Verdict | Meaning | Required Evidence |
|---------|---------|-------------------|
| **Verified** | APIs demonstrably connect — matching types, documented bridge, or shared protocol | At least one export from Skill A is consumable by an API in Skill B (or vice versa) with compatible types |
| **Plausible** | Compatible types or protocols but no documented integration path | Both libraries operate in compatible domains with compatible data formats, but no direct API bridge is evident |
| **Risky** | Type mismatch, protocol gap, or language boundary requiring a bridge | A clear gap exists (e.g., TypeScript↔Rust FFI needed) but a workaround is architecturally feasible |
| **Blocked** | Fundamental incompatibility — no feasible integration path even with a bridge or adapter layer | The two libraries cannot exchange data in any documented way; requires replacing one of the libraries |

---

## Cross-Reference Protocol

For each integration pair (Library A ↔ Library B):

### 1. Language Boundary Check

| A Language | B Language | Assessment |
|-----------|-----------|------------|
| Same language | Same language | No boundary — direct API calls possible |
| TypeScript ↔ Rust | Requires FFI, IPC, or WebSocket bridge | Check if a bridge library exists in the stack (e.g., Tauri provides JS↔Rust IPC) |
| TypeScript ↔ Python | Requires REST/gRPC/WebSocket bridge | Typically not direct |
| Any ↔ C/C++ | FFI available in most languages | Check for bindings |

### 2. Protocol Compatibility Check

| A Protocol | B Protocol | Assessment |
|-----------|-----------|------------|
| In-process (same runtime) | In-process | Direct — function calls |
| HTTP/REST | HTTP/REST | Network bridge — compatible if API endpoints match |
| WebSocket | WebSocket | Real-time bridge — check message format compatibility |
| Shared filesystem | Shared filesystem | Async — check format compatibility |
| Embedded database | Embedded database | May conflict on lock files — check for multi-writer support |

### 3. Type Compatibility Check

- Extract the primary data types each library produces/consumes from the skill's export list
- Check: does Library A export a type that Library B accepts as input?
- Common patterns: JSON serialization (universal bridge), binary formats (check codec), shared schemas (strong compatibility)

### 4. Documentation Cross-Reference

- Search Skill A's content for mentions of Library B's name
- Search Skill B's content for mentions of Library A's name
- If either mentions the other: strong evidence of documented integration
- Check if either library's README lists the other as a companion/integration

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
