# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""SKF QMD Classify Collections — Set arithmetic over QMD collection names.

Replaces the prose-driven classification logic in `src/skf-setup/steps-c/
step-03-auto-index.md` §3 with one Python invocation. Compares the live
QMD collections (from `qmd collection list`) against the forge registry
(`qmd_collections` array in forge-tier.yaml) and classifies each name as
Healthy / Orphaned / Stale, applying the forge-namespace suffix filter
added in PR #244 to silently exclude collections owned by unrelated
tools sharing the QMD daemon.

Classification rules (per step-03 §3):

  Healthy   — name in {forge-suffix-matched live} AND in registry.
              No action needed.
  Orphaned  — name in {forge-suffix-matched live} but NOT in registry.
              Flagged for user-prompted removal in step-03 §4.
  Stale     — name in registry but NOT in {all live}. Registry entry
              should be removed.
  Foreign   — name in live but does NOT match a forge suffix. Silently
              excluded from every classification — never displayed,
              never proposed for removal. Reported as a count for
              telemetry only.

Forge suffixes (the only suffixes a forge-managed collection can have,
set by producers `skf-brief-skill` and `skf-create-skill` per
src/knowledge/qmd-registry.md § Collection Types):

  -brief, -temporal, -docs, -extraction

Inputs:

  --live-names    Comma-separated list of collection names currently
                  in QMD (caller obtains this from `qmd collection list`
                  before invoking the script). Empty string → no live
                  collections, which is a valid first-run state.

  --registry-from-yaml <path>
                  Path to forge-tier.yaml. The script reads the file's
                  `qmd_collections` array and extracts the `name` field
                  from each entry. Missing file or missing array → empty
                  registry, which is a valid first-run state.

Output (single JSON document on stdout):

  {
    "status": "ok",
    "version": "v1",
    "healthy":          ["foo-brief", "foo-extraction"],
    "orphaned":         ["bar-extraction"],
    "stale":            ["baz-docs"],
    "foreign_filtered_count": 4,
    "foreign_filtered_sample": ["memory-root-1", "sessions-2"]
  }

`foreign_filtered_sample` is capped at 5 names (telemetry; the full list
is never useful — if it were forge-relevant it would have a forge suffix).

CLI — invoke via `uv run` so the PEP 723 PyYAML dependency declared
above is auto-resolved on first call and cached. `docs/getting-started.md`
documents uv as the runtime prerequisite for exactly this. Bare
`python3` will fail with `ModuleNotFoundError: No module named 'yaml'`
on a fresh interpreter:

  uv run skf-qmd-classify-collections.py \\
      --live-names foo-brief,foo-extraction,memory-root-1 \\
      --registry-from-yaml /path/forge-tier.yaml

Exit codes:
  0 success
  1 user error (bad args, malformed registry file)
  2 internal error
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml


FORGE_SUFFIXES = ("-brief", "-temporal", "-docs", "-extraction")
FOREIGN_SAMPLE_CAP = 5


def _die(code: int, message: str) -> None:
    print(json.dumps({"status": "error", "message": message}), file=sys.stderr)
    sys.exit(code)


def _ok(payload: dict) -> None:
    payload.setdefault("status", "ok")
    payload.setdefault("version", "v1")
    print(json.dumps(payload))


def is_forge_owned(name: str) -> bool:
    """True if `name` ends with one of the forge suffixes."""
    return any(name.endswith(suffix) for suffix in FORGE_SUFFIXES)


def parse_live_names(raw: str) -> list[str]:
    """Comma-separated → de-duplicated list, preserving first-occurrence order.

    Collection names from `qmd collection list` are user-facing strings;
    we trust them as-is rather than imposing additional validation.
    """
    seen = set()
    out: list[str] = []
    for token in raw.split(","):
        name = token.strip()
        if not name:
            continue
        if name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out


def load_registry_names(path: Path) -> list[str]:
    """Read forge-tier.yaml and extract `name` from each qmd_collections entry.

    Missing file → empty list (valid first-run state). Malformed file
    (parse error, wrong top-level type) → exit 1 with an actionable
    message. Entries without a `name` field are skipped silently — the
    forge-tier-rw.py contract guarantees `name` is always present, but
    a hand-edited file might violate it; classify what we can.
    """
    if not path.exists():
        return []
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        _die(1, f"failed to parse {path}: {e}")
    if data is None:
        return []
    if not isinstance(data, dict):
        _die(1, f"expected mapping at top of {path}, got {type(data).__name__}")
    entries = data.get("qmd_collections", []) or []
    if not isinstance(entries, list):
        _die(1, f"qmd_collections in {path} is not a list (got {type(entries).__name__})")
    names: list[str] = []
    for entry in entries:
        if isinstance(entry, dict) and isinstance(entry.get("name"), str):
            names.append(entry["name"])
    return names


def classify(live: list[str], registry: list[str]) -> dict:
    """Pure function: classify live vs registry into healthy/orphaned/stale/foreign.

    Returns the classification payload (without status/version envelope).
    """
    forge_live = [n for n in live if is_forge_owned(n)]
    foreign_live = [n for n in live if not is_forge_owned(n)]

    forge_live_set = set(forge_live)
    registry_set = set(registry)
    all_live_set = set(live)

    healthy = sorted(forge_live_set & registry_set)
    orphaned = sorted(forge_live_set - registry_set)
    # Stale uses the full live set, NOT just the forge-filtered set, so a
    # registry entry whose name happens to match a non-forge live collection
    # would still count as stale. Registry entries always have forge suffixes
    # by convention, so this distinction matters only on hand-edited files.
    stale = sorted(registry_set - all_live_set)

    return {
        "healthy": healthy,
        "orphaned": orphaned,
        "stale": stale,
        "foreign_filtered_count": len(foreign_live),
        "foreign_filtered_sample": foreign_live[:FOREIGN_SAMPLE_CAP],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Classify QMD collections vs forge registry.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--live-names",
        default="",
        help="Comma-separated list of collection names currently in QMD "
             "(from `qmd collection list`). Empty string → no live collections.",
    )
    parser.add_argument(
        "--registry-from-yaml",
        type=Path,
        required=True,
        help="Path to forge-tier.yaml. Script reads qmd_collections array. "
             "Missing file → empty registry (first-run state).",
    )
    args = parser.parse_args()

    live = parse_live_names(args.live_names)
    registry = load_registry_names(args.registry_from_yaml)
    _ok(classify(live, registry))


if __name__ == "__main__":
    main()
