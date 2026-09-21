---
created: "2026-04-07 23:39"
session: "8bcb9111-b354-4301-ab90-f1e2a73bbfdf"
source: claude-mem
source_table: observations
source_ids: [4544, 4551]
---

# validate-skills.js, validate-file-refs.js and platform-codes.yaml are adapted BMAD-METHOD copies

`tools/validate-skills.js`, `tools/validate-file-refs.js` and `tools/cli/lib/platform-codes.yaml` were copied from BMAD-METHOD (`tools/validate-skills.js`, `tools/validate-file-refs.js`, `tools/installer/ide/platform-codes.yaml` there; a checkout lives at `../BMAD-METHOD`) and then patched for SKF, and nothing in the file headers or CONTRIBUTING.md says so. The SKF deltas: `NAME_REGEX = /^(?:bmad|skf)-[a-z0-9]+(-[a-z0-9]+)*$/` (upstream accepts `bmad-` only), `WF_SKIP_SKILLS` emptied (upstream skips `bmad-agent-tech-writer`), a `steps-c` fallback in `validateSkill` that is now vestigial because stage prompts live in `references/`, the `_bmad/skf/` to `src/` mapping plus SKF entries in `UNRESOLVABLE_VARS` and `INSTALL_ONLY_PATHS` in the refs validator, and in platform-codes.yaml the `skill_invocation_prefix` keys and Junie's `target_dir: .junie/skills` (upstream: `.agents/skills`), which docs/_internal/STABILITY.md declares part of the v1.0.0 install contract. Upstream is the reference when rules or IDE lists change, but re-copying it verbatim makes every `skf-*` skill fail SKILL-04 and silently changes an install path.
