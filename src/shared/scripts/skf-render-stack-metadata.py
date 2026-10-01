# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""SKF Render Stack Metadata: a stack's pair tiers and the computed fields of its metadata.json.

create-stack-skill gives each integration the tier of its pair
(detect-integrations section 3) and writes the counted and ranked fields of
metadata.json (generate-output section 6). This helper holds those rules
once, so no step file restates them, and skf-validate-output.py
--skill-type stack recomputes the dominant tier with dominant_tier here.

Rules:
  Tiers, from the strongest: T1, T1-low, T2, T3.

  combine_pair_tier(a, b, mode)
      An integration takes the weaker of its two libraries' tiers, one rule
      in code mode and compose mode: T1 + T1 is T1; T1 + T1-low and
      T1-low + T1-low are T1-low; T1 + T2, T1-low + T2 and T2 + T2 are T2; a
      pair with a T3 member is T3. A T2 member lowers the pair like any
      other tier: its temporal annotations never keep a stronger one.
      `mode` must name a mode, and both modes take this rule.

  dominant_tier(distribution)
      The tier of the largest bin of a confidence_distribution. A tie goes
      to the weaker tier, so the tier never overstates confidence, and a
      distribution with no positive bin (no library) reads T1-low. This is
      the stack's confidence_tier.

  confidence_distribution
      Each library once, in the bin of its tier, so the four bins sum to
      library_count. The evidence report bins the provenance entries
      instead (skf-render-metadata-stats.py).

  source_authority
      The lowest authority among the libraries: official, then community,
      then internal, so a community and an internal library give internal.
      A library that records none counts as community, so a constituent
      without one never lifts a stack to official, and a code-mode stack,
      whose libraries are dependencies rather than skills with an
      authority, is community.

Input (--input <json-file-or-'-'>, where '-' reads stdin):
  {
    "mode": "code" | "compose",
    "libraries": [
      {"name": "<library>",
       "confidence": "T1|T1-low|T2|T3",          # per_library_extractions[].confidence
       "source_authority": "official|community|internal"},   # optional
      ...
    ],
    "integrations": [{"a": "<library>", "b": "<library>"}, ...]   # optional
  }
  Tier, mode and authority tokens compare case-insensitively and are printed
  in their canonical spelling. Each library is named once, and each pair
  names two different libraries of `libraries`, once in either order.

Subcommands:
  pair-tiers  the tier of each integration (detect-integrations section 3):
                {"mode": "<mode>",
                 "integrations": [{"a": "<a>", "b": "<b>", "tier": "<tier>"}, ...]}
  metadata    the computed fields of metadata.json (generate-output section
              6), with the libraries and pairs in the order given:
                {"mode": "<mode>",
                 "library_count": N,
                 "integration_count": M,
                 "libraries": ["<library>", ...],
                 "integration_pairs": [["<a>", "<b>"], ...],
                 "confidence_distribution": {"t1": 0, "t1_low": 0, "t2": 0, "t3": 0},
                 "confidence_tier": "<dominant tier>",
                 "source_authority": "<authority>",
                 "integrations": [{"a": "<a>", "b": "<b>", "tier": "<tier>"}, ...]}

CLI:
  uv run skf-render-stack-metadata.py pair-tiers --input -
  uv run skf-render-stack-metadata.py metadata --input stack.json

Exit codes:
  0  the JSON is printed
  2  a usage, read or input error: one line on stderr, no JSON
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

# Tiers from the strongest to the weakest: T1-low is weaker than T1, T2 than
# T1-low, T3 than T2.
TIERS = ("T1", "T1-low", "T2", "T3")
MODES = ("code", "compose")
# Authorities from the highest to the lowest.
AUTHORITIES = ("official", "community", "internal")
# The authority of a library that records none.
DEFAULT_AUTHORITY = "community"

# The confidence_distribution bins of metadata.json, from the strongest tier
# to the weakest. dominant_tier reads them in this order and lets a later bin
# win a tie, so a tie resolves toward the weaker tier.
_DISTRIBUTION_BINS = (("t1", "T1"), ("t1_low", "T1-low"), ("t2", "T2"), ("t3", "T3"))

# The tier of a distribution that records no evidence (the conservative default).
_NO_EVIDENCE_TIER = "T1-low"


class InputError(ValueError):
    """An input the caller must fix: exit 2 with one line on stderr."""


def _token(value, allowed: tuple[str, ...], what: str) -> str:
    """`value` in its canonical spelling from `allowed`, compared case-insensitively."""
    if isinstance(value, str):
        for token in allowed:
            if value.strip().lower() == token.lower():
                return token
    raise InputError(f"{what} must be one of {', '.join(allowed)}; got {value!r}")


# --------------------------------------------------------------------------
# Rules
# --------------------------------------------------------------------------


def combine_pair_tier(a: str, b: str, mode: str) -> str:
    """The tier of an integration between a library of tier `a` and one of tier `b`.

    The weaker of the two, in both modes. Raises InputError on an unknown tier
    or mode.
    """
    _token(mode, MODES, "mode")
    return max(_token(a, TIERS, "tier"), _token(b, TIERS, "tier"), key=TIERS.index)


# Keep identical to _bin_count and dominant_tier in skf-enumerate-stack-skills.py
# (test/test-skf-render-stack-metadata.py pins the copies).
def _bin_count(value):
    """A confidence_distribution bin's count: a positive finite number, else 0."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    if isinstance(value, float) and not math.isfinite(value):
        return 0
    return value if value > 0 else 0


def dominant_tier(distribution) -> str:
    """The tier of the largest bin of a metadata.json confidence_distribution.

    The bins are read from the strongest tier to the weakest and a later bin
    wins a tie, so a tie resolves toward the weaker tier (T1-low over T1, T2
    over T1-low, T3 over T2) and the tier never overstates confidence. A bin
    counts only when it holds a positive number. T1-low when none does: the
    distribution is absent, not an object or all zero.
    """
    tier, best = _NO_EVIDENCE_TIER, 0
    if isinstance(distribution, dict):
        for key, bin_tier in _DISTRIBUTION_BINS:
            count = _bin_count(distribution.get(key))
            if count and count >= best:
                tier, best = bin_tier, count
    return tier


def library_distribution(tiers: list[str]) -> dict[str, int]:
    """confidence_distribution with each library once, in the bin of its tier."""
    bin_of = {tier: key for key, tier in _DISTRIBUTION_BINS}
    distribution = {key: 0 for key, _ in _DISTRIBUTION_BINS}
    for tier in tiers:
        distribution[bin_of[tier]] += 1
    return distribution


def lowest_authority(authorities: list[str | None]) -> str:
    """The lowest of the authorities, a library that records none (None)
    counting as DEFAULT_AUTHORITY; DEFAULT_AUTHORITY for no library."""
    return max((authority or DEFAULT_AUTHORITY for authority in authorities),
               key=AUTHORITIES.index, default=DEFAULT_AUTHORITY)


# --------------------------------------------------------------------------
# Input and projections
# --------------------------------------------------------------------------


def parse_stack(data) -> tuple[str, list[dict], list[tuple[str, str]]]:
    """(mode, libraries, pairs) from the input JSON. Raises InputError."""
    if not isinstance(data, dict):
        raise InputError(f"the input must be a JSON object; got {type(data).__name__}")
    mode = _token(data.get("mode"), MODES, "mode")

    raw_libraries = data.get("libraries")
    if not isinstance(raw_libraries, list):
        raise InputError("`libraries` must be an array of {name, confidence} objects")
    libraries: list[dict] = []
    tiers: dict[str, str] = {}
    for i, item in enumerate(raw_libraries):
        where = f"libraries[{i}]"
        if not isinstance(item, dict):
            raise InputError(f"{where} must be an object with `name` and `confidence`; got {item!r}")
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            raise InputError(f"{where}.name must be a non-empty string; got {name!r}")
        if name in tiers:
            raise InputError(f"library {name!r} is listed twice")
        tier = _token(item.get("confidence"), TIERS, f"{where}.confidence")
        authority = item.get("source_authority")
        if authority is not None:
            authority = _token(authority, AUTHORITIES, f"{where}.source_authority")
        tiers[name] = tier
        libraries.append({"name": name, "confidence": tier, "source_authority": authority})

    raw_pairs = data.get("integrations", [])
    if not isinstance(raw_pairs, list):
        raise InputError("`integrations` must be an array of {a, b} objects")
    pairs: list[tuple[str, str]] = []
    seen: set[frozenset[str]] = set()
    for i, item in enumerate(raw_pairs):
        where = f"integrations[{i}]"
        if not isinstance(item, dict):
            raise InputError(f"{where} must be an object with `a` and `b`; got {item!r}")
        a, b = item.get("a"), item.get("b")
        for side, name in (("a", a), ("b", b)):
            if not isinstance(name, str) or name not in tiers:
                raise InputError(f"{where}.{side} {name!r} is not one of the libraries")
        if a == b:
            raise InputError(f"{where} pairs {a!r} with itself")
        key = frozenset((a, b))
        if key in seen:
            raise InputError(f"the pair {a!r} + {b!r} is listed twice")
        seen.add(key)
        pairs.append((a, b))
    return mode, libraries, pairs


def pair_tiers(mode: str, libraries: list[dict], pairs: list[tuple[str, str]]) -> list[dict]:
    """Each pair with the tier combine_pair_tier gives it."""
    tier = {library["name"]: library["confidence"] for library in libraries}
    return [{"a": a, "b": b, "tier": combine_pair_tier(tier[a], tier[b], mode)} for a, b in pairs]


def stack_metadata(mode: str, libraries: list[dict], pairs: list[tuple[str, str]]) -> dict:
    """The computed fields of a stack's metadata.json."""
    distribution = library_distribution([library["confidence"] for library in libraries])
    return {
        "mode": mode,
        "library_count": len(libraries),
        "integration_count": len(pairs),
        "libraries": [library["name"] for library in libraries],
        "integration_pairs": [[a, b] for a, b in pairs],
        "confidence_distribution": distribution,
        "confidence_tier": dominant_tier(distribution),
        "source_authority": lowest_authority([library["source_authority"] for library in libraries]),
        "integrations": pair_tiers(mode, libraries, pairs),
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _read_input(source: str):
    """The parsed JSON of a file path, or of stdin for '-'. Raises InputError."""
    try:
        text = sys.stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise InputError(f"cannot read the input {source}: {exc}") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise InputError(f"the input is not valid JSON: {exc}") from exc


def _cmd_pair_tiers(args: argparse.Namespace) -> dict:
    mode, libraries, pairs = parse_stack(_read_input(args.input))
    return {"mode": mode, "integrations": pair_tiers(mode, libraries, pairs)}


def _cmd_metadata(args: argparse.Namespace) -> dict:
    return stack_metadata(*parse_stack(_read_input(args.input)))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skf-render-stack-metadata",
        description=(
            "Compute a stack's pair tiers (the weaker of the two libraries' tiers, in "
            "both modes) and the counted and ranked fields of its metadata.json: "
            "counts, libraries, integration_pairs, confidence_distribution (each "
            "library once), confidence_tier (the dominant tier) and source_authority "
            "(the lowest, community for a library that records none)."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name, func, text in (
        ("pair-tiers", _cmd_pair_tiers, "print the tier of each integration pair as JSON"),
        ("metadata", _cmd_metadata, "print the computed metadata.json fields of the stack as JSON"),
    ):
        command = sub.add_parser(name, help=text, description=text)
        command.add_argument(
            "--input",
            required=True,
            help="path to the stack JSON ({mode, libraries, integrations}), or '-' for stdin",
        )
        command.set_defaults(func=func)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        result = args.func(args)
    except InputError as exc:
        print(f"error: {' '.join(str(exc).split())}", file=sys.stderr)
        return 2
    # ASCII escapes: a Windows console's code page cannot encode every name.
    sys.stdout.write(json.dumps(result, indent=2) + "\n")
    return 0


def _force_utf8(*streams) -> None:
    """Reconfigure the standard streams to UTF-8, keeping each one's error handler.

    A Windows console pipes them as cp1252, which cannot carry every character
    a library name or an error message may hold. stdin is reconfigured before
    its first read, so `--input -` reads the UTF-8 JSON a step pipes.
    """
    for stream in streams:
        if hasattr(stream, "reconfigure"):
            errors = getattr(stream, "errors", None)
            if errors is None:
                stream.reconfigure(encoding="utf-8")
            else:
                stream.reconfigure(encoding="utf-8", errors=errors)


if __name__ == "__main__":
    _force_utf8(sys.stdin, sys.stdout, sys.stderr)
    sys.exit(main())
