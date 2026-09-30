---
created: "2026-09-30 12:40"
session: "1eac7d31-a255-4a86-b7ad-388ffb7624ab"
---

# datetime.fromtimestamp fails on Windows for far-future timestamps

On Windows, `datetime.fromtimestamp(seconds, tz=timezone.utc)` goes through the C runtime, which rejects timestamps far in the future: `test/test-skf-emit-result-envelope.py::test_utc_parts_match_the_calendar[253402300799]` (the last second of year 9999) raised `OSError: [Errno 22] Invalid argument` on `python (windows-latest)` while ubuntu passed (PR #616, fixed in 0cffac19). Epoch arithmetic has no such limit and is exact on every platform: `datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=seconds)`. Use it wherever a script or a test turns an arbitrary or far-future timestamp into a date, a test's expected value included.
