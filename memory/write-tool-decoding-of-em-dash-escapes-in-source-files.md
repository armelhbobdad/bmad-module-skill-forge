---
created: "2026-09-28 13:06"
session: "1eac7d31-a255-4a86-b7ad-388ffb7624ab"
---

# Write tool decoding of em dash escapes in source files

The Write tool can decode JavaScript escapes for U+2014 and U+2013 (`\u2014`, `\u2013`) in regex and string literals into the raw characters on disk, while control-character escapes such as `\u001B` in the same file stay intact. It hit `tools/validate-no-em-dash.js` (the `EM_DASH` regex) and `test/test-validate-no-em-dash.js` (`const D`), and the tests still passed. Only a grep for the raw character, or `npm run validate:em-dash`, which fails on any added line holding U+2014, reveals it. After writing source that needs such an escape, scan the file for non-ASCII characters (`grep -nP '[^\x00-\x7F]' <file>`) before committing. To restore an escape, edit with Python and build the backslash from `chr(92)` so it cannot be decoded again, or avoid the escape: the validator now builds its pattern with `String.fromCodePoint(0x20_14)`, the form ESLint's `unicorn/prefer-code-point` and `unicorn/numeric-separators-style` rules accept.
