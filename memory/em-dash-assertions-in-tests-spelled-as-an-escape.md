---
created: "2026-11-04 20:31"
session: "76fdf8e2-4067-429c-80c2-b3ed2b66e2e2"
---

# Em dash assertions in tests spelled as an escape

`npm run validate:em-dash` (`tools/validate-no-em-dash.js --strict`) runs in `npm test`, so in the husky pre-commit hook too, and in the `em-dash` job of quality.yaml. It checks every line a branch adds, test files included, so a test asserting that a file holds no em dash must not contain the character itself. On 2026-11-04 such an assert written with the literal character in `test/test-skf-test-skill-signature-rules.py` failed it with `1 em dash finding(s) in published docs, lines added since origin/main`. The repo spells the character as the escape `\u2014` inside the Python string (`test/test-skf-activation-customization.py:391`, `test/test-skf-campaign-provenance.py:133`). Writing that escape through the Edit and Write tools put the literal dash back, most likely because the escape decodes in the tool's JSON input, and a `sed` edit that writes the backslash sequence fixed it. After any edit meant to hold the escape, run `grep -nP '\x{2014}' <file>` before committing.
