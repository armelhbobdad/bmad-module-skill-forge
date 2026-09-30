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
  scan <root> [--ecosystems=auto] [--include-dev]
      Walk `<root>` (every depth, pruning the excluded and hidden
      directories) for recognised manifests, parse each one and emit:
        {
          "manifests": [
            {
              "path": "<rel-from-root, forward-slash>",
              "ecosystem": "<name>",
              "name": "<the package's own name>" | null,
              "private": true | false | null,
              "deps": [{"name": "...", "version": "...|null"}],
              "internal_deps": ["<name of another scanned manifest>", ...]
            },
            ...
          ],
          "total_unique": N,          // unique runtime dep names across all manifests
          "monorepo": <bool>,         // >1 manifest of same ecosystem at non-overlapping depths
          "umbrella_candidates": [
            {"path": "...", "name": "...", "ecosystem": "...",
             "internal_dep_count": N, "member_count": M},
            ...
          ],
          "searched_filenames": ["package.json", ...],   // every manifest name looked for
          "warnings": ["..."]         // optional: only present if any warning was emitted
        }
      Default `--ecosystems=auto` detects all supported ecosystems. The flag
      is currently a placeholder for future filtering: `auto` is the only
      accepted value today, but its presence keeps the CLI shape stable.

      `--include-dev` also lists each manifest's development dependencies in
      its `deps[]`, each tagged `"scope": "dev"` (a dependency with no
      `scope` is a runtime one; a name the manifest already lists as runtime
      is not repeated), and adds `total_unique_dev`: the unique names that
      appear only as dev dependencies. Without the flag the output holds
      runtime dependencies only, as before.

Manifest fields:
  name           the name the manifest gives its own package: package.json,
                 composer.json and pyproject.toml ([project] or
                 [tool.poetry]) `name`, setup.py and setup.cfg `name`, Cargo
                 [package] `name`, the go.mod `module` path, pom.xml
                 `groupId:artifactId` (the group inherited from <parent> when
                 absent), Package.swift `Package(name:)`; null for
                 requirements.txt, Pipfile, Gemfile and Gradle build scripts,
                 which name no package.
  private        true when the manifest says the package is not published:
                 package.json `"private": true`, Cargo `publish = false` (or
                 `[]`), the `Private :: Do Not Upload` classifier or Poetry
                 `package-mode = false`, pom.xml `maven.deploy.skip`; false
                 when the manifest could set such a flag and does not; null
                 when it cannot tell (go.mod, composer.json, Package.swift,
                 the formats that name no package, a Cargo virtual workspace
                 or a Cargo `publish` inherited from the workspace).
  internal_deps  the runtime dependencies that name another scanned manifest
                 of the same ecosystem (the workspace members this one uses),
                 as those members spell their names, sorted. Names compare
                 as the ecosystem does (PEP 503 for Python, `-` and `_` alike
                 for Rust, case-insensitive for Composer and Swift), and a
                 pom.xml `${project.groupId}` resolves to its own group.

umbrella_candidates lists the published manifests (named, `private` not
true) whose internal_deps cover at least 2 of the other published members of
their ecosystem, and at least half of them: a root or facade package that
depends on the members it would re-export. A private package (an example or
an app) is never a candidate, since a facade is the public surface. Sorted by
internal_dep_count (highest first), then path. It is a signal for the
cohesion judgment, not a verdict.

Supported ecosystems (manifest filename, then ecosystem): the
`MANIFEST_ECOSYSTEMS` table below. `references/manifest-patterns.md` in
skf-create-stack-skill documents it, and test/test-skf-scan-manifests.py
fails when the two drift.

Parsing approach: JSON manifests via stdlib `json`, TOML via stdlib
`tomllib` (3.11+); text manifests (requirements.txt, Pipfile, setup.py,
setup.cfg, go.mod, Gemfile, pom.xml, build.gradle*, Package.swift) via
ad-hoc regex extraction. `deps[]` holds production dependencies by default,
so the consumer-facing list stays focused on runtime libraries. The
development sections read with `--include-dev`: package.json
`devDependencies`; pyproject.toml `[dependency-groups]`, the
`[project.optional-dependencies]` extras named dev, develop, development,
test, tests, testing, lint, docs or doc, `[tool.poetry.dev-dependencies]`,
every `[tool.poetry.group.<name>.dependencies]`,
`[tool.pdm.dev-dependencies]` and `[tool.uv] dev-dependencies`; setup.py and
setup.cfg `tests_require` and those same extras; Pipfile `[dev-packages]`;
Cargo `[dev-dependencies]`; pom.xml `<scope>test</scope>`; Gradle `test*`
and `androidTest*` configurations; Gemfile gems inside a `group
:development` or `:test` block; composer.json `require-dev`. requirements.txt,
go.mod and Package.swift have no development section. Unparseable manifests
emit a top-level `warnings[]` entry and the manifest still appears in
`manifests[]` with whatever deps were salvageable (possibly empty).

Exit codes:
  0  success (including: zero manifests found, which emits an empty result)
  1  user error (bad root path, root not a directory)

CLI example:
  uv run skf-scan-manifests.py scan /path/to/repo
  uv run skf-scan-manifests.py scan /path/to/repo --include-dev
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
# The same order is `searched_filenames`. The Supported Ecosystems table in
# skf-create-stack-skill's references/manifest-patterns.md mirrors this dict
# (test/test-skf-scan-manifests.py keeps the two equal).
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
# references/manifest-patterns.md "Scan Exclusion Patterns"
# (test/test-skf-scan-manifests.py keeps the two equal).
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
# Development dependencies (--include-dev)
# --------------------------------------------------------------------------


# Optional-dependency extras read as development dependencies.
DEV_EXTRAS: frozenset[str] = frozenset(
    {"dev", "develop", "development", "test", "tests", "testing", "lint", "docs", "doc"}
)


def _table_deps(
    table: object, *, skip_python: bool = False, star_as_none: bool = False
) -> list[Dep]:
    """Deps from a TOML or JSON table of name -> version string or spec table.

    `skip_python` drops Poetry's `python` constraint; `star_as_none` reads a
    `*` version as no version, as Pipfile does.
    """
    if not isinstance(table, dict):
        return []
    deps: list[Dep] = []
    for name, spec in table.items():
        if not isinstance(name, str) or (skip_python and name.lower() == "python"):
            continue
        if isinstance(spec, dict):
            spec = spec.get("version")
        version = spec if isinstance(spec, str) else None
        if star_as_none and version == "*":
            version = None
        deps.append({"name": name, "version": version})
    return deps


def _requirement_list(entries: object) -> list[Dep]:
    """Deps from a list of PEP 508 strings (tables such as include-group skipped)."""
    if not isinstance(entries, list):
        return []
    deps: list[Dep] = []
    for entry in entries:
        if isinstance(entry, str):
            parsed = _parse_pep508_or_pip(entry)
            if parsed:
                deps.append(parsed)
    return deps


def dev_package_json(text: str) -> list[Dep]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    return _table_deps(data.get("devDependencies")) if isinstance(data, dict) else []


def dev_pyproject_toml(text: str) -> list[Dep]:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return []
    deps: list[Dep] = []
    groups = data.get("dependency-groups")
    if isinstance(groups, dict):
        for entries in groups.values():
            deps.extend(_requirement_list(entries))
    project = data.get("project")
    extras = project.get("optional-dependencies") if isinstance(project, dict) else None
    if isinstance(extras, dict):
        for extra, entries in extras.items():
            if isinstance(extra, str) and extra.lower() in DEV_EXTRAS:
                deps.extend(_requirement_list(entries))
    tool = data.get("tool") if isinstance(data.get("tool"), dict) else {}
    poetry = tool.get("poetry")
    if isinstance(poetry, dict):
        deps.extend(_table_deps(poetry.get("dev-dependencies"), skip_python=True))
        poetry_groups = poetry.get("group")
        if isinstance(poetry_groups, dict):
            for group in poetry_groups.values():
                if isinstance(group, dict):
                    deps.extend(_table_deps(group.get("dependencies"), skip_python=True))
    pdm = tool.get("pdm")
    if isinstance(pdm, dict) and isinstance(pdm.get("dev-dependencies"), dict):
        for entries in pdm["dev-dependencies"].values():
            deps.extend(_requirement_list(entries))
    uv = tool.get("uv")
    if isinstance(uv, dict):
        deps.extend(_requirement_list(uv.get("dev-dependencies")))
    return deps


def dev_setup_py(text: str) -> list[Dep]:
    deps: list[Dep] = []
    m = re.search(r"tests_require\s*=\s*\[([^\]]*)\]", text, re.DOTALL)
    if m:
        for match in re.finditer(r"""(['"])([^'"]+)\1""", m.group(1)):
            parsed = _parse_pep508_or_pip(match.group(2).strip())
            if parsed:
                deps.append(parsed)
    extras = re.search(r"extras_require\s*=\s*\{(.*?)\}", text, re.DOTALL)
    if extras:
        for group in re.finditer(
            r"""(['"])([\w.-]+)\1\s*:\s*\[([^\]]*)\]""", extras.group(1)
        ):
            if group.group(2).lower() not in DEV_EXTRAS:
                continue
            for match in re.finditer(r"""(['"])([^'"]+)\1""", group.group(3)):
                parsed = _parse_pep508_or_pip(match.group(2).strip())
                if parsed:
                    deps.append(parsed)
    return deps


def _cfg_section(text: str, name: str) -> str:
    sec = re.search(
        rf"^\[{re.escape(name)}\][ \t]*$(.*?)(?=^\[|\Z)", text, re.MULTILINE | re.DOTALL
    )
    return sec.group(1) if sec else ""


def _cfg_values(value: str) -> list[Dep]:
    deps: list[Dep] = []
    for line in value.splitlines():
        parsed = _parse_pep508_or_pip(line.strip())
        if parsed:
            deps.append(parsed)
    return deps


# `key = value` in a setup.cfg section, with its indented continuation lines.
_CFG_OPTION = re.compile(
    r"^(?P<key>[\w.-]+)[ \t]*=[ \t]*(?P<value>.*(?:\n[ \t]+\S.*)*)", re.MULTILINE
)


def dev_setup_cfg(text: str) -> list[Dep]:
    deps: list[Dep] = []
    for m in _CFG_OPTION.finditer(_cfg_section(text, "options")):
        if m.group("key") == "tests_require":
            deps.extend(_cfg_values(m.group("value")))
    for m in _CFG_OPTION.finditer(_cfg_section(text, "options.extras_require")):
        if m.group("key").lower() in DEV_EXTRAS:
            deps.extend(_cfg_values(m.group("value")))
    return deps


def dev_pipfile(text: str) -> list[Dep]:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return []
    return _table_deps(data.get("dev-packages"), star_as_none=True)


def dev_cargo_toml(text: str) -> list[Dep]:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return []
    return _table_deps(data.get("dev-dependencies"))


def dev_pom_xml(text: str) -> list[Dep]:
    deps: list[Dep] = []
    for block in re.finditer(r"<dependency>(.*?)</dependency>", text, re.DOTALL):
        body = block.group(1)
        scope_m = re.search(r"<scope>\s*(.*?)\s*</scope>", body)
        if not scope_m or scope_m.group(1).strip().lower() != "test":
            continue
        gid = re.search(r"<groupId>\s*(.*?)\s*</groupId>", body)
        aid = re.search(r"<artifactId>\s*(.*?)\s*</artifactId>", body)
        ver = re.search(r"<version>\s*(.*?)\s*</version>", body)
        if gid and aid:
            deps.append(
                {
                    "name": f"{gid.group(1).strip()}:{aid.group(1).strip()}",
                    "version": ver.group(1).strip() if ver else None,
                }
            )
    return deps


# Whitespace or `(` must follow the configuration, so the `"test"` inside
# `testImplementation(kotlin("test"))` never starts a match.
_GRADLE_DEV_DEP = re.compile(
    r"""\b(?:test|androidTest)[A-Za-z]*
        (?:\s+|\s*\(\s*)
        (?:['"])
        (?P<coord>[^'"\n]+)
        (?:['"])
        """,
    re.VERBOSE,
)


def dev_gradle(text: str) -> list[Dep]:
    deps: list[Dep] = []
    for m in _GRADLE_DEV_DEP.finditer(text):
        parts = m.group("coord").split(":")
        if len(parts) >= 2:
            deps.append(
                {"name": f"{parts[0]}:{parts[1]}", "version": parts[2] if len(parts) >= 3 else None}
            )
    return deps


def dev_gemfile(text: str) -> list[Dep]:
    """Gems inside `group :development` / `group :test` blocks."""
    deps: list[Dep] = []
    depth = 0
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0]
        if re.search(r"group\s+:(development|test)\b", line):
            depth += 1
            continue
        if depth > 0:
            if re.search(r"\bend\b", line):
                depth -= 1
                continue
            m = _GEMFILE_LINE.match(line)
            if m:
                deps.append({"name": m.group("name"), "version": m.group("version")})
    return deps


def dev_composer_json(text: str) -> list[Dep]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, dict):
        return []
    return [
        d
        for d in _table_deps(data.get("require-dev"))
        if d["name"].lower() != "php" and not d["name"].startswith("ext-")
    ]


DEV_PARSERS = {
    "package.json": dev_package_json,
    "pyproject.toml": dev_pyproject_toml,
    "setup.py": dev_setup_py,
    "setup.cfg": dev_setup_cfg,
    "Pipfile": dev_pipfile,
    "Cargo.toml": dev_cargo_toml,
    "pom.xml": dev_pom_xml,
    "build.gradle": dev_gradle,
    "build.gradle.kts": dev_gradle,
    "Gemfile": dev_gemfile,
    "composer.json": dev_composer_json,
}


# --------------------------------------------------------------------------
# Package identity: the manifest's own name and publish flag
# --------------------------------------------------------------------------


PRIVATE_CLASSIFIER = "Private :: Do Not Upload"

Identity = tuple  # (name: str | None, private: bool | None)


def identity_package_json(text: str) -> Identity:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None, None
    if not isinstance(data, dict):
        return None, None
    name = data.get("name") if isinstance(data.get("name"), str) and data.get("name") else None
    return name, data.get("private") is True


def identity_pyproject_toml(text: str) -> Identity:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return None, None
    project = data.get("project") if isinstance(data.get("project"), dict) else {}
    tool = data.get("tool") if isinstance(data.get("tool"), dict) else {}
    poetry = tool.get("poetry") if isinstance(tool.get("poetry"), dict) else {}
    name = project.get("name") or poetry.get("name")
    name = name if isinstance(name, str) and name else None
    if not project and not poetry:
        return None, None
    classifiers = [
        c
        for source in (project.get("classifiers"), poetry.get("classifiers"))
        if isinstance(source, list)
        for c in source
    ]
    private = PRIVATE_CLASSIFIER in classifiers or poetry.get("package-mode") is False
    return name, private


def identity_setup_py(text: str) -> Identity:
    call = re.search(r"\bsetup\s*\((.*)", text, re.DOTALL)
    m = re.search(r"""\bname\s*=\s*(['"])([^'"]+)\1""", call.group(1)) if call else None
    if not m:
        return None, None
    return m.group(2), PRIVATE_CLASSIFIER in text


def identity_setup_cfg(text: str) -> Identity:
    metadata = _cfg_section(text, "metadata")
    m = re.search(r"^name[ \t]*=[ \t]*(\S+)", metadata, re.MULTILINE)
    if not m:
        return None, None
    return m.group(1), PRIVATE_CLASSIFIER in metadata


def identity_cargo_toml(text: str) -> Identity:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return None, None
    package = data.get("package")
    if not isinstance(package, dict):
        return None, None  # a virtual workspace manifest names no package
    name = package.get("name") if isinstance(package.get("name"), str) else None
    publish = package.get("publish")
    if isinstance(publish, dict):
        return name, None  # `publish.workspace = true`: set by the workspace root
    return name, publish is False or publish == []


def identity_go_mod(text: str) -> Identity:
    m = re.search(r"""^\s*module\s+["`]?([^\s"`]+)""", text, re.MULTILINE)
    return (m.group(1) if m else None), None


# Sections of a pom.xml whose <groupId>/<artifactId> are not the project's own.
_POM_FOREIGN_SECTIONS = (
    "parent",
    "dependencies",
    "dependencyManagement",
    "build",
    "profiles",
    "reporting",
    "modules",
)


def identity_pom_xml(text: str) -> Identity:
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    parent = re.search(r"<parent>(.*?)</parent>", text, re.DOTALL)
    own = text
    for tag in _POM_FOREIGN_SECTIONS:
        own = re.sub(rf"<{tag}>.*?</{tag}>", "", own, flags=re.DOTALL)
    aid = re.search(r"<artifactId>\s*(.*?)\s*</artifactId>", own)
    if not aid:
        return None, None
    gid = re.search(r"<groupId>\s*(.*?)\s*</groupId>", own)
    if not gid and parent:
        gid = re.search(r"<groupId>\s*(.*?)\s*</groupId>", parent.group(1))
    name = f"{gid.group(1)}:{aid.group(1)}" if gid else aid.group(1)
    skip = re.search(r"<maven\.deploy\.skip>\s*true\s*</maven\.deploy\.skip>", own)
    return name, skip is not None


def identity_composer_json(text: str) -> Identity:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None, None
    if not isinstance(data, dict):
        return None, None
    name = data.get("name")
    return (name if isinstance(name, str) and name else None), None


def identity_package_swift(text: str) -> Identity:
    m = re.search(r'\bPackage\s*\(\s*name\s*:\s*"([^"]+)"', text)
    return (m.group(1) if m else None), None


IDENTITY_READERS = {
    "package.json": identity_package_json,
    "pyproject.toml": identity_pyproject_toml,
    "setup.py": identity_setup_py,
    "setup.cfg": identity_setup_cfg,
    "Cargo.toml": identity_cargo_toml,
    "go.mod": identity_go_mod,
    "pom.xml": identity_pom_xml,
    "composer.json": identity_composer_json,
    "Package.swift": identity_package_swift,
}


# --------------------------------------------------------------------------
# Aggregation
# --------------------------------------------------------------------------


def _describe_manifest(path: Path, include_dev: bool) -> tuple[dict, list[str]]:
    """Read one manifest once: its identity, runtime deps and (optionally)
    dev deps tagged `scope: dev`. Returns (record fields, warnings)."""
    record: dict = {"name": None, "private": None, "deps": []}
    parser = PARSERS.get(path.name)
    if parser is None:
        return record, [f"{path.name}: no parser registered"]
    text = _safe_read_text(path)
    if text is None:
        return record, [f"{path.name}: file unreadable"]
    try:
        deps, warnings = parser(text)
    except Exception as exc:  # noqa: BLE001 (best-effort parsing)
        deps, warnings = [], [f"{path.name}: parser raised {type(exc).__name__}: {exc}"]
    # identity and dev readers are best-effort too; the runtime parser has
    # already reported a malformed file
    reader = IDENTITY_READERS.get(path.name)
    try:
        record["name"], record["private"] = reader(text) if reader else (None, None)
    except Exception:  # noqa: BLE001
        pass
    if include_dev and path.name in DEV_PARSERS:
        try:
            dev = DEV_PARSERS[path.name](text)
        except Exception:  # noqa: BLE001
            dev = []
        runtime = {d["name"] for d in deps}
        for dep in dev:
            if dep["name"] not in runtime:
                runtime.add(dep["name"])
                deps.append({**dep, "scope": "dev"})
    record["deps"] = deps
    return record, warnings


def _member_key(ecosystem: str, name: str) -> str:
    """How an ecosystem compares package names."""
    if ecosystem == "python":
        return re.sub(r"[-_.]+", "-", name).lower()
    if ecosystem == "rust":
        return name.lower().replace("_", "-")
    if ecosystem in ("composer", "swift"):
        return name.lower()
    return name


def _add_internal_deps(manifests: list[dict]) -> None:
    """Set each manifest's `internal_deps`: its runtime deps that name another
    scanned manifest of the same ecosystem, spelled as that member names itself."""
    members: dict[str, dict[str, str]] = {}
    for m in manifests:
        if m["name"]:
            members.setdefault(m["ecosystem"], {}).setdefault(
                _member_key(m["ecosystem"], m["name"]), m["name"]
            )
    for m in manifests:
        ecosystem = m["ecosystem"]
        known = members.get(ecosystem, {})
        own = _member_key(ecosystem, m["name"]) if m["name"] else None
        # a pom.xml names sibling modules as ${project.groupId}:<artifact>
        group = None
        if ecosystem == "maven" and m["name"] and ":" in m["name"]:
            group = m["name"].split(":", 1)[0]
        internal: set[str] = set()
        for dep in m["deps"]:
            name = dep.get("name")
            if not isinstance(name, str) or dep.get("scope") == "dev":
                continue
            if group:
                for token in ("${project.groupId}", "${pom.groupId}", "${groupId}"):
                    name = name.replace(token, group)
            key = _member_key(ecosystem, name)
            if key != own and key in known:
                internal.add(known[key])
        m["internal_deps"] = sorted(internal)


def _umbrella_candidates(manifests: list[dict]) -> list[dict]:
    """Published manifests whose internal_deps cover at least 2, and at least
    half, of the other published members of their ecosystem."""
    published: dict[str, set[str]] = {}
    for m in manifests:
        if m["name"] and m["private"] is not True:
            published.setdefault(m["ecosystem"], set()).add(_member_key(m["ecosystem"], m["name"]))
    candidates: list[dict] = []
    for m in manifests:
        if not m["name"] or m["private"] is True:
            continue
        ecosystem = m["ecosystem"]
        own = _member_key(ecosystem, m["name"])
        pool = published.get(ecosystem, set()) - {own}
        covered = {_member_key(ecosystem, n) for n in m["internal_deps"]} & pool
        if len(covered) >= 2 and 2 * len(covered) >= len(pool):
            candidates.append(
                {
                    "path": m["path"],
                    "name": m["name"],
                    "ecosystem": ecosystem,
                    "internal_dep_count": len(covered),
                    "member_count": len(pool),
                }
            )
    candidates.sort(key=lambda c: (-c["internal_dep_count"], c["path"]))
    return candidates


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


def scan(root: Path, include_dev: bool = False) -> dict:
    """Run a full manifest scan rooted at `root`.

    With `include_dev`, each manifest's development dependencies join its
    `deps[]` tagged `scope: dev`, and `total_unique_dev` is added.
    """
    paths = find_manifests(root)
    manifests: list[dict] = []
    warnings: list[str] = []

    for path in paths:
        record, warns = _describe_manifest(path, include_dev)
        rel = path.relative_to(root).as_posix()
        for w in warns:
            warnings.append(f"{rel}: {w}")
        manifests.append(
            {
                "path": rel,
                "ecosystem": MANIFEST_ECOSYSTEMS[path.name],
                "name": record["name"],
                "private": record["private"],
                "deps": record["deps"],
            }
        )
    _add_internal_deps(manifests)

    unique_names: set[str] = set()
    dev_names: set[str] = set()
    for m in manifests:
        for dep in m["deps"]:
            name = dep.get("name")
            if isinstance(name, str) and name and name != "<unparsable>":
                (dev_names if dep.get("scope") == "dev" else unique_names).add(name)

    result: dict = {
        "manifests": manifests,
        "total_unique": len(unique_names),
    }
    if include_dev:
        result["total_unique_dev"] = len(dev_names - unique_names)
    result["monorepo"] = _is_monorepo(manifests)
    result["umbrella_candidates"] = _umbrella_candidates(manifests)
    result["searched_filenames"] = list(MANIFEST_ECOSYSTEMS)
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
        result = scan(root, include_dev=args.include_dev)
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
    p_scan.add_argument(
        "--include-dev",
        action="store_true",
        help="also list development dependencies, each tagged scope: dev",
    )
    p_scan.set_defaults(func=_cmd_scan)

    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
