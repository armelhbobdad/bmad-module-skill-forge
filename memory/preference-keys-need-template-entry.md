---
created: "2026-04-09 00:22"
session: "4a1c1afc-7896-4732-8b7d-d05e14e39405"
source: claude-mem
source_table: session_summaries
source_ids: [1442, 1453, 1454]
---

# Preference keys must be added to the shipped preferences.yaml template

Every preference key that `src/shared/scripts/skf-preflight.py` (or any workflow step) reads from the Ferris sidecar `preferences.yaml` must also be added, with a comment and default, to the shipped template `src/forger/preferences.yaml`, which `tools/cli/lib/installer.js` copies to `_bmad/_memory/forger-sidecar/preferences.yaml` on install. Twice a key was wired into code but not the template (`headless_mode`, then `compact_greeting`), so fresh installs had no discoverable knob and the read silently fell back to its default. At v2.1.0 the template carries `tier_override`, `passive_context`, `headless_mode` and `compact_greeting`; no test compares template keys against the `prefs.get(...)` reads, so this stays a by-hand rule when adding a preference.
