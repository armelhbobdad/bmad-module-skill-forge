# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""SKF Scan Manifests — discover and parse package manifests across ecosystems.

Two skill workflows ask the LLM to perform the same deterministic operation:
walk a project root, find every recognised dependency manifest, parse each
one into a `{name, version}` dep list, dedupe across files, and flag whether
the layout looks like a monorepo.

  1. **skf-create-stack-skill / detect-manifests.md §2–§3** — Scans the
     project root to enumerate manifest files (depth 0–1), parses every
     manifest to extract dependency names + versions, dedupes the unique
     set, and feeds the dep list into the ranking stage. The prose lists
     every supported ecosystem with parsing hints; that list is exactly the
     ecosystem table this script implements.

  2. **skf-analyze-source / scan-project.md §2** — Finds the same set of
     manifest files in the broader project-scan pass. Service-config files
     (Dockerfile, docker-compose.yml) stay LLM-driven; only the manifest
     enumeration is extracted here.

Pulling this into a deterministic script gives both stages identical
manifest-set semantics (no LLM drift on what counts as a manifest), a stable
JSON envelope for the LLM to consume, and a single place to evolve the
ecosystem matrix as new languages land.

Subcommand:
  scan <root> [--ecosystems=auto]
      Walk `<root>` (depth 0–1 plus common monorepo packages/* paths) for
      recognised manifests, parse each to extract `production` deps only,
      and emit:
        {
          "manifests": [
            {
              "path": "<rel-from-root, forward-slash>",
              "ecosystem": "<name>",
              "deps": [{"name": "...", "version": "...|null"}]
            },
            ...
          ],
          "total_unique": N,    // unique dep names across all manifests
          "monorepo": <bool>,    // >1 manifest of same ecosystem at non-overlapping depths
          "warnings": ["..."]    // optional: only present if any warning was emitted
        }
      Default `--ecosystems=auto` detects all supported ecosystems. The flag
      is currently a placeholder for future filtering — `auto` is the only
      accepted value today, but its presence keeps the CLI shape stable.

Supported ecosystems (manifest filename → ecosystem):
  - package.json                    → npm           (npm/pnpm/yarn share this)
  - pyproject.toml                  → python        (pip/poetry/pdm)
  - requirements.txt                → python
  - setup.py                        → python
  - setup.cfg                       → python
  - Pipfile                         → python
  - Cargo.toml                      → rust
  - go.mod                          → go
  - pom.xml                         → maven         (java/kotlin)
  - build.gradle                    → gradle
  - build.gradle.kts                → gradle
  - Gemfile                         → ruby
  - composer.json                   → composer
  - Package.swift                   → swift

Parsing approach: JSON manifests via stdlib `json`, TOML via stdlib
`tomllib` (3.11+); text manifests (requirements.txt, Pipfile, setup.py,
setup.cfg, go.mod, Gemfile, pom.xml, build.gradle*, Package.swift) via
ad-hoc regex extraction. Production deps only — devDependencies /
[tool.poetry.dev-dependencies] / require-dev are intentionally skipped to
keep the consumer-facing dep list focused on runtime libraries. Unparseable
manifests emit a top-level `warnings[]` entry and the manifest still appears
in `manifests[]` with whatever deps were salvageable (possibly empty).

Exit codes:
  0  — success (including: zero manifests found — emit empty result)
  1  — user error (bad root path, root not a directory)

CLI example:
  uv run skf-scan-manifests.py scan /path/to/repo
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path
from typing import Iterable


# --------------------------------------------------------------------------
# Ecosystem table
# --------------------------------------------------------------------------


# (manifest filename) → ecosystem label. Order matters only for the scan walk
# (we test each name in order, but every match is recorded). Lowercase compare
# is NOT used — manifest filenames are case-sensitive on POSIX, and Windows
# CI normalises case during the FS walk anyway.
MANIFEST_ECOSYSTEMS: dict[str, str] = {
    "package.json": "npm",
    "pyproject.toml": "python",
    "requirements.txt": "python",
    "setup.py": "python",
    "setup.cfg": "python",
    "Pipfile": "python",
    "Cargo.toml": "rust",
    "go.mod": "go",
    "pom.xml": "maven",
    "build.gradle": "gradle",
    "build.gradle.kts": "gradle",
    "Gemfile": "ruby",
    "composer.json": "composer",
    "Package.swift": "swift",
}

# Directories the scan must never descend into. Mirrors
# references/manifest-patterns.md "Scan Exclusion Patterns".
EXCLUDED_DIRS: frozenset[str] = frozenset(
    {
        "node_modules",
        ".venv",
        "venv",
        ".env",
        "vendor",
        "Pods",
        "dist",
        "build",
        "out",
        "target",
        "__pycache__",
        ".next",
        ".nuxt",
        ".output",
        ".git",
    }
)


# --------------------------------------------------------------------------
# Walking
# --------------------------------------------------------------------------


def _is_excluded_dir(name: str) -> bool:
    """Return True if the dir name should be skipped during scan."""
    if name in EXCLUDED_DIRS:
        return True
    # Hidden directories (".github", ".idea", etc.) — never descend
    if name.startswith(".") and name != ".":
        return True
    return False


def find_manifests(root: Path) -> list[Path]:
    """Walk `root` returning every recognised manifest file.

    Excludes `EXCLUDED_DIRS` and all hidden directories. Returns absolute
    paths in stable sorted order so caller output is reproducible.
    """
    found: list[Path] = []
    # Iterative BFS so we can prune at the directory level.
    stack: list[Path] = [root]
    while stack:
        current = stack.pop()
        try:
            entries = sorted(current.iterdir(), key=lambda p: p.name)
        except OSError:
            continue
        for entry in entries:
            try:
                if entry.is_dir():
                    if _is_excluded_dir(entry.name):
                        continue
                    stack.append(entry)
                elif entry.is_file() and entry.name in MANIFEST_ECOSYSTEMS:
                    found.append(entry)
            except OSError:
                continue
    found.sort()
    return found


# --------------------------------------------------------------------------
# Parsers
# --------------------------------------------------------------------------


Dep = dict  # {"name": str, "version": str | None}


def _safe_read_text(path: Path) -> str | None:
    """Read a file as utf-8 text; return None on failure (caller emits warning)."""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def parse_package_json(text: str) -> tuple[list[Dep], list[str]]:
    """Extract `dependencies` (skip devDependencies) from a package.json."""
    warnings: list[str] = []
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return [], [f"package.json: JSON parse failed ({exc.msg})"]
    if not isinstance(data, dict):
        return [], ["package.json: top-level is not an object"]
    deps_raw = data.get("dependencies")
    if deps_raw is None:
        return [], warnings
    if not isinstance(deps_raw, dict):
        return [], ["package.json: `dependencies` is not an object"]
    deps: list[Dep] = []
    for name, version in deps_raw.items():
        if not isinstance(name, str):
            continue
        ver = version if isinstance(version, str) else None
        deps.append({"name": name, "version": ver})
    return deps, warnings


def parse_pyproject_toml(text: str) -> tuple[list[Dep], list[str]]:
    """Extract production deps from a pyproject.toml.

    Supports both PEP 621 `[project] dependencies = [...]` and Poetry-style
    `[tool.poetry.dependencies]`. Dev-only sections (`[project.optional-dependencies.dev]`,
    `[tool.poetry.dev-dependencies]`) are skipped.
    """
    warnings: list[str] = []
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        return [], [f"pyproject.toml: TOML parse failed ({exc})"]
    deps: list[Dep] = []

    # PEP 621
    project = data.get("project")
    if isinstance(project, dict):
        deps_raw = project.get("dependencies")
        if isinstance(deps_raw, list):
            for entry in deps_raw:
                if not isinstance(entry, str):
                    continue
                parsed = _parse_pep508_or_pip(entry)
                if parsed:
                    deps.append(parsed)

    # Poetry
    poetry = data.get("tool", {}).get("poetry") if isinstance(data.get("tool"), dict) else None
    if isinstance(poetry, dict):
        deps_raw = poetry.get("dependencies")
        if isinstance(deps_raw, dict):
            for name, spec in deps_raw.items():
                if not isinstance(name, str) or name.lower() == "python":
                    continue
                if isinstance(spec, str):
                    deps.append({"name": name, "version": spec})
                elif isinstance(spec, dict):
                    ver = spec.get("version") if isinstance(spec.get("version"), str) else None
                    deps.append({"name": name, "version": ver})
                else:
                    deps.append({"name": name, "version": None})

    return deps, warnings


_PIP_REQ = re.compile(
    r"""
    ^\s*
    (?P<name>[A-Za-z0-9_.\-]+)
    \s*
    (?:\[[^\]]*\])?              # optional extras
    \s*
    (?P<op>==|>=|<=|~=|!=|>|<)?
    \s*
    (?P<version>[A-Za-z0-9_.\-+*]+)?
    """,
    re.VERBOSE,
)


def _parse_pep508_or_pip(line: str) -> Dep | None:
    """Best-effort parse of a PEP 508 / pip requirement line."""
    line = line.strip()
    if not line or line.startswith("#") or line.startswith("-"):
        return None
    # Strip environment markers and comments
    if ";" in line:
        line = line.split(";", 1)[0].strip()
    if "#" in line:
        line = line.split("#", 1)[0].strip()
    m = _PIP_REQ.match(line)
    if not m:
        return {"name": "<unparsable>", "version": None}
    name = m.group("name")
    ver = m.group("version")
    op = m.group("op")
    version = (op + ver) if (op and ver) else (ver if ver else None)
    return {"name": name, "version": version}


def parse_requirements_txt(text: str) -> tuple[list[Dep], list[str]]:
    deps: list[Dep] = []
    warnings: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        parsed = _parse_pep508_or_pip(line)
        if parsed:
            deps.append(parsed)
    return deps, warnings


def parse_setup_py(text: str) -> tuple[list[Dep], list[str]]:
    """Best-effort regex extraction of `install_requires=[...]` from setup.py."""
    warnings: list[str] = []
    m = re.search(r"install_requires\s*=\s*\[([^\]]*)\]", text, re.DOTALL)
    if not m:
        return [], warnings
    deps: list[Dep] = []
    for match in re.finditer(r"""(['"])([^'"]+)\1""", m.group(1)):
        entry = match.group(2).strip()
        parsed = _parse_pep508_or_pip(entry)
        if parsed:
            deps.append(parsed)
    return deps, warnings


def parse_setup_cfg(text: str) -> tuple[list[Dep], list[str]]:
    """Extract `install_requires` from setup.cfg's `[options]` section."""
    warnings: list[str] = []
    # find [options] section through next [section]
    sec = re.search(
        r"\[options\](.*?)(?=^\[|\Z)", text, re.MULTILINE | re.DOTALL
    )
    if not sec:
        return [], warnings
    body = sec.group(1)
    m = re.search(r"install_requires\s*=\s*((?:\n[ \t]+\S.*)+)", body)
    if not m:
        return [], warnings
    deps: list[Dep] = []
    for line in m.group(1).splitlines():
        entry = line.strip()
        if not entry:
            continue
        parsed = _parse_pep508_or_pip(entry)
        if parsed:
            deps.append(parsed)
    return deps, warnings


def parse_pipfile(text: str) -> tuple[list[Dep], list[str]]:
    """Pipfile is TOML — read `[packages]` (skip `[dev-packages]`)."""
    warnings: list[str] = []
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        return [], [f"Pipfile: TOML parse failed ({exc})"]
    deps_raw = data.get("packages")
    if not isinstance(deps_raw, dict):
        return [], warnings
    deps: list[Dep] = []
    for name, spec in deps_raw.items():
        if not isinstance(name, str):
            continue
        if isinstance(spec, str):
            deps.append({"name": name, "version": spec if spec != "*" else None})
        elif isinstance(spec, dict):
            ver = spec.get("version") if isinstance(spec.get("version"), str) else None
            deps.append({"name": name, "version": ver if ver and ver != "*" else None})
        else:
            deps.append({"name": name, "version": None})
    return deps, warnings


def parse_cargo_toml(text: str) -> tuple[list[Dep], list[str]]:
    """Extract `[dependencies]` (skip `[dev-dependencies]`) from Cargo.toml."""
    warnings: list[str] = []
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        return [], [f"Cargo.toml: TOML parse failed ({exc})"]
    deps_raw = data.get("dependencies")
    if not isinstance(deps_raw, dict):
        return [], warnings
    deps: list[Dep] = []
    for name, spec in deps_raw.items():
        if not isinstance(name, str):
            continue
        if isinstance(spec, str):
            deps.append({"name": name, "version": spec})
        elif isinstance(spec, dict):
            ver = spec.get("version") if isinstance(spec.get("version"), str) else None
            deps.append({"name": name, "version": ver})
        else:
            deps.append({"name": name, "version": None})
    return deps, warnings


_GO_REQUIRE_LINE = re.compile(
    r"^\s*(?P<name>[A-Za-z0-9_./\-]+)\s+(?P<version>v[\w.\-+]+|[\w.\-+]+)\s*(?://.*)?$"
)


def parse_go_mod(text: str) -> tuple[list[Dep], list[str]]:
    """Extract `require (...)` and single-line `require` entries from go.mod."""
    warnings: list[str] = []
    deps: list[Dep] = []
    # Single-line: `require <module> <version>`
    for line in text.splitlines():
        m = re.match(
            r"^\s*require\s+(?P<name>[A-Za-z0-9_./\-]+)\s+(?P<version>v[\w.\-+]+|[\w.\-+]+)",
            line,
        )
        if m:
            deps.append({"name": m.group("name"), "version": m.group("version")})

    # Block: `require ( ... )`
    for block in re.finditer(r"require\s*\(\s*(.*?)\s*\)", text, re.DOTALL):
        body = block.group(1)
        for line in body.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("//"):
                continue
            # exclude "// indirect" suffix from version
            m = _GO_REQUIRE_LINE.match(stripped)
            if m:
                deps.append({"name": m.group("name"), "version": m.group("version")})
    return deps, warnings


def parse_pom_xml(text: str) -> tuple[list[Dep], list[str]]:
    """Best-effort regex extraction of <dependency>...</dependency> blocks."""
    warnings: list[str] = []
    deps: list[Dep] = []
    for block in re.finditer(r"<dependency>(.*?)</dependency>", text, re.DOTALL):
        body = block.group(1)
        scope_m = re.search(r"<scope>\s*(.*?)\s*</scope>", body)
        # skip test/provided/system scopes — runtime + compile + (no-scope) are production
        if scope_m and scope_m.group(1).strip().lower() in {"test", "provided", "system"}:
            continue
        gid = re.search(r"<groupId>\s*(.*?)\s*</groupId>", body)
        aid = re.search(r"<artifactId>\s*(.*?)\s*</artifactId>", body)
        ver = re.search(r"<version>\s*(.*?)\s*</version>", body)
        if not gid or not aid:
            continue
        name = f"{gid.group(1).strip()}:{aid.group(1).strip()}"
        version = ver.group(1).strip() if ver else None
        deps.append({"name": name, "version": version})
    return deps, warnings


_GRADLE_DEP = re.compile(
    r"""(?P<scope>implementation|api|compile|runtimeOnly)
        \s*\(?\s*
        (?:['"])
        (?P<coord>[^'"]+)
        (?:['"])
        """,
    re.VERBOSE,
)


def parse_gradle(text: str) -> tuple[list[Dep], list[str]]:
    """Extract `implementation/api/compile/runtimeOnly` coords from a Gradle build script."""
    warnings: list[str] = []
    deps: list[Dep] = []
    for m in _GRADLE_DEP.finditer(text):
        coord = m.group("coord")
        parts = coord.split(":")
        if len(parts) == 2:
            name, version = parts[0] + ":" + parts[1], None
            deps.append({"name": name, "version": version})
        elif len(parts) >= 3:
            name = parts[0] + ":" + parts[1]
            version = parts[2]
            deps.append({"name": name, "version": version})
    return deps, warnings


_GEMFILE_LINE = re.compile(
    r"""^\s*gem\s+
        (?:['"])(?P<name>[^'"]+)(?:['"])
        (?:\s*,\s*(?:['"])(?P<version>[^'"]+)(?:['"]))?
        """,
    re.VERBOSE,
)


def parse_gemfile(text: str) -> tuple[list[Dep], list[str]]:
    """Extract `gem 'name', 'version'` entries from a Gemfile."""
    warnings: list[str] = []
    deps: list[Dep] = []
    # naive: skip lines inside `group :development|:test do ... end` blocks
    skip_depth = 0
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0]  # strip comments
        if re.search(r"group\s+:(development|test)\b", line):
            skip_depth += 1
            continue
        if skip_depth > 0:
            if re.search(r"\bend\b", line):
                skip_depth -= 1
            continue
        m = _GEMFILE_LINE.match(line)
        if m:
            deps.append({"name": m.group("name"), "version": m.group("version")})
    return deps, warnings


def parse_composer_json(text: str) -> tuple[list[Dep], list[str]]:
    """Extract `require` (skip `require-dev`) from a composer.json."""
    warnings: list[str] = []
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return [], [f"composer.json: JSON parse failed ({exc.msg})"]
    if not isinstance(data, dict):
        return [], ["composer.json: top-level is not an object"]
    deps_raw = data.get("require")
    if deps_raw is None:
        return [], warnings
    if not isinstance(deps_raw, dict):
        return [], ["composer.json: `require` is not an object"]
    deps: list[Dep] = []
    for name, version in deps_raw.items():
        if not isinstance(name, str):
            continue
        # skip platform / php constraints
        if name.lower() == "php" or name.startswith("ext-"):
            continue
        deps.append(
            {"name": name, "version": version if isinstance(version, str) else None}
        )
    return deps, warnings


_SWIFT_PACKAGE = re.compile(
    r"""\.package\s*\(\s*url\s*:\s*(?:['"])(?P<url>[^'"]+)(?:['"])
        (?:[^)]*?from\s*:\s*(?:['"])(?P<version>[^'"]+)(?:['"]))?
        """,
    re.VERBOSE | re.DOTALL,
)


def parse_package_swift(text: str) -> tuple[list[Dep], list[str]]:
    """Extract `.package(url:..., from:...)` entries from a Package.swift."""
    warnings: list[str] = []
    deps: list[Dep] = []
    for m in _SWIFT_PACKAGE.finditer(text):
        url = m.group("url")
        # derive name from final path segment, trim trailing `.git`
        name = url.rstrip("/").rsplit("/", 1)[-1]
        if name.endswith(".git"):
            name = name[: -len(".git")]
        version = m.group("version")
        deps.append({"name": name, "version": version})
    return deps, warnings


PARSERS = {
    "package.json": parse_package_json,
    "pyproject.toml": parse_pyproject_toml,
    "requirements.txt": parse_requirements_txt,
    "setup.py": parse_setup_py,
    "setup.cfg": parse_setup_cfg,
    "Pipfile": parse_pipfile,
    "Cargo.toml": parse_cargo_toml,
    "go.mod": parse_go_mod,
    "pom.xml": parse_pom_xml,
    "build.gradle": parse_gradle,
    "build.gradle.kts": parse_gradle,
    "Gemfile": parse_gemfile,
    "composer.json": parse_composer_json,
    "Package.swift": parse_package_swift,
}


# --------------------------------------------------------------------------
# Aggregation
# --------------------------------------------------------------------------


def _parse_manifest(path: Path) -> tuple[list[Dep], list[str]]:
    """Read and parse a single manifest file. Returns (deps, warnings)."""
    parser = PARSERS.get(path.name)
    if parser is None:
        return [], [f"{path.name}: no parser registered"]
    text = _safe_read_text(path)
    if text is None:
        return [], [f"{path.name}: file unreadable"]
    try:
        return parser(text)
    except Exception as exc:  # noqa: BLE001 — best-effort parsing
        return [], [f"{path.name}: parser raised {type(exc).__name__}: {exc}"]


def _is_monorepo(manifests: list[dict]) -> bool:
    """True if any ecosystem has >1 manifest at non-overlapping depths.

    "Non-overlapping" means two manifest paths don't share a strict parent-
    child relationship. Two `package.json` at `./package.json` and
    `./packages/foo/package.json` ARE overlapping (the second is under the
    first), but `./packages/foo/package.json` and `./packages/bar/package.json`
    are NOT overlapping siblings — that's the monorepo signal.
    """
    by_ecosystem: dict[str, list[str]] = {}
    for m in manifests:
        by_ecosystem.setdefault(m["ecosystem"], []).append(m["path"])

    for paths in by_ecosystem.values():
        if len(paths) < 2:
            continue
        # collect parent directories; two manifests overlap iff one's parent
        # dir is a prefix of the other's parent dir
        parents = [p.rsplit("/", 1)[0] if "/" in p else "" for p in paths]
        for i, a in enumerate(parents):
            for j, b in enumerate(parents):
                if i >= j:
                    continue
                if _path_is_ancestor(a, b) or _path_is_ancestor(b, a):
                    continue
                # found a non-overlapping pair — monorepo
                return True
    return False


def _path_is_ancestor(a: str, b: str) -> bool:
    """True if `a` is a strict ancestor of `b` (or equal). Both POSIX-style."""
    if a == b:
        return True
    if a == "":
        return True  # root is ancestor of everything
    return b.startswith(a + "/")


def scan(root: Path) -> dict:
    """Run a full manifest scan rooted at `root`."""
    paths = find_manifests(root)
    manifests: list[dict] = []
    warnings: list[str] = []

    for path in paths:
        deps, warns = _parse_manifest(path)
        rel = path.relative_to(root).as_posix()
        for w in warns:
            warnings.append(f"{rel}: {w}")
        manifests.append(
            {
                "path": rel,
                "ecosystem": MANIFEST_ECOSYSTEMS[path.name],
                "deps": deps,
            }
        )

    unique_names: set[str] = set()
    for m in manifests:
        for dep in m["deps"]:
            name = dep.get("name")
            if isinstance(name, str) and name and name != "<unparsable>":
                unique_names.add(name)

    result: dict = {
        "manifests": manifests,
        "total_unique": len(unique_names),
        "monorepo": _is_monorepo(manifests),
    }
    if warnings:
        result["warnings"] = warnings
    return result


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _cmd_scan(args: argparse.Namespace) -> int:
    root = Path(args.root)
    if not root.is_dir():
        print(f"error: root not a directory: {root}", file=sys.stderr)
        return 1
    if args.ecosystems != "auto":
        print(
            f"error: --ecosystems supports only 'auto' today; got {args.ecosystems!r}",
            file=sys.stderr,
        )
        return 1
    try:
        result = scan(root)
    except OSError as exc:
        print(f"error: filesystem error during scan: {exc}", file=sys.stderr)
        return 1
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skf-scan-manifests",
        description=(
            "Scan a project root for dependency manifests, parse each, and emit "
            "a deduplicated JSON envelope describing the dep set + monorepo flag."
        ),
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_scan = sub.add_parser(
        "scan",
        help="walk root for recognised manifests and emit JSON",
    )
    p_scan.add_argument("root", help="path to project root")
    p_scan.add_argument(
        "--ecosystems",
        default="auto",
        help="ecosystem filter (currently only 'auto' is accepted)",
    )
    p_scan.set_defaults(func=_cmd_scan)

    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
