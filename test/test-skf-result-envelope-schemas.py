#!/usr/bin/env python3
"""Every headless result-envelope schema is one the shared emitter can serve.

skf-emit-result-envelope.py builds a workflow's SKF_<NAME>_RESULT_JSON line
from the schema under src/shared/scripts/schemas/ whose emitter settings
(the `const` of its `$defs` entry `skf-envelope`) name the workflow. A
workflow adopts the emitter by adding that schema, so these checks run on
every *-result-envelope.v<N>.json there, today's and the ones later
workflows add:

- the schema is valid Draft 2020-12 and uses only standard keywords, so a
  strict validator (Ajv's default mode) compiles the installed file; it
  uses only the keywords the emitter's built-in validator enforces (the
  rest are annotations, and `$defs`, which holds only the settings); and
  the settings are complete and agree with the schema: the prefix opens the
  title, the wrapper is the one required object, the halt status is a
  status, and every halt_reason has an exit code the schema allows;
- the emitter's halt envelope, for every halt_reason the schema lists (one
  halt when it lists none), validates against the schema under jsonschema,
  an independent validator, and carries the exit code the settings map.

Across the workflows (#593):

- every workflow but the forger has its schema, so each one's halts go
  through the emitter;
- every halt_reason a workflow's step files and contracts name is one its
  schema lists, every one its schema lists is named there, and an
  exit-code table row that names a halt_reason carries the code the schema
  maps it to; the emitter then emits each of them (above), audit's
  `no-baseline` included;
- docs/_internal/STABILITY.md names every envelope schema, and the
  workflow it belongs to, as covered surface.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
SCHEMA_DIR = SRC / "shared" / "scripts" / "schemas"
SCRIPT_PATH = SRC / "shared" / "scripts" / "skf-emit-result-envelope.py"

spec = importlib.util.spec_from_file_location("skf_emit_result_envelope_schemas", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

ENVELOPE_SCHEMAS = sorted(SCHEMA_DIR.glob("*-result-envelope.v*.json"))
IDS = [p.name for p in ENVELOPE_SCHEMAS]


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _meta(schema: dict) -> dict:
    """The schema's emitter settings, which every envelope schema must carry."""
    meta = mod._meta_of(schema)
    assert meta is not None, f"{schema.get('title')}: no $defs.{mod.META_KEY}.const object"
    return meta


def _inner(schema: dict) -> dict:
    wrapper = _meta(schema).get("wrapper")
    return schema["properties"][wrapper] if wrapper else schema


def _halt_reasons(schema: dict) -> list:
    prop = _inner(schema).get("properties", {}).get("halt_reason")
    if not prop:
        return [None]
    return [r for r in prop.get("enum", []) if r is not None]


# Every workflow under src/: the forger is an agent, with no headless contract.
WORKFLOWS = sorted(d.name for d in SRC.iterdir()
                   if d.is_dir() and d.name.startswith("skf-") and d.name != "skf-forger")
STABILITY = ROOT / "docs" / "_internal" / "STABILITY.md"


def test_the_known_envelope_schemas_are_found():
    names = {p.name for p in ENVELOPE_SCHEMAS}
    assert {"skf-setup-result-envelope.v1.json", "skf-brief-result-envelope.v1.json",
            "skf-update-result-envelope.v1.json"} <= names


def test_every_workflow_has_an_envelope_schema():
    claimed = {_meta(_load(p))["workflow"] for p in ENVELOPE_SCHEMAS}
    assert len(WORKFLOWS) == 15, WORKFLOWS
    assert claimed == set(WORKFLOWS), sorted(set(WORKFLOWS) ^ claimed)


@pytest.mark.parametrize("path", ENVELOPE_SCHEMAS, ids=IDS)
def test_schema_is_valid_draft_2020_12(path):
    schema = _load(path)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    Draft202012Validator.check_schema(schema)


def _schema_nodes(node, where="$"):
    """Yield (pointer, subschema) for every subschema, skipping property names
    and the values of `const`, `enum` and `default`, which are data."""
    yield where, node
    for key in ("properties", "$defs"):
        for name, child in (node.get(key) or {}).items():
            yield from _schema_nodes(child, f"{where}.{key}.{name}")
    for key in ("items", "additionalProperties"):
        if isinstance(node.get(key), dict):
            yield from _schema_nodes(node[key], f"{where}.{key}")
    for key in ("oneOf", "anyOf"):
        for i, child in enumerate(node.get(key) or []):
            yield from _schema_nodes(child, f"{where}.{key}[{i}]")


# The keywords of the Draft 2020-12 vocabularies: core, applicator,
# unevaluated, validation, meta-data, format-annotation and content. Ajv's
# default strict mode refuses to compile a schema that uses any other
# keyword, so a pipeline that checks envelopes against the installed schema
# files would fail on the first unknown one.
DRAFT_2020_12_KEYWORDS = frozenset({
    "$schema", "$id", "$ref", "$anchor", "$dynamicRef", "$dynamicAnchor", "$vocabulary", "$comment",
    "$defs",
    "prefixItems", "items", "contains", "additionalProperties", "properties", "patternProperties",
    "dependentSchemas", "propertyNames", "if", "then", "else", "allOf", "anyOf", "oneOf", "not",
    "unevaluatedItems", "unevaluatedProperties",
    "type", "const", "enum", "multipleOf", "maximum", "exclusiveMaximum", "minimum", "exclusiveMinimum",
    "maxLength", "minLength", "pattern", "maxItems", "minItems", "uniqueItems", "maxContains",
    "minContains", "maxProperties", "minProperties", "required", "dependentRequired",
    "title", "description", "default", "deprecated", "readOnly", "writeOnly", "examples",
    "format",
    "contentEncoding", "contentMediaType", "contentSchema",
})


@pytest.mark.parametrize("path", ENVELOPE_SCHEMAS, ids=IDS)
def test_schema_uses_only_standard_keywords(path):
    for where, node in _schema_nodes(_load(path)):
        unknown = set(node) - DRAFT_2020_12_KEYWORDS
        assert not unknown, f"{path.name} {where}: {sorted(unknown)} is not a Draft 2020-12 keyword"


def test_the_emitter_skips_only_standard_keywords():
    """What the built-in validator enforces or skips stays inside the standard set."""
    assert mod.VALIDATOR_KEYWORDS | mod.ANNOTATION_KEYWORDS <= DRAFT_2020_12_KEYWORDS


@pytest.mark.parametrize("path", ENVELOPE_SCHEMAS, ids=IDS)
def test_schema_uses_only_keywords_the_emitter_enforces(path):
    known = mod.VALIDATOR_KEYWORDS | mod.ANNOTATION_KEYWORDS
    for where, node in _schema_nodes(_load(path)):
        unknown = set(node) - known
        assert not unknown, f"{path.name} {where}: the emitter does not enforce {sorted(unknown)}"
        if isinstance(node.get("additionalProperties"), dict):
            pytest.fail(f"{path.name} {where}: additionalProperties must be true or false")


@pytest.mark.parametrize("path", ENVELOPE_SCHEMAS, ids=IDS)
def test_defs_hold_only_the_emitter_settings(path):
    """`$defs` is skipped by the built-in validator, so it may hold nothing a
    field could use: only the settings entry, a `const` with a description."""
    schema = _load(path)
    assert set(schema["$defs"]) == {mod.META_KEY}
    assert set(schema["$defs"][mod.META_KEY]) <= {"const", "description"}
    for where, node in _schema_nodes(schema):
        if where != "$":
            assert "$defs" not in node, f"{path.name} {where}: $defs belongs at the top level only"


@pytest.mark.parametrize("path", ENVELOPE_SCHEMAS, ids=IDS)
def test_envelope_block_agrees_with_the_schema(path):
    schema = _load(path)
    meta = _meta(schema)
    assert set(meta) <= set(mod.META_FIELDS), set(meta) - set(mod.META_FIELDS)
    assert (SRC / meta["workflow"] / "SKILL.md").is_file(), meta["workflow"]
    assert re.fullmatch(r"SKF_[A-Z_]+_RESULT_JSON", meta["prefix"]), meta["prefix"]
    assert schema["title"].startswith(f"{meta['prefix']} envelope"), schema["title"]
    wrapper = meta.get("wrapper")
    if wrapper is not None:
        assert schema["required"] == [wrapper]
        assert schema["properties"][wrapper]["type"] == "object"
    props = _inner(schema)["properties"]
    assert meta["halt_status"] in props["status"]["enum"]
    codes = meta.get("exit_codes")
    if codes is not None:
        assert set(codes) == set(_halt_reasons(schema)), "every halt_reason needs an exit code"
        allowed = props["exit_code"].get("enum")
        for reason, code in codes.items():
            assert isinstance(code, int) and not isinstance(code, bool), reason
            assert allowed is None or code in allowed, (reason, code)
        if "success_exit_code" in meta:
            assert allowed is None or meta["success_exit_code"] in allowed
    result_file = meta.get("result_file")
    assert result_file is None or re.fullmatch(r"[a-z][a-z-]*-result", result_file), result_file


def test_no_two_schemas_claim_one_workflow_at_one_version():
    seen = {}
    for path in ENVELOPE_SCHEMAS:
        stem, version = mod._schema_version(path)
        key = (_meta(_load(path))["workflow"], version)
        assert key not in seen, f"{path.name} and {seen[key]} both claim {key}"
        seen[key] = path.name


@pytest.mark.parametrize("path", ENVELOPE_SCHEMAS, ids=IDS)
def test_the_emitter_resolves_the_workflow_to_its_schema(path):
    schema = _load(path)
    workflow = _meta(schema)["workflow"]
    stem, version = mod._schema_version(path)
    newest = max(mod._schema_version(p)[1] for p in ENVELOPE_SCHEMAS
                 if _meta(_load(p))["workflow"] == workflow)
    if version == newest:
        for name in (workflow, stem):
            found, found_path = mod.load_workflow_schema(name)
            assert found_path == path and found == schema, name


def _synthetic(prop: dict):
    """A value the property accepts, for a required field a halt must supply."""
    if "enum" in prop:
        return next(v for v in prop["enum"] if v is not None)
    kind = prop.get("type")
    kind = kind[0] if isinstance(kind, list) else kind
    return {"string": "x", "integer": 1, "number": 1, "boolean": True, "array": [], "object": {}}[kind]


def _halt_payload(schema: dict, halt_reason) -> dict:
    meta = _meta(schema)
    payload = {"phase": "test:halt", "reason": "the step halted", "path": "/p/x"}
    if halt_reason is not None:
        payload["halt_reason"] = halt_reason
        payload["exit_code"] = meta["exit_codes"][halt_reason]
    inner = _inner(schema)
    for key in inner.get("required", []):
        prop = inner["properties"][key]
        if key in mod.HALT_KEYS or key in ("status", "error", "headless_decisions", "warnings"):
            continue
        if mod._placeholder(prop, halt=True) is mod._MISSING:
            payload[key] = _synthetic(prop)
    return payload


HALTS = [(path, reason) for path in ENVELOPE_SCHEMAS for reason in _halt_reasons(_load(path))]


@pytest.mark.parametrize("path,halt_reason", HALTS,
                         ids=[f"{p.name}:{r}" for p, r in HALTS])
def test_every_halt_reason_emits_a_schema_valid_envelope(path, halt_reason):
    schema = _load(path)
    meta = _meta(schema)
    proc = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "emit-halt", "--workflow", meta["workflow"]],
        input=json.dumps(_halt_payload(schema, halt_reason)),
        capture_output=True, text=True, encoding="utf-8", timeout=20,
    )
    assert proc.returncode == 0, proc.stderr
    [line] = proc.stdout.splitlines()
    prefix = f"{meta['prefix']}: "
    assert line.startswith(prefix)
    envelope = json.loads(line[len(prefix):])
    errors = sorted(Draft202012Validator(schema).iter_errors(envelope), key=str)
    assert not errors, [e.message for e in errors]
    inner = envelope[meta["wrapper"]] if meta.get("wrapper") else envelope
    assert inner["status"] == meta["halt_status"]
    if halt_reason is not None:
        assert inner["halt_reason"] == halt_reason
        assert inner["exit_code"] == meta["exit_codes"][halt_reason]


def test_setup_prefix_matches_the_emitter_constant():
    meta = _meta(_load(SCHEMA_DIR / "skf-setup-result-envelope.v1.json"))
    assert f"{meta['prefix']}: " == mod.ENVELOPE_PREFIX


# ---------------------------------------------------------------------------
# Every halt_reason a workflow names, against its schema (#593)
# ---------------------------------------------------------------------------


def _newest_schema(workflow: str) -> dict:
    paths = [p for p in ENVELOPE_SCHEMAS if _meta(_load(p))["workflow"] == workflow]
    return _load(max(paths, key=lambda p: mod._schema_version(p)[1]))


def _workflow_markdown(workflow: str) -> list[Path]:
    skill = SRC / workflow
    return [skill / "SKILL.md", *sorted((skill / "references").rglob("*.md"))]


def _token(reason: str) -> re.Pattern:
    return re.compile(rf"(?<![\w-]){re.escape(reason)}(?![\w-])")


# A halt_reason a payload or a HALT names outright. The other mentions (a
# script's own halt_reason that a step maps to another, a class name in an
# exit-code table) are not a value the emitter receives.
EXPLICIT_REASON_RES = (
    re.compile(r'`halt_reason: "([a-z][a-z0-9-]*)"`'),
    re.compile(r'"halt_reason": "([a-z][a-z0-9-]*)"'),
    re.compile(r"--halt-reason ([a-z][a-z0-9-]*)\b"),
)
CODED = [w for w in WORKFLOWS if _meta(_newest_schema(w)).get("exit_codes")]


def _explicit_reasons(workflow: str) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for path in _workflow_markdown(workflow):
        text = path.read_text(encoding="utf-8")
        for pattern in EXPLICIT_REASON_RES:
            for reason in pattern.findall(text):
                found.setdefault(reason, []).append(path.relative_to(SRC).as_posix())
    return found


@pytest.mark.parametrize("workflow", CODED)
def test_every_halt_reason_a_workflow_names_is_in_its_schema(workflow):
    """The emitter refuses a halt_reason its schema does not list, so a halt
    that names one would print no envelope."""
    reasons = set(_meta(_newest_schema(workflow))["exit_codes"])
    unknown = {r: sorted(set(w)) for r, w in _explicit_reasons(workflow).items() if r not in reasons}
    assert not unknown, f"{workflow}: halt_reason values its schema does not list: {unknown}"


@pytest.mark.parametrize("workflow", CODED)
def test_every_schema_halt_reason_is_named_by_the_workflow(workflow):
    """A halt_reason no step or contract names is one no run can raise."""
    text = "\n".join(p.read_text(encoding="utf-8") for p in _workflow_markdown(workflow))
    unnamed = [r for r in _meta(_newest_schema(workflow))["exit_codes"] if not _token(r).search(text)]
    assert not unnamed, f"{workflow}: schema halt_reason values no step names: {unnamed}"


def _exit_code_rows(workflow: str):
    """(file, code, row text) for each row of the workflow's exit-code tables."""
    for path in _workflow_markdown(workflow):
        lines = path.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            if not re.match(r"^\|\s*Code\s*\|\s*Meaning\b", line):
                continue
            for row in lines[i + 2:]:
                if not row.startswith("|"):
                    break
                cells = [c.strip() for c in row.strip().strip("|").split("|")]
                if cells[0].isdigit():
                    yield path.relative_to(SRC).as_posix(), int(cells[0]), " | ".join(cells[1:])


@pytest.mark.parametrize("workflow", CODED)
def test_exit_code_tables_map_each_halt_reason_as_the_schema_does(workflow):
    codes = _meta(_newest_schema(workflow))["exit_codes"]
    rows = list(_exit_code_rows(workflow))
    # "every `halt_reason` below but `hard-gate-blocked`" names a reason the row excludes.
    wrong = [f"{where}: exit {code} names `{reason}`, which the schema maps to {codes[reason]}"
             for where, code, text in rows
             if not where.endswith("step-shape-detect.md")
             for reason in codes
             if _token(reason).search(text) and f"but `{reason}`" not in text and codes[reason] != code]
    assert not wrong, "\n".join(wrong)


def test_audit_no_baseline_is_a_documented_exit_3_halt():
    """A skill with no provenance map halts with `no-baseline` (exit 3); the
    exit-code table, the step that raises it and the schema agree."""
    codes = _meta(_newest_schema("skf-audit-skill"))["exit_codes"]
    assert codes["no-baseline"] == 3
    table = [text for _, code, text in _exit_code_rows("skf-audit-skill") if code == 3]
    assert len(table) == 1 and "`no-baseline`" in table[0], table
    init = (SRC / "skf-audit-skill" / "references" / "init.md").read_text(encoding="utf-8")
    assert 'HALT with **exit 3**, `halt_reason: "no-baseline"`, phase `init:provenance`' in init
    assert ("skf-audit-result-envelope.v1.json", "no-baseline") in HALTS_BY_NAME


HALTS_BY_NAME = {(path.name, reason) for path, reason in HALTS}


# ---------------------------------------------------------------------------
# STABILITY.md names every envelope schema as covered surface
# ---------------------------------------------------------------------------


def _stability_schema_entry() -> str:
    text = STABILITY.read_text(encoding="utf-8")
    [entry] = [line for line in text.splitlines()
               if line.startswith("- **Schema enum values and properties.**")]
    return entry


@pytest.mark.parametrize("path", ENVELOPE_SCHEMAS, ids=IDS)
def test_stability_names_the_schema_and_its_workflow(path):
    entry = _stability_schema_entry()
    workflow = _meta(_load(path))["workflow"]
    assert f"`{workflow}` (`{path.name}`" in entry, f"STABILITY.md does not name {workflow}'s {path.name}"


def test_stability_covers_the_envelope_values_from_3_0_0():
    entry = _stability_schema_entry()
    assert "covered from 3.0.0 with its `status`, `exit_code` and `halt_reason` values and its properties" in entry
    for token in ("`helper-missing`", "`provenance-invalid`", "`source-unreadable`", "`no-baseline`",
                  "`upstream_moved`", "`upstream_ref`", "`run_id`", "`result_path`", "`headless_decisions`",
                  "`warnings`"):
        assert token in entry, token
