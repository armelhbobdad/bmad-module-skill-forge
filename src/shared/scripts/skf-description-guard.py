# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""SKF Description Guard — defend SKILL.md frontmatter description against
well-meaning tool rewrites.

External validators (`skill-check check --fix`, `skill-check split-body`) may
rewrite the frontmatter `description` field — replace it with a generic
version, truncate it, or re-introduce angle-bracket tokens that earlier
sanitization removed. The compiled/merged description on disk is the
authoritative one; losing it breaks agent discovery quality.

This script implements the deterministic parts of the four-phase guard
protocol (capture before tool call; verify-and-restore after) so that
workflows do not have to re-implement frontmatter parsing or token-stream
comparison in prose.

Subcommands:
  capture <skill-md>
      Snapshot the current `description` field. Emits JSON
      {"description": "...", "schema_hash": "sha256:..."}
      where schema_hash covers the full frontmatter block (handy for
      tamper detection if the caller wants belt-and-braces verification).

  verify-restore <skill-md> --captured-description <STR>
      Re-read the file, compare current description against the captured
      value using token-stream equality (split on whitespace, compare
      element-by-element). If diverged, atomically rewrite the frontmatter
      with the captured description and emit
        {"diverged": true, "restored": true|false, "diff_kind": "...",
         "current_description": "..."}
      If not diverged (including whitespace-only differences), emit
        {"diverged": false, "restored": false, "diff_kind": "none"|"whitespace-only"}

Token-stream comparison is the documented sweet spot — catches replaced
words, truncation, and reintroduced angle-brackets while ignoring cosmetic
whitespace fixes (trailing newline, re-wrapped quoted strings). See
src/shared/references/description-guard-protocol.md for the full protocol.

CLI — invoke via `uv run` so the PEP 723 PyYAML dependency declared above
is auto-resolved:

  uv run skf-description-guard.py capture <skill-md>
  uv run skf-description-guard.py verify-restore <skill-md> \\
      --captured-description "the snapshot string"

Exit codes:
  0  — operation succeeded (including no-divergence verify)
  1  — user error (bad args, file missing, frontmatter unparseable)
  2  — operation failure (restore write failed)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

import yaml


# --------------------------------------------------------------------------
# Frontmatter parsing
# --------------------------------------------------------------------------


def _split_frontmatter(text: str) -> tuple[str, str, str]:
    """Split a markdown file into (leading, frontmatter_yaml, body).

    Returns ('', '', text) if there is no frontmatter. Frontmatter is
    recognized when the file starts with '---\\n' and a matching '---\\n'
    line closes it before the body.
    """
    if not text.startswith("---\n"):
        return "", "", text
    rest = text[4:]
    close = rest.find("\n---\n")
    if close == -1:
        # also accept '\n---' as the closing line at EOF (no trailing newline)
        if rest.endswith("\n---"):
            return "---\n", rest[: -len("\n---")], ""
        return "", "", text
    fm = rest[:close]
    body = rest[close + len("\n---\n") :]
    return "---\n", fm, body


def read_description(skill_md: Path) -> tuple[str, str]:
    """Read `description` field from SKILL.md frontmatter.

    Returns (description, schema_hash). schema_hash is the sha256 of the
    raw frontmatter YAML block as bytes, prefixed with "sha256:".

    Raises ValueError if the file has no frontmatter, the frontmatter is
    unparseable, or the description field is missing.
    """
    text = skill_md.read_text(encoding="utf-8")
    _, fm_yaml, _ = _split_frontmatter(text)
    if not fm_yaml:
        raise ValueError(f"no frontmatter found in {skill_md}")
    try:
        fm = yaml.safe_load(fm_yaml)
    except yaml.YAMLError as exc:
        raise ValueError(f"frontmatter in {skill_md} is not valid YAML: {exc}") from exc
    if not isinstance(fm, dict):
        raise ValueError(f"frontmatter in {skill_md} is not a mapping")
    if "description" not in fm:
        raise ValueError(f"frontmatter in {skill_md} has no `description` field")
    description = fm["description"]
    if not isinstance(description, str):
        raise ValueError(f"`description` in {skill_md} is not a string")
    schema_hash = "sha256:" + hashlib.sha256(fm_yaml.encode("utf-8")).hexdigest()
    return description, schema_hash


# --------------------------------------------------------------------------
# Divergence detection
# --------------------------------------------------------------------------


def classify_divergence(captured: str, current: str) -> str:
    """Compare two descriptions and classify the difference.

    Returns one of:
      "none"            — strings are byte-identical
      "whitespace-only" — token streams match but raw strings differ
      "replaced"        — token streams differ (semantic content change)
      "truncated"       — current's tokens are a strict prefix of captured's
      "deleted"         — current is empty/whitespace-only and captured is not
    """
    if captured == current:
        return "none"
    if not current.strip() and captured.strip():
        return "deleted"
    cap_tokens = captured.split()
    cur_tokens = current.split()
    if cap_tokens == cur_tokens:
        return "whitespace-only"
    # truncation = cur_tokens is a strict prefix of cap_tokens
    if len(cur_tokens) < len(cap_tokens) and cap_tokens[: len(cur_tokens)] == cur_tokens:
        return "truncated"
    return "replaced"


def is_diverged(diff_kind: str) -> bool:
    """Whether a diff_kind indicates real (non-whitespace) divergence."""
    return diff_kind not in ("none", "whitespace-only")


# --------------------------------------------------------------------------
# Restore (atomic frontmatter rewrite)
# --------------------------------------------------------------------------


def restore_description(skill_md: Path, captured: str) -> None:
    """Atomically rewrite SKILL.md so its frontmatter `description` equals captured.

    Parses the entire frontmatter via PyYAML, replaces the top-level
    `description` value, and re-emits the frontmatter via `yaml.safe_dump`.
    This guarantees valid YAML output regardless of the source representation
    (inline, double-quoted, single-quoted, folded `>`, literal `|`), and
    avoids the line-level pitfalls a previous implementation had with folded
    block scalars and nested `description:` keys in sibling mappings.

    Key order is preserved (PyYAML's `safe_dump` honours dict insertion order;
    this module's `requires-python = ">=3.10"` guarantees ordered dicts).
    Quoting style of *other* fields may change to whatever `safe_dump`
    chooses for each scalar — downstream readers parse YAML, so any valid
    YAML emission is acceptable.
    """
    text = skill_md.read_text(encoding="utf-8")
    leading, fm_yaml, body = _split_frontmatter(text)
    if not fm_yaml:
        raise ValueError(f"cannot restore: no frontmatter in {skill_md}")

    try:
        fm = yaml.safe_load(fm_yaml)
    except yaml.YAMLError as exc:
        raise ValueError(f"frontmatter in {skill_md} is not valid YAML: {exc}") from exc
    if not isinstance(fm, dict):
        raise ValueError(f"frontmatter in {skill_md} is not a mapping")
    if "description" not in fm:
        raise ValueError(f"frontmatter in {skill_md} has no `description` field")

    fm["description"] = captured

    # `width=10**9` keeps the description on one line regardless of length;
    # PyYAML otherwise inserts line breaks at ~80 chars which would re-introduce
    # folded-scalar continuation lines — the exact failure mode this rewrite fixes.
    new_fm = yaml.safe_dump(
        fm,
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
        width=10**9,
    ).rstrip("\n")
    new_text = f"{leading}{new_fm}\n---\n{body}"

    # atomic: write to a sibling temp file, fsync, rename
    fd, tmp_path = tempfile.mkstemp(
        prefix=skill_md.name + ".", suffix=".skf-guard.tmp", dir=skill_md.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp:
            tmp.write(new_text)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_path, skill_md)
    except Exception:
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass
        raise


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _cmd_capture(args: argparse.Namespace) -> int:
    skill_md = Path(args.skill_md)
    if not skill_md.is_file():
        _fail(f"file not found: {skill_md}")
    try:
        description, schema_hash = read_description(skill_md)
    except ValueError as exc:
        _fail(str(exc))
    json.dump({"description": description, "schema_hash": schema_hash}, sys.stdout)
    sys.stdout.write("\n")
    return 0


def _cmd_verify_restore(args: argparse.Namespace) -> int:
    skill_md = Path(args.skill_md)
    if not skill_md.is_file():
        _fail(f"file not found: {skill_md}")
    try:
        current, _ = read_description(skill_md)
    except ValueError as exc:
        _fail(str(exc))

    captured = args.captured_description
    diff_kind = classify_divergence(captured, current)
    diverged = is_diverged(diff_kind)

    result = {
        "diverged": diverged,
        "restored": False,
        "diff_kind": diff_kind,
        "current_description": current,
    }

    if diverged:
        try:
            restore_description(skill_md, captured)
            result["restored"] = True
        except (OSError, ValueError) as exc:
            json.dump({**result, "restore_error": str(exc)}, sys.stdout)
            sys.stdout.write("\n")
            return 2

    json.dump(result, sys.stdout)
    sys.stdout.write("\n")
    return 0


def _fail(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    raise SystemExit(1)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skf-description-guard",
        description="Defend SKILL.md frontmatter description against tool rewrites.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_cap = sub.add_parser("capture", help="snapshot the current description value")
    p_cap.add_argument("skill_md", help="path to SKILL.md")
    p_cap.set_defaults(func=_cmd_capture)

    p_ver = sub.add_parser(
        "verify-restore",
        help="verify on-disk description against captured snapshot; restore if diverged",
    )
    p_ver.add_argument("skill_md", help="path to SKILL.md")
    p_ver.add_argument(
        "--captured-description",
        required=True,
        help="the description string captured before the tool call",
    )
    p_ver.set_defaults(func=_cmd_verify_restore)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
