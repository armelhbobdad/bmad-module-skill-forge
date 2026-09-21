---
created: "2026-04-09 01:18"
session: "59c7313e-e858-4b50-adc3-7e7cd9e3d750"
source: claude-mem
source_table: observations
source_ids: [4939, 4947]
---

# Timestamped SKF:BEGIN managed-section markers

export-skill writes managed-section markers with a timestamp — `<!-- SKF:BEGIN updated:YYYY-MM-DD -->` per `src/skf-export-skill/assets/managed-section-format.md` — never the bare `<!-- SKF:BEGIN -->`. `src/shared/scripts/skf-rebuild-managed-sections.py` once matched the bare literal, so `check`/`read`/`replace`/`clear` silently found no section in every real exported CLAUDE.md/AGENTS.md; the fix is `BEGIN_MARKER_PREFIX = "<!-- SKF:BEGIN"` plus `MARKER_PATTERN = r"(<!-- SKF:BEGIN[^>]*-->)(.*?)(<!-- SKF:END -->)"` (`skf-count-tokens.py` uses the same regex). Any new script or prose step that detects the section must match the prefix, not the closed literal — `src/skf-drop-skill/references/execute.md` and `src/skf-rename-skill/references/execute.md` still spell the bare `<!-- SKF:BEGIN -->` in their marker checks. Keep the timestamped `SAMPLE_FILE` fixture in `test/test-skf-rebuild-managed-sections.py` next to the bare one: bare-only fixtures are exactly what masked the bug.
