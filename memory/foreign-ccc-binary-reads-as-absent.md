---
created: "2026-05-15 14:18"
session: "aa307bf9-20a5-4395-aa9d-821b8dc28003"
source: claude-mem
source_table: observations
source_ids: [9538, 9589, 9591]
---

# Foreign ccc binary is reported exactly like a missing ccc

`probe_ccc()` in `src/shared/scripts/skf-detect-tools.py` (lines 266-274) returns `{"available": False, "daemon": None, "version": None}` both when `ccc` is not on PATH and when `ccc --help` exits 0 but its output lacks the `cocoindex code` identity marker (`CCC_IDENTITY_MARKER`, line 131), i.e. a PATH-shadowing alias such as code2prompt. Downstream nothing can tell the cases apart, so the skf-setup climb hint (`src/skf-setup/references/report.md:56`) tells a user who already installed cocoindex-code to "Install cocoindex-code". `qmd` already carries a `status` enum (absent / daemon_stopped / healthy, lines 252-264); the proposed fix is a parallel `ccc.status` with a `foreign_binary` value that report.md can branch on. As of v2.1.0 it is not built and no GitHub issue tracks it, so anyone touching probe_ccc or the climb hints should treat this as the known blind spot.
