# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""SKF Setup Args: the flags of one /skf-setup invocation, as JSON.

Setup Forge's On Activation item 1 runs this helper before anything else,
so every later halt knows whether to print its blocked envelope. The
invocation's arguments go in on stdin, exactly as given, through a quoted
heredoc, so no argument ever becomes a shell word:

  for r in "uv run" python3 python "py -3"; do
    out=$($r skf-setup-args.py <<'SKF_ARGS'
  --headless --require-tier=Deep
  SKF_ARGS
  ) && case "$out" in "{"*) printf '%s\\n' "$out"; break ;; esac
  done

Activation runs before `uv` is proven present, so a bare python3, python
or py -3 may run it: the helper is stdlib-only and keeps Python 3.9 syntax.

Input. stdin is read as UTF-8, a leading BOM dropped and bytes that are
not UTF-8 replaced; a terminal stdin is never read and means no arguments.
The text is split on whitespace (spaces, tabs, CR and line breaks alike).

Output. One JSON object on one stdout line, UTF-8, exit 0:

  {"headless": bool, "quiet": bool, "require_tier": str|null,
   "orphan_action": str|null, "ccc_skip_index": bool}

  headless        --headless or -H
  quiet           --headless, -H or --quiet
  ccc_skip_index  --ccc-skip-index
  require_tier    the value of --require-tier, and orphan_action that of
  orphan_action   --orphan-action: the text after "=", else the next token
                  unless it starts with "-" (that token is then read as a
                  flag), else ""; null when the flag is absent. The last
                  occurrence wins.

Every other token is ignored. The values stay exactly as given: step 1's
detector rejects a require_tier that names no tier. An orphan_action that
is non-null and not exactly keep or remove adds two keys:

  "phase":  "on-activation:orphan-action-invalid"
  "reason": "Setup cannot proceed: --orphan-action takes keep or remove,
             not <value>. Re-run with --orphan-action=keep or
             --orphan-action=remove." (one line; <value> as given, or
             "an empty value" for "")

The helper never halts the run itself: setup's halt contract passes the
reason to the envelope helper on stdin.
"""

from __future__ import annotations

import argparse
import json
import sys

# Flags that only switch a mode on, by the keys they set.
SWITCHES = {
    "--headless": ("headless", "quiet"),
    "-H": ("headless", "quiet"),
    "--quiet": ("quiet",),
    "--ccc-skip-index": ("ccc_skip_index",),
}
# Flags that take a value, by the key that holds it.
VALUED = {"--require-tier": "require_tier", "--orphan-action": "orphan_action"}
ORPHAN_ACTIONS = ("keep", "remove")
ORPHAN_PHASE = "on-activation:orphan-action-invalid"


def read_arguments(stream) -> str:
    """The invocation's arguments from stdin; a terminal or a missing stdin is no arguments."""
    if stream is None or stream.isatty():
        return ""
    return stream.buffer.read().decode("utf-8", "replace").lstrip("﻿")


def parse(text: str) -> dict:
    """The flags `text` holds, as the module docstring describes."""
    out = {"headless": False, "quiet": False, "require_tier": None, "orphan_action": None,
           "ccc_skip_index": False}
    tokens = text.split()
    i = 0
    while i < len(tokens):
        token = tokens[i]
        i += 1
        if token in SWITCHES:
            for key in SWITCHES[token]:
                out[key] = True
            continue
        name, eq, value = token.partition("=")
        if name not in VALUED:
            continue
        if not eq:
            value = ""
            if i < len(tokens) and not tokens[i].startswith("-"):
                value = tokens[i]
                i += 1
        out[VALUED[name]] = value
    action = out["orphan_action"]
    if action is not None and action not in ORPHAN_ACTIONS:
        given = action if action else "an empty value"
        out["phase"] = ORPHAN_PHASE
        out["reason"] = (f"Setup cannot proceed: --orphan-action takes keep or remove, not {given}. "
                         "Re-run with --orphan-action=keep or --orphan-action=remove.")
    return out


def _force_utf8(stream) -> None:
    """Print UTF-8 on a console that defaults to another code page (a Windows cp1252 one)."""
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8")


def main() -> None:
    _force_utf8(sys.stdout)
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    sys.stdout.write(json.dumps(parse(read_arguments(sys.stdin)), ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
