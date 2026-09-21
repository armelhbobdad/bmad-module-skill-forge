---
created: "2026-04-17 19:58"
session: "6136f3e1-3e68-4154-932d-814217f75e88"
source: claude-mem
source_table: both
source_ids: [6184, 6185, 6186, 6187, 6188, 6192]
---

# Windows cp1252 default encoding in Python text I/O

The quality CI matrix runs the Python tests on `windows-latest` (.github/workflows/quality.yaml), where Python text I/O without `encoding="utf-8"` defaults to cp1252. Em-dashes and accents in SKILL.md, context-snippet.md or test fixtures then fail with `UnicodeDecodeError: 'utf-8' codec can't decode byte 0x97` (first hit in skf-validate-output.py's `read_text` of SKILL.md). Adding encoding to the readers alone (e7815bcf) made it worse, because the test `write_text()` calls still wrote cp1252 bytes; e06ac5f0 fixed the tests. The rule: every `open()` / `read_text()` / `write_text()` under src/shared/scripts, src/*/scripts and test/ passes `encoding="utf-8"`; only binary `"rb"` opens and the `os.open()` byte writes in skf-atomic-write.py are exempt. The same default bites stdio: a script that emits or reads JSON carrying non-ASCII must `reconfigure(encoding="utf-8")` its streams at entry (95039cac; see the `cp1252` regression tests in test/).
