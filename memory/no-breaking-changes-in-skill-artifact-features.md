---
created: "2026-03-21 20:23"
session: "d861eaa9-da63-4075-99fb-dc178fa8291a"
source: claude-mem
source_table: observations
source_ids: [2123, 2149, 2160]
---

# No-breaking-changes constraint on skill artifact features

Feature work that touches the compiled-skill artifacts (`metadata.json`, `provenance-map.json`, SKILL.md sections) runs under a hard constraint the user set for the scripts/assets feature: "Moreover, we do not introduce any breaking changes, missing impacts, etc...". In practice: every new artifact field is optional, every new SKILL.md section is conditional (Section 7b Scripts & Assets in `src/skf-create-skill/assets/skill-sections.md` is emitted only when an inventory is non-empty), and every workflow that consumes the artifact is traced end to end — today `src/skf-quick-skill`, `skf-test-skill`, `skf-update-skill`, `skf-audit-skill`, `skf-export-skill`, `skf-rename-skill` and `skf-create-stack-skill` all read `metadata.json` / `provenance-map.json`. The trap this guards against is real: a deep review of that feature found `skf-update-skill` detected script/asset changes but had no merge logic and no `file_entries` write until fixed (now `references/merge.md` Category D and `references/write.md` "For script/asset file changes"). `docs/_internal/STABILITY.md` only governs the npm/CLI surface and marks step-file internals `@internal`; it does not relax this constraint for skills already compiled on users' disks.
