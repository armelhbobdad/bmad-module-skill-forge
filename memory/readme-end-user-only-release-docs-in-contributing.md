---
created: "2026-05-18 17:49"
session: "900827df-c0f7-4954-b899-977f414b6435"
source: claude-mem
source_table: observations
source_ids: [10102, 10103, 10104, 10105]
---

# README is end-user only; release docs live behind CONTRIBUTING.md

README.md carries end-user material only. The `## Versioning & Stability` and `## Release Process` sections (pointing at docs/\_internal/STABILITY.md and docs/\_internal/RELEASING.md) were removed in commit b3e4e31e (v1.5.0) at the user's request: "I want to remove these section from the @README.md ... I don't think they are usefull anymore." Maintainer material is reached through the `## Releasing` section of CONTRIBUTING.md ('Maintainers only'), which links RELEASING.md and its rollback playbook, so do not re-add release or versioning sections to README. Beware that the rename-coupling paragraph of docs/\_internal/RELEASING.md still says to update 'the `## Release Process` enumeration in `README.md`'; that section no longer exists and the CONTRIBUTING.md `## Releasing` text is what to update instead.
