---
created: "2026-04-04 21:18"
session: "7070fa3d-9a71-4237-8b63-c0f357f172e0"
source: claude-mem
source_table: observations
source_ids: [4385, 4392, 5224, 5226, 5231, 5232, 5236]
---

# No unverified assertions in docs/

The user's standing rule for `docs/`: every claim must be verifiable against `src/` — "carefully review, verify and rewrite the entire @docs/ so we will not have unverify assertion anymore". The April 2026 rewrite removed a fictional `manifest_reader` utility from `docs/how-it-works.md` (manifest detection is a reference pattern in `skf-create-stack-skill/references/manifest-patterns.md`, not a tool), replaced invented timing headings ("47 Seconds", "8 Minutes") with "Under a minute" / "Pipeline or per-workflow", generalised a hardcoded `skills/cognee/0.5.5/` path to `<version>`, replaced the setup banner with real captured output, dropped an invented Analyze Source "unknowns for the risk register" artifact from `docs/bmad-synergy.md`, and deleted command examples that do not run (`forge lodash`). `CONTRIBUTING.md` does not state this, so when writing docs: capture real output, name only tools and files that exist in `src/`, and avoid timings, versions or outputs you cannot reproduce.
