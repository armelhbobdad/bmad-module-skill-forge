---
created: "2026-04-08 00:37"
session: "7cba3f62-fa07-467b-9eac-6fc6674d6c0b"
source: claude-mem
source_table: observations
source_ids: [4598, 4625, 4668]
---

# detection_marker required for generic or installer-created skill dirs

`getDetectionMarkers()` in `tools/cli/lib/ide-skills.js` (line 60) derives an IDE's install-prompt auto-detection marker from the top-level directory of its `installer.target_dir` in `tools/cli/lib/platform-codes.yaml` unless `installer.detection_marker` is set. That derivation breaks two ways: when the installer itself creates the directory (Codex: `.agents/` from `.agents/skills`) detection can never fire before the first install, and when the directory is generic (GitHub Copilot's `.github/skills` was pre-checked in virtually every repo, Antigravity's `.agent/skills` in any repo with `.agent/`) the prompt falsely pre-selects the IDE. Explicit markers exist today for antigravity (`.agent/antigravity`), cline (`.clinerules`), codex (`.codex`) and github-copilot (`.github/copilot-instructions.md`), but the yaml header comment (lines 1-16) still documents only `target_dir` and `legacy_targets`, and no test covers the markers. Any new platform whose skills dir lives under a shared or installer-created directory (`.github`, `.agent`, `.agents`, `.config`) must set `detection_marker`.
