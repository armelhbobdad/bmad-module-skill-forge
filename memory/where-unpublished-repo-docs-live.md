---
created: "2026-04-23 12:33"
session: "bc54b00a-a138-475d-9c5b-a28ae8e97030"
source: claude-mem
source_table: both
source_ids: [6949, 6951, 6952, 6953, 6954]
---

# Where tracked-but-unpublished docs live

docs/ is the published site itself: website/src/content/docs is a symlink to ../../../docs, so any plain docs/*.md appears on the Starlight site and in the generated llms-full.txt. Only underscore-prefixed paths stay unpublished (Astro skips them by convention and tools/build-docs.js:236 excludes them from llms-full.txt), which is why maintainer docs live in docs/\_internal/ (RELEASING.md, STABILITY.md; commit 784921c4). \_bmad-output/ is gitignored (.gitignore:44), so anything put there is local-only and cannot be shared through git. Launch-gate audits are tracked but unpublished at repo-root release-audits/ (the v1.0.0 audit was moved out of docs/ because it was being published and its dotted filename produced a broken site slug); docs/\_internal/RELEASING.md:679 says only launch cuts get one, routine releases do not. Pick the location by these properties rather than dropping a new internal file into docs/.
