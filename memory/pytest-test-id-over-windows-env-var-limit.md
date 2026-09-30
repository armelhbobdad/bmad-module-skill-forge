---
created: "2026-09-30 12:38"
session: "1eac7d31-a255-4a86-b7ad-388ffb7624ab"
---

# A pytest test id over 32767 characters errors on Windows

pytest copies each running test's node id into the `PYTEST_CURRENT_TEST` environment variable, and Windows refuses an environment variable longer than 32767 characters, so such a test errors at setup and at teardown with `ValueError: the environment variable is longer than 32767 characters`, on `python (windows-latest)` only. A parametrize case with no explicit id takes its id from the parameter: in `test/test-skf-enumerate-stack-skills.py` the case `"[" * 200000` (a manifest nested too deeply for the JSON parser) produced a 200150-character id and two errors on PR #617 (fixed in 68a80a69). Give any huge or generated parameter an explicit id, as in `pytest.param(value, expected, id="deeply-nested")`. `pytest --collect-only -q` lists every id, so an id near the limit can be found before CI runs.
