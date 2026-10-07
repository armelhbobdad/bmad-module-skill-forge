# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""SKF Derive Assembly Shape — decide whether a brief is a whole-language reference.

create-skill's SKILL.md assembly is mostly LLM-driven prose, but the BRANCH
SELECTION — does this skill get the whole-language "Language Guide" treatment
(prose foregrounded, compiler internals demoted) or the standard
library-export layout? — must be deterministic. This helper computes that one
decision from the brief so the assembler (and the doc-fetch step) branch on a
machine value instead of grepping free-text `scope.notes`.

The gate is a single, structured, schema-validated condition: the brief's
`doc_urls` contains at least one entry with `source: "language-registry"`
(issue #432). Registry-sourced corpora are stamped ONLY by
skf-language-corpora.py, which is invoked ONLY for a whole-language reference
(a grammar_file:/tree_triad: signal) in step-auto-scope-corpora.md, which
step-auto-scope.md §6 loads for that signal. So the gate
fires exactly when there is registry-guaranteed prose to foreground, and never
for an ordinary library, a parser library (pest), a component-library, a
reference-app, or a docs-only brief — none of which carry a language-registry
entry. A registry-miss (N==0) whole-language reference carries no such entry
and is intentionally NOT gated: there is no canonical prose to foreground, so
it keeps the standard layout (and its scope.notes DEGRADED caveat stands).

Gating on the structured `source` field — not the operator-editable
`scope.notes` substring — means a hand-edited or interactive brief cannot
silently disable (or misfire) the override.

CLI:
  uv run skf-derive-assembly-shape.py <path/to/skill-brief.yaml>
  cat brief.yaml | uv run skf-derive-assembly-shape.py -

Output (JSON on stdout):
  {
    "assembly_shape": "whole-language-reference" | "standard",
    "gate_signal":    "language-registry" | null
  }

Exit codes:
  0  success (shape emitted)
  2  error (missing/unreadable/invalid brief)
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import yaml

RESOLVER = Path(__file__).resolve().parent / "skf-resolve-authoritative-files.py"


def derive_assembly_shape(brief: dict[str, Any]) -> dict[str, Any]:
    """Return the assembly-shape decision for a parsed brief."""
    doc_urls = brief.get("doc_urls")
    if isinstance(doc_urls, list):
        for entry in doc_urls:
            if isinstance(entry, dict) and entry.get("source") == "language-registry":
                return {
                    "assembly_shape": "whole-language-reference",
                    "gate_signal": "language-registry",
                }
    return {"assembly_shape": "standard", "gate_signal": None}


def _die(message: str) -> None:
    json.dump({"error": message}, sys.stderr)
    sys.stderr.write("\n")
    sys.exit(2)


def _parse_brief_yaml(text: str):
    """The brief's YAML as skf-resolve-authoritative-files.py (from this
    folder) reads it: an SKF 1.x brief's trailing `---` is no second document."""
    spec = importlib.util.spec_from_file_location("skf_resolve_authoritative_files", RESOLVER)
    if spec is None or spec.loader is None:
        _die(f"cannot load {RESOLVER.name} beside {Path(__file__).name}")
    resolver = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(resolver)
    except (OSError, ImportError, SyntaxError) as exc:
        _die(f"cannot load {RESOLVER.name} beside {Path(__file__).name}: {exc}")
    return resolver.parse_brief_yaml(text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="skf-derive-assembly-shape",
        description="Decide whether a skill brief is a whole-language reference.",
    )
    parser.add_argument(
        "path",
        help="path to skill-brief.yaml; pass `-` to read YAML from stdin",
    )
    args = parser.parse_args(argv)

    if args.path == "-":
        text = sys.stdin.read()
    else:
        p = Path(args.path)
        if not p.is_file():
            _die(f"Brief not found at {p.as_posix()}")
        text = p.read_text(encoding="utf-8")

    try:
        brief = _parse_brief_yaml(text)
    except yaml.YAMLError as exc:
        _die(f"Brief is not valid YAML: {exc}")
    if not isinstance(brief, dict):
        _die("Brief must be a YAML mapping")

    json.dump(derive_assembly_shape(brief), sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
