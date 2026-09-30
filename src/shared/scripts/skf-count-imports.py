# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""SKF Count Imports: count, for each dependency, the source files that import it.

Two workflows need the same fact, which has one right answer per tree:

  1. **skf-create-stack-skill** ranks the project's dependencies by how many
     files import them (2 or more files: included by default), and hands
     each library's file list to `skf-pair-intersect.py`.
  2. **skf-analyze-source** maps which units import which (Imports From and
     Imported By), gives co-imported units to `skf-pair-intersect.py` and
     the unit-to-unit edges to `skf-find-cycles.py`.

A grep with no module boundary counts `react-dom` and `react-router` as
`react`, and a Python distribution is often imported under another name
(`PyYAML` as `yaml`, `Pillow` as `PIL`), so hand counts drift from run to
run. This helper reads each source file once, parses its import statements
per language, matches them on module boundaries and maps distribution names
to import names.

Subcommand:
  count <root> [--deps <json-file-or-'-'>] [--units <json-file-or-'-'>]
               [--threshold N] [--exclude GLOB]... [--format full|libraries]

      Walk <root>, read every source file of the languages the targets need,
      and count the files that import each target. At least one of --deps
      and --units is required; only one of them may read stdin ('-').

      --deps accepts any of:
        - the `skf-scan-manifests.py scan` envelope, as it is: every
          `manifests[].deps[]` entry becomes a dependency of that manifest's
          ecosystem (a dependency tagged `scope: dev` stays dev only when no
          manifest lists it as a runtime dependency);
        - {"dependencies": [<dep>, ...]} or a bare [<dep>, ...] list, where
          <dep> is a name string or
          {"name": "...", "ecosystem": "npm|python|...", "modules": [...],
           "scope": "runtime|dev"}. `ecosystem` limits the match to that
          ecosystem's source files (omitted: every language, with the name
          and its Python-style guesses). `modules` gives the import names
          explicitly and skips the name rules below.

      --units accepts {"units": [<unit>, ...]} or a bare list, where <unit> is
        {"name": "...", "path": "<dir relative to root>", "modules": [...],
         "ecosystem": "..."}.
      A unit is an internal part of the tree. Each scanned file belongs to
      the unit with the longest `path` that contains it. A file imports a
      unit when one of its imports matches the unit's `modules`, or when a
      relative import (JS/TS `./` and `../`, Python leading dots, Ruby
      `require_relative`) resolves into the unit's `path`. A unit's own
      files never count as importing it.

      --threshold N    a dependency is `above_threshold` when file_count >= N
                       (default 2: two or more importing files)
      --exclude GLOB   another path to leave out, added to the defaults below
                       (repeatable)
      --format         `full` (default) prints the envelope below;
                       `libraries` prints [{"name", "files": [<path>, ...]}]
                       for every dependency, then every unit: the input of
                       `skf-pair-intersect.py intersect --libraries -`.

      Emit JSON (`full`):
        {
          "threshold": 2,
          "files_scanned": N,
          "dependencies": [
            {"name": "react", "ecosystem": "npm",
             "import_names": ["react"], "resolution": "exact",
             "files": [{"path": "src/App.tsx", "line": 1}, ...],
             "file_count": N, "above_threshold": true},
            ...
          ],
          "unresolved": [
            {"name": "...", "ecosystem": "...", "import_names": [...],
             "reason": "guess-unmatched|no-import-name|unsupported-ecosystem"},
            ...
          ],
          "units": [
            {"name": "...", "path": "...", "import_names": [...],
             "files": [{"path": "...", "line": N}, ...], "file_count": N,
             "imported_by": [...], "imports_from": [...],
             "external_deps": [...]},
            ...
          ],
          "edges": [["<importing unit>", "<imported unit>"], ...],
          "warnings": ["..."]
        }
      `units` and `edges` are present only with --units; `warnings` only when
      a file could not be read. A dependency entry carries `scope: "dev"`
      when its input said so. `files` lists each importing file once, with
      the first line that imports the target, sorted by path.
      `dependencies[]` is sorted by file_count (highest first), then name.
      `unresolved[]` (sorted by name) holds the dependencies this helper
      cannot count with confidence, for the model to judge: a guessed import
      name that matched no file (`guess-unmatched`), no import name to try
      (`no-import-name`), or an ecosystem it has no import rules for
      (`unsupported-ecosystem`). `edges` is the `skf-find-cycles.py find
      --edges` input as it is (that helper reads only the `edges` key).

Resolution of a dependency's import names (`resolution`):
  exact     the ecosystem's own rule: an npm package is imported by its name,
            a Rust crate by its name with `-` as `_`, a Go module by its path;
            a Composer package by the namespaces its installed
            `vendor/<name>/composer.json` autoloads
  mapped    an entry of the built-in distribution-to-import tables (`PyYAML`
            as `yaml`, `Pillow` as `PIL`, `beautifulsoup4` as `bs4`,
            `com.google.guava:guava` as `com.google.common`, ...)
  guessed   a naming rule that is often but not always right: a Python
            distribution as its name with `-` as `_`, a namespace family
            (`google-cloud-storage` as `google.cloud.storage`), `@types/react`
            as `react`, a Symfony package as its namespace
            (`symfony/framework-bundle` as `Symfony\\Bundle\\FrameworkBundle`),
            a Maven group as its package, a gem as its name. A guess that
            matches no file goes to `unresolved[]` instead of counting 0
  explicit  the `modules` the caller gave

Matching is boundary-anchored: an import binds to the dependency whose
import name equals the imported module or is a prefix of it at a module
separator (`/` for JS, Go and Ruby, `.` for Python and the JVM, `::` for
Rust, `\\` for PHP, whole names for Swift). `react` matches `react` and
`react/jsx-runtime`, never `react-dom`; `yaml` matches `yaml.loader`, never
`yamlordereddict`. When several import names prefix the same import, the
longest wins, so `opentelemetry.sdk.trace` counts for `opentelemetry-sdk`
and not for `opentelemetry-api`.

Import statements read per language (lines that start a comment are
skipped; Python files are parsed with `ast`, and one that does not parse or
is over 1,000,000 characters (`PYTHON_AST_MAX_CHARS`) is read line by line,
outside comments and triple-quoted strings):
  js      .js .jsx .mjs .cjs .ts .tsx .mts .cts .vue .svelte .astro:
          `import ... from 'm'`, `import 'm'`, `export ... from 'm'`,
          `import('m')`, `require('m')`
  python  .py .pyi: `import m`, `from m import n` (also read as `m.n`),
          `importlib.import_module('m')`, `__import__('m')`
  rust    .rs: `use m::...`, `extern crate m`, and qualified paths `m::x`
  go      .go: `import "m"` and `import ( ... )` blocks
  jvm     .java .kt .kts .groovy .scala: `import m.x`, `import static m.x`
  ruby    .rb: `require 'm'`, `require_relative 'p'`
  php     .php: `use M\\X` (case-insensitive, as PHP namespaces are)
  swift   .swift: `import M`
Ecosystems map to languages: npm to js, python to python, rust to rust,
go to go, maven and gradle to jvm, ruby to ruby, composer to php, swift to
swift.

Excluded paths, matched against the path relative to <root> (the list in
`DEFAULT_EXCLUDES`, which `references/manifest-patterns.md` in
skf-create-stack-skill documents): a pattern ending in `/` names a directory
at any depth, a pattern with no `/` matches a file name at any depth, any
other pattern matches the whole relative path (`**` spans directories, `*`
and `?` stay inside one). A leading `/` or `./` anchors a pattern to <root>
(`./examples/` is only the top-level `examples`). Symbolic links are not
followed.

CLI examples:
  uv run skf-scan-manifests.py scan . > manifests.json
  uv run skf-count-imports.py count . --deps manifests.json
  echo '["react", "PyYAML"]' | uv run skf-count-imports.py count . --deps -
  uv run skf-count-imports.py count . --units units.json --format libraries \\
    | uv run skf-pair-intersect.py intersect --libraries -
  uv run skf-count-imports.py count . --units units.json \\
    | uv run skf-find-cycles.py find --edges -

Exit codes:
  0  success (including: no dependency imported, no source file found)
  1  user error (root not a directory, unreadable or malformed JSON input,
     a bad dependency or unit entry, both inputs on stdin, bad --threshold)
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import posixpath
import re
import sys
import warnings
from pathlib import Path


DEFAULT_THRESHOLD = 2

# A Python file up to this many characters is parsed with `ast`. A larger one
# (a generated table or protobuf module) is read line by line, because its
# syntax tree can take 200 times its size in memory.
PYTHON_AST_MAX_CHARS = 1_000_000

# Source file extensions read for each language.
LANGUAGE_EXTENSIONS: dict[str, tuple[str, ...]] = {
    "js": (
        ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts", ".vue", ".svelte", ".astro",
    ),
    "python": (".py", ".pyi"),
    "rust": (".rs",),
    "go": (".go",),
    "jvm": (".java", ".kt", ".kts", ".groovy", ".scala"),
    "ruby": (".rb",),
    "php": (".php",),
    "swift": (".swift",),
}

# `skf-scan-manifests.py` ecosystem label -> language whose imports it reads.
ECOSYSTEM_LANGUAGE: dict[str, str] = {
    "npm": "js",
    "python": "python",
    "rust": "rust",
    "go": "go",
    "maven": "jvm",
    "gradle": "jvm",
    "ruby": "ruby",
    "composer": "php",
    "swift": "swift",
}

# Module separator per language; None matches whole module names only.
SEPARATORS: dict[str, str | None] = {
    "js": "/",
    "python": ".",
    "rust": "::",
    "go": "/",
    "jvm": ".",
    "ruby": "/",
    "php": "\\",
    "swift": None,
}

# Paths never counted, documented in
# src/skf-create-stack-skill/references/manifest-patterns.md "Import Counting"
# (test/test-skf-count-imports.py keeps the two lists equal).
DEFAULT_EXCLUDES: tuple[str, ...] = (
    # hidden files and directories
    ".*/",
    ".*",
    # tests
    "test/",
    "tests/",
    "__tests__/",
    "spec/",
    "*.test.*",
    "*.spec.*",
    "*_test.*",
    "test_*.py",
    "*_spec.rb",
    "conftest.py",
    # config and build scripts
    "*.config.*",
    "setup.py",
    "noxfile.py",
    "*.gradle.kts",
    "Package.swift",
    # build output and vendored code
    "dist/",
    "build/",
    "out/",
    "target/",
    "node_modules/",
    "vendor/",
    "venv/",
    "Pods/",
    "__pycache__/",
)

# --------------------------------------------------------------------------
# Distribution-to-import tables
# --------------------------------------------------------------------------


# Python distributions whose import name differs from the distribution name,
# keyed by the PEP 503 normalised name (lower case, runs of -_. as -).
PYTHON_IMPORT_NAMES: dict[str, tuple[str, ...]] = {
    "absl-py": ("absl",),
    "apache-airflow": ("airflow",),
    "attrs": ("attr", "attrs"),
    "beautifulsoup4": ("bs4",),
    "discord-py": ("discord",),
    "django-cors-headers": ("corsheaders",),
    "django-environ": ("environ",),
    "django-filter": ("django_filters",),
    "djangorestframework": ("rest_framework",),
    "dnspython": ("dns",),
    "faiss-cpu": ("faiss",),
    "faiss-gpu": ("faiss",),
    "gitpython": ("git",),
    "google-api-python-client": ("googleapiclient",),
    "google-auth": ("google.auth",),
    "google-genai": ("google.genai",),
    "google-generativeai": ("google.generativeai",),
    "grpcio": ("grpc",),
    "grpcio-status": ("grpc_status",),
    "grpcio-tools": ("grpc_tools",),
    "ipython": ("IPython",),
    "msgpack-python": ("msgpack",),
    "mysql-connector-python": ("mysql.connector",),
    "mysqlclient": ("MySQLdb",),
    "opencv-contrib-python": ("cv2",),
    "opencv-contrib-python-headless": ("cv2",),
    "opencv-python": ("cv2",),
    "opencv-python-headless": ("cv2",),
    "opentelemetry-api": ("opentelemetry",),
    "paho-mqtt": ("paho.mqtt",),
    "pdfminer-six": ("pdfminer",),
    "pillow": ("PIL",),
    "protobuf": ("google.protobuf",),
    "psycopg2-binary": ("psycopg2",),
    "pycairo": ("cairo",),
    "pycryptodome": ("Crypto",),
    "pycryptodomex": ("Cryptodome",),
    "pygithub": ("github",),
    "pygobject": ("gi",),
    "pyinstaller": ("PyInstaller",),
    "pyjwt": ("jwt",),
    "pymongo": ("pymongo", "bson", "gridfs"),
    "pymupdf": ("fitz", "pymupdf"),
    "pynacl": ("nacl",),
    "pyopenssl": ("OpenSSL",),
    "pyqt5": ("PyQt5",),
    "pyqt6": ("PyQt6",),
    "pyserial": ("serial",),
    "pyside2": ("PySide2",),
    "pyside6": ("PySide6",),
    "pysocks": ("socks",),
    "python-dateutil": ("dateutil",),
    "python-docx": ("docx",),
    "python-dotenv": ("dotenv",),
    "python-gitlab": ("gitlab",),
    "python-jose": ("jose",),
    "python-json-logger": ("pythonjsonlogger",),
    "python-levenshtein": ("Levenshtein",),
    "python-magic": ("magic",),
    "python-multipart": ("multipart", "python_multipart"),
    "python-pptx": ("pptx",),
    "python-slugify": ("slugify",),
    "python-socketio": ("socketio",),
    "python-telegram-bot": ("telegram",),
    "pywavelets": ("pywt",),
    "pywin32": ("win32api", "win32con", "win32com", "win32gui", "pythoncom", "pywintypes"),
    "pyyaml": ("yaml",),
    "pyzmq": ("zmq",),
    "ruamel-yaml": ("ruamel.yaml",),
    "scikit-image": ("skimage",),
    "scikit-learn": ("sklearn",),
    "setuptools": ("setuptools", "pkg_resources"),
    "tensorflow-cpu": ("tensorflow",),
    "tensorflow-gpu": ("tensorflow",),
    "websocket-client": ("websocket",),
}

# Python namespace families: normalised prefix -> (import namespace, the
# character that replaces `-` in the rest of the name). A rule, not a table
# of names, so the names it builds are guesses.
PYTHON_NAMESPACE_FAMILIES: dict[str, tuple[str, str]] = {
    "google-cloud-": ("google.cloud.", "_"),
    "azure-": ("azure.", "."),
    "opentelemetry-": ("opentelemetry.", "."),
    "backports-": ("backports.", "."),
    "jaraco-": ("jaraco.", "."),
    "sphinxcontrib-": ("sphinxcontrib.", "."),
    "zope-": ("zope.", "."),
}

# Maven and Gradle coordinates (group:artifact) whose package is not the group.
JVM_IMPORT_NAMES: dict[str, tuple[str, ...]] = {
    "com.fasterxml.jackson.core:jackson-annotations": ("com.fasterxml.jackson.annotation",),
    "com.fasterxml.jackson.core:jackson-core": ("com.fasterxml.jackson.core",),
    "com.fasterxml.jackson.core:jackson-databind": ("com.fasterxml.jackson.databind",),
    "com.google.code.gson:gson": ("com.google.gson",),
    "com.google.guava:guava": ("com.google.common",),
    "com.h2database:h2": ("org.h2",),
    "com.squareup.okhttp3:okhttp": ("okhttp3",),
    "com.squareup.retrofit2:retrofit": ("retrofit2",),
    "commons-codec:commons-codec": ("org.apache.commons.codec",),
    "commons-io:commons-io": ("org.apache.commons.io",),
    "jakarta.servlet:jakarta.servlet-api": ("jakarta.servlet",),
    "javax.servlet:javax.servlet-api": ("javax.servlet",),
    "junit:junit": ("org.junit", "junit.framework"),
    "mysql:mysql-connector-java": ("com.mysql",),
    "org.apache.commons:commons-collections4": ("org.apache.commons.collections4",),
    "org.apache.commons:commons-lang3": ("org.apache.commons.lang3",),
    "org.jetbrains.kotlinx:kotlinx-coroutines-core": ("kotlinx.coroutines",),
    "org.jetbrains.kotlinx:kotlinx-serialization-json": ("kotlinx.serialization",),
    "org.junit.jupiter:junit-jupiter": ("org.junit.jupiter",),
    "org.junit.jupiter:junit-jupiter-api": ("org.junit.jupiter.api",),
    "org.postgresql:postgresql": ("org.postgresql",),
    "org.projectlombok:lombok": ("lombok",),
    "org.slf4j:slf4j-api": ("org.slf4j",),
    "org.xerial:sqlite-jdbc": ("org.sqlite",),
}

# Gems required under another name, keyed by lower-case gem name.
RUBY_IMPORT_NAMES: dict[str, tuple[str, ...]] = {
    "actioncable": ("action_cable",),
    "actionmailer": ("action_mailer",),
    "actionpack": ("action_controller", "action_dispatch"),
    "actionview": ("action_view",),
    "activejob": ("active_job",),
    "activemodel": ("active_model",),
    "activerecord": ("active_record",),
    "activestorage": ("active_storage",),
    "activesupport": ("active_support",),
    "concurrent-ruby": ("concurrent",),
    "dotenv-rails": ("dotenv",),
    "google-protobuf": ("google/protobuf",),
    "railties": ("rails",),
    "rest-client": ("rest-client", "restclient"),
    "ruby-openai": ("openai",),
}

# Composer packages and the namespace they autoload, keyed by lower-case name.
# An installed vendor/<name>/composer.json wins over this table.
COMPOSER_IMPORT_NAMES: dict[str, tuple[str, ...]] = {
    "aws/aws-sdk-php": ("Aws",),
    "doctrine/dbal": ("Doctrine\\DBAL",),
    "doctrine/orm": ("Doctrine\\ORM",),
    "firebase/php-jwt": ("Firebase\\JWT",),
    "guzzlehttp/guzzle": ("GuzzleHttp",),
    "guzzlehttp/promises": ("GuzzleHttp\\Promise",),
    "guzzlehttp/psr7": ("GuzzleHttp\\Psr7",),
    "laravel/framework": ("Illuminate",),
    "league/flysystem": ("League\\Flysystem",),
    "monolog/monolog": ("Monolog",),
    "nesbot/carbon": ("Carbon",),
    "phpunit/phpunit": ("PHPUnit",),
    "predis/predis": ("Predis",),
    "psr/http-message": ("Psr\\Http\\Message",),
    "psr/log": ("Psr\\Log",),
    "ramsey/uuid": ("Ramsey\\Uuid",),
    "stripe/stripe-php": ("Stripe",),
    "twig/twig": ("Twig",),
    "vlucas/phpdotenv": ("Dotenv",),
}

# Swift packages (as skf-scan-manifests.py names them: the last URL segment)
# and the modules they ship, keyed by lower-case name.
SWIFT_IMPORT_NAMES: dict[str, tuple[str, ...]] = {
    "async-http-client": ("AsyncHTTPClient",),
    "firebase-ios-sdk": (
        "FirebaseAnalytics",
        "FirebaseAuth",
        "FirebaseCore",
        "FirebaseCrashlytics",
        "FirebaseDatabase",
        "FirebaseFirestore",
        "FirebaseFunctions",
        "FirebaseMessaging",
        "FirebaseRemoteConfig",
        "FirebaseStorage",
    ),
    "grpc-swift": ("GRPC",),
    "realm-swift": ("RealmSwift", "Realm"),
    "rxswift": ("RxSwift", "RxCocoa", "RxRelay"),
    "snapkit": ("SnapKit",),
    "swift-algorithms": ("Algorithms",),
    "swift-argument-parser": ("ArgumentParser",),
    "swift-async-algorithms": ("AsyncAlgorithms",),
    "swift-atomics": ("Atomics",),
    "swift-collections": ("Collections", "DequeModule", "OrderedCollections"),
    "swift-crypto": ("Crypto",),
    "swift-log": ("Logging",),
    "swift-markdown": ("Markdown",),
    "swift-metrics": ("Metrics",),
    "swift-nio": (
        "NIO",
        "NIOConcurrencyHelpers",
        "NIOCore",
        "NIOEmbedded",
        "NIOFoundationCompat",
        "NIOHTTP1",
        "NIOPosix",
        "NIOTLS",
        "NIOWebSocket",
    ),
    "swift-nio-ssl": ("NIOSSL",),
    "swift-numerics": ("Numerics", "RealModule", "ComplexModule"),
    "swift-protobuf": ("SwiftProtobuf",),
    "swift-syntax": ("SwiftSyntax", "SwiftParser"),
    "swift-system": ("SystemPackage",),
    "swiftyjson": ("SwiftyJSON",),
}


# --------------------------------------------------------------------------
# Input
# --------------------------------------------------------------------------


class InputError(Exception):
    """A malformed input: exit code 1."""


def _read_json_source(source: str, what: str) -> object:
    """Read JSON from a file path, or from stdin when source is '-'."""
    if source == "-":
        try:
            text = sys.stdin.read()
        except OSError as exc:
            raise InputError(f"failed to read {what} JSON from stdin: {exc}") from exc
    else:
        path = Path(source)
        if not path.exists() or path.is_dir():
            raise InputError(f"{what} file not found: {path}")
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise InputError(f"failed to read {what} file {path}: {exc}") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise InputError(f"malformed JSON in {what} input: {exc}") from exc


def _pep503(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _dedupe_key(ecosystem: str | None, name: str) -> tuple[str, str]:
    """Key under which two spellings of one dependency collapse."""
    if ecosystem == "python":
        return ecosystem, _pep503(name)
    if ecosystem == "rust":
        return ecosystem, name.lower().replace("_", "-")
    if ecosystem == "composer":
        return ecosystem, name.lower()
    return ecosystem or "", name


def _string_list(value: object, where: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
        raise InputError(f"{where} must be a list of non-empty strings")
    return list(dict.fromkeys(value))


def _dependency_entry(raw: object, where: str) -> dict:
    if isinstance(raw, str):
        raw = {"name": raw}
    if not isinstance(raw, dict):
        raise InputError(f"{where} must be a name string or an object")
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        raise InputError(f"{where} needs a non-empty `name`")
    ecosystem = raw.get("ecosystem")
    if ecosystem is not None and (not isinstance(ecosystem, str) or not ecosystem):
        raise InputError(f"{where} `ecosystem` must be a non-empty string")
    scope = raw.get("scope")
    if scope not in (None, "runtime", "dev"):
        raise InputError(f"{where} `scope` must be 'runtime' or 'dev'; got {scope!r}")
    entry = {"name": name.strip(), "ecosystem": ecosystem, "scope": scope or "runtime"}
    if raw.get("modules") is not None:
        entry["modules"] = _string_list(raw["modules"], f"{where} `modules`")
    return entry


def parse_dependencies(payload: object) -> list[dict]:
    """Read the --deps payload into deduplicated dependency entries.

    Accepts the skf-scan-manifests.py envelope, {"dependencies": [...]} or a
    bare list. Two entries of one ecosystem whose names normalise alike
    (PyYAML and pyyaml) collapse into the first; the merged entry is dev only
    when every occurrence is dev.
    """
    raw_entries: list[tuple[object, str]] = []
    if isinstance(payload, dict) and "manifests" in payload:
        manifests = payload["manifests"]
        if not isinstance(manifests, list):
            raise InputError("`manifests` must be a list")
        for m_idx, manifest in enumerate(manifests):
            if not isinstance(manifest, dict):
                raise InputError(f"manifests[{m_idx}] is not an object")
            ecosystem = manifest.get("ecosystem")
            deps = manifest.get("deps") or []
            if not isinstance(deps, list):
                raise InputError(f"manifests[{m_idx}].deps must be a list")
            for d_idx, dep in enumerate(deps):
                if not isinstance(dep, dict):
                    raise InputError(f"manifests[{m_idx}].deps[{d_idx}] is not an object")
                name = dep.get("name")
                # the scanner writes `<unparsable>` for a line it could not read
                if not isinstance(name, str) or not name or name.startswith("<"):
                    continue
                raw_entries.append(
                    (
                        {"name": name, "ecosystem": ecosystem, "scope": dep.get("scope")},
                        f"manifests[{m_idx}].deps[{d_idx}]",
                    )
                )
    else:
        if isinstance(payload, dict) and "dependencies" in payload:
            payload = payload["dependencies"]
        if not isinstance(payload, list):
            raise InputError(
                "--deps must be the skf-scan-manifests.py envelope, "
                '{"dependencies": [...]} or a JSON array'
            )
        raw_entries = [(raw, f"dependencies[{idx}]") for idx, raw in enumerate(payload)]

    merged: dict[tuple[str, str], dict] = {}
    for raw, where in raw_entries:
        entry = _dependency_entry(raw, where)
        key = _dedupe_key(entry["ecosystem"], entry["name"])
        seen = merged.get(key)
        if seen is None:
            merged[key] = entry
            continue
        if entry["scope"] == "runtime":
            seen["scope"] = "runtime"
        if "modules" in entry:
            seen["modules"] = list(dict.fromkeys(seen.get("modules", []) + entry["modules"]))
    return list(merged.values())


def _normalise_unit_path(path: str) -> str:
    """A unit path as a root-relative POSIX path; the root itself is ''."""
    path = path.replace("\\", "/").strip().strip("/")
    if not path:
        return ""
    path = posixpath.normpath(path)
    return "" if path == "." else path


def parse_units(payload: object) -> list[dict]:
    """Read the --units payload: unique names and unique paths."""
    if isinstance(payload, dict) and "units" in payload:
        payload = payload["units"]
    if not isinstance(payload, list):
        raise InputError('--units must be {"units": [...]} or a JSON array')
    units: list[dict] = []
    names: set[str] = set()
    paths: set[str] = set()
    for idx, raw in enumerate(payload):
        where = f"units[{idx}]"
        if not isinstance(raw, dict):
            raise InputError(f"{where} is not an object")
        name = raw.get("name")
        if not isinstance(name, str) or not name.strip():
            raise InputError(f"{where} needs a non-empty `name`")
        path = raw.get("path")
        if not isinstance(path, str):
            raise InputError(f"{where} needs a `path` string (relative to the root)")
        path = _normalise_unit_path(path)
        if path == ".." or path.startswith("../"):
            raise InputError(f"{where} `path` leaves the root: {raw.get('path')!r}")
        ecosystem = raw.get("ecosystem")
        if ecosystem is not None and (not isinstance(ecosystem, str) or not ecosystem):
            raise InputError(f"{where} `ecosystem` must be a non-empty string")
        name = name.strip()
        if name in names:
            raise InputError(f"{where} repeats unit name {name!r}")
        if path in paths:
            raise InputError(f"{where} repeats unit path {path!r}")
        names.add(name)
        paths.add(path)
        unit = {"name": name, "path": path, "ecosystem": ecosystem, "modules": []}
        if raw.get("modules") is not None:
            unit["modules"] = _string_list(raw["modules"], f"{where} `modules`")
        units.append(unit)
    return units


# --------------------------------------------------------------------------
# Import names
# --------------------------------------------------------------------------


def _studly(part: str) -> str:
    return "".join(p[:1].upper() + p[1:] for p in re.split(r"[-_.]+", part) if p)


def _npm_import_names(name: str) -> tuple[list[str], str]:
    if name.startswith("@types/") and len(name) > len("@types/"):
        # a guess: @types/node types built-ins, @types/jest types globals
        inner = name[len("@types/"):]
        # DefinitelyTyped spells @scope/pkg as scope__pkg
        if "__" in inner:
            scope, _, pkg = inner.partition("__")
            return [f"@{scope}/{pkg}"], "guessed"
        return [inner], "guessed"
    return [name], "exact"


def _python_import_names(name: str) -> tuple[list[str], str]:
    key = _pep503(name)
    if key.startswith("types-") and len(key) > len("types-"):
        # typeshed stubs: types-PyYAML types the `yaml` module
        return _python_import_names(key[len("types-"):])
    mapped = PYTHON_IMPORT_NAMES.get(key)
    if mapped:
        return list(mapped), "mapped"
    for prefix, (namespace, joiner) in PYTHON_NAMESPACE_FAMILIES.items():
        if key.startswith(prefix) and len(key) > len(prefix):
            # a guess: google-cloud-pubsub is imported as google.cloud.pubsub_v1
            return [namespace + key[len(prefix):].replace("-", joiner)], "guessed"
    guess = name.replace("-", "_")
    if not re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*", guess):
        return [], "guessed"
    return list(dict.fromkeys([guess, guess.lower()])), "guessed"


def _jvm_import_names(name: str) -> tuple[list[str], str]:
    mapped = JVM_IMPORT_NAMES.get(name)
    if mapped:
        return list(mapped), "mapped"
    group = name.split(":", 1)[0]
    if re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*", group):
        return [group], "guessed"
    return [], "guessed"


def _ruby_import_names(name: str) -> tuple[list[str], str]:
    mapped = RUBY_IMPORT_NAMES.get(name.lower())
    if mapped:
        return list(mapped), "mapped"
    return list(dict.fromkeys([name, name.replace("-", "/")])), "guessed"


_COMPOSER_NAME = re.compile(r"[A-Za-z0-9][\w.-]*/[A-Za-z0-9][\w.-]*")


def _composer_installed_namespaces(root: Path, name: str) -> list[str]:
    """Namespaces the installed vendor/<name>/composer.json autoloads."""
    if not _COMPOSER_NAME.fullmatch(name):
        return []
    manifest = root / "vendor" / name / "composer.json"
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return []
    autoload = data.get("autoload") if isinstance(data, dict) else None
    if not isinstance(autoload, dict):
        return []
    namespaces: set[str] = set()
    for kind in ("psr-4", "psr-0"):
        table = autoload.get(kind)
        if isinstance(table, dict):
            namespaces.update(p.strip("\\") for p in table if p.strip("\\"))
    return sorted(namespaces)


def _symfony_namespace(package: str) -> str:
    """The namespace a symfony/<package> usually autoloads, by Symfony's naming."""
    if package.endswith("-bundle"):
        return "Symfony\\Bundle\\" + _studly(package)
    if package.endswith("-bridge"):
        return "Symfony\\Bridge\\" + _studly(package[: -len("-bridge")])
    if package.endswith("-contracts"):
        return "Symfony\\Contracts\\" + _studly(package[: -len("-contracts")])
    if package.startswith("ux-"):
        return "Symfony\\UX\\" + _studly(package[len("ux-"):])
    if package.startswith("polyfill-"):
        return "Symfony\\Polyfill\\" + _studly(package[len("polyfill-"):])
    if package.startswith("security-"):
        return "Symfony\\Component\\Security\\" + _studly(package[len("security-"):])
    return "Symfony\\Component\\" + _studly(package)


def _composer_import_names(name: str, root: Path) -> tuple[list[str], str]:
    installed = _composer_installed_namespaces(root, name)
    if installed:
        return installed, "exact"
    key = name.lower()
    mapped = COMPOSER_IMPORT_NAMES.get(key)
    if mapped:
        return list(mapped), "mapped"
    vendor, _, package = key.partition("/")
    if vendor == "symfony" and package:
        return [_symfony_namespace(package)], "guessed"
    if vendor and package:
        return [f"{_studly(vendor)}\\{_studly(package)}", _studly(vendor)], "guessed"
    return [], "guessed"


def _swift_import_names(name: str) -> tuple[list[str], str]:
    mapped = SWIFT_IMPORT_NAMES.get(name.lower())
    if mapped:
        return list(mapped), "mapped"
    base = name[len("swift-"):] if name.lower().startswith("swift-") else name
    names = [name] if re.fullmatch(r"[A-Za-z_]\w*", name) else []
    camel = _studly(base)
    if camel:
        names.append(camel)
    return list(dict.fromkeys(names)), "guessed"


def import_names(name: str, ecosystem: str | None, root: Path) -> tuple[list[str], str]:
    """Return (import names, resolution) for a dependency of an ecosystem.

    With no ecosystem the name is tried as it is and with the Python guesses,
    in every language.
    """
    if ecosystem == "npm":
        return _npm_import_names(name)
    if ecosystem == "python":
        return _python_import_names(name)
    if ecosystem == "rust":
        return [name.replace("-", "_")], "exact"
    if ecosystem == "go":
        return [name], "exact"
    if ecosystem in ("maven", "gradle"):
        return _jvm_import_names(name)
    if ecosystem == "ruby":
        return _ruby_import_names(name)
    if ecosystem == "composer":
        return _composer_import_names(name, root)
    if ecosystem == "swift":
        return _swift_import_names(name)
    guesses, _ = _python_import_names(name)
    return list(dict.fromkeys([name, *guesses])), "guessed"


# --------------------------------------------------------------------------
# Exclusion globs
# --------------------------------------------------------------------------


def _glob_regex(pattern: str) -> re.Pattern[str]:
    """Translate a glob to a regex: `*` and `?` stay in one path segment,
    `**/` spans zero or more directories and `**` any characters."""
    out: list[str] = []
    i = 0
    while i < len(pattern):
        char = pattern[i]
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
            continue
        if pattern.startswith("**", i):
            out.append(".*")
            i += 2
            continue
        if char == "*":
            out.append("[^/]*")
        elif char == "?":
            out.append("[^/]")
        elif char == "[" and pattern.find("]", i + 1) != -1:
            end = pattern.find("]", i + 1)
            body = pattern[i + 1 : end]
            if body.startswith("!"):
                body = "^" + body[1:]
            out.append("[" + body.replace("\\", "\\\\") + "]")
            i = end + 1
            continue
        else:
            out.append(re.escape(char))
        i += 1
    return re.compile("".join(out))


class Excludes:
    """The exclusion globs, split by what each one is matched against."""

    def __init__(self, patterns: list[str]) -> None:
        self.dir_names: list[re.Pattern[str]] = []
        self.dir_paths: list[re.Pattern[str]] = []
        self.file_names: list[re.Pattern[str]] = []
        self.file_paths: list[re.Pattern[str]] = []
        for raw in patterns:
            pattern = raw.strip().replace("\\", "/")
            # a leading / or ./ anchors the pattern to the root
            anchored = pattern.startswith(("/", "./"))
            is_dir = pattern.endswith("/")
            body = posixpath.normpath(pattern.lstrip("/") or ".")
            if body == ".":
                continue
            if is_dir:
                target = self.dir_paths if anchored or "/" in body else self.dir_names
            else:
                target = self.file_paths if anchored or "/" in body else self.file_names
            target.append(_glob_regex(body))

    def skip_dir(self, name: str, rel: str) -> bool:
        return any(r.fullmatch(name) for r in self.dir_names) or any(
            r.fullmatch(rel) for r in self.dir_paths
        )

    def skip_file(self, name: str, rel: str) -> bool:
        return any(r.fullmatch(name) for r in self.file_names) or any(
            r.fullmatch(rel) for r in self.file_paths
        )


# --------------------------------------------------------------------------
# Import extraction
# --------------------------------------------------------------------------


# A record is (line, kind, value): kind "module" holds an imported module
# name; kind "path" holds a relative import resolved to a root-relative path.
Record = tuple[int, str, str]

_JS_IMPORT = re.compile(
    r"""(?<![\w$.])(?:
          (?:from|import)\s*(?P<q1>['"])(?P<s1>[^'"\n]+)(?P=q1)
        | (?:import|require)\s*\(\s*(?P<q2>['"`])(?P<s2>[^'"`\n]+)(?P=q2)
        )""",
    re.VERBOSE,
)
_PY_FROM = re.compile(r"from\s+(?P<mod>\.+[\w.]*|[A-Za-z_][\w.]*)\s+import\s*(?P<names>.*)")
_PY_DYNAMIC = re.compile(
    r"""(?<!\w)(?:import_module|__import__)\s*\(\s*(['"])(?P<mod>[A-Za-z_][\w.]*)\1"""
)
_PY_DOTTED = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*")
_RS_USE = re.compile(
    r"^\s*(?:pub(?:\s*\([^)]*\))?\s+)?use\s+(?:::)?(?P<path>[A-Za-z_]\w*(?:::[A-Za-z_]\w*)*)"
)
_RS_EXTERN = re.compile(r"^\s*extern\s+crate\s+(?P<path>[A-Za-z_]\w*)")
_RS_PATH = re.compile(r"(?<![\w:])(?P<path>[A-Za-z_]\w*(?:::[A-Za-z_]\w*)+)")
_GO_IMPORT_ONE = re.compile(r'^\s*import\s+(?:[\w.]+\s+)?"(?P<path>[^"]+)"')
_GO_IMPORT_OPEN = re.compile(r"^\s*import\s*\(")
_GO_QUOTED = re.compile(r'(?:^|[\s(;])(?:[\w.]+\s+)?"(?P<path>[^"]+)"')
_JVM_IMPORT = re.compile(
    r"^\s*import\s+(?:static\s+)?(?P<path>[A-Za-z_]\w*(?:\.(?:[A-Za-z_]\w*|\*))*)"
)
_RB_REQUIRE = re.compile(
    r"""^\s*(?P<kind>require_relative|require)\s*\(?\s*(['"])(?P<path>[^'"]+)\2"""
)
_PHP_USE = re.compile(r"^\s*use\s+(?P<body>[^;]*)")
_SWIFT_IMPORT = re.compile(
    r"^\s*(?:@\w+(?:\([^)]*\))?\s+)*import\s+"
    r"(?:(?:typealias|struct|class|enum|protocol|let|var|func)\s+)?(?P<mod>[A-Za-z_]\w*)"
)


def _lines(text: str) -> list[str]:
    """The lines of a file as editors and `ast` number them (str.splitlines
    also breaks at form feeds and Unicode line separators)."""
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def _resolve_relative(base_dir: str, spec: str) -> str | None:
    """Join a relative import to its file's directory; None if it leaves the root."""
    joined = posixpath.normpath(posixpath.join(base_dir, spec) if base_dir else spec)
    if joined == ".." or joined.startswith("../"):
        return None
    return "" if joined == "." else joined


def _js_records(text: str, rel: str) -> list[Record]:
    records: list[Record] = []
    base = posixpath.dirname(rel)
    for number, line in enumerate(_lines(text), start=1):
        if line.lstrip().startswith(("//", "/*", "*")):
            continue
        if "import" not in line and "require" not in line and "from" not in line:
            continue
        for m in _JS_IMPORT.finditer(line):
            spec = m.group("s1") or m.group("s2")
            if not spec or "${" in spec:
                continue
            if spec in (".", "..") or spec.startswith(("./", "../")):
                resolved = _resolve_relative(base, spec)
                if resolved is not None:
                    records.append((number, "path", resolved))
            elif not spec.startswith("/"):
                records.append((number, "module", spec))
    return records


def _py_names(text: str) -> tuple[list[str], bool]:
    """Names of a `from m import ...` list, and whether its `)` was seen."""
    closed = True
    if text.startswith("("):
        text = text[1:]
        closed = False
    if not closed and ")" in text:
        text = text.split(")", 1)[0]
        closed = True
    names = []
    for item in text.split(","):
        item = item.strip().split(" as ", 1)[0].strip()
        if item and item != "*" and re.fullmatch(r"[A-Za-z_]\w*", item):
            names.append(item)
    return names, closed


def _py_from_records(number: int, mod: str, names: list[str], base: str) -> list[Record]:
    if not mod.startswith("."):
        return [(number, "module", mod)] + [(number, "module", f"{mod}.{n}") for n in names]
    level = len(mod) - len(mod.lstrip("."))
    rest = mod[level:]
    target = base
    for _ in range(level - 1):
        if not target:
            return []
        target = posixpath.dirname(target)
    if rest:
        sub = rest.replace(".", "/")
        target = posixpath.join(target, sub) if target else sub
    records: list[Record] = [(number, "path", target)]
    for n in names:
        records.append((number, "path", posixpath.join(target, n) if target else n))
    return records


def _py_statements(tree: ast.Module):
    """Every statement of a module, the ones in nested blocks included."""
    queue: list[ast.AST] = list(tree.body)
    for node in queue:
        yield node
        for field in ("body", "orelse", "finalbody", "handlers", "cases"):
            queue.extend(getattr(node, field, ()))


def _python_records(text: str, rel: str) -> list[Record]:
    base = posixpath.dirname(rel)
    if "import" not in text:
        return []
    if len(text) > PYTHON_AST_MAX_CHARS:
        return _python_line_records(text, base)
    try:
        with warnings.catch_warnings():
            # an invalid escape sequence warns; the file is only read
            warnings.simplefilter("ignore")
            tree = ast.parse(text)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        # Python 2, a syntax error, syntax newer than this interpreter, or
        # nesting too deep to parse
        return _python_line_records(text, base)
    # an import statement sits in a block; a dynamic import is a call in any expression
    dynamic = "import_module" in text or "__import__" in text
    records: list[Record] = []
    for node in ast.walk(tree) if dynamic else _py_statements(tree):
        if isinstance(node, ast.Import):
            records.extend((node.lineno, "module", alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            mod = "." * node.level + (node.module or "")
            names = [alias.name for alias in node.names if alias.name != "*"]
            records.extend(_py_from_records(node.lineno, mod, names, base))
        elif isinstance(node, ast.Call) and node.args:
            func, arg = node.func, node.args[0]
            called = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
            if (
                called in ("import_module", "__import__")
                and isinstance(arg, ast.Constant)
                and isinstance(arg.value, str)
                and _PY_DOTTED.fullmatch(arg.value)
            ):
                records.append((node.lineno, "module", arg.value))
    return sorted(records, key=lambda record: record[0])


def _py_code(line: str, quote: str | None) -> tuple[str, str | None]:
    """The code of one line, and the triple quote still open at its end.

    `quote` is the triple quote open when the line starts. Triple-quoted text
    and the comment are left out; a `#` inside a string literal is kept.
    """
    code: list[str] = []
    i, end = 0, len(line)
    while i < end:
        if quote:
            if line.startswith(quote, i):
                quote = None
                i += 3
            else:
                i += 2 if line[i] == "\\" else 1
            continue
        char = line[i]
        if char == "#":
            break
        if line.startswith(('"""', "'''"), i):
            quote = line[i : i + 3]
            i += 3
        elif char in "'\"":
            close = i + 1
            while close < end and line[close] != char:
                close += 2 if line[close] == "\\" else 1
            code.append(line[i : close + 1])
            i = close + 1
        else:
            code.append(char)
            i += 1
    return "".join(code), quote


def _python_line_records(text: str, base: str) -> list[Record]:
    """The imports of a file `ast` cannot parse, read line by line."""
    records: list[Record] = []
    quote: str | None = None
    pending: tuple[int, str] | None = None  # (line, module) of an open `from m import (`
    for number, line in enumerate(_lines(text), start=1):
        code, quote = _py_code(line, quote)
        if pending is not None:
            names, closed = _py_names("(" + code)
            records.extend(_py_from_records(pending[0], pending[1], names, base)[1:])
            if closed:
                pending = None
            continue
        for statement in code.split(";"):
            statement = statement.strip()
            if statement.startswith("import "):
                for item in statement[len("import "):].split(","):
                    item = item.strip().split(" as ", 1)[0].strip()
                    if _PY_DOTTED.fullmatch(item):
                        records.append((number, "module", item))
            elif statement.startswith("from "):
                m = _PY_FROM.match(statement)
                if not m:
                    continue
                names, closed = _py_names(m.group("names").strip())
                records.extend(_py_from_records(number, m.group("mod"), names, base))
                if not closed:
                    pending = (number, m.group("mod"))
        if "import_module" in code or "__import__" in code:
            for m in _PY_DYNAMIC.finditer(code):
                records.append((number, "module", m.group("mod")))
    return records


def _rust_records(text: str, rel: str) -> list[Record]:
    records: list[Record] = []
    for number, line in enumerate(_lines(text), start=1):
        if line.lstrip().startswith(("//", "/*", "*")):
            continue
        for regex in (_RS_USE, _RS_EXTERN):
            m = regex.match(line)
            if m:
                records.append((number, "module", m.group("path")))
        if "::" in line:
            for m in _RS_PATH.finditer(line):
                records.append((number, "module", m.group("path")))
    return records


def _go_records(text: str, rel: str) -> list[Record]:
    records: list[Record] = []
    in_block = False
    for number, line in enumerate(_lines(text), start=1):
        code = line.split("//", 1)[0]
        if in_block:
            if code.strip().startswith(")"):
                in_block = False
                continue
            m = _GO_QUOTED.search(code)
            if m:
                records.append((number, "module", m.group("path")))
            if ")" in code.split('"')[-1]:
                in_block = False
            continue
        if _GO_IMPORT_OPEN.match(code):
            rest = code.split("(", 1)[1]
            for m in _GO_QUOTED.finditer(rest):
                records.append((number, "module", m.group("path")))
            in_block = ")" not in rest.split('"')[-1]
            continue
        m = _GO_IMPORT_ONE.match(code)
        if m:
            records.append((number, "module", m.group("path")))
    return records


def _jvm_records(text: str, rel: str) -> list[Record]:
    records: list[Record] = []
    for number, line in enumerate(_lines(text), start=1):
        m = _JVM_IMPORT.match(line)
        if m:
            path = m.group("path")
            if path.endswith(".*"):
                path = path[:-2]
            records.append((number, "module", path))
    return records


def _ruby_records(text: str, rel: str) -> list[Record]:
    records: list[Record] = []
    base = posixpath.dirname(rel)
    for number, line in enumerate(_lines(text), start=1):
        m = _RB_REQUIRE.match(line)
        if not m:
            continue
        path = m.group("path")
        if m.group("kind") == "require_relative" or path.startswith(("./", "../")):
            resolved = _resolve_relative(base, path)
            if resolved is not None:
                records.append((number, "path", resolved))
        else:
            records.append((number, "module", path))
    return records


def _php_records(text: str, rel: str) -> list[Record]:
    records: list[Record] = []
    for number, line in enumerate(_lines(text), start=1):
        m = _PHP_USE.match(line)
        if not m:
            continue
        body = m.group("body").strip()
        if body.startswith(("function ", "const ")):
            body = body.split(None, 1)[1] if " " in body else ""
        if "{" in body:
            prefix = body.split("{", 1)[0].strip().strip("\\")
            items = [prefix] if prefix else []
        else:
            items = [
                item.strip().split(" as ", 1)[0].strip().strip("\\") for item in body.split(",")
            ]
        for item in items:
            if re.fullmatch(r"[A-Za-z_]\w*(?:\\[A-Za-z_]\w*)*", item):
                records.append((number, "module", item))
    return records


def _swift_records(text: str, rel: str) -> list[Record]:
    records: list[Record] = []
    for number, line in enumerate(_lines(text), start=1):
        m = _SWIFT_IMPORT.match(line)
        if m:
            records.append((number, "module", m.group("mod")))
    return records


EXTRACTORS = {
    "js": _js_records,
    "python": _python_records,
    "rust": _rust_records,
    "go": _go_records,
    "jvm": _jvm_records,
    "ruby": _ruby_records,
    "php": _php_records,
    "swift": _swift_records,
}


def extract_records(language: str, text: str, rel: str) -> list[Record]:
    """Import records of one source file, in line order."""
    return EXTRACTORS[language](text.lstrip("\ufeff"), rel)


def _key(language: str, name: str) -> str:
    return name.lower() if language == "php" else name


def candidates(language: str, module: str) -> list[str]:
    """Every prefix of `module` at the language's separator, longest first."""
    module = _key(language, module)
    sep = SEPARATORS[language]
    if sep is None:
        return [module]
    parts = module.split(sep)
    return [sep.join(parts[:i]) for i in range(len(parts), 0, -1)]


# --------------------------------------------------------------------------
# Counting
# --------------------------------------------------------------------------


def _walk(root: Path, excludes: Excludes, extensions: dict[str, str]):
    """Yield (rel, path, language) for every source file left after exclusions."""
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root).replace(os.sep, "/")
        rel_dir = "" if rel_dir == "." else rel_dir
        kept = []
        for name in sorted(dirnames):
            rel = f"{rel_dir}/{name}" if rel_dir else name
            if os.path.islink(os.path.join(dirpath, name)) or excludes.skip_dir(name, rel):
                continue
            kept.append(name)
        dirnames[:] = kept
        for name in sorted(filenames):
            language = extensions.get(os.path.splitext(name)[1])
            if language is None:
                continue
            rel = f"{rel_dir}/{name}" if rel_dir else name
            path = os.path.join(dirpath, name)
            if os.path.islink(path) or excludes.skip_file(name, rel):
                continue
            yield rel, path, language


def _files(first_lines: dict[str, int]) -> list[dict]:
    return [{"path": p, "line": first_lines[p]} for p in sorted(first_lines)]


def _languages(ecosystem: str | None) -> list[str]:
    """The languages whose files a target of this ecosystem is matched in."""
    if ecosystem in ECOSYSTEM_LANGUAGE:
        return [ECOSYSTEM_LANGUAGE[ecosystem]]
    return list(LANGUAGE_EXTENSIONS)


def count_imports(
    root: Path,
    dependencies: list[dict],
    units: list[dict] | None = None,
    threshold: int = DEFAULT_THRESHOLD,
    extra_excludes: list[str] | None = None,
) -> dict:
    """Count the files under `root` that import each dependency and unit."""
    units = units or []
    targets: list[dict] = []
    unresolved: list[dict] = []

    for dep in dependencies:
        ecosystem = dep["ecosystem"]
        if "modules" in dep:
            names, resolution = list(dep["modules"]), "explicit"
        elif ecosystem is not None and ecosystem not in ECOSYSTEM_LANGUAGE:
            unresolved.append(_unresolved(dep, [], "unsupported-ecosystem"))
            continue
        else:
            names, resolution = import_names(dep["name"], ecosystem, root)
        if not names:
            unresolved.append(_unresolved(dep, names, "no-import-name"))
            continue
        targets.append(
            {
                "kind": "dependency",
                "dep": dep,
                "names": names,
                "resolution": resolution,
                "languages": _languages(ecosystem),
            }
        )

    unit_index: dict[int, int] = {}  # position in `units` -> position in `targets`
    for pos, unit in enumerate(units):
        unit_index[pos] = len(targets)
        targets.append(
            {
                "kind": "unit",
                "unit": pos,
                "names": list(unit["modules"]),
                "languages": _languages(unit["ecosystem"]),
            }
        )

    # language -> import-name key -> target positions
    index: dict[str, dict[str, list[int]]] = {lang: {} for lang in LANGUAGE_EXTENSIONS}
    for t_pos, target in enumerate(targets):
        for language in target["languages"]:
            for name in target["names"]:
                index[language].setdefault(_key(language, name), []).append(t_pos)

    needed = {lang for target in targets for lang in target["languages"] if target["names"]}
    if units:
        # relative imports resolve into unit paths in these languages
        needed.update(("js", "python", "ruby"))
    extensions = {ext: lang for lang in needed for ext in LANGUAGE_EXTENSIONS[lang]}

    unit_by_path = {unit["path"]: pos for pos, unit in enumerate(units)}

    def unit_of(rel: str) -> int | None:
        """The unit with the longest path that contains `rel`."""
        while True:
            if rel in unit_by_path:
                return unit_by_path[rel]
            if not rel:
                return None
            rel = posixpath.dirname(rel)

    excludes = Excludes(list(DEFAULT_EXCLUDES) + list(extra_excludes or []))
    first_lines: list[dict[str, int]] = [{} for _ in targets]
    edges: set[tuple[str, str]] = set()
    external: dict[int, set[str]] = {pos: set() for pos in range(len(units))}
    warnings: list[str] = []
    files_scanned = 0

    for rel, path, language in _walk(root, excludes, extensions):
        try:
            with open(path, "rb") as handle:
                text = handle.read().decode("utf-8", errors="replace")
        except OSError as exc:
            warnings.append(f"{rel}: unreadable ({exc.strerror or exc})")
            continue
        files_scanned += 1
        records = extract_records(language, text, rel)
        if not records:
            continue
        own_unit = unit_of(rel) if units else None
        lang_index = index[language]
        for number, kind, value in records:
            if kind == "module":
                hits: list[int] = []
                for candidate in candidates(language, value):
                    if candidate in lang_index:
                        hits = lang_index[candidate]
                        break
            else:
                pos = unit_of(value) if units else None
                hits = [unit_index[pos]] if pos is not None else []
            for t_pos in hits:
                target = targets[t_pos]
                if target["kind"] == "unit":
                    if target["unit"] == own_unit:
                        continue
                    if own_unit is not None:
                        edges.add((units[own_unit]["name"], units[target["unit"]]["name"]))
                elif own_unit is not None:
                    external[own_unit].add(target["dep"]["name"])
                seen = first_lines[t_pos].get(rel)
                if seen is None or number < seen:
                    first_lines[t_pos][rel] = number

    dependencies_out: list[dict] = []
    for t_pos, target in enumerate(targets):
        if target["kind"] != "dependency":
            continue
        dep = target["dep"]
        if target["resolution"] == "guessed" and not first_lines[t_pos]:
            unresolved.append(_unresolved(dep, target["names"], "guess-unmatched"))
            continue
        entry = {
            "name": dep["name"],
            "ecosystem": dep["ecosystem"],
            "import_names": target["names"],
            "resolution": target["resolution"],
        }
        if dep["scope"] == "dev":
            entry["scope"] = "dev"
        entry["files"] = _files(first_lines[t_pos])
        entry["file_count"] = len(first_lines[t_pos])
        entry["above_threshold"] = entry["file_count"] >= threshold
        dependencies_out.append(entry)
    dependencies_out.sort(key=lambda d: (-d["file_count"], d["name"], d["ecosystem"] or ""))
    unresolved.sort(key=lambda d: (d["name"], d["ecosystem"] or ""))

    result: dict = {
        "threshold": threshold,
        "files_scanned": files_scanned,
        "dependencies": dependencies_out,
        "unresolved": unresolved,
    }
    if units:
        imported_by: dict[str, set[str]] = {u["name"]: set() for u in units}
        imports_from: dict[str, set[str]] = {u["name"]: set() for u in units}
        for src, dst in edges:
            imports_from[src].add(dst)
            imported_by[dst].add(src)
        units_out = []
        for pos, unit in enumerate(units):
            lines = first_lines[unit_index[pos]]
            units_out.append(
                {
                    "name": unit["name"],
                    "path": unit["path"],
                    "import_names": list(unit["modules"]),
                    "files": _files(lines),
                    "file_count": len(lines),
                    "imported_by": sorted(imported_by[unit["name"]]),
                    "imports_from": sorted(imports_from[unit["name"]]),
                    "external_deps": sorted(external[pos]),
                }
            )
        result["units"] = sorted(units_out, key=lambda u: u["name"])
        result["edges"] = [list(edge) for edge in sorted(edges)]
    if warnings:
        result["warnings"] = warnings
    return result


def _unresolved(dep: dict, names: list[str], reason: str) -> dict:
    entry = {
        "name": dep["name"],
        "ecosystem": dep["ecosystem"],
        "import_names": names,
        "reason": reason,
    }
    if dep["scope"] == "dev":
        entry["scope"] = "dev"
    return entry


def as_libraries(result: dict) -> list[dict]:
    """The skf-pair-intersect.py `--libraries` input: dependencies, then units."""
    rows = [
        {"name": d["name"], "files": [f["path"] for f in d["files"]]}
        for d in result["dependencies"]
    ]
    rows += [
        {"name": u["name"], "files": [f["path"] for f in u["files"]]}
        for u in result.get("units", [])
    ]
    return rows


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _cmd_count(args: argparse.Namespace) -> int:
    root = Path(args.root)
    if not root.is_dir():
        print(f"error: root not a directory: {root}", file=sys.stderr)
        return 1
    if args.deps is None and args.units is None:
        print("error: pass --deps, --units or both", file=sys.stderr)
        return 1
    if args.deps == "-" and args.units == "-":
        print("error: only one of --deps and --units may read stdin", file=sys.stderr)
        return 1
    if args.threshold < 0:
        print(f"error: --threshold must be >= 0; got {args.threshold}", file=sys.stderr)
        return 1
    try:
        dependencies: list[dict] = []
        units: list[dict] | None = None
        if args.deps is not None:
            dependencies = parse_dependencies(_read_json_source(args.deps, "--deps"))
        if args.units is not None:
            units = parse_units(_read_json_source(args.units, "--units"))
    except InputError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    try:
        result = count_imports(
            root,
            dependencies,
            units=units,
            threshold=args.threshold,
            extra_excludes=args.exclude,
        )
    except OSError as exc:
        print(f"error: filesystem error during scan: {exc}", file=sys.stderr)
        return 1
    output = as_libraries(result) if args.format == "libraries" else result
    json.dump(output, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skf-count-imports",
        description=(
            "Count, per dependency and per unit, the source files that import "
            "it, with boundary-anchored matching and distribution-to-import names."
        ),
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_count = sub.add_parser("count", help="count importing files and emit JSON")
    p_count.add_argument("root", help="path to the tree to scan")
    p_count.add_argument(
        "--deps",
        default=None,
        help=(
            "dependencies JSON file, or '-' for stdin: the skf-scan-manifests.py "
            'envelope, {"dependencies": [...]} or a list of names or '
            '{"name", "ecosystem", "modules", "scope"} objects'
        ),
    )
    p_count.add_argument(
        "--units",
        default=None,
        help=(
            "units JSON file, or '-' for stdin: a list of "
            '{"name", "path", "modules", "ecosystem"} objects'
        ),
    )
    p_count.add_argument(
        "--threshold",
        type=int,
        default=DEFAULT_THRESHOLD,
        help=f"file count at which a dependency is above_threshold (default {DEFAULT_THRESHOLD})",
    )
    p_count.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="GLOB",
        help=(
            "another path glob to leave out, added to the defaults (repeatable; "
            "a leading / or ./ anchors it to the root)"
        ),
    )
    p_count.add_argument(
        "--format",
        choices=("full", "libraries"),
        default="full",
        help="full envelope (default) or the skf-pair-intersect.py --libraries list",
    )
    p_count.set_defaults(func=_cmd_count)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
