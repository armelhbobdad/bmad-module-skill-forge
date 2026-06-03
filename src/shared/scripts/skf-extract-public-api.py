# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""SKF Extract Public API — pure parser for manifest + entry-point content.

Takes a JSON payload on stdin describing one logical package (one
manifest, one or more entry-point files) and emits a structured
extraction inventory: package name, version, description, public
exports, declared dependencies, and (for Maven/Gradle) discovered
sub-modules. The helper does NO file I/O — the caller fetches files
(via gh api / web browsing / local filesystem / wherever) and pipes
their contents in. Multi-module monorepos are caller-orchestrated:
invoke once per module, aggregate the results.

Supported languages (--language values; first listed is preferred):

  js, ts, javascript, typescript    package.json     index.{js,ts}, src/index.{js,ts}
  python                            pyproject.toml   __init__.py / setup.py
  rust                              Cargo.toml       src/lib.rs
  go                                go.mod           top-level *.go
  java                              pom.xml          src/main/java/**/*.java
  kotlin                            build.gradle*    src/main/kotlin/**/*.kt

Mode flag (currently `quick` only; `full` reserved for skf-create-skill):

  --mode quick    Top-level exports only (one entry file per language).

Input JSON shape (stdin):

  {
    "language": "python",
    "manifest": {"path": "pyproject.toml", "content": "..."},
    "entries":  [{"path": "src/foo/__init__.py", "content": "..."}, ...],
    "mode":     "quick"
  }

Output JSON shape (stdout):

  {
    "language":    "python",
    "package_name": "foo",
    "version":      "1.2.3",
    "description":  "...",
    "exports":      [{"name": "Bar", "type": "class", "source_file": "..."}, ...],
    "dependencies": ["requests", "pydantic", ...],
    "modules":      ["server", "client"],         (Maven/Gradle only)
    "extra":        {"group_id": "com.example"}, (Maven only)
    "warnings":     ["..."]                        (parse failures, fallbacks)
  }

Exit codes:

  0    success
  1    payload-level error (unknown language, no manifest content)
  2    stdin / argparse / JSON-decode error
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
import xml.etree.ElementTree as ET
from typing import Callable

# --------------------------------------------------------------------------
# Manifest parsers
# --------------------------------------------------------------------------


def parse_package_json(content: str) -> dict:
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        return {"_parse_error": f"package.json JSON parse error: {e}"}
    if not isinstance(data, dict):
        return {"_parse_error": "package.json root is not an object"}
    return {
        "name": data.get("name"),
        "version": data.get("version"),
        "description": data.get("description"),
        "main": data.get("main"),
        "exports": data.get("exports"),
        "dependencies": list((data.get("dependencies") or {}).keys()),
        "modules": [],
    }


def parse_pyproject_toml(content: str) -> dict:
    try:
        data = tomllib.loads(content)
    except tomllib.TOMLDecodeError as e:
        return {"_parse_error": f"pyproject.toml parse error: {e}"}
    project = data.get("project") or {}
    raw_deps = project.get("dependencies") or []
    dep_names: list[str] = []
    for d in raw_deps:
        if isinstance(d, str):
            m = re.match(r"^([A-Za-z0-9_.\-]+)", d.strip())
            if m:
                dep_names.append(m.group(1))
    return {
        "name": project.get("name"),
        "version": project.get("version"),
        "description": project.get("description"),
        "dependencies": dep_names,
        "modules": [],
    }


def parse_setup_py(content: str) -> dict:
    """Best-effort regex parse of setup.py — does NOT execute the file."""

    def find_kwarg(name: str) -> str | None:
        m = re.search(rf'\b{name}\s*=\s*["\']([^"\']+)["\']', content)
        return m.group(1) if m else None

    return {
        "name": find_kwarg("name"),
        "version": find_kwarg("version"),
        "description": find_kwarg("description"),
        "dependencies": [],
        "modules": [],
    }


def parse_cargo_toml(content: str) -> dict:
    try:
        data = tomllib.loads(content)
    except tomllib.TOMLDecodeError as e:
        return {"_parse_error": f"Cargo.toml parse error: {e}"}
    pkg = data.get("package") or {}
    return {
        "name": pkg.get("name"),
        "version": pkg.get("version"),
        "description": pkg.get("description"),
        "dependencies": list((data.get("dependencies") or {}).keys()),
        "modules": [],
    }


def parse_go_mod(content: str) -> dict:
    name: str | None = None
    deps: list[str] = []
    in_require_block = False
    for line in content.splitlines():
        s = line.strip()
        if not s or s.startswith("//"):
            continue
        if s.startswith("module "):
            name = s.split(None, 1)[1].strip()
            continue
        if s.startswith("require ("):
            in_require_block = True
            continue
        if s == ")" and in_require_block:
            in_require_block = False
            continue
        if s.startswith("require "):
            parts = s.split(None, 2)
            if len(parts) >= 2:
                deps.append(parts[1])
            continue
        if in_require_block:
            parts = s.split()
            if parts:
                deps.append(parts[0])
    return {
        "name": name,
        "version": None,
        "description": None,
        "dependencies": deps,
        "modules": [],
    }


def _strip_ns(tag: str) -> str:
    return tag.split("}", 1)[1] if "}" in tag else tag


def parse_pom_xml(content: str) -> dict:
    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        return {"_parse_error": f"pom.xml parse error: {e}"}

    group_id = artifact_id = version = description = None
    modules: list[str] = []
    deps: list[str] = []

    for child in root:
        tag = _strip_ns(child.tag)
        if tag == "groupId":
            group_id = (child.text or "").strip() or None
        elif tag == "artifactId":
            artifact_id = (child.text or "").strip() or None
        elif tag == "version":
            version = (child.text or "").strip() or None
        elif tag == "description":
            description = (child.text or "").strip() or None
        elif tag == "modules":
            for m in child:
                if _strip_ns(m.tag) == "module":
                    text = (m.text or "").strip()
                    if text:
                        modules.append(text)
        elif tag == "dependencies":
            for d in child:
                d_artifact = None
                for c in d:
                    if _strip_ns(c.tag) == "artifactId":
                        d_artifact = (c.text or "").strip() or None
                if d_artifact:
                    deps.append(d_artifact)

    out = {
        "name": artifact_id,
        "version": version,
        "description": description,
        "dependencies": deps,
        "modules": modules,
    }
    if group_id:
        out["_extra"] = {"group_id": group_id}
    return out


def parse_gradle(content: str) -> dict:
    """Best-effort regex parse of build.gradle / build.gradle.kts."""

    def find_assignment(name: str) -> str | None:
        for pat in (
            rf'\b{name}\s*=\s*["\']([^"\']+)["\']',
            rf'\b{name}\s+["\']([^"\']+)["\']',
            rf'\b{name}\s*\(\s*["\']([^"\']+)["\']',
            rf'\b{name}\s*:\s*["\']([^"\']+)["\']',
        ):
            m = re.search(pat, content)
            if m:
                return m.group(1)
        return None

    return {
        "name": find_assignment("artifactId") or find_assignment("group"),
        "version": find_assignment("version"),
        "description": find_assignment("description"),
        "dependencies": [],
        "modules": [],
    }


def parse_settings_gradle(content: str) -> list[str]:
    """Extract include('...') / include(":a", ":b") entries."""
    modules: list[str] = []
    for m in re.finditer(r"include\s*\(?(.+?)\)?$", content, flags=re.MULTILINE):
        for s in re.findall(r"""['"]:?([^'"]+)['"]""", m.group(1)):
            modules.append(s)
    return modules


def parse_package_swift(content: str) -> dict:
    """Best-effort parse of a SwiftPM Package.swift manifest.

    SwiftPM has no version field in the manifest (versions come from git tags),
    so `version` is always None; the brief falls back to target_version / default.
    """
    name_m = re.search(r"\bPackage\s*\(\s*name:\s*['\"]([^'\"]+)['\"]", content, re.DOTALL)
    deps: list[str] = []
    for m in re.finditer(r"\.package\s*\(\s*url:\s*['\"]([^'\"]+)['\"]", content):
        seg = m.group(1).rstrip("/").rsplit("/", 1)[-1]
        if seg.endswith(".git"):
            seg = seg[: -len(".git")]
        if seg:
            deps.append(seg)
    return {
        "name": name_m.group(1).strip() if name_m else None,
        "version": None,
        "description": None,
        "dependencies": deps,
        "modules": [],
    }


# --------------------------------------------------------------------------
# Export scanners
# --------------------------------------------------------------------------

_JS_DECL_RE = re.compile(
    r"^export\s+(?:default\s+)?(const|function|class|type|interface|enum)\s+(\w+)",
    re.MULTILINE,
)
_JS_REEXPORT_RE = re.compile(r"^export\s*\{([^}]+)\}", re.MULTILINE)


def scan_exports_js(content: str, source_file: str) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for m in _JS_DECL_RE.finditer(content):
        kind, name = m.group(1), m.group(2)
        if name not in seen:
            seen.add(name)
            out.append({"name": name, "type": kind, "source_file": source_file})
    for m in _JS_REEXPORT_RE.finditer(content):
        for piece in m.group(1).split(","):
            piece = piece.strip()
            if not piece:
                continue
            # Handle `foo as bar` — keep the local name (foo) and the alias (bar);
            # we only emit one entry, the exposed name.
            if " as " in piece:
                _, _, exposed = piece.partition(" as ")
                exposed = exposed.strip()
            else:
                exposed = piece
            m2 = re.match(r"\w+$", exposed)
            if m2 and exposed not in seen:
                seen.add(exposed)
                out.append({"name": exposed, "type": "re-export", "source_file": source_file})
    return out


def scan_exports_python(content: str, source_file: str) -> list[dict]:
    all_names: list[str] | None = None
    m = re.search(r"^__all__\s*=\s*\[([^\]]+)\]", content, re.MULTILINE | re.DOTALL)
    if m:
        all_names = re.findall(r"""['"]([^'"]+)['"]""", m.group(1))

    out: list[dict] = []
    for m in re.finditer(r"^(def|class)\s+(\w+)", content, re.MULTILINE):
        kind, name = m.group(1), m.group(2)
        if name.startswith("_"):
            continue
        if all_names is not None and name not in all_names:
            continue
        out.append({"name": name, "type": kind, "source_file": source_file})
    return out


def scan_exports_rust(content: str, source_file: str) -> list[dict]:
    out: list[dict] = []
    for m in re.finditer(
        r"^\s*pub\s+(fn|struct|enum|trait|mod|type|const|static)\s+(\w+)",
        content,
        re.MULTILINE,
    ):
        out.append({"name": m.group(2), "type": m.group(1), "source_file": source_file})
    return out


def scan_exports_go(content: str, source_file: str) -> list[dict]:
    out: list[dict] = []
    for m in re.finditer(r"^(func|type|var|const)\s+([A-Z]\w*)", content, re.MULTILINE):
        out.append({"name": m.group(2), "type": m.group(1), "source_file": source_file})
    return out


_JAVA_PUBLIC_RE = re.compile(
    r"^\s*public\s+(?:static\s+|final\s+|abstract\s+)*(class|interface|enum|record)\s+(\w+)",
    re.MULTILINE,
)
_JAVA_ANNOTATION_RE = re.compile(
    r"^\s*@(RestController|Service|Component|Configuration|Controller|Repository|Bean)\b",
    re.MULTILINE,
)


def scan_exports_java(content: str, source_file: str) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for m in _JAVA_PUBLIC_RE.finditer(content):
        name = m.group(2)
        if name in seen:
            continue
        seen.add(name)
        out.append({"name": name, "type": m.group(1), "source_file": source_file})
    # Annotation-marked classes (Spring/Jakarta CDI) — find the annotation, then
    # the next class/interface/enum/record declaration after it.
    for m in _JAVA_ANNOTATION_RE.finditer(content):
        annotation = m.group(1)
        tail = content[m.end():]
        m2 = re.search(r"\b(class|interface|enum|record)\s+(\w+)", tail)
        if m2:
            name = m2.group(2)
            if name not in seen:
                seen.add(name)
                out.append({"name": name, "type": annotation.lower(), "source_file": source_file})
    return out


_KOTLIN_DECL_RE = re.compile(
    r"^(?!\s*(?:internal|private)\b)"
    r"\s*(?:open\s+|sealed\s+|data\s+|abstract\s+)*"
    r"(fun|class|object|interface)\s+(\w+)",
    re.MULTILINE,
)


def scan_exports_kotlin(content: str, source_file: str) -> list[dict]:
    """Kotlin defaults to public — omit internal/private declarations."""
    out: list[dict] = []
    seen: set[str] = set()
    for m in _KOTLIN_DECL_RE.finditer(content):
        name = m.group(2)
        if name in seen:
            continue
        seen.add(name)
        out.append({"name": name, "type": m.group(1), "source_file": source_file})
    return out


# Swift declarations are public only when explicitly marked `public`/`open`
# (the default is internal). The lazy `[^\n]*?` skips intervening modifiers
# (final/static/class-method/@attributes) between the access keyword and the
# declaration keyword.
_SWIFT_DECL_RE = re.compile(
    r"^\s*(?:public|open)\b[^\n]*?\b"
    r"(func|class|struct|enum|protocol|actor|typealias|var|let)\s+([A-Za-z_]\w*)",
    re.MULTILINE,
)
_SWIFT_DECL_KEYWORDS = {
    "func", "class", "struct", "enum", "protocol", "actor", "typealias", "var", "let",
}


def scan_exports_swift(content: str, source_file: str) -> list[dict]:
    """Swift defaults to internal — emit only public/open declarations."""
    out: list[dict] = []
    seen: set[str] = set()
    for m in _SWIFT_DECL_RE.finditer(content):
        name = m.group(2)
        # Guard the rare `public class func foo` case where the lazy skip stops
        # on the `class` modifier and captures the next keyword as the name.
        if name in _SWIFT_DECL_KEYWORDS or name in seen:
            continue
        seen.add(name)
        out.append({"name": name, "type": m.group(1), "source_file": source_file})
    return out


# --------------------------------------------------------------------------
# Orchestrator
# --------------------------------------------------------------------------

ManifestParser = Callable[[str], dict]
ExportScanner = Callable[[str, str], list[dict]]

LANGUAGE_DISPATCH: dict[str, tuple[ManifestParser, ExportScanner]] = {
    "js": (parse_package_json, scan_exports_js),
    "ts": (parse_package_json, scan_exports_js),
    "javascript": (parse_package_json, scan_exports_js),
    "typescript": (parse_package_json, scan_exports_js),
    "python": (parse_pyproject_toml, scan_exports_python),
    "rust": (parse_cargo_toml, scan_exports_rust),
    "go": (parse_go_mod, scan_exports_go),
    "java": (parse_pom_xml, scan_exports_java),
    "kotlin": (parse_gradle, scan_exports_kotlin),
    "swift": (parse_package_swift, scan_exports_swift),
}


def _select_manifest_parser(language: str, manifest_path: str) -> ManifestParser:
    """Pick the right manifest parser, special-casing Python's setup.py."""
    if language == "python" and manifest_path.endswith("setup.py"):
        return parse_setup_py
    return LANGUAGE_DISPATCH[language][0]


# Release-time placeholder versions that appear in committed manifests but
# resolve to a real version only at publish time. Briefs that silently inherit
# these as the resolved version produce skills tagged with garbage version
# strings; surface them at brief-creation instead.
_PLACEHOLDER_VERSION_PREFIXES = ("workspace:",)
_PLACEHOLDER_VERSION_EXACTS = frozenset({"0.0.0-development", "0.0.0-semantically-released"})


def _detect_placeholder_version(version: str | None) -> str | None:
    """Return the original placeholder string if `version` is a known release-time sentinel, else None."""
    if not version or not isinstance(version, str):
        return None
    v = version.strip().lower()
    if v in _PLACEHOLDER_VERSION_EXACTS:
        return version
    if any(v.startswith(prefix) for prefix in _PLACEHOLDER_VERSION_PREFIXES):
        return version
    return None


def extract(payload: dict) -> dict:
    """Orchestrate manifest parse + export scan for one logical package."""
    warnings: list[str] = []
    language = (payload.get("language") or "").lower()
    if language not in LANGUAGE_DISPATCH:
        return {"_error": f"unknown language: {language!r}; expected one of {sorted(LANGUAGE_DISPATCH)}"}

    manifest = payload.get("manifest") or {}
    manifest_path = (manifest.get("path") or "").strip()
    manifest_content = manifest.get("content") or ""

    if not manifest_content:
        warnings.append("no manifest content provided; metadata will be empty")
        parsed: dict = {}
    else:
        manifest_parser = _select_manifest_parser(language, manifest_path)
        parsed = manifest_parser(manifest_content)
        if "_parse_error" in parsed:
            warnings.append(parsed["_parse_error"])
            parsed = {}

    placeholder = _detect_placeholder_version(parsed.get("version"))
    if placeholder is not None:
        warnings.append(
            f"manifest version {placeholder!r} is a release-time placeholder "
            f"(workspace protocol or semantic-release sentinel) and is not a real version; "
            f"the brief will fall back to user-supplied target_version or the default"
        )
        parsed["version"] = None

    _, scanner = LANGUAGE_DISPATCH[language]
    exports: list[dict] = []
    for entry in payload.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        content = entry.get("content") or ""
        path = entry.get("path") or ""
        if not content:
            continue
        try:
            exports.extend(scanner(content, path))
        except Exception as e:  # noqa: BLE001 — best-effort: scanner errors are warnings, not fatal
            warnings.append(f"export scan failed for {path}: {e}")

    result = {
        "language": language,
        "package_name": parsed.get("name"),
        "version": parsed.get("version"),
        "description": parsed.get("description"),
        "exports": exports,
        "dependencies": parsed.get("dependencies", []),
        "modules": parsed.get("modules", []),
        "warnings": warnings,
    }
    if "_extra" in parsed:
        result["extra"] = parsed["_extra"]
    return result


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Extract public-API surface from manifest + entry-point content (pure parser, no I/O).",
    )
    parser.add_argument(
        "--mode",
        default="quick",
        choices=("quick",),
        help="Extraction mode (only 'quick' currently; 'full' reserved for skf-create-skill).",
    )
    args = parser.parse_args(argv)

    raw = sys.stdin.read()
    if not raw.strip():
        sys.stderr.write("error: no input on stdin (expected JSON payload)\n")
        return 2
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        sys.stderr.write(f"error: stdin JSON parse error: {e}\n")
        return 2
    if not isinstance(payload, dict):
        sys.stderr.write("error: stdin payload must be a JSON object\n")
        return 2

    payload.setdefault("mode", args.mode)
    result = extract(payload)
    print(json.dumps(result, indent=2))
    return 1 if "_error" in result else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
