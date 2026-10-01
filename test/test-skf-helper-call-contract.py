#!/usr/bin/env python3
"""Every call a step file makes to a shared helper must fit the helper's CLI.

Step prose is not executed by any test. A call such as
`python3 {updateActiveSymlinkHelper} flip-link --link ...` reads fine and
fails with argparse's exit 2 the first time a workflow runs it. This test
finds the helper calls in src/**/*.md and checks each one against the
helper itself:

- A helper built on argparse subcommands: the call's arguments run through
  the helper's own parser, so a subcommand it does not have, a flag it does
  not know (spelled in full: abbreviations fail), a missing required flag or
  a stray argument fails the test.
- A flag-only helper listed in FLAG_ONLY (argparse, no subcommands, such as
  skf-render-metadata-stats.py and skf-names-present.py): the same check,
  so a missing positional or required flag, an unknown flag or a value
  outside a flag's choices fails the test.
- skf-manifest-ops.py reads sys.argv by hand, the skills folder first: the
  call must name, second, a command its main() dispatches, with at least as
  many arguments as main() requires for it.

What counts as a call. Inside fenced code or an inline code span, in the
body of a src/**/*.md file (never the YAML frontmatter, whose comments use
shorthand such as `{manifestOpsHelper} read`): a helper placeholder followed
by at least one argument. A placeholder alone (`{atomicWriteHelper}`) names
the helper and is not a call. Fenced lines continued with a backslash are
joined, and a call ends at the first shell operator (`|`, `&&`, `;`, `>`,
`<`, `)` ...).

How a placeholder maps to a script. The file's own frontmatter binds it: a
`<stem>ProbeOrder` list binds `{<stem>Helper}` and `{<stem>}` to the script
its src/ entry names, and a `<name>: 'scripts/<x>.py'` scalar binds `{<name>}`
to that script in the skill's folder. A SKILL.md that resolves a helper once
for every stage binds it in its body: a line that names `{<name>}`, then
`←`, then the helper's `{project-root}/src/...` path binds `{<name>}` to that
script. A reference file that binds nothing (a protocol a step loads, or a
stage of a skill whose SKILL.md resolves the helper) uses the one binding
the other files agree on; a `{...Helper}` in a call that no file binds, or
that files bind to two scripts, fails the test.

How the arguments are read. `{...}` and `<...>` placeholders become opaque
values that satisfy any type or choices, except that a `{a|b}` placeholder
given to an option with choices must list only real choices. A `[--flag
...]` synopsis group is checked twice: dropped (the required arguments must
still be there) and kept (every flag inside must exist).
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import functools
import importlib.util
import io
import re
import runpy
import shlex
import sys
import tempfile
from pathlib import Path
from typing import NamedTuple

import pytest

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
MANIFEST_OPS = SRC / "shared" / "scripts" / "skf-manifest-ops.py"
# Helpers without subcommands whose calls are checked all the same. A helper
# joins only when every prose call to it fits: a flag-only helper that reads
# sys.argv by hand (skf-detect-docs.py, skf-rebuild-managed-sections.py)
# cannot be parsed this way.
FLAG_ONLY = frozenset({
    SRC / "shared" / "scripts" / "skf-render-metadata-stats.py",
    SRC / "shared" / "scripts" / "skf-names-present.py",
})

FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.S)
FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")
INLINE_RE = re.compile(r"(`+)(.+?)\1")
PLACEHOLDER_RE = re.compile(r"\{([A-Za-z][A-Za-z0-9]*)\}")
PROBE_KEY_RE = re.compile(r"^([A-Za-z]+)ProbeOrder:\s*$")
PROBE_ITEM_RE = re.compile(r"^\s+-\s*'([^']+)'\s*$")
SCRIPT_SCALAR_RE = re.compile(r"^([A-Za-z][A-Za-z0-9]*):\s*'(scripts/[^']+\.py)'\s*$", re.M)
ACTIVATION_BIND_RE = re.compile(r"`\{([A-Za-z][A-Za-z0-9]*)\}` ←([^\n]*)")
SRC_SCRIPT_RE = re.compile(r"`\{project-root\}/(src/[^`\s]+\.py)`")
OPAQUE_RE = re.compile(r"\{[^{}\n]*\}|<[A-Za-z][^<>\n]*>")
ALTERNATIVES_RE = re.compile(r"[\w.-]+(?:\|[\w.-]+)+")
REDIRECT_FD_RE = re.compile(r"(?<!\S)\d+(?=[<>])")
SYNOPSIS_RE = re.compile(r"(?<!\S)\[(--?[A-Za-z][^\[\]]*)\](?!\S)")
SHELL_OPERATORS = frozenset("|&;<>()")
OPAQUE = "\ue000"  # brackets a word that stands for a placeholder value
ALT = "\ue001"  # the | of a {a|b} placeholder


class Call(NamedTuple):
    rel: str
    line: int
    name: str
    script: Path
    rest: str  # the text after the placeholder


def _uses_subcommands(script: Path) -> bool:
    return "add_subparsers(" in script.read_text(encoding="utf-8")


def _checked(script: Path) -> bool:
    return script == MANIFEST_OPS or script in FLAG_ONLY or _uses_subcommands(script)


# --------------------------------------------------------------------------
# Extraction
# --------------------------------------------------------------------------


def _split_frontmatter(text: str) -> tuple[str, str, int]:
    m = FRONTMATTER_RE.match(text)
    if not m:
        return "", text, 0
    return m.group(1), text[m.end():], text[:m.end()].count("\n")


def _bindings(rel: str, frontmatter: str) -> dict[str, Path]:
    """Placeholder name -> script, from one file's frontmatter."""
    out: dict[str, Path] = {}
    lines = frontmatter.splitlines()
    for i, line in enumerate(lines):
        m = PROBE_KEY_RE.match(line)
        if not m:
            continue
        items = []
        for nxt in lines[i + 1:]:
            item = PROBE_ITEM_RE.match(nxt)
            if not item:
                break
            items.append(item.group(1))
        src = [p for p in items if p.startswith("{project-root}/src/") and p.endswith(".py")]
        if src:
            script = REPO / src[0][len("{project-root}/"):]
            out[m.group(1)] = script
            out[m.group(1) + "Helper"] = script
    skill_dir = REPO.joinpath(*Path(rel).parts[:2])
    for name, path in SCRIPT_SCALAR_RE.findall(frontmatter):
        out[name] = skill_dir / path
    return out


def _activation_bindings(body: str) -> dict[str, Path]:
    """Placeholder name -> script, from the SKILL.md lines that resolve a helper for every stage."""
    out: dict[str, Path] = {}
    for name, rest in ACTIVATION_BIND_RE.findall(body):
        src = SRC_SCRIPT_RE.search(rest)
        if src:
            out[name] = REPO / src.group(1)
    return out


def _code(body: str, first_line: int):
    """Yield (line, text) for each fenced logical line and inline code span."""
    fence = None
    joined, start = "", None
    for number, line in enumerate(body.split("\n"), start=first_line + 1):
        m = FENCE_RE.match(line)
        if fence is not None:
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence):
                fence, joined, start = None, "", None
                continue
            start = start or number
            if line.rstrip().endswith("\\"):
                joined += line.rstrip()[:-1] + " "
                continue
            yield start, joined + line
            joined, start = "", None
        elif m:
            fence = m.group(1)
        else:
            for span in INLINE_RE.finditer(line):
                yield number, span.group(2)


def _collect() -> tuple[list[Call], list[str]]:
    found = []  # (rel, line, name, rest)
    local: dict[str, dict[str, Path]] = {}
    for md in sorted(SRC.rglob("*.md")):
        rel = md.relative_to(REPO).as_posix()
        frontmatter, body, first = _split_frontmatter(md.read_text(encoding="utf-8"))
        local[rel] = _bindings(rel, frontmatter)
        if md.name == "SKILL.md":
            local[rel].update(_activation_bindings(body))
        for line, text in _code(body, first):
            for m in PLACEHOLDER_RE.finditer(text):
                rest = text[m.end():]
                if rest[:1] in (" ", "\t") and rest.strip():
                    found.append((rel, line, m.group(1), rest))
    agreed: dict[str, set[Path]] = {}
    for binds in local.values():
        for name, script in binds.items():
            agreed.setdefault(name, set()).add(script)
    calls, unbound = [], []
    for rel, line, name, rest in found:
        script = local[rel].get(name)
        if script is None:
            choices = agreed.get(name, set())
            if not choices and not name.endswith("Helper"):
                continue  # not a helper: {skills_output_folder} and the like
            if len(choices) != 1:
                unbound.append(f"{rel}:{line} {{{name}}} -> {sorted(p.name for p in choices)}")
                continue
            script = next(iter(choices))
        if script.suffix == ".py" and _checked(script):
            calls.append(Call(rel, line, name, script, rest))
    return calls, unbound


CALLS, UNBOUND = _collect()


# --------------------------------------------------------------------------
# Checking
# --------------------------------------------------------------------------


class _Captured(Exception):
    def __init__(self, parser: argparse.ArgumentParser):
        super().__init__()
        self.parser = parser


def _capture(self, *args, **kwargs):
    raise _Captured(self)


@functools.lru_cache(maxsize=None)
def _parser(script: Path) -> argparse.ArgumentParser:
    """The helper's own parser, relaxed for placeholders."""
    name = "skf_call_contract_" + re.sub(r"\W", "_", script.stem)
    spec = importlib.util.spec_from_file_location(name, script)
    module = importlib.util.module_from_spec(spec)
    with tempfile.TemporaryDirectory() as cwd, pytest.MonkeyPatch.context() as mp:
        mp.setitem(sys.modules, name, module)  # dataclasses look their module up
        spec.loader.exec_module(module)
        if callable(getattr(module, "_build_parser", None)):
            return _relaxed(module._build_parser())
        # Run main() as the script would run, and stop it at parse_args.
        mp.setattr(argparse.ArgumentParser, "parse_args", _capture)
        mp.setattr(argparse.ArgumentParser, "parse_known_args", _capture)
        mp.setattr(sys, "argv", [str(script)])
        mp.setattr(sys, "stdin", io.StringIO(""))
        mp.chdir(cwd)
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                runpy.run_path(str(script), run_name="__main__")
        except _Captured as caught:
            return _relaxed(caught.parser)
    raise AssertionError(f"{script.name}: main() never reached parse_args")


class _AnyChoice(list):
    """Choices that also accept an opaque placeholder value."""

    def __contains__(self, value):
        if isinstance(value, str) and len(value) >= 2 and value[0] == value[-1] == OPAQUE:
            inner = value[1:-1]
            if inner:  # {a|b}: every alternative must be a real choice
                return all(list.__contains__(self, alt) for alt in inner.split(ALT))
            return True
        return list.__contains__(self, value)


def _relaxed(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.allow_abbrev = False  # a step spells every flag in full
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for sub in {id(p): p for p in action.choices.values()}.values():
                _relaxed(sub)
            continue
        if action.type is not None:
            real = action.type

            def opaque_or_real(value, real=real):
                return value if OPAQUE in value else real(value)

            opaque_or_real.__name__ = getattr(real, "__name__", "type")
            action.type = opaque_or_real
        if action.choices is not None:
            action.choices = _AnyChoice(action.choices)
    return parser


def _opaque(match: re.Match) -> str:
    inner = match.group(0)[1:-1]
    if ALTERNATIVES_RE.fullmatch(inner):  # {a|b}: keep the alternatives
        return OPAQUE + inner.replace("|", ALT) + OPAQUE
    return OPAQUE + OPAQUE


def _words(rest: str) -> list[str] | None:
    """Shell words of `rest` up to the first operator; None on bad quoting."""
    s = OPAQUE_RE.sub(_opaque, rest)
    s = REDIRECT_FD_RE.sub("", s)  # `2>/dev/null`: the 2 is not an argument
    lex = shlex.shlex(s, posix=True, punctuation_chars="".join(sorted(SHELL_OPERATORS)))
    lex.whitespace_split = True
    words: list[str] = []
    try:
        for word in lex:
            if set(word) <= SHELL_OPERATORS:
                break
            words.append(word)
    except ValueError:
        return None
    return words


def _parse_error(parser: argparse.ArgumentParser, words: list[str]) -> str | None:
    err = io.StringIO()
    try:
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            parser.parse_args(words)
    except SystemExit as exc:
        if exc.code in (0, None):  # --help
            return None
        lines = err.getvalue().strip().splitlines()
        return lines[-1] if lines else f"exit {exc.code}"
    return None


@functools.lru_cache(maxsize=None)
def manifest_ops_commands() -> dict[str, int]:
    """Command -> the fewest arguments skf-manifest-ops.py's main() accepts for it.

    Read from main()'s `command == "..."` tests and the `len(sys.argv) >= N`
    test beside each one; argv[0] is the script, so N - 1 arguments.
    """
    tree = ast.parse(MANIFEST_OPS.read_text(encoding="utf-8"))
    main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
    out: dict[str, int] = {}
    for node in ast.walk(main):
        tests = node.values if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.And) else [node]
        command, least = None, 2
        for test in tests:
            if not isinstance(test, ast.Compare) or len(test.comparators) != 1:
                continue
            right = test.comparators[0]
            if (isinstance(test.left, ast.Name) and test.left.id == "command"
                    and isinstance(test.ops[0], ast.Eq) and isinstance(right, ast.Constant)):
                command = right.value
            elif (isinstance(test.left, ast.Call) and getattr(test.left.func, "id", None) == "len"
                  and isinstance(test.ops[0], ast.GtE) and isinstance(right, ast.Constant)):
                least = right.value - 1
        if command is not None:
            out[command] = max(out.get(command, 0), least)
    return out


def call_error(script: Path, rest: str) -> str | None:
    """Why the arguments `rest` do not fit `script`'s CLI, or None."""
    dropped = SYNOPSIS_RE.sub(" ", rest)
    kept = SYNOPSIS_RE.sub(lambda m: " " + m.group(1) + " ", rest)
    variants = [_words(v) for v in dict.fromkeys((dropped, kept))]
    if any(words is None for words in variants):
        return "unbalanced quotes"
    if script == MANIFEST_OPS:
        commands = manifest_ops_commands()
        for words in variants:
            if len(words) < 2 or words[1] not in commands:
                return f"the second argument must be one of {sorted(commands)} (the skills folder comes first)"
            if len(words) < commands[words[1]]:
                return f"`{words[1]}` takes at least {commands[words[1]]} arguments"
        return None
    parser = _parser(script)
    for words in variants:
        error = _parse_error(parser, words)
        if error:
            return error.replace(OPAQUE + OPAQUE, "{…}").replace(OPAQUE, "")
    return None


def _script(name: str) -> Path:
    return SRC / "shared" / "scripts" / name


# --------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------


def test_every_helper_placeholder_is_bound():
    assert not UNBOUND, (
        "bind each placeholder in the file's frontmatter with a <stem>ProbeOrder list; "
        "no single script is bound to it elsewhere:\n" + "\n".join(UNBOUND))


@pytest.mark.parametrize("rel", sorted({c.rel for c in CALLS}))
def test_helper_calls_fit_the_helper_cli(rel):
    failures = []
    for call in CALLS:
        if call.rel != rel:
            continue
        error = call_error(call.script, call.rest)
        if error:
            failures.append(f"{rel}:{call.line} {{{call.name}}}{call.rest.rstrip()[:160]}\n    -> {error}")
    assert not failures, "\n".join(failures)


# One known call per extraction path (fenced, backslash-joined, inline,
# heredoc, a reference file without frontmatter, a shared protocol whose
# helper only its callers bind, a helper a SKILL.md resolves for its stages,
# the hand-parsed helper), so a change to the extractor cannot silently check
# nothing.
MUST_FIND = [
    ("src/skf-rename-skill/references/execute.md", "skf-atomic-write.py", "flip-link"),
    ("src/skf-rename-skill/references/execute.md", "skf-atomic-write.py", "write"),
    ("src/skf-rename-skill/references/execute.md", "skf-manifest-ops.py", "rename"),
    ("src/skf-create-skill/references/report.md", "skf-atomic-write.py", "write"),
    ("src/skf-create-skill/references/authoritative-files-protocol.md", "skf-write-skill-brief.py", "amend"),
    ("src/shared/references/description-guard-protocol.md", "skf-description-guard.py", "capture"),
    ("src/skf-quick-skill/references/finalize.md", "skf-atomic-write.py", "flip-link"),
    ("src/skf-create-stack-skill/references/generate-output.md", "skf-atomic-write.py", "commit-dir"),
    ("src/skf-create-stack-skill/references/generate-output.md", "skf-verify-provenance-completeness.py", "verify"),
    ("src/skf-create-stack-skill/references/generate-output.md", "skf-verify-provenance-completeness.py", "fix"),
    ("src/skf-update-skill/references/write.md", "skf-update-active-symlink.py", "update"),
    ("src/skf-update-skill/references/write.md", "skf-update-active-symlink.py", "verify"),
    ("src/skf-drop-skill/references/execute.md", "skf-update-active-symlink.py", "update"),
    ("src/skf-drop-skill/references/report.md", "skf-manifest-ops.py", "affected-versions"),
    # A helper the SKILL.md resolves at activation, and a stage that calls it.
    ("src/skf-brief-skill/SKILL.md", "skf-emit-brief-result-envelope.py", "emit"),
    ("src/skf-brief-skill/references/write-brief.md", "skf-emit-brief-result-envelope.py", "emit"),
]


def _command_word(call: Call) -> str | None:
    words = _words(call.rest) or []
    index = 1 if call.script == MANIFEST_OPS else 0
    return words[index] if len(words) > index else None


@pytest.mark.parametrize("rel,script,command", MUST_FIND)
def test_the_extractor_finds_known_calls(rel, script, command):
    found = [_command_word(c) for c in CALLS if c.rel == rel and c.script.name == script]
    assert command in found, f"{rel}: the {script} calls found start with {found}"


def test_a_skill_md_binds_the_helper_it_resolves_for_every_stage():
    """skf-brief-skill's stages call {emitBriefEnvelopeHelper}, which only its SKILL.md resolves."""
    _, body, _ = _split_frontmatter((SRC / "skf-brief-skill" / "SKILL.md").read_text(encoding="utf-8"))
    assert _activation_bindings(body)["emitBriefEnvelopeHelper"] == _script("skf-emit-brief-result-envelope.py")
    # A line that resolves a setting, not a script, binds nothing.
    assert _activation_bindings("`{onCompleteCommand}` ← `workflow.on_complete` if non-empty") == {}


# Every step that runs a flag-only helper on a provenance map, so a call
# that drops the map, misspells a flag or names no real shape fails.
FLAG_ONLY_MUST_FIND = [
    ("src/skf-create-skill/references/compile.md", "skf-render-metadata-stats.py", ()),
    ("src/skf-create-skill/references/validate.md", "skf-render-metadata-stats.py", ("--check",)),
    ("src/skf-update-skill/references/write.md", "skf-render-metadata-stats.py", ("--shape", "reference-app")),
    ("src/skf-create-stack-skill/references/parallel-extract.md", "skf-render-metadata-stats.py",
     ("--shape", "stack")),
    ("src/skf-create-stack-skill/references/generate-output.md", "skf-render-metadata-stats.py",
     ("--shape", "stack")),
    ("src/skf-create-stack-skill/references/generate-output.md", "skf-names-present.py",
     ("--provenance", "--skill-dir")),
]


@pytest.mark.parametrize("rel,script,flags", FLAG_ONLY_MUST_FIND)
def test_the_extractor_finds_flag_only_calls(rel, script, flags):
    assert _script(script) in FLAG_ONLY
    runs = [words for words in (_words(c.rest) or [] for c in CALLS if c.rel == rel and c.script.name == script)
            if words and not {"-h", "--help"} & set(words)]
    assert runs, f"{rel}: no {script} call on a provenance map found"
    assert any(all(flag in words for flag in flags) for words in runs), (
        f"{rel}: no {script} call passes {flags}: {runs}")


def test_the_extractor_sees_many_calls():
    # The floor sits above the count of fenced calls alone, so it also fails
    # when the inline scan stops.
    assert len(CALLS) >= 90, f"only {len(CALLS)} calls found; the extractor has stopped matching"
    assert sum(c.script == MANIFEST_OPS for c in CALLS) >= 8


def test_manifest_ops_commands_are_read_from_its_main():
    commands = manifest_ops_commands()
    expected = {"read": 2, "get": 3, "set": 4, "remove": 3, "deprecate": 3, "rename": 4, "affected-versions": 3}
    for command, least in expected.items():
        assert commands.get(command) == least, (command, commands)


@pytest.mark.parametrize("script,rest", [
    # The two rename-skill step 2 calls and the create-skill prose this test was written for.
    ("skf-update-active-symlink.py", " flip-link --link {new_skill_group}/active --target {target_version}"),
    ("skf-atomic-write.py", " write {skills_output_folder}/.export-manifest.json"),
    ("skf-atomic-write.py", " write"),
    # A missing required flag, an unknown flag, an abbreviation, a misspelling, a stray argument.
    ("skf-update-active-symlink.py", " update --skill-group {new_skill_group}"),
    ("skf-atomic-write.py", " flip-link --link {x}/active --target {v} --bogus {y}"),
    ("skf-atomic-write.py", " write --targ {x}"),
    ("skf-atomic-write.py", " write --tagret {x}"),
    ("skf-atomic-write.py", " write --target {x} {y}"),
    # A synopsis group that holds a misspelled flag, or the only required flag.
    ("skf-forge-tier-rw.py", ' clean-stale --target "{t}" [--qmd-live-name "{n}"]'),
    ("skf-forge-tier-rw.py", " clean-stale [--target {t}]"),
    # A choice the option does not offer, spelled out or inside a {a|b} placeholder.
    ("skf-emit-brief-result-envelope.py", " emit --target stdlog"),
    ("skf-emit-brief-result-envelope.py", " emit --target {stdout|stdlog}"),
    # skf-manifest-ops.py: the folder left out, an unknown command, a missing argument.
    ("skf-manifest-ops.py", " rename {old_name} {new_name}"),
    ("skf-manifest-ops.py", " {skills_output_folder} move {old_name} {new_name}"),
    ("skf-manifest-ops.py", " {skills_output_folder} rename {old_name}"),
    # The flag-only stats helper: the map left out, a shape it lacks (spelled out
    # or inside a {a|b} placeholder), a misspelled flag, a stray argument.
    ("skf-render-metadata-stats.py", " --shape stack"),
    ("skf-render-metadata-stats.py", " {labels_json} --shape bundle"),
    ("skf-render-metadata-stats.py", " {labels_json} --shape {stack|bundle}"),
    ("skf-render-metadata-stats.py", " {p}/provenance-map.json --chek {p}/metadata.json"),
    ("skf-render-metadata-stats.py", " {p}/provenance-map.json {p}/metadata.json"),
    # The names helper: the package left out, a map given without its flag,
    # an abbreviated flag.
    ("skf-names-present.py", " --provenance {forge_version}/provenance-map.json"),
    ("skf-names-present.py", " {forge_version}/provenance-map.json --skill-dir {skill_staging}"),
    ("skf-names-present.py", " --provenance {p}/provenance-map.json --skill-dir {s} --drop"),
])
def test_the_checker_rejects_broken_calls(script, rest):
    assert call_error(_script(script), rest), f"{script}{rest} must not fit the CLI"


@pytest.mark.parametrize("script,rest", [
    ("skf-update-active-symlink.py", ' update --skill-group "{g}" --version "{v}"'),
    ("skf-atomic-write.py", ' write --target "{skills_output_folder}/.export-manifest.json" <<\'SKF_MANIFEST_BACKUP\''),
    ("skf-atomic-write.py", ' write --target "{x}" 2>/dev/null'),
    ("skf-atomic-write.py", " flip-link --link {x}/active --target {v} && echo ok"),
    ("skf-atomic-write.py", " flip-link --link {x}/active --target <version>"),
    ("skf-forge-tier-rw.py", ' clean-stale --target "{t}" [--qmd-live-names "{n}"] [--prune-missing-ccc-paths]'),
    ("skf-emit-brief-result-envelope.py", " emit --target {stdout|stderr}"),
    ("skf-manifest-ops.py", ' "{skills_output_folder}" rename {new_name} {old_name}'),
    ("skf-manifest-ops.py", " {skills_output_folder} read"),
    ("skf-render-metadata-stats.py", " {forge_data_folder}/{project_name}-stack.skf-labels.json --shape stack"),
    ("skf-render-metadata-stats.py",
     " <staging-skill-dir>/provenance-map.json --check <staging-skill-dir>/metadata.json"),
    ("skf-render-metadata-stats.py", " {p}/provenance-map.json --shape {library|reference-app}"),
    ("skf-render-metadata-stats.py", " --help"),
    ("skf-names-present.py", " --provenance {forge_version}/provenance-map.json --skill-dir {skill_staging}"),
    ("skf-names-present.py", " --provenance {p}/provenance-map.json --skill-dir {s} --drop-absent"),
])
def test_the_checker_accepts_valid_calls(script, rest):
    assert call_error(_script(script), rest) is None
