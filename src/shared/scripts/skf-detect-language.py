# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""SKF Detect Language — deterministic primary-language detection from a flat file tree.

Single source of truth for the language-detection rule table that
skf-brief-skill step 2 §3 applies. The rule walk is purely deterministic:
manifest-file presence first (Cargo.toml → rust, package.json → js/ts,
etc.), then extension-frequency fallback. Moving it into a shared script
saves ~150-250 tokens per workflow invocation and removes a quiet drift
seam — the JS-vs-TS disambiguation in particular benefits from being
co-located with a deterministic rule rather than restated in prose.

Detection rules (apply in order, first match wins):

  0. workspace_signal (optional, from skf-detect-workspaces.manifest_kind):
       "cargo-workspace"       → rust (high)
       "python-multi-package"  → python (high)
       A non-JS workspace root's language wins over a nested package.json +
       tsconfig.json (e.g. a docs/ or website/ site that is not a workspace
       member). JS-family workspaces (npm/pnpm/lerna/rush/nx) carry no entry
       here and fall through to rule 1, whose package.json files correctly
       resolve js/ts.
  1. package.json (with optional tsconfig.json companion):
       tsconfig.json present → typescript (high)
       tsconfig.json absent  → javascript (high)
  2. Cargo.toml          → rust (high)
  3. pyproject.toml | setup.py | setup.cfg → python (high)
  4. go.mod              → go (high)
  5. pom.xml             → java (high)
  6. build.gradle.kts    → kotlin (high)
  7. Package.swift       → swift (high)
  8. Gemfile             → ruby (high)
  9. build.gradle (Groovy), the tree decides:
       src/main/kotlin/  → kotlin (medium)
       else              → java (medium)
 10. *.csproj | *.sln    → csharp (high)
 11. Extension-frequency fallback over the full tree.
       dominant extension >= 50% of code files → that language (medium)
       no clear winner                        → unknown (low)

Which manifests decide (rules 1-10). The tree's root is the deepest folder
that holds every path: the repository root for a whole listing, a unit's
own folder for the files of one unit. A manifest in a hidden folder or in
a folder _NON_CORE_PATH_SEGMENTS names (docs, examples, tests, fixtures,
benchmarks, scripts, tools, ...) below that root is not the project's own
package, so it decides only when no other manifest exists. The rules then
run over the shallowest of the remaining manifests first: the manifests of
the least deep folder that holds one decide, in rule order, so a root
pyproject.toml beats docs/package.json and pydantic-core/Cargo.toml. A
manifest at the root decides at its rule's confidence. When none sits at
the root (CPython's listing holds only Platforms/ and PCbuild/ ones), the
shallowest manifest below it decides at medium confidence, and
detected_languages ends with source_language, the language most of the
tree's source files are written in, so the caller sees both answers. The
tsconfig.json check reads every core folder (every folder when no
manifest is core), so a docs site's tsconfig.json does not make a root
package.json typescript.

CLI:
  echo '{"tree": ["path1", "path2", ...]}' | uv run skf-detect-language.py
  uv run skf-detect-language.py --json '{"tree": [...]}'
  uv run skf-detect-language.py --tree-file <file> [--workspace-signal <manifest_kind>]
  <listing> | uv run skf-detect-language.py --tree-file - [--workspace-signal <manifest_kind>]
  uv run skf-detect-language.py scope-patterns --tree-file <file> --language <language>

--tree-file reads the repository's file list from a file (`-` reads it from
stdin), so a tree of any size reaches the script whole and never passes
through a shell string or the model:
  - JSON: an object whose `tree` lists the paths, such as the output of
    skf-github-probe.py tree (a listing whose `status` is not "ok" is
    refused, with its `message`) or a GitHub git/trees response (only its
    `blob` entries count); or a JSON list of paths.
  - Anything else: one path per line, as `git -c core.quotePath=false
    ls-files` prints them (a leading `./`, as `find .` prints it, is
    dropped).
A byte order mark before the listing is dropped, and a listing that holds
no path is refused. These are the listings skf-recommend-scope-type.py's
--tree-file reads, which takes `[]` as its deliberate fallback.
read_tree_file() is the reader skf-detect-workspaces.py and
skf-shape-detect.py load for their own --tree-file. With --tree-file, stdin
is never read for the payload, so a payload piped in beside a --tree-file
<file> is not seen: pass workspace_signal with --workspace-signal (or the
payload with --json, which may not carry `tree` as well).
--workspace-signal sets the payload's workspace_signal in any form; passing
it in the payload as well is an error.

Input (JSON object on stdin or via --json):
  tree              list of repo-relative file paths (required, non-empty;
                    or --tree-file)
  workspace_signal  optional manifest_kind from skf-detect-workspaces (or
                    --workspace-signal). When it names a non-JS workspace
                    ("cargo-workspace", "python-multi-package"), rule 0
                    returns the root language and ignores nested
                    package.json/tsconfig matches.

Output (JSON on stdout):
  language          — javascript | typescript | rust | python | go
                       | java | kotlin | csharp | ruby | swift | php
                       | unknown
  confidence        — "high" | "medium" | "low"
  detection_source  — human-readable string naming what fired (manifest
                       basename, extension share, etc.); a manifest below
                       the root is named by its path
  fallback_to_extension_frequency: bool (true when rule 11 fired)
  source_language:  the extension-frequency answer over the full tree
                       (rule 11's language, or unknown), whatever decided
                       `language`: the language most source files are in
  detected_languages — ordered, deduplicated list of EVERY manifest-level
                       match, ranked as the winner walk ranks them (folder
                       depth, then rule order), then the languages of the
                       manifests that never decide (non-core folders), then
                       source_language when no manifest sits at the root.
                       language == detected_languages[0] whenever the manifest
                       table fired, so a caller can auto-pick detected_languages[0]
                       and gate multi-language disambiguation on
                       len(detected_languages) > 1. Special cases: a
                       workspace_signal override (rule 0) is decisive and returns
                       a single-element [language]; the extension-frequency
                       fallback (rule 11) contributes [language] for a best guess
                       or [] when language is "unknown".

Exit codes:
  0  recommendation produced (even when language is "unknown")
  2  bad input: invalid JSON, a missing or empty tree, the tree or the
     workspace_signal passed twice, or a tree listing that cannot be read,
     holds no path or reports a failure

scope-patterns prints a brief's `scope.include` and `scope.exclude` for one
language (a value `language` above takes) from the --tree-file listing alone,
so a manifests-only sparse checkout, which holds no source folder on disk,
roots them the same as a full one. The paths are read below the tree's root
(above), and the patterns carry that root, so the files of one unit give
patterns rooted at the unit's folder. The source folders are the first of
these to hold files of the language's extensions (_SCOPE_RULES) and leave
no package out:
  1. the language's conventional folders, in order (src/ then lib/ for
     JavaScript and TypeScript; `**/src/main/java` is every module's). A
     file counts when no folder down to the conventional one is hidden or
     non-core, whatever the folders below it are named (a Java package
     path such as com/example/);
  2. for Python, every top-level core folder that holds an __init__.py
     itself: the import packages (sklearn/ of scikit-learn, django/);
  3. otherwise the whole tree, less each top-level hidden or non-core
     folder that holds files of the language. Go always takes the whole
     tree, and `unknown` matches every file.
A folder leaves a package out when a core folder below the root that holds
a manifest (not a vendored copy) has files of the language outside it, in
its own files or a core folder of its own: a monorepo merged into one
skill, whose root lib/ is one package among its members (aws-sdk-js-v3,
with clients/ and packages/ beside it). Then only a later conventional
folder that matches at any depth (`**/src/main/java`) may still answer,
and otherwise the whole tree does.
`include` lists `<folder>/**/*<ext>` for each extension the source folders
hold (every extension of the language when they hold none); `exclude` lists
the language's test, benchmark and vendored-code globs, then the left-out
folders. Output: {language, source_folders, include, exclude}, with
`source_folders` repo-relative (`.` for the repository root). Exit 2 on an
unusable listing or a language outside the list.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from typing import Any

# A --tree-file listing is JSON when it opens like a JSON object or list of
# paths. A bare leading bracket is not enough: a line listing can start with
# a path such as `[slug]/page.tsx`.
JSON_LISTING_RE = re.compile(r'\{\s*["}]|\[\s*["{\]]')

# Workspace manifest_kind → root language (rule 0). Only non-JS workspace kinds
# appear here: a Cargo/Python workspace root is unambiguously rust/python, and a
# nested package.json+tsconfig (a docs or website subproject) must not win. JS
# workspace kinds (npm-workspaces/pnpm-workspaces/lerna/rush/nx) are
# intentionally absent: their repositories hold package.json files, so rule 1
# resolves js/ts correctly. generic-folders / null carry no language signal.
_WORKSPACE_SIGNAL_LANGUAGE: dict[str, str] = {
    "cargo-workspace": "rust",
    "python-multi-package": "python",
}

# Manifest basenames the rule table checks. Kept tight — tree-wide pattern
# matches (e.g. *.csproj) are handled separately to avoid false positives
# from generated artifacts under build/ or dist/.
_MANIFEST_RULES: list[tuple[str, str, str]] = [
    # (basename, language, detection_source)
    ("Cargo.toml", "rust", "Cargo.toml present"),
    ("pyproject.toml", "python", "pyproject.toml present"),
    ("setup.py", "python", "setup.py present"),
    ("setup.cfg", "python", "setup.cfg present"),
    ("go.mod", "go", "go.mod present"),
    ("pom.xml", "java", "pom.xml present"),
    ("build.gradle.kts", "kotlin", "build.gradle.kts present"),
    ("Package.swift", "swift", "Package.swift present"),
    ("Gemfile", "ruby", "Gemfile present"),
]

# Glob-style suffix rules — matches anywhere in the tree. csproj/sln are
# C#-specific. Ordered so the first hit wins.
_SUFFIX_RULES: list[tuple[str, str, str]] = [
    (".csproj", "csharp", ".csproj project file present"),
    (".sln", "csharp", ".sln solution file present"),
]

# Extension → language for the frequency fallback. Tightly limited to source
# extensions; keeping this small avoids the fallback being skewed by
# auto-generated assets (.json, .md, .yaml, etc.).
_EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".cs": "csharp",
    ".rb": "ruby",
    ".swift": "swift",
    ".php": "php",
}

_DOMINANCE_THRESHOLD = 0.50

# Folders whose manifests are not the project's own package: a docs or
# website site, an example, a test fixture, a benchmark, a script or a tool.
# A copy of skf-shape-detect.py's _NON_CORE_PATH_SEGMENTS, which cannot be
# imported from there: skf-shape-detect.py loads this script. A hidden folder
# (.github/, .devcontainer/) is non-core too.
_NON_CORE_PATH_SEGMENTS = frozenset({
    "example", "examples", "demo", "demos", "sample", "samples",
    "playground", "playgrounds", "e2e", "benchmark", "benchmarks", "bench",
    "fixture", "fixtures", "website", "websites", "www",
    "docs", "doc", "scripts", "tools", "tooling", "devtools", "dev-tools",
    "test", "tests", "__tests__", "integration", "smoke",
})


def _die(message: str, code: int = 2) -> None:
    sys.stderr.write(f"skf-detect-language: {message}\n")
    sys.exit(code)


def _basename(path: str) -> str:
    return path.rsplit("/", 1)[-1]


def _has_basename(tree: list[str], basename: str) -> bool:
    return any(_basename(p) == basename for p in tree)


def _has_suffix(tree: list[str], suffix: str) -> bool:
    return any(p.endswith(suffix) for p in tree)


def _has_path_segment(tree: list[str], segment: str) -> bool:
    """True when any path contains the given segment (e.g. 'src/main/kotlin/')."""
    return any(segment in p for p in tree)


def _extension(path: str) -> str:
    """Return the lowercased file extension including the leading dot, or empty string."""
    base = _basename(path)
    if "." not in base or base.startswith("."):
        return ""
    return "." + base.rsplit(".", 1)[-1].lower()


def is_source_file(path: str) -> bool:
    """Whether a path is a source file the extension-frequency fallback
    counts (skf-detect-workspaces.py's tree snapshot counts the same)."""
    return _extension(path) in _EXTENSION_TO_LANGUAGE


def _frequency_fallback(tree: list[str]) -> dict[str, Any]:
    """Score the tree by source-extension frequency. Returns the result envelope."""
    counter: Counter[str] = Counter()
    for path in tree:
        ext = _extension(path)
        if ext in _EXTENSION_TO_LANGUAGE:
            counter[ext] += 1

    total = sum(counter.values())
    if total == 0:
        return {
            "language": "unknown",
            "confidence": "low",
            "detection_source": "no recognized source extensions in tree",
            "fallback_to_extension_frequency": True,
        }

    # Largest-share extension wins. Ties (e.g. equal counts) broken by
    # the natural order of _EXTENSION_TO_LANGUAGE — Counter.most_common
    # is stable for equal counts and we don't rely on which loses.
    top_ext, top_count = counter.most_common(1)[0]
    share = top_count / total
    language = _EXTENSION_TO_LANGUAGE[top_ext]

    if share >= _DOMINANCE_THRESHOLD:
        confidence = "medium"
        source = f"extension frequency: {top_ext} is {top_count}/{total} of source files ({share:.0%})"
    else:
        confidence = "low"
        source = f"no dominant extension: top is {top_ext} at {top_count}/{total} ({share:.0%}, threshold {int(_DOMINANCE_THRESHOLD * 100)}%)"
        # Still surface the best-guess language; caller / step 3 §4 lets
        # the user override on low confidence.
    return {
        "language": language,
        "confidence": confidence,
        "detection_source": source,
        "fallback_to_extension_frequency": True,
    }


def _parts(path: str) -> list[str]:
    """The segments of a repo-relative path, without empty and `.` ones."""
    return [p for p in path.split("/") if p and p != "."]


def _tree_root(tree: list[str]) -> list[str]:
    """The folder segments every path of the tree sits under (the tree's root)."""
    root: list[str] | None = None
    for path in tree:
        folders = _parts(path)[:-1]
        if root is None:
            root = folders
            continue
        depth = 0
        while depth < min(len(root), len(folders)) and root[depth] == folders[depth]:
            depth += 1
        root = root[:depth]
        if not root:
            break
    return root or []


def _is_core(folders: list[str]) -> bool:
    """Whether no folder below the tree's root is hidden or a non-core folder."""
    return not any(seg.startswith(".") or seg.lower() in _NON_CORE_PATH_SEGMENTS for seg in folders)


def _rule_of(basename: str) -> int | None:
    """The rank of the table rule a manifest basename fires, in rule order
    (package.json first, the suffix rules last), or None."""
    if basename == "package.json":
        return 0
    for i, (name, _language, _source) in enumerate(_MANIFEST_RULES):
        if basename == name:
            return 1 + i
    if basename == "build.gradle":
        return 1 + len(_MANIFEST_RULES)
    for i, (suffix, _language, _source) in enumerate(_SUFFIX_RULES):
        if basename.endswith(suffix):
            return 2 + len(_MANIFEST_RULES) + i
    return None


def _rule_result(rank: int, context: dict[str, bool]) -> dict[str, Any]:
    """The result a table rule gives; `context` says whether the paths its
    checks read hold a tsconfig.json and a src/main/kotlin/ folder."""
    if rank == 0:
        if context["tsconfig"]:
            return {"language": "typescript", "confidence": "high",
                    "detection_source": "package.json + tsconfig.json present"}
        return {"language": "javascript", "confidence": "high",
                "detection_source": "package.json present (no tsconfig.json)"}
    if rank <= len(_MANIFEST_RULES):
        _name, language, source = _MANIFEST_RULES[rank - 1]
        return {"language": language, "confidence": "high", "detection_source": source}
    if rank == 1 + len(_MANIFEST_RULES):
        # build.gradle (Groovy DSL): build.gradle.kts, earlier in the table,
        # already decided when both sit in the same folder depth.
        if context["kotlin"]:
            return {"language": "kotlin", "confidence": "medium",
                    "detection_source": "build.gradle (Groovy) + src/main/kotlin/ present"}
        return {"language": "java", "confidence": "medium",
                "detection_source": "build.gradle (Groovy) present without src/main/kotlin/ \u2014 defaulting to java"}
    _suffix, language, source = _SUFFIX_RULES[rank - 2 - len(_MANIFEST_RULES)]
    return {"language": language, "confidence": "high", "detection_source": source}


def _ranked_manifests(tree: list[str]) -> dict[str, Any]:
    """The tree's manifests, ranked for the winner walk (see the module
    docstring): `deciding` and `other` list (depth, rule rank, path, result)
    tuples in rank order, `deciding` the manifests that may decide and
    `other` the non-core ones that may not."""
    root = _tree_root(tree)
    core: list[tuple[int, int, str]] = []
    rest: list[tuple[int, int, str]] = []
    tsconfig = {True: False, False: False}  # a tsconfig.json in a core / non-core folder
    for path in tree:
        parts = _parts(path)
        if not parts:
            continue
        folders = parts[len(root):-1]
        is_core = _is_core(folders)
        if parts[-1] == "tsconfig.json":
            tsconfig[is_core] = True
        rank = _rule_of(parts[-1])
        if rank is not None:
            (core if is_core else rest).append((len(folders), rank, path))
    # A source path such as src/main/kotlin/com/example/App.kt is the
    # project's own whatever its folder names: the Kotlin check reads them all.
    kotlin = _has_path_segment(tree, "src/main/kotlin/")
    whole = {"tsconfig": tsconfig[True] or tsconfig[False], "kotlin": kotlin}
    context = {"tsconfig": tsconfig[True], "kotlin": kotlin} if core else whole
    deciding, other = (core, rest) if core else (rest, [])
    return {
        "deciding": [(d, r, p, _rule_result(r, context)) for d, r, p in sorted(deciding)],
        "other": [(d, r, p, _rule_result(r, whole)) for d, r, p in sorted(other)],
    }


def _detected_languages(payload: dict[str, Any], winner: dict[str, Any]) -> list[str]:
    """Accumulate every manifest-level match into an ordered, deduplicated list.

    The walk follows the winner walk's ranking exactly (folder depth, then
    rule order), so winner["language"] == detected_languages[0] whenever the
    manifest table fired; the non-core manifests follow, then, when no
    manifest sits at the root, the tree's source language. Two decisive
    short-circuits diverge from a full walk on purpose:

      * A workspace_signal override (rule 0) is authoritative — the workspace
        root language wins over any nested package.json, so this returns a
        single-element [winner_language] and never surfaces a spurious
        multi-language gate for what workspace detection already resolved.
      * When no manifest matched (rule 11 fired), the list carries the
        extension-frequency best guess as a single element, or [] when the
        guess was "unknown".
    """
    tree: list[str] = payload["tree"]  # validated non-empty by _winner()

    workspace_signal = payload.get("workspace_signal")
    if isinstance(workspace_signal, str) and workspace_signal in _WORKSPACE_SIGNAL_LANGUAGE:
        return [winner["language"]]

    ranked = _ranked_manifests(tree)
    langs: list[str] = []
    for _depth, _rank, _path, result in ranked["deciding"] + ranked["other"]:
        if result["language"] not in langs:
            langs.append(result["language"])

    if langs:
        no_root_manifest = ranked["deciding"][0][0] > 0
        source = winner["source_language"]
        if no_root_manifest and source != "unknown" and source not in langs:
            langs.append(source)
        return langs

    # No manifest matched — the winner came from the extension-frequency
    # fallback (rule 11). Carry its best guess, or [] when it was "unknown".
    fallback_language = winner["language"]
    return [] if fallback_language == "unknown" else [fallback_language]


def detect(payload: dict[str, Any]) -> dict[str, Any]:
    """Apply the documented rule walk and annotate the full manifest match set.

    Returns the single-winner envelope (language/confidence/detection_source/
    fallback_to_extension_frequency) plus source_language, the
    extension-frequency answer, and detected_languages[] (the ordered,
    deduplicated set of every manifest-level match), so a caller can both
    auto-pick and gate multi-language disambiguation off one JSON shape.
    """
    winner = _winner(payload)
    winner["source_language"] = _frequency_fallback(payload["tree"])["language"]
    winner["detected_languages"] = _detected_languages(payload, winner)
    return winner


def _winner(payload: dict[str, Any]) -> dict[str, Any]:
    """Apply the documented rule walk. Always returns a recommendation."""
    tree = payload.get("tree")
    if not isinstance(tree, list):
        _die("payload.tree must be an array of repo-relative file paths")
    if len(tree) == 0:
        _die("payload.tree must be non-empty")

    # Rule 0 — workspace precedence. A non-JS workspace root (from
    # skf-detect-workspaces.manifest_kind) wins over any nested package.json +
    # tsconfig.json, which would otherwise be misread as a typescript root.
    workspace_signal = payload.get("workspace_signal")
    if isinstance(workspace_signal, str) and workspace_signal in _WORKSPACE_SIGNAL_LANGUAGE:
        return {
            "language": _WORKSPACE_SIGNAL_LANGUAGE[workspace_signal],
            "confidence": "high",
            "detection_source": f"workspace manifest_kind={workspace_signal} (root manifest wins over nested package.json)",
            "fallback_to_extension_frequency": False,
        }

    # Rules 1-10: the manifest table, over the manifests nearest the
    # tree's root (the non-core folders left out unless nothing else holds
    # a manifest): the first ranked manifest decides.
    deciding = _ranked_manifests(tree)["deciding"]
    if deciding:
        depth, _rank, path, result = deciding[0]
        if depth > 0:
            # No manifest at the root: one below it is a guess about the
            # whole tree, never a high-confidence answer.
            result = {
                "language": result["language"],
                "confidence": "medium",
                "detection_source": f"{result['detection_source']} at {path} (no manifest at the tree's root)",
            }
        return {**result, "fallback_to_extension_frequency": False}

    # Rule 11: extension-frequency fallback
    return _frequency_fallback(tree)


# --------------------------------------------------------------------------
# scope-patterns: a brief's include and exclude patterns
# --------------------------------------------------------------------------

# Per language: the extensions an include lists, the conventional source
# folders in the order they are tried (None: the whole tree, as Go keeps its
# packages in the module's own folders; a leading `**/` matches the folder at
# any depth) and the exclude globs, where `{ext}` stands for each included
# extension. `unknown` has no extension: it matches every file.
_SCOPE_RULES: dict[str, tuple[tuple[str, ...], tuple[str, ...] | None, tuple[str, ...]]] = {
    "typescript": ((".ts", ".tsx"), ("src", "lib"), ("**/*.test{ext}", "**/*.spec{ext}", "**/node_modules/**")),
    "javascript": ((".js", ".jsx", ".mjs", ".cjs"), ("src", "lib"),
                   ("**/*.test{ext}", "**/*.spec{ext}", "**/node_modules/**")),
    "python": ((".py",), ("src",), ("**/*_test.py", "**/test_*.py", "**/tests/**")),
    "rust": ((".rs",), ("src",), ("**/tests/**", "**/benches/**")),
    "go": ((".go",), None, ("**/*_test.go", "**/vendor/**")),
    "java": ((".java",), ("src/main/java", "**/src/main/java"), ("**/src/test/**",)),
    "kotlin": ((".kt",), ("src/main/kotlin", "**/src/main/kotlin"), ("**/src/test/**",)),
    "swift": ((".swift",), ("Sources",), ("**/Tests/**",)),
    "csharp": ((".cs",), ("src",), ("**/bin/**", "**/obj/**", "**/*Tests/**")),
    "ruby": ((".rb",), ("lib",), ("**/spec/**", "**/test/**")),
    "php": ((".php",), ("src", "lib"), ("**/tests/**", "**/vendor/**")),
    "unknown": ((), (), ("**/test/**", "**/tests/**")),
}


def _depth_below(parts: list[str], folder: str) -> int:
    """How many of a file's folder segments reach down to `folder` (whose
    leading `**/` matches it at any depth), or 0 when the file is not below
    it. Only those segments are judged core: a Java package path below
    src/main/java/ (com/example/, org/.../samples/) is the project's own."""
    segs = folder.split("/")
    folders = parts[:-1]
    if segs[0] != "**":
        return len(segs) if folders[:len(segs)] == segs and _is_core(segs) else 0
    tail = segs[1:]
    for i in range(len(folders) - len(tail) + 1):
        if folders[i:i + len(tail)] == tail and _is_core(folders[:i + len(tail)]):
            return i + len(tail)
    return 0


# Folders that hold a copy of someone else's code: a manifest there is no
# package of the repository's own (scope_patterns' merged-monorepo check).
_VENDORED_SEGMENTS = frozenset({"vendor", "vendored", "third_party", "third-party", "thirdparty"})


def _leaves_out_a_package(paths: list[list[str]], files: list[list[str]], folders: list[str]) -> bool:
    """Whether a package below the root (a core folder, not a vendored copy,
    that holds a manifest) holds files of the language that none of
    `folders` covers, in a folder of its own that is core: a monorepo merged
    into one skill, whose root src/ or lib/ is one package among its members
    (aws-sdk-js-v3's lib/ beside clients/ and packages/)."""
    packages = {tuple(parts[:-1]) for parts in paths
                if len(parts) > 1 and _rule_of(parts[-1]) is not None and _is_core(parts[:-1])
                and not any(seg.lower() in _VENDORED_SEGMENTS for seg in parts[:-1])}
    for parts in files:
        if any(_depth_below(parts, folder) for folder in folders):
            continue
        below = parts[:-1]
        if any(tuple(below[:len(pkg)]) == pkg and _is_core(below[:len(pkg) + 1]) for pkg in packages):
            return True
    return False


def scope_patterns(tree: list[str], language: str) -> dict[str, Any]:
    """A brief's include and exclude patterns for `language` from the file
    list alone (see the module docstring)."""
    exts, conventional, excludes = _SCOPE_RULES[language]
    root = _tree_root(tree)
    prefix = "".join(f"{seg}/" for seg in root)
    paths = [parts for parts in (_parts(p)[len(root):] for p in tree) if parts]
    files = [parts for parts in paths if not exts or _extension(parts[-1]) in exts]
    sources = [parts for parts in files if _is_core(parts[:-1])]
    folders: list[str] = []
    merged = False  # a source folder held files but left a package's out
    for folder in conventional or ():
        if merged and not folder.startswith("**/"):
            continue
        if any(_depth_below(parts, folder) for parts in files):
            if not _leaves_out_a_package(paths, files, [folder]):
                folders = [folder]
                break
            merged = True
    if not folders and not merged and language == "python":
        packages = sorted({parts[0] for parts in sources if len(parts) == 2 and parts[1] == "__init__.py"})
        if packages and not _leaves_out_a_package(paths, files, packages):
            folders = packages
    left_out: list[str] = []
    if not folders:
        left_out = sorted({parts[0] for parts in files if len(parts) > 1 and not _is_core(parts[:1])})
    chosen = ([parts for parts in files if any(_depth_below(parts, f) for f in folders)] if folders
              else sources)
    held = [ext for ext in exts if any(_extension(parts[-1]) == ext for parts in chosen)] or list(exts)
    names = [f"*{ext}" for ext in held] or ["*"]
    bases = [f"{prefix}{folder}/" for folder in folders] or [prefix]
    exclude: list[str] = []
    for glob in excludes:
        for ext in held if "{ext}" in glob else [""]:
            if glob.replace("{ext}", ext) not in exclude:
                exclude.append(glob.replace("{ext}", ext))
    return {
        "language": language,
        "source_folders": [base.rstrip("/") or "." for base in bases],
        "include": [f"{base}**/{name}" for base in bases for name in names],
        "exclude": exclude + [f"{prefix}{folder}/**" for folder in left_out],
    }


def _scope_patterns_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="skf-detect-language.py scope-patterns",
        description="Print a brief's scope.include and scope.exclude for one language from a file list.",
    )
    parser.add_argument("--tree-file", required=True,
                        help="the repository's file list, as the detector's --tree-file reads it; - reads stdin")
    parser.add_argument("--language", required=True, choices=sorted(_SCOPE_RULES),
                        help="the language the skill documents: a value the detector's `language` takes")
    args = parser.parse_args(argv)
    try:
        tree = read_tree_file(args.tree_file)[0]
    except TreeListingError as e:
        _die(str(e))
    json.dump(scope_patterns(tree, args.language), sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


# --------------------------------------------------------------------------
# --tree-file listings
# --------------------------------------------------------------------------


class TreeListingError(ValueError):
    """A --tree-file listing that cannot be read, holds no path or reports a failure."""


def parse_tree_listing(text: str, source: str) -> tuple[list[str], bool]:
    """(the file paths, whether the listing was cut short) of a --tree-file
    listing: JSON, or one path per line, after a byte order mark (Windows
    PowerShell writes one into a pipe). Only a JSON listing can say it was
    cut short (a GitHub tree's `truncated`). `source` says where the
    listing came from in an error. Raises TreeListingError, also for a
    listing that holds no path (`[]`, or a tree with no file)."""
    stripped = text.lstrip("﻿").strip()
    if not stripped:
        raise TreeListingError(f"the tree listing {source} is empty; the command that wrote it may have failed")
    truncated = False
    if not JSON_LISTING_RE.match(stripped):
        paths = []
        for line in stripped.splitlines():
            path = line.strip().removeprefix("./")
            if path:
                paths.append(path)
    else:
        try:
            data = json.loads(stripped)
        except json.JSONDecodeError as e:
            raise TreeListingError(f"the tree listing {source} is not valid JSON: {e}") from e
        entries = data
        if isinstance(data, dict):
            status = data.get("status")
            if status is not None and status != "ok":
                raise TreeListingError(
                    f"the tree listing {source} reports a failure ({status}): {data.get('message') or 'no message'}")
            entries, truncated = data.get("tree"), data.get("truncated") is True
        if not isinstance(entries, list):
            raise TreeListingError(f"the tree listing {source} holds no list of paths (a `tree` list, or a JSON list)")
        paths = []
        for entry in entries:
            if isinstance(entry, str):
                paths.append(entry)
            elif isinstance(entry, dict) and isinstance(entry.get("path"), str) and entry.get("type", "blob") == "blob":
                paths.append(entry["path"])
    if not paths:
        raise TreeListingError(f"the tree listing {source} holds no file path; the command that wrote it may have failed")
    return paths, truncated


def read_tree_file(value: str) -> tuple[list[str], bool]:
    """parse_tree_listing() of the file `value` names, or of stdin for `-`
    (a caller reconfigures stdin to UTF-8 first). Raises TreeListingError."""
    if value == "-":
        return parse_tree_listing(sys.stdin.read(), "on stdin")
    try:
        with open(value, encoding="utf-8-sig") as fh:
            text = fh.read()
    except (OSError, UnicodeDecodeError) as e:
        raise TreeListingError(f"cannot read --tree-file {value}: {getattr(e, 'strerror', None) or e}") from e
    return parse_tree_listing(text, f"in {value}")


def _parse_argv(argv: list[str]) -> dict:
    parser = argparse.ArgumentParser(
        description="Detect primary language from a flat repo file tree by walking the documented rule table.",
    )
    parser.add_argument("--json", help="JSON payload (alternative to stdin)")
    parser.add_argument(
        "--tree-file",
        help="the repository's file list: JSON (a `tree` list, or a list) or one path per line; - reads stdin. "
             "With --tree-file <file>, stdin is not read: pass the other keys with --workspace-signal or --json",
    )
    parser.add_argument(
        "--workspace-signal",
        help="the payload's workspace_signal: the manifest_kind skf-detect-workspaces.py returns",
    )
    args = parser.parse_args(argv)
    if args.tree_file is not None:
        # The listing is the tree; stdin is never read for the payload here.
        payload = _load_payload(args.json) if args.json is not None else {}
        if "tree" in payload:
            _die("pass the tree once: in the payload or with --tree-file, not both")
        try:
            payload["tree"] = read_tree_file(args.tree_file)[0]
        except TreeListingError as e:
            _die(str(e))
    else:
        payload = _load_payload(args.json if args.json is not None else sys.stdin.read())
    if args.workspace_signal is not None:
        if "workspace_signal" in payload:
            _die("pass workspace_signal once: in the payload or with --workspace-signal, not both")
        payload["workspace_signal"] = args.workspace_signal
    return payload


def _load_payload(raw: str) -> dict:
    if not raw or not raw.strip():
        _die("empty input (expected JSON payload on stdin or via --json)")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        _die(f"invalid JSON input: {e}")
    if not isinstance(payload, dict):
        _die("payload must be a JSON object")
    return payload


def _force_utf8(*streams) -> None:
    """Reconfigure JSON-carrying streams to UTF-8 (issue #465).

    A default Windows console decodes stdio as cp1252, which cannot carry
    non-ASCII JSON (ensure_ascii=False output, raw UTF-8 input). Preserves
    each stream's existing error handler — reconfigure(encoding=...) alone
    would reset it to 'strict', downgrading e.g. an already-UTF-8 stderr on
    Linux. For stdin this must run before the first read. Skips in-process
    test doubles without reconfigure().
    """
    for stream in streams:
        if hasattr(stream, "reconfigure"):
            errors = getattr(stream, "errors", None)
            if errors is None:
                stream.reconfigure(encoding="utf-8")
            else:
                stream.reconfigure(encoding="utf-8", errors=errors)


def main(argv: list[str]) -> int:
    _force_utf8(sys.stdin, sys.stdout)
    if argv[:1] == ["scope-patterns"]:
        return _scope_patterns_main(argv[1:])
    payload = _parse_argv(argv)
    result = detect(payload)
    json.dump(result, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
