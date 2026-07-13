#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""SKF Verify No Trace — post-rename commit gate.

Confirms that no structural reference to the old skill name survives inside the
freshly-materialized new location before the rename is committed (before the old
directories are deleted). Every check is a fixed-file-set, case-sensitive scan
plus a region partition — fully deterministic, so the prompt keeps only the
roll-back-or-commit decision.

The scan matches the old name only as a complete skill-name token: an occurrence
NOT adjacent to another skill-name character `[a-z0-9-]` on either side. This is
what a literal substring grep intends but gets wrong when the old name is a
substring of the new name (rename -> rename-skill): a bare substring scan would
flag every correctly-renamed `rename-skill` as a leftover and make the rename
un-committable. Token matching flags a genuine leftover path segment
(`.claude/skills/rename/`), JSON value (`"rename"`), or header (`[rename v...]`)
while ignoring `rename-skill` and `renamed`.

For each version under --versions it scans:

  {skill_group}/{v}/{new_name}/SKILL.md          -> frontmatter matches are HARD;
                                                    body matches (below the closing
                                                    `---`) are advisory warnings
  {skill_group}/{v}/{new_name}/metadata.json     -> any match is HARD
  {skill_group}/{v}/{new_name}/context-snippet.md-> any match is HARD
  {forge_group}/{v}/provenance-map.json          -> any match is HARD

and the directory listing:

  {skill_group}/{v}/  MUST contain {new_name}/ and MUST NOT contain {old_name}/

The SKILL.md frontmatter/body split uses the same closing-`---`-on-its-own-line
rule as skf-validate-output.py, so a legitimate body mention of the old name (a
changelog line, a cross-reference) is a warning, never a blocker.

Output (stdout, always JSON):
  {hard_matches[], body_warnings[], dir_violations[], skipped[], clean}

Exit codes:
  0  clean (no hard_matches and no dir_violations)
  1  not clean (at least one hard match or dir violation)
  2  operation error (bad args)

CLI example:
  python3 skf-verify-no-trace.py /out/rename-skill \
      --forge-group /forge/rename-skill \
      --old-name rename --new-name rename-skill --versions 1.0.0,0.9.0
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def _name_token_re(old_name: str) -> "re.Pattern[str]":
    """Match old_name only where it is a complete skill-name token.

    Negative lookbehind/lookahead on `[a-z0-9-]` so `rename` matches inside
    `/rename/` or `"rename"` but not inside `rename-skill` or `renamed`.
    """
    return re.compile(r"(?<![a-z0-9-])" + re.escape(old_name) + r"(?![a-z0-9-])")


def _split_frontmatter_body(content: str):
    """Return (frontmatter_lines, body_lines) as lists of (lineno, text).

    Uses the closing-`---`-on-its-own-line rule (matching skf-validate-output.py).
    When there is no valid frontmatter block, the whole file is treated as body —
    a SKILL.md without frontmatter has no "structural" region to protect, so any
    old-name match there is advisory, and the separate metadata/snippet/provenance
    scans still gate the commit.
    """
    lines = content.split("\n")
    numbered = list(enumerate(lines, start=1))
    if not content.startswith("---\n"):
        return [], numbered
    close_idx = None  # 0-based index into `lines` of the closing '---'
    for i in range(1, len(lines)):
        if lines[i].rstrip() == "---":
            close_idx = i
            break
    if close_idx is None:
        return [], numbered
    # Frontmatter = lines strictly between the opening (line 1) and closing '---'.
    frontmatter = numbered[1:close_idx]
    body = numbered[close_idx + 1 :]
    return frontmatter, body


def _scan_lines(numbered, pattern):
    """Return [(lineno, text)] for every line where pattern matches (name token)."""
    return [(n, text) for (n, text) in numbered if pattern.search(text)]


def verify(skill_group: Path, forge_group: Path, old_name: str, new_name: str, versions):
    hard_matches = []
    body_warnings = []
    dir_violations = []
    skipped = []
    pattern = _name_token_re(old_name)

    def scan_file(path: Path, region: str, version: str):
        if not path.exists():
            skipped.append({"version": version, "file": str(path), "reason": "missing"})
            return None
        try:
            return path.read_text(encoding="utf-8")
        except OSError as e:
            skipped.append({"version": version, "file": str(path), "reason": f"read-error: {e}"})
            return None

    for v in versions:
        inner = skill_group / v / new_name

        # SKILL.md — region-partitioned (frontmatter=hard, body=warning).
        skill_md = inner / "SKILL.md"
        content = scan_file(skill_md, "skill-md", v)
        if content is not None:
            fm, body = _split_frontmatter_body(content)
            for n, text in _scan_lines(fm, pattern):
                hard_matches.append(
                    {"version": v, "file": str(skill_md), "region": "skill-frontmatter",
                     "line": n, "text": text.strip()}
                )
            for n, text in _scan_lines(body, pattern):
                body_warnings.append(
                    {"version": v, "file": str(skill_md), "region": "skill-body",
                     "line": n, "text": text.strip()}
                )

        # Whole-file hard scans.
        for rel, region, base in (
            (inner / "metadata.json", "metadata-json", skill_group),
            (inner / "context-snippet.md", "context-snippet", skill_group),
            (forge_group / v / "provenance-map.json", "provenance-json", forge_group),
        ):
            content = scan_file(rel, region, v)
            if content is None:
                continue
            for n, text in _scan_lines(list(enumerate(content.split("\n"), start=1)), pattern):
                hard_matches.append(
                    {"version": v, "file": str(rel), "region": region,
                     "line": n, "text": text.strip()}
                )

        # Directory listing: must contain {new_name}/, must not contain {old_name}/.
        version_dir = skill_group / v
        old_dir = version_dir / old_name
        new_dir = version_dir / new_name
        if old_dir.exists():
            dir_violations.append(
                {"version": v, "path": str(version_dir),
                 "issue": "old-name-dir-present", "detail": f"{old_name}/"}
            )
        if not new_dir.exists():
            dir_violations.append(
                {"version": v, "path": str(version_dir),
                 "issue": "new-name-dir-missing", "detail": f"{new_name}/"}
            )

    clean = not hard_matches and not dir_violations
    return {
        "status": "ok",
        "old_name": old_name,
        "new_name": new_name,
        "versions": list(versions),
        "hard_matches": hard_matches,
        "body_warnings": body_warnings,
        "dir_violations": dir_violations,
        "skipped": skipped,
        "clean": clean,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("skill_group", type=Path, help="new_skill_group ({skills_output_folder}/{new_name})")
    parser.add_argument("--forge-group", type=Path, required=True, help="new_forge_group ({forge_data_folder}/{new_name})")
    parser.add_argument("--old-name", required=True, help="Old skill name to scan for")
    parser.add_argument("--new-name", required=True, help="New skill name")
    parser.add_argument("--versions", required=True, help="Comma-separated version list (affected_versions)")
    parser.add_argument("--verbose", action="store_true", help="Diagnostics to stderr")
    args = parser.parse_args()

    versions = [v for v in (s.strip() for s in args.versions.split(",")) if v]
    if not versions:
        print(json.dumps({"status": "error", "message": "no versions provided"}), file=sys.stderr)
        sys.exit(2)

    result = verify(args.skill_group, args.forge_group, args.old_name, args.new_name, versions)

    if args.verbose:
        print(
            f"[skf-verify-no-trace] hard={len(result['hard_matches'])} "
            f"warn={len(result['body_warnings'])} dir={len(result['dir_violations'])} "
            f"clean={result['clean']}",
            file=sys.stderr,
        )

    print(json.dumps(result, indent=2))
    sys.exit(0 if result["clean"] else 1)


if __name__ == "__main__":
    main()
