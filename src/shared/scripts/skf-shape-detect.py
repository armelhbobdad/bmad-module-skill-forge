# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""SKF Shape Detect — classify repos into known skill shapes from manifest files.

Single source of truth for shape-level classification consumed by
skf-analyze-source (AN auto-scope), skf-brief-skill (BS auto-brief),
and skf-test-skill (TS threshold selection).  Moving shape heuristics
into a shared script eliminates duplicate classification logic across
three pipelines.

The five-shape heuristic ladder (apply in order, first match wins):

  1. language-reference — parser/grammar/language-toolchain project
     Signals: parser-related deps (pest, antlr4, tree-sitter, lark ...)
  2. stack-compose     — multi-ecosystem composite project
     Signals: manifests from 2+ distinct ecosystems
  3. reference-app     — application, CLI, or demo project
     Signals: npm bin field, Rust [[bin]], framework deps
  4. library-API       — library exposing a programmatic API
     Signals: main/module/exports fields, [lib] target, export count
  5. unknown           — no heuristic matched

CLI:
  uv run src/shared/scripts/skf-shape-detect.py \\
      --repo-url <url> --manifests <path1,path2,...>

Input:
  --repo-url   repository URL (required; context only, no cloning)
  --manifests  comma-separated local file paths to manifest files (required)

Output (JSON on stdout):
  shape         library-API | reference-app | language-reference
                | stack-compose | unknown
  signals       array of human-readable evidence strings
  confidence    float 0.0-1.0
  export_count  integer (total public-facing exports)
  package_count integer (distinct packages detected)

Exit codes:
  0  shape classified (not unknown)
  1  unknown shape (no heuristic matched)
  2  error (invalid args, missing/unreadable files, parse failure)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    import tomllib
except ImportError:
    tomllib = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Parser/grammar deps that signal language-reference shape
# ---------------------------------------------------------------------------

_PARSER_DEPS_NPM = frozenset({
    "antlr4", "antlr4-runtime", "tree-sitter", "nearley",
    "chevrotain", "pegjs", "peggy", "ohm-js", "jison",
    "moo", "lezer", "@lezer/generator",
})
_PARSER_DEPS_PYTHON = frozenset({
    "antlr4-tools", "antlr4-runtime", "lark", "lark-parser",
    "ply", "tree-sitter", "textx", "parso", "pyparsing",
    "sly", "tatsu",
})
_PARSER_DEPS_RUST = frozenset({
    "pest", "pest_derive", "lalrpop", "lalrpop-util",
    "tree-sitter", "nom", "chumsky", "winnow", "logos",
})

_ALL_PARSER_DEPS = _PARSER_DEPS_NPM | _PARSER_DEPS_PYTHON | _PARSER_DEPS_RUST

# ---------------------------------------------------------------------------
# Framework deps that signal reference-app shape
# ---------------------------------------------------------------------------

_FRAMEWORK_DEPS_NPM = frozenset({
    "next", "nuxt", "express", "fastify", "koa", "hono",
    "@nestjs/core", "gatsby", "electron",
})
_FRAMEWORK_DEPS_PYTHON = frozenset({
    "django", "flask", "fastapi", "uvicorn", "starlette",
    "tornado", "aiohttp", "sanic", "streamlit", "gradio",
})
_FRAMEWORK_DEPS_RUST = frozenset({
    "actix-web", "axum", "rocket", "warp", "tide",
    "tauri", "dioxus", "leptos", "yew",
})

_ALL_FRAMEWORK_DEPS = _FRAMEWORK_DEPS_NPM | _FRAMEWORK_DEPS_PYTHON | _FRAMEWORK_DEPS_RUST


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _die(message: str, code: str = "INTERNAL_ERROR") -> None:
    json.dump({"error": message, "code": code}, sys.stderr, ensure_ascii=False)
    sys.stderr.write("\n")
    sys.exit(2)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


# ---------------------------------------------------------------------------
# Minimal TOML parser (Python < 3.11 fallback)
# ---------------------------------------------------------------------------

def _split_preserving_nesting(s: str, sep: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    in_str = ""
    for ch in s:
        if in_str:
            buf.append(ch)
            if ch == in_str:
                in_str = ""
            continue
        if ch in ('"', "'"):
            in_str = ch
            buf.append(ch)
            continue
        if ch in ("[", "{"):
            depth += 1
            buf.append(ch)
            continue
        if ch in ("]", "}"):
            depth -= 1
            buf.append(ch)
            continue
        if ch == sep and depth == 0:
            parts.append("".join(buf))
            buf = []
            continue
        buf.append(ch)
    if buf:
        parts.append("".join(buf))
    return parts


def _decode_toml_value(raw: str) -> Any:
    s = raw.strip()
    if not s:
        return ""
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        return s[1:-1]
    if len(s) >= 2 and s[0] == "'" and s[-1] == "'":
        return s[1:-1]
    if s == "true":
        return True
    if s == "false":
        return False
    if s.startswith("["):
        idx = s.rfind("]")
        if idx < 0:
            return []
        inner = s[1:idx].strip()
        if not inner:
            return []
        items = []
        for item in _split_preserving_nesting(inner, ","):
            item = item.strip()
            if item and item[0] != "#":
                items.append(_decode_toml_value(item))
        return items
    if s.startswith("{"):
        idx = s.rfind("}")
        if idx < 0:
            return {}
        inner = s[1:idx].strip()
        result: dict[str, Any] = {}
        for pair in _split_preserving_nesting(inner, ","):
            pair = pair.strip()
            if "=" in pair:
                k, _, v = pair.partition("=")
                result[k.strip()] = _decode_toml_value(v.strip())
        return result
    try:
        return int(s) if "." not in s else float(s)
    except ValueError:
        return s


def _loads_toml_fallback(content: str) -> dict[str, Any]:
    """Parse the TOML subset found in pyproject.toml / Cargo.toml."""
    root: dict[str, Any] = {}
    current = root
    lines = content.split("\n")
    i = 0
    while i < len(lines):
        raw = lines[i]
        i += 1
        stripped = raw.strip()
        if not stripped or stripped[0] == "#":
            continue

        # [[array.of.tables]]
        if stripped.startswith("[["):
            end = stripped.find("]]")
            if end < 0:
                continue
            path = [p.strip() for p in stripped[2:end].split(".")]
            target = root
            for key in path[:-1]:
                target = target.setdefault(key, {})
            arr = target.setdefault(path[-1], [])
            if not isinstance(arr, list):
                arr = [arr]
                target[path[-1]] = arr
            entry: dict[str, Any] = {}
            arr.append(entry)
            current = entry
            continue

        # [table]
        if stripped.startswith("[") and not stripped.startswith("[["):
            end = stripped.find("]")
            if end < 0:
                continue
            path = [p.strip() for p in stripped[1:end].split(".")]
            current = root
            for key in path:
                nxt = current.setdefault(key, {})
                if not isinstance(nxt, dict):
                    nxt = {}
                    current[key] = nxt
                current = nxt
            continue

        # key = value
        eq = stripped.find("=")
        if eq < 0:
            continue
        key = stripped[:eq].strip().strip('"')
        val_str = stripped[eq + 1:].strip()

        # Remove trailing comment outside strings
        if val_str and val_str[0] not in ('"', "'", "[", "{"):
            ci = val_str.find(" #")
            if ci >= 0:
                val_str = val_str[:ci].strip()

        # Multi-line array
        if val_str.startswith("[") and "]" not in val_str:
            while i < len(lines):
                val_str += " " + lines[i].strip()
                i += 1
                if "]" in val_str:
                    break

        current[key] = _decode_toml_value(val_str)
    return root


def _parse_toml(content: str) -> dict[str, Any]:
    if tomllib is not None:
        return tomllib.loads(content)
    return _loads_toml_fallback(content)


# ---------------------------------------------------------------------------
# Manifest parsers — each returns a normalised dict
# ---------------------------------------------------------------------------

def _parse_package_json(path: Path) -> dict[str, Any]:
    try:
        content = path.read_text(encoding="utf-8")
        data = json.loads(content)
    except (OSError, json.JSONDecodeError) as exc:
        _die(f"Cannot parse {path.as_posix()}: {exc}", "MANIFEST_PARSE_ERROR")
        return {}  # unreachable

    if not isinstance(data, dict):
        _die(f"Expected JSON object in {path.as_posix()}, got {type(data).__name__}", "MANIFEST_PARSE_ERROR")
        return {}  # unreachable

    deps: set[str] = set()
    for key in ("dependencies", "devDependencies", "peerDependencies"):
        section = data.get(key)
        if isinstance(section, dict):
            deps.update(section)

    exports_field = data.get("exports")
    export_count = 0
    if isinstance(exports_field, dict):
        export_count = len(exports_field)
    elif isinstance(exports_field, str):
        export_count = 1
    elif data.get("main") or data.get("module"):
        export_count = 1

    return {
        "ecosystem": "npm",
        "name": data.get("name", ""),
        "deps": deps,
        "has_bin": bool(data.get("bin")),
        "has_library_structure": bool(
            data.get("main") or data.get("module") or exports_field
        ),
        "export_count": export_count,
    }


def _dep_name_from_pep508(spec: str) -> str:
    """Extract package name from a PEP 508 dependency string."""
    for ch in (">", "<", "=", "!", "[", ";", " "):
        spec = spec.split(ch, 1)[0]
    return spec.strip().lower()


def _parse_pyproject_toml(path: Path) -> dict[str, Any]:
    try:
        content = path.read_text(encoding="utf-8")
        data = _parse_toml(content)
    except OSError as exc:
        _die(f"Cannot read {path.as_posix()}: {exc}", "MANIFEST_READ_ERROR")
        return {}
    except Exception as exc:
        _die(f"Cannot parse {path.as_posix()}: {exc}", "MANIFEST_PARSE_ERROR")
        return {}

    project = data.get("project", {})
    if not isinstance(project, dict):
        project = {}

    deps: set[str] = set()
    for raw in project.get("dependencies", []):
        if isinstance(raw, str):
            name = _dep_name_from_pep508(raw)
            if name:
                deps.add(name)
    poetry_deps = (
        data.get("tool", {}).get("poetry", {}).get("dependencies", {})
    )
    if isinstance(poetry_deps, dict):
        deps.update(k.lower() for k in poetry_deps if k.lower() != "python")

    scripts = project.get("scripts", {})
    gui_scripts = project.get("gui-scripts", {})
    if not isinstance(scripts, dict):
        scripts = {}
    if not isinstance(gui_scripts, dict):
        gui_scripts = {}
    export_count = len(scripts) + len(gui_scripts)
    if export_count == 0 and project.get("name"):
        export_count = 1

    return {
        "ecosystem": "python",
        "name": project.get("name", ""),
        "deps": deps,
        "has_bin": False,
        "has_library_structure": bool(project.get("name")),
        "export_count": export_count,
    }


def _parse_cargo_toml(path: Path) -> dict[str, Any]:
    try:
        content = path.read_text(encoding="utf-8")
        data = _parse_toml(content)
    except OSError as exc:
        _die(f"Cannot read {path.as_posix()}: {exc}", "MANIFEST_READ_ERROR")
        return {}
    except Exception as exc:
        _die(f"Cannot parse {path.as_posix()}: {exc}", "MANIFEST_PARSE_ERROR")
        return {}

    pkg = data.get("package", {})
    if not isinstance(pkg, dict):
        pkg = {}

    deps: set[str] = set()
    for dep_key in ("dependencies", "dev-dependencies", "build-dependencies"):
        section = data.get(dep_key, {})
        if isinstance(section, dict):
            deps.update(k.lower() for k in section)

    has_lib = "lib" in data and isinstance(data["lib"], dict)
    bin_targets = data.get("bin", [])
    if not isinstance(bin_targets, list):
        bin_targets = []
    has_bin = len(bin_targets) > 0

    export_count = (1 if has_lib else 0) + len(bin_targets)
    if export_count == 0 and pkg.get("name"):
        export_count = 1

    workspace_members = data.get("workspace", {}).get("members", [])
    if not isinstance(workspace_members, list):
        workspace_members = []

    return {
        "ecosystem": "rust",
        "name": pkg.get("name", ""),
        "deps": deps,
        "has_bin": has_bin,
        "has_library_structure": has_lib or bool(pkg.get("name")),
        "export_count": export_count,
    }


_PARSERS = {
    "package.json": _parse_package_json,
    "pyproject.toml": _parse_pyproject_toml,
    "Cargo.toml": _parse_cargo_toml,
}


def _parse_manifest(path: Path) -> dict[str, Any]:
    parser = _PARSERS.get(path.name)
    if parser is None:
        _die(f"Unsupported manifest type: {path.name}", "UNSUPPORTED_MANIFEST")
    return parser(path)


# ---------------------------------------------------------------------------
# Core classification
# ---------------------------------------------------------------------------

def detect(repo_url: str, manifest_paths: list[str]) -> dict[str, Any]:
    """Classify a repo into a skill shape from its manifest files."""
    if not manifest_paths:
        _die("--manifests requires at least one path", "MISSING_MANIFESTS")

    parsed: list[dict[str, Any]] = []
    for mp in manifest_paths:
        p = Path(mp)
        if not p.is_file():
            _die(f"Manifest not found: {p.as_posix()}", "MANIFEST_NOT_FOUND")
        parsed.append(_parse_manifest(p))

    all_deps: set[str] = set()
    ecosystems: set[str] = set()
    total_exports = 0
    signals: list[str] = []
    has_bin = False
    has_library_structure = False

    for m in parsed:
        eco = m["ecosystem"]
        ecosystems.add(eco)
        signals.append(f"has_{path_to_manifest_name(eco)}")
        all_deps.update(m.get("deps", set()))
        total_exports += m.get("export_count", 0)
        if m.get("has_bin"):
            has_bin = True
        if m.get("has_library_structure"):
            has_library_structure = True

    package_count = len(parsed)

    if total_exports > 50:
        signals.append("exports_count_gt_50")
    if has_bin:
        signals.append("has_bin_field")
    elif has_library_structure:
        signals.append("no_bin_field")
    if has_library_structure:
        signals.append("has_library_structure")

    # Collect dep-category matches
    parser_deps = sorted(d for d in all_deps if d.lower() in _ALL_PARSER_DEPS)
    framework_deps = sorted(d for d in all_deps if d.lower() in _ALL_FRAMEWORK_DEPS)
    has_framework = len(framework_deps) > 0

    for d in parser_deps:
        signals.append(f"parser_dep:{d}")
    for d in framework_deps:
        signals.append(f"framework_dep:{d}")
    if len(ecosystems) > 1:
        signals.append("multiple_ecosystems")
        for eco in sorted(ecosystems):
            signals.append(f"ecosystem:{eco}")

    result_base = {
        "export_count": total_exports,
        "package_count": package_count,
    }

    # --- Heuristic ladder (first match wins) ---

    # 1. language-reference
    if parser_deps:
        confidence = _clamp(0.75 + len(parser_deps) * 0.05, 0.75, 0.85)
        return {"shape": "language-reference", "signals": signals,
                "confidence": round(confidence, 2), **result_base}

    # 2. stack-compose
    if len(ecosystems) > 1:
        confidence = _clamp(0.80 + (len(ecosystems) - 2) * 0.05, 0.80, 0.90)
        return {"shape": "stack-compose", "signals": signals,
                "confidence": round(confidence, 2), **result_base}

    # 3. reference-app
    if has_bin or has_framework:
        strength = (1 if has_bin else 0) + (1 if has_framework else 0)
        confidence = _clamp(0.80 + (strength - 1) * 0.05, 0.80, 0.90)
        return {"shape": "reference-app", "signals": signals,
                "confidence": round(confidence, 2), **result_base}

    # 4. library-API
    if has_library_structure or total_exports > 0:
        base = 0.65
        if has_library_structure:
            base = 0.80
        if total_exports > 50:
            base = max(base, 0.90)
        elif total_exports > 10:
            base = max(base, 0.80)
        confidence = _clamp(base, 0.65, 0.95)
        return {"shape": "library-API", "signals": signals,
                "confidence": round(confidence, 2), **result_base}

    # 5. unknown
    return {"shape": "unknown", "signals": signals,
            "confidence": 0.0, **result_base}


def path_to_manifest_name(ecosystem: str) -> str:
    return {"npm": "package_json", "python": "pyproject_toml",
            "rust": "cargo_toml"}.get(ecosystem, ecosystem)


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Classify a repo into a known skill shape from its manifest files.",
    )
    parser.add_argument("--repo-url", required=True, help="Repository URL")
    parser.add_argument(
        "--manifests", required=True,
        help="Comma-separated local file paths to manifest files",
    )
    args = parser.parse_args(argv)

    manifest_paths = [p.strip() for p in args.manifests.split(",") if p.strip()]
    if not manifest_paths:
        _die("--manifests requires at least one path", "MISSING_MANIFESTS")

    result = detect(args.repo_url, manifest_paths)
    json.dump(result, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")

    return 1 if result["shape"] == "unknown" else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
