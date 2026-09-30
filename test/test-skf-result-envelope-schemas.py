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


def test_the_known_envelope_schemas_are_found():
    names = {p.name for p in ENVELOPE_SCHEMAS}
    assert {"skf-setup-result-envelope.v1.json", "skf-brief-result-envelope.v1.json",
            "skf-update-result-envelope.v1.json"} <= names


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
