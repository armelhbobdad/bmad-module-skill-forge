# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""SKF Language Corpora — canonical companion prose corpora for a language.

A whole-language skill (issue #427) is forged from a language-reference repo
(a compiler/interpreter such as rust-lang/rust). That repo carries the
language's CODE, but a skill's value comes from the language's PROSE — the
guide/Book, the standard/library API docs, idioms. README detection
(skf-detect-docs.py) is the primary source for those; this lookup guarantees
the canonical corpora for well-known languages even when the repo's README
does not link them.

Pure static lookup over src/shared/data/language-corpora.json — no network,
no git, no `gh`. Output is the brief `doc_urls` contract (`{url, label}`), so
the result can be seeded directly into a skill brief.

CLI:
  uv run src/shared/scripts/skf-language-corpora.py --language <id>

Output (JSON array on stdout): [{"url": "...", "label": "..."}, ...]

Exit codes:
  0  registry hit — one or more corpora emitted
  1  no entry for this language (long-tail / unknown) — emits []
  2  error (bad args, missing/unreadable/invalid data file)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "language-corpora.json"


def _die(message: str, code: str = "INTERNAL_ERROR") -> None:
    json.dump({"error": message, "code": code}, sys.stderr, ensure_ascii=False)
    sys.stderr.write("\n")
    sys.exit(2)


def _load_registry() -> dict:
    try:
        data = json.loads(_DATA_FILE.read_text(encoding="utf-8"))
    except OSError as exc:
        _die(f"Cannot read {_DATA_FILE.as_posix()}: {exc}", "DATA_READ_ERROR")
    except json.JSONDecodeError as exc:
        _die(f"Cannot parse {_DATA_FILE.as_posix()}: {exc}", "DATA_PARSE_ERROR")
    if not isinstance(data, dict):
        _die("Corpora registry must be a JSON object", "DATA_PARSE_ERROR")
    return data


def corpora_for(language: str) -> list[dict]:
    """Return the `{url, label}` corpora for a language id, or [] if none."""
    registry = _load_registry()
    entries = registry.get((language or "").strip().lower())
    if not isinstance(entries, list):
        return []
    out: list[dict] = []
    for e in entries:
        if isinstance(e, dict) and e.get("url"):
            out.append({"url": e["url"], "label": e.get("label", "")})
    return out


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Look up canonical companion prose corpora for a language.",
    )
    parser.add_argument(
        "--language", required=True,
        help="Lowercase language id (rust, python, go, typescript, ruby, ...)",
    )
    args = parser.parse_args(argv)

    result = corpora_for(args.language)
    json.dump(result, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0 if result else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
