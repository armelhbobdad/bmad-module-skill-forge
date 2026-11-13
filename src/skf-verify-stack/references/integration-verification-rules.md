# Integration Verification Rules

## Verdict Definitions

Token set is defined canonically in the SKF shared feasibility report schema (`{project-root}/_bmad/skf/shared/references/feasibility-report-schema.md` in installed mode; `{project-root}/src/shared/references/feasibility-report-schema.md` in a dev checkout); the table below restates the same set with this skill's evidence obligations. Tokens are case-sensitive (`Verified`, `Plausible`, `Risky`, `Blocked`); emitting any other token is a schema violation.

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

- Same `language` on both skills: direct calls. Different languages: the pair needs a bridge (FFI, IPC or a network protocol).
- The load-bearing nudge: **check whether a bridge library already exists in the stack** before assuming one must be built (e.g., Tauri provides JS↔Rust IPC).

### 2. Protocol Compatibility Check

- Input: each skill's `protocols_inferred` and `data_formats_inferred` tokens, inferred from its SKILL.md prose. Conflicting transports or formats with no adapter in the stack flag a risk. A shared or complementary token (e.g. "HTTP client" and "HTTP server"), or no token on either side, flags none: the tokens are too weak to prove compatibility, and a library pair that names no transport usually calls in-process.
- The load-bearing nudge: **two embedded databases may conflict on lock files — check for multi-writer support** before treating them as compatible.

### 3. Type Compatibility Check

- Passes when a type one skill's `exports` produce is one the other skill's `exports` accept, each cited by its signature.

### 4. Documentation Cross-Reference (required for `Verified`)

- Search Skill A's SKILL.md for a literal substring/name citation of Library B, and Skill B's SKILL.md for the reciprocal citation. The shared SKILL.md scanner runs that search (`skf-scan-skill-md-structure.py cross-reference`, integrations.md §4): a citation is a hit it lists, never a line read from a SKILL.md
- A hit that only matches a common word does not count (`the next step` for a skill named `next`): quote the first hit whose excerpt names the library, and a direction whose hits name only the common word has no citation
- A pass requires at least one literal citation in at least one direction; record the exact substring and its line in the evidence block. A fail brings the Plausible cap above into play.
