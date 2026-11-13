#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""Deterministic parse + validation of a forger pipeline invocation.

Pipeline Mode (references/pipeline-mode.md §1-2) turns a raw code sequence
(`BS CS[cocoindex] TS[min:80] EX`, `AN -> CS -> TS -> EX`, or an alias such as
`forge-quick cognee`) into a normalized run plan and a list of sequence
anti-patterns.
Splitting the tokens, expanding aliases against a fixed table, classifying each
bracket argument, and detecting anti-patterns (duplicates, ordering, missing
prerequisites) is set/order plumbing with exactly one correct answer per input —
so it runs here, not in the prompt. The prompt keeps only the judgment the
script cannot make: interpreting the user's freeform request into a code
sequence, and deciding whether to proceed past a warned anti-pattern.

The forger passes the user's whole invocation, so an alias may carry its
arguments after it (`forge-auto <repo-or-doc-url>`, `forge <repo-url-or-path>
<skill-name>`, `forge-quick <package-or-url>`, `maintain <skill>`) and
`--pin <version>` may appear anywhere. The alias expands, and its arguments
bind, in order, to the inputs of the alias's first workflow (ALIAS_INPUTS);
`--pin` joins them, as the Pipeline Arguments rule says. An input left
unbound is reported, because that workflow requires it and a pipeline runs
headless. A leading `SF` (one plain token, in any case) may come before an
alias (`SF forge-auto <repo-or-doc-url>`, `SF deepwiki <url>`): the plan is
SF, then the alias's codes, `alias` and `deprecated_alias` are set as for a
leading alias, and the arguments after the alias bind as above, to the
workflow after SF. `SF onboard` is the removed alias, as `onboard` is. A
chain of codes binds no input, so a runnable plan whose first
workflow (past a leading SF) starts from an input that no bracket gives
reports it as `first_input` (FIRST_INPUTS) and stays valid: the forger asks
for it, or halts headless, before any workflow runs. A quoted argument (a
path with a space) stays one token. Codes and the bracket keywords `min` and
`auto` match in any case; a bracket that starts like `min` but is not
`min:<number>` is reported as malformed instead of passing on as a target.

The alias-expansion and anti-pattern tables mirror
`src/shared/references/pipeline-contracts.md` (the human-readable contract);
this script is the executable form the forger consumes.

CLI usage:
  uv run scripts/parse-pipeline.py 'BS CS TS EX'      # positional
  uv run scripts/parse-pipeline.py 'forge-quick cognee'
  uv run scripts/parse-pipeline.py 'forge-quick'      # exit 3: missing_args [target]
  uv run scripts/parse-pipeline.py 'QS TS EX'         # exit 0: first_input, QS's target
  uv run scripts/parse-pipeline.py 'forge-auto https://github.com/o/r --pin 0.2.1'
  uv run scripts/parse-pipeline.py 'SF forge-auto https://github.com/o/r'
  echo 'AN -> CS -> TS -> EX' | uv run scripts/parse-pipeline.py --stdin
  echo 'CS[hono] TS EX' | uv run scripts/parse-pipeline.py --stdin \\
      --forge-data-folder <dir> --skills-output-folder <dir>

Output (stdout, one object):
  {
    "raw": "<input>",
    "alias": "forge" | null,          # set when the input starts with an alias,
                                      # or with SF and an alias
    "deprecated_alias": "deepwiki" | null,
    "removed_alias": "onboard" | null,
    "expanded": ["BS", "CS", "TS", "EX"],   # normalized tokens (post-expansion)
    "plan": [{"code","min","mode","target","skill","description"}, ...],
    "codes": ["BS", "CS", "TS", "EX"],
    "args": {"<input>": "<value>", "pin": "<version>"},  # for the first workflow
    "unknown_codes": [],
    "unexpected_args": [],            # extra alias arguments, unknown flags
    "missing_args": [],               # alias inputs left unbound, e.g. "target"
    "malformed_brackets": [],         # e.g. "TS[min:80%]"
    "anti_patterns": [{"pattern","message","suggestion"}, ...],
    "first_input": null | {"code","input","form","halt_reason"},
    "valid": <bool>                   # runnable: real codes, nothing unknown,
  }                                   # unexpected, missing or malformed, not
                                      # removed

A plan entry's `min`, `mode` and `target` are its bracket values, and its
`skill` and `description` are its code's Capabilities row in SKILL.md
(SKILLS).

`args` holds only what the invocation gave: `project_path` (forge-auto),
`target_repo` and `skill_name` (forge), `target` (forge-quick), `skill_name`
(maintain), and `pin`. `--headless`/`-H` is Ferris's own flag, read at
activation, so it is accepted and not returned.

`first_input` names the input the chain's first workflow lacks (`input`, as
"a target"). `form` is the invocation to parse again with the answer in
place of each `<...>` placeholder (`QS[<target>] TS EX`), or null when no
chain can carry that input: RS and DS need more than one bracket, a BS
outside `forge <repo-url-or-path> <skill-name>` has no bracket for its skill
name, and a bracket that already holds `min:N` or `auto` holds one value.
`halt_reason` is what a headless run halts with (`QS needs a target before
the pipeline can start: give it as QS[<target>]`), or null for a leading CS:
create-skill compiles the only brief, or halts naming the briefs.

The anti-patterns read the order of the codes. Two of them also read the
forge state on disk when the folders are given (`--forge-data-folder`, and
`--skills-output-folder` for the audit check), so a chain whose skill
already has what the pattern misses raises none:

  cs-without-brief  a CS with no BS or AN before it is warned about only
                    when a CS entry's `target` is missing, is not one folder
                    name, or has no `<forge-data-folder>/<target>/skill-brief.yaml`
  us-without-audit  a US with no AS is warned about only when a US entry's
                    `target` is missing, is not one folder name, or names a
                    skill with no audit-skill-result-latest.json beside the
                    test record of its active version, as forge-status.py
                    (beside this script, loaded only for this check) finds
                    them: `skill_entry` gives the active version, and a
                    skill it does not list, or a forge-status.py that does
                    not load, counts as no audit

Without the folders each check keeps its order rule alone.

Exit codes:
  0  parsed, runnable (anti-patterns and a deprecated alias are warnings)
  1  no input provided (usage error)
  2  removed alias (e.g. `onboard`): the forger HALTs
  3  nothing runnable (empty, or an unknown code, an unexpected or missing
     argument or a malformed bracket): the forger names the problem and asks,
     or halts headless, before any workflow runs
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import shlex
import sys
from pathlib import Path

# Shipped scripts are consumer files, not a place for interpreter caches.
sys.dont_write_bytecode = True

# forge-status.py, beside this script: the audit check reads a skill's active version through it.
FORGE_STATUS = Path(__file__).resolve().parent / "forge-status.py"
BRIEF = "skill-brief.yaml"

# Workflow codes that can appear in a pipeline. KI/WS are inline actions, not
# pipeline steps; `campaign` is a standalone workflow, not a pipeline code.
KNOWN_CODES = frozenset(
    {"SF", "AN", "BS", "CS", "QS", "SS", "US", "AS", "VS", "RA", "TS", "EX", "RS", "DS"}
)

# The skill each code runs and its description, as the Capabilities rows in
# the forger's SKILL.md give them (the dash that joins two clauses there
# reads ": " here). Every plan entry carries both: Pipeline Mode reports the
# description and invokes the skill by that exact name.
SKILLS = {
    "SF": ("skf-setup", "Initialize forge environment, detect tools, set tier"),
    "AN": ("skf-analyze-source", "Discover what to skill in a large repo: produces recommended skill briefs"),
    "BS": ("skf-brief-skill", "Design a skill scope through guided discovery"),
    "CS": ("skf-create-skill", "Compile a skill from brief (supports --batch)"),
    "QS": ("skf-quick-skill", "Fast skill from a package name or GitHub URL: no brief needed"),
    "SS": ("skf-create-stack-skill", "Consolidated project stack skill with integration patterns"),
    "US": ("skf-update-skill", "Smart regeneration preserving [MANUAL] sections after source changes"),
    "AS": ("skf-audit-skill", "Drift detection between skill and current source code"),
    "VS": ("skf-verify-stack", "Pre-code stack feasibility verification against architecture and PRD"),
    "RA": ("skf-refine-architecture",
           "Refine an architecture document against generated skills and a Verify Stack report"),
    "TS": ("skf-test-skill", "Cognitive completeness verification: quality gate before export"),
    "EX": ("skf-export-skill", "Validate a skill's package, write its context snippet and update the managed "
                               "section in CLAUDE.md, AGENTS.md or .cursorrules"),
    "RS": ("skf-rename-skill", "Rename a skill across all its versions (transactional)"),
    "DS": ("skf-drop-skill", "Drop a skill: deprecate (soft) or purge (hard)"),
}

# Only these take a `min:N`: AN as the fewest units it must confirm (the
# pipeline gate's --min) and TS as its test threshold (--threshold). CS, AS and
# VS have circuit breakers with no number to set, so on them, as on any other
# code, a `min:N` bracket is ignored (recorded as `min: null`, with a warning).
THRESHOLD_CODES = frozenset({"AN", "TS"})

# Alias table — mirrors pipeline-contracts.md. `forge-auto`'s TS[min:90] gate is
# non-default and is kept in lockstep with init.md §1b's forge-auto → 90 lookup.
ALIASES = {
    "forge-auto": ["AN[auto]", "BS[auto]", "CS", "TS[min:90]", "EX"],
    "forge": ["BS", "CS", "TS", "EX"],
    "forge-quick": ["QS", "TS", "EX"],
    "maintain": ["AS", "US", "TS", "EX"],
}
DEPRECATED_ALIASES = {"deepwiki": "forge-auto"}  # renamed; still expands
REMOVED_ALIASES = {"onboard"}  # no expansion — the forger HALTs

# The arguments each alias takes after it, in order. Each names the input of
# the alias's first workflow that receives it: analyze-source's project_path,
# brief-skill's target_repo and skill_name, quick-skill's target and
# audit-skill's skill_name. Mirrors the alias forms in SKILL.md's Pipelines
# paragraph.
ALIAS_INPUTS = {
    "forge-auto": ("project_path",),
    "forge": ("target_repo", "skill_name"),
    "forge-quick": ("target",),
    "maintain": ("skill_name",),
}

# What a code's workflow starts from at the head of a chain of codes, where no
# alias argument binds it: the `args` keys that give it, the input as the ask
# names it, and the placeholder its bracket takes. A pipeline runs every
# workflow headless, so one left without its input halts at once. SF and SS
# start from none, and the check looks past a leading SF. CS's input is its
# brief: headless, create-skill compiles the only brief or halts naming them,
# so a leading CS is asked for its input but never halted for it.
FIRST_INPUTS = {
    "AN": (("project_path",), "a project path", "<project-path>"),
    "QS": (("target",), "a target", "<target>"),
    "CS": (("skill_name", "brief_path"), "a skill name", "<skill-name>"),
    "TS": (("skill_name",), "a skill name", "<skill-name>"),
    "EX": (("skill_name",), "a skill name", "<skill-name>"),
    "US": (("skill_name",), "a skill name", "<skill-name>"),
    "AS": (("skill_name",), "a skill name", "<skill-name>"),
    "VS": (("architecture_doc_path",), "an architecture document", "<architecture-doc>"),
    "RA": (("architecture_doc_path",), "an architecture document", "<architecture-doc>"),
}
# BS needs a target and a skill name, and a bracket holds one value: only the
# `forge` alias gives it both.
BS_INPUTS = ("target_repo", "skill_name")
FORGE_FORM = "forge <repo-url-or-path> <skill-name>"
# These need more than a bracket can hold (rename-skill a new name, drop-skill
# a version and a drop mode), so they run on their own, outside a chain.
ON_THEIR_OWN = {
    "RS": "a skill name and its new name",
    "DS": "a skill name, a version and a drop mode",
}

# Pipeline-level flags (pipeline-contracts.md Pipeline Arguments): each takes a
# value and reaches the first workflow as the named input.
VALUE_FLAGS = {"--pin": "pin"}
# Ferris's own flag: On Activation already read it from the invocation.
IGNORED_FLAGS = frozenset({"--headless", "-H"})

_TOKEN_RE = re.compile(r"^([A-Za-z]+)(?:\[([^\]]*)\])?$")
_ARROWS = re.compile(r"->|→|—>|»")
_MIN_RE = re.compile(r"min:(\d+)", re.IGNORECASE)
# `min`, `min:`, `min=80`, `MIN:80%`: a threshold written wrong. A target such
# as `minimatch` does not match, because no `:` or `=` follows `min`.
_MIN_LIKE_RE = re.compile(r"min\s*(?:[:=]|$)", re.IGNORECASE)


def _unquote(token):
    """Drop one pair of matching quotes around a token."""
    if len(token) >= 2 and token[0] == token[-1] and token[0] in "'\"":
        return token[1:-1]
    return token


def _tokenize(raw):
    """Split a raw invocation on whitespace and arrow separators.

    A quoted argument stays one token, without its quotes. Backslashes are
    kept as they are, so a Windows path survives; an unbalanced quote falls
    back to a plain whitespace split.
    """
    normalized = _ARROWS.sub(" ", raw)
    lexer = shlex.shlex(normalized, posix=False)
    lexer.whitespace_split = True
    lexer.commenters = ""  # a URL fragment (`#readme`) is not a comment
    try:
        tokens = list(lexer)
    except ValueError:
        return normalized.split()
    return [t for t in map(_unquote, tokens) if t]


def _split_flags(tokens):
    """Return (other tokens, args from flags, unexpected flag tokens).

    `--pin <version>` and `--pin=<version>` give `pin`. A flag with no value,
    one given twice or one the pipeline does not take is unexpected: which
    value was meant has no single answer, so the parse reports it.
    """
    rest, args, unexpected = [], {}, []
    tokens = list(tokens)
    while tokens:
        tok = tokens.pop(0)
        if not tok.startswith("-") or tok == "-":
            rest.append(tok)
            continue
        if tok in IGNORED_FLAGS:
            continue
        name, eq, value = tok.partition("=")
        if name not in VALUE_FLAGS:
            unexpected.append(tok)
            continue
        if not eq and tokens and not tokens[0].startswith("-"):
            value = tokens.pop(0)
            tok = f"{name} {value}"
        key = VALUE_FLAGS[name]
        if not value or key in args:
            unexpected.append(tok)
        else:
            args[key] = value
    return rest, args, unexpected


def _classify_bracket(code, value):
    """Return (min, mode, target, malformed) for a bracket value on a code.

    Keywords match in any case (`TS[MIN:80]`, `AN[Auto]`). `min:N` counts only
    on AN and TS; elsewhere it is recorded as `min: null`.
    """
    if value is None or value == "":
        return None, None, None, False
    m = _MIN_RE.fullmatch(value)
    if m:
        # min:N only applies to AN and TS; ignored elsewhere.
        return (int(m.group(1)) if code in THRESHOLD_CODES else None), None, None, False
    if _MIN_LIKE_RE.match(value):
        return None, None, None, True
    if value.lower() == "auto":
        return None, "auto", None, False
    return None, None, value, False


def _normalized_token(code, value):
    """The token as `expanded` lists it: keywords lower case, `min:N` as a number."""
    if value in (None, ""):
        return code
    m = _MIN_RE.fullmatch(value)
    if m:
        return f"{code}[min:{int(m.group(1))}]"
    if value.lower() == "auto":
        return f"{code}[auto]"
    return f"{code}[{value}]"


def _one_folder(target):
    """Whether a bracket target names one folder: no separator, and not `.` or `..`."""
    return (isinstance(target, str) and bool(target.strip()) and "/" not in target and "\\" not in target
            and target not in (".", ".."))


def _briefs_on_disk(plan, forge_data_folder):
    """Whether each CS entry names a skill whose brief is on disk (False without the folder: an empty one is
    none, since an empty path would read the working directory)."""
    if not forge_data_folder:
        return False
    targets = [entry["target"] for entry in plan if entry["code"] == "CS"]
    return all(_one_folder(t) and (Path(forge_data_folder) / t / BRIEF).is_file() for t in targets)


def _load_forge_status():
    """forge-status.py, beside this script, or None when it cannot load (no audit is then known)."""
    try:
        spec = importlib.util.spec_from_file_location("skf_forge_status", FORGE_STATUS)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except (OSError, ImportError, SyntaxError):
        return None
    return module


def _audit_on_disk(status, target, forge_data_folder, skills_output_folder):
    """Whether the skill `target` names has an audit beside its active version's test record."""
    fdf, sof = Path(forge_data_folder), Path(skills_output_folder)
    try:
        entry = status.skill_entry(sof, fdf, target)
        active = entry.get("active_version") if isinstance(entry, dict) else None
        return isinstance(active, str) and bool(active) and status.audit_on_record(fdf, target, active)
    except (OSError, ValueError):
        return False


def _audits_on_disk(plan, forge_data_folder, skills_output_folder):
    """Whether each US entry names a skill whose active version has an audit on record (False without the
    folders, an empty one included, or when forge-status.py does not load)."""
    if not forge_data_folder or not skills_output_folder:
        return False
    targets = [entry["target"] for entry in plan if entry["code"] == "US"]
    if not all(_one_folder(t) for t in targets):
        return False
    status = _load_forge_status()
    return status is not None and all(
        _audit_on_disk(status, t, forge_data_folder, skills_output_folder) for t in targets)


def _detect_anti_patterns(plan, *, forge_data_folder=None, skills_output_folder=None):
    """Deterministic sequence checks, mirroring pipeline-contracts.md; the brief and audit checks read disk when
    given the folders."""
    codes = [entry["code"] for entry in plan]
    found = []

    # Duplicate codes.
    seen = set()
    dupes = []
    for c in codes:
        if c in seen and c not in dupes:
            dupes.append(c)
        seen.add(c)
    if dupes:
        found.append(
            {
                "pattern": "duplicate-codes",
                "codes": dupes,
                "message": f"same workflow appears more than once: {', '.join(dupes)}",
                "suggestion": "remove the duplicate",
            }
        )

    # EX before TS (equivalently, TS after EX).
    ex_idxs = [i for i, c in enumerate(codes) if c == "EX"]
    ts_idxs = [i for i, c in enumerate(codes) if c == "TS"]
    if ex_idxs and ts_idxs and min(ex_idxs) < max(ts_idxs):
        found.append(
            {
                "pattern": "ex-before-ts",
                "codes": ["EX", "TS"],
                "message": "EX (export) runs before TS (test) — exporting an untested skill",
                "suggestion": "move TS before EX",
            }
        )

    # CS without BS or AN, unless each CS names a skill whose brief is on disk.
    if "CS" in codes and "BS" not in codes and "AN" not in codes and not _briefs_on_disk(plan, forge_data_folder):
        found.append(
            {
                "pattern": "cs-without-brief",
                "codes": ["CS"],
                "message": "CS (compile) has no preceding BS or AN — compiling without a brief",
                "suggestion": "use QS for the quick path, or add AN/BS to produce a brief",
            }
        )

    # US without AS, unless each US names a skill whose active version has an audit on record.
    if ("US" in codes and "AS" not in codes
            and not _audits_on_disk(plan, forge_data_folder, skills_output_folder)):
        found.append(
            {
                "pattern": "us-without-audit",
                "codes": ["US"],
                "message": "US (update) has no preceding AS — updating without an audit",
                "suggestion": "run AS first to detect what changed",
            }
        )

    return found


def _min_ignored(tokens):
    """The warning for `min:N` brackets on codes other than AN and TS."""
    return {
        "pattern": "min-ignored",
        "codes": [t.split("[", 1)[0] for t in tokens],
        "message": f"{', '.join(tokens)} is ignored: only AN (a unit count) and TS (a test threshold) take min:N",
        "suggestion": "remove it, or put the threshold on TS (TS[min:N])",
    }


def _form(result, index, token):
    """The invocation again, with `token` in place of the plan entry at `index`."""
    tokens = list(result["expanded"])
    tokens[index] = token
    return _with_pin(" ".join(tokens), result["args"])


def _with_pin(text, args):
    return f"{text} --pin {shlex.quote(args['pin'])}" if args.get("pin") else text


def _needs(code, needs, form, rest):
    """A `first_input` entry; `rest` follows the reason's fixed opening."""
    reason = f"{code} needs {needs} before the pipeline can start{rest}" if rest is not None else None
    return {"code": code, "input": needs, "form": form, "halt_reason": reason}


def _bs_input(result, index, entry):
    """BS's two inputs: the forge alias gives both, a chain of codes no skill name."""
    if all(key in result["args"] for key in BS_INPUTS):
        return None
    target = entry["target"]
    after = result["plan"][index + 1:]
    if (index == 0 and result["codes"] == ALIASES["forge"] and entry["mode"] is None
            and all(e["min"] is None and e["mode"] is None and e["target"] is None for e in after)):
        needs = "a skill name" if target else "a target and a skill name"
        form = FORGE_FORM.replace("<repo-url-or-path>", target) if target else FORGE_FORM
        return _needs("BS", needs, _with_pin(form, result["args"]),
                      f": give {'it' if target else 'them'} as {form}")
    return _needs("BS", "a target and a skill name", None,
                  f", and a chain gives it one bracket: run BS on its own first, or use {FORGE_FORM}")


def _first_input(result):
    """The input the chain's first workflow lacks, or None (pipeline-mode.md step 1).

    Only for a runnable plan. The first workflow is the first plan entry
    other than SF, and it lacks its input when no bracket target and no
    alias argument gives it.
    """
    if not result["valid"]:
        return None
    index = next((i for i, e in enumerate(result["plan"]) if e["code"] != "SF"), None)
    if index is None:
        return None
    entry = result["plan"][index]
    code = entry["code"]
    if code in ON_THEIR_OWN:
        return _needs(code, ON_THEIR_OWN[code], None,
                      f", and a chain gives it one bracket: run {code} on its own, outside a chain")
    if code == "BS":
        return _bs_input(result, index, entry)
    if code not in FIRST_INPUTS:
        return None
    keys, needs, placeholder = FIRST_INPUTS[code]
    if entry["target"] is not None or any(key in result["args"] for key in keys):
        return None
    taken = "auto" if entry["mode"] else (f"min:{entry['min']}" if entry["min"] is not None else None)
    token = f"{code}[{placeholder}]"
    if code == "CS":
        return None if taken else _needs(code, needs, _form(result, index, token), None)
    if taken:
        hint = ", so start the chain as forge-auto <repo-or-doc-url>" if code == "AN" and taken == "auto" else ""
        return _needs(code, needs, None,
                      f", and its bracket already holds {taken}: a bracket holds one value{hint}")
    return _needs(code, needs, _form(result, index, token), f": give it as {token}")


def _alias_word(token):
    """Whether a token names an alias: a live, deprecated or removed one."""
    word = token.lower()
    return word in ALIASES or word in DEPRECATED_ALIASES or word in REMOVED_ALIASES


def parse_pipeline(raw, *, forge_data_folder=None, skills_output_folder=None):
    """Parse and validate a raw pipeline invocation. Deterministic for a given disk.

    With the folders, the brief and audit anti-patterns read the forge state
    on disk (the module docstring); without them, the order of the codes.
    """
    result = {
        "raw": raw,
        "alias": None,
        "deprecated_alias": None,
        "removed_alias": None,
        "expanded": [],
        "plan": [],
        "codes": [],
        "args": {},
        "unknown_codes": [],
        "unexpected_args": [],
        "missing_args": [],
        "malformed_brackets": [],
        "anti_patterns": [],
        "first_input": None,
        "valid": False,
    }
    tokens, args, unexpected = _split_flags(_tokenize(raw))
    result["args"] = args
    result["unexpected_args"] = unexpected
    if not tokens:
        return result

    # A leading alias expands, after a leading SF too; the tokens after it are its arguments.
    setup = len(tokens) > 1 and tokens[0].upper() == "SF" and _alias_word(tokens[1])
    if setup:
        tokens = tokens[1:]
    lead = tokens[0].lower()
    if lead in REMOVED_ALIASES:
        result["removed_alias"] = lead
        return result
    alias = None
    if lead in DEPRECATED_ALIASES:
        result["deprecated_alias"] = lead
        alias = DEPRECATED_ALIASES[lead]
    elif lead in ALIASES:
        alias = lead
    if alias:
        result["alias"] = alias
        positionals = tokens[1:]
        names = ALIAS_INPUTS[alias]
        result["args"] = {**dict(zip(names, positionals)), **args}
        result["unexpected_args"] = positionals[len(names):] + unexpected
        result["missing_args"] = list(names[len(positionals):])
        tokens = (["SF"] if setup else []) + list(ALIASES[alias])

    ignored_min = []
    for tok in tokens:
        m = _TOKEN_RE.match(tok)
        if not m:
            result["unknown_codes"].append(tok)
            continue
        code = m.group(1).upper()
        value = m.group(2)
        result["expanded"].append(_normalized_token(code, value))
        if code not in KNOWN_CODES:
            result["unknown_codes"].append(tok)
            continue
        min_n, mode, target, malformed = _classify_bracket(code, value)
        if malformed:
            result["malformed_brackets"].append(tok)
        elif value and _MIN_RE.fullmatch(value) and code not in THRESHOLD_CODES:
            ignored_min.append(_normalized_token(code, value))
        result["codes"].append(code)
        skill, description = SKILLS[code]
        result["plan"].append(
            {"code": code, "min": min_n, "mode": mode, "target": target,
             "skill": skill, "description": description}
        )

    result["anti_patterns"] = _detect_anti_patterns(result["plan"], forge_data_folder=forge_data_folder,
                                                    skills_output_folder=skills_output_folder)
    if ignored_min:
        result["anti_patterns"].append(_min_ignored(ignored_min))
    result["valid"] = (
        bool(result["codes"])
        and not result["unknown_codes"]
        and not result["unexpected_args"]
        and not result["missing_args"]
        and not result["malformed_brackets"]
    )
    result["first_input"] = _first_input(result)
    return result


# --- CLI --------------------------------------------------------------------


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="parse-pipeline",
        description=(
            "Deterministic parse + validation of a forger pipeline invocation "
            "(pipeline-mode.md §1-2): tokenize, expand aliases (after a leading SF "
            "too), bind an alias's arguments to its first workflow, classify bracket "
            "arguments, and detect sequence anti-patterns, the brief and audit ones "
            "against the forge state on disk when given the folders, returning a "
            "normalized run plan as JSON."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    src = parser.add_mutually_exclusive_group()
    src.add_argument(
        "sequence",
        nargs="?",
        help="The whole pipeline invocation as a positional argument.",
    )
    src.add_argument(
        "--stdin",
        action="store_true",
        help="Read the whole pipeline invocation from stdin.",
    )
    parser.add_argument(
        "--forge-data-folder",
        help="The forge data folder: CS is warned about without a brief only when a CS skill has no "
             "skill-brief.yaml there.",
    )
    parser.add_argument(
        "--skills-output-folder",
        help="The skills output folder: with --forge-data-folder, US is warned about without an audit only "
             "when a US skill's active version has no audit on record.",
    )
    return parser


def _resolve_input(args):
    if args.stdin:
        # A Windows console reads cp1252: the arrows and paths need UTF-8.
        if hasattr(sys.stdin, "reconfigure"):
            sys.stdin.reconfigure(encoding="utf-8")
        return sys.stdin.read().strip()
    if args.sequence is not None:
        return args.sequence
    return ""


def main(argv=None):
    parser = _build_parser()
    args = parser.parse_args(argv)
    raw = _resolve_input(args)
    if not raw.strip():
        parser.print_usage(file=sys.stderr)
        print("error: no input provided (positional arg or --stdin)", file=sys.stderr)
        return 1

    result = parse_pipeline(raw, forge_data_folder=args.forge_data_folder,
                            skills_output_folder=args.skills_output_folder)
    print(json.dumps(result, indent=2))
    if result["removed_alias"]:
        return 2
    if not result["valid"]:
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
