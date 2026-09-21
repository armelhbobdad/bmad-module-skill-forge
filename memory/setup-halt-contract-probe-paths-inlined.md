---
created: "2026-05-15 14:28"
session: "aa307bf9-20a5-4395-aa9d-821b8dc28003"
source: claude-mem
source_table: observations
source_ids: [9580, 9553, 9556]
---

# Envelope helper probe paths inlined in skf-setup SKILL.md

The "Halt contract for headless/quiet runs" blockquote in src/skf-setup/SKILL.md (On Activation) spells out the helper probe order itself — `{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py`, then `{project-root}/src/shared/scripts/skf-emit-result-envelope.py` — even though references/report.md and references/write-config.md carry the identical list as `emitEnvelopeProbeOrder` frontmatter. The duplication is deliberate: the `on-activation:uv-missing`, `on-activation:config-missing` and `on-activation:config-malformed` halts fire before any reference file has been loaded, so a cross-reference to a reference's frontmatter cannot be resolved at that point. An earlier version did point at report.md's frontmatter and left those bootstrap halts unable to emit a `status: blocked` envelope; 3dd864cd inlined the paths. Do not DRY them back into a reference frontmatter — the SKILL.md contract has to stay self-contained (and compaction-safe).
