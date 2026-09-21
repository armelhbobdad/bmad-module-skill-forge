---
created: "2026-04-04 16:15"
session: "df728e58-0eb9-400c-b12a-7050f7f8c623"
source: claude-mem
source_table: both
source_ids: [4226, 4229]
---

# Export-skill gotchas carry-forward exists because the evidence report is never loaded

`src/skf-export-skill/references/generate-snippet.md` §3 step 5 says to derive the `|gotchas:` line from "T2-future annotations in evidence report", but export-skill's step 1 (`references/load-skill.md`, "Load all files") reads only `SKILL.md`, `metadata.json`, `references/` and the prior `context-snippet.md` from `{resolved_skill_package}` — `{forge_version}/evidence-report.md` is never loaded, so on a re-export without a fresh create/update cycle the derivation yields nothing. That is why §2.5 reads the prior snippet's `|gotchas:` line and §3.5 carries it forward with a `[CARRIED]` prefix and the warning "**Gotchas preserved from prior export (one-cycle carry-forward).** These gotchas will be DROPPED on the next export unless new gotchas are derived or you manually refresh them." (first export: prior gotchas are treated as fresh; second carry: the line is dropped with "**Stale gotchas dropped**"). The carry-forward tree is intentional fallback logic, not dead code — do not simplify it away, and if gotchas keep vanishing the real fix is to load the evidence report, not to loosen the expiry. First hit on a tanstack-db re-export in 2026-04 (fix 4a7ada1, refined by c804264 for #298).
