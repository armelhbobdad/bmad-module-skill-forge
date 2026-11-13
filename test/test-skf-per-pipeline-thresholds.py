"""Structural integration tests for per-pipeline quality thresholds (story 3.2).

Validates the per-pipeline threshold lookup table in init.md §1b, the
four-layer threshold resolution precedence, resolved once in init.md §1b and
written into the report frontmatter, which score.md §1 reads back (#587:
later steps read the verdict inputs from the frontmatter), threshold source
logging in score.md §6, pipeline_alias forwarding in the forger, and
pipeline-contracts.md documentation.  Also confirms hard-gate independence
(AC #4): step-hard-gate.md has no threshold-driven logic.

#1189 customization-2: `default_threshold` ships empty and, set by an
override, outranks a pipeline's default, so the order is CLI, override,
pipeline table, bundled 80. The matrix tests resolve each case in the order
init.md §1b's sentence names its layers, so they read the prose the model runs.

The alias gates come from parse-pipeline.py's ALIASES, the table the forger
runs, not from a prose copy of it.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import re
import subprocess
import sys
import tomllib

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
TS_DIR = REPO_ROOT / "src" / "skf-test-skill"
INIT_FILE = TS_DIR / "references" / "init.md"
TEMPLATE_FILE = TS_DIR / "templates" / "test-report-template.md"
SCORE_FILE = TS_DIR / "references" / "score.md"
HARD_GATE_FILE = TS_DIR / "references" / "step-hard-gate.md"
SKILL_MD = TS_DIR / "SKILL.md"
CONTRACT_FILE = TS_DIR / "references" / "invocation-contract.md"
CUSTOMIZE_TOML = TS_DIR / "customize.toml"
FORGER_MD = REPO_ROOT / "src" / "skf-forger" / "SKILL.md"
PIPELINE_CONTRACTS = REPO_ROOT / "src" / "shared" / "references" / "pipeline-contracts.md"
PIPELINE_MODE = REPO_ROOT / "src" / "skf-forger" / "references" / "pipeline-mode.md"
PARSE_PIPELINE = REPO_ROOT / "src" / "skf-forger" / "scripts" / "parse-pipeline.py"

_spec = importlib.util.spec_from_file_location("parse_pipeline", PARSE_PIPELINE)
parse_pipeline = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(parse_pipeline)
ALIASES = parse_pipeline.ALIASES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_compute_score():
    spec = importlib.util.spec_from_file_location("compute_score_threshold_source", TS_DIR / "scripts" / "compute-score.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def _flow(text: str) -> str:
    return re.sub(r"\s+", " ", text)


# init.md §1b's one sentence: each layer as it names it, and what the layer gives for a run. A run is a dict
# of `cli` (the --threshold value), `override` (the bound {defaultThreshold}) and `alias` ({pipeline_alias}).
PRECEDENCE_LEAD = "`effective_threshold` is the first of "
LAYERS = {
    "`--threshold=<N>`": lambda run, table: run.get("cli"),
    "a bound `{defaultThreshold}`": lambda run, table: run.get("override"),
    "the table's value for `{pipeline_alias}` when the table lists it": lambda run, table: table.get(run.get("alias")),
    "`80`": lambda run, table: 80,
}
LABELS = ["CLI override ({N}%)", "workflow override ({N}%)", "pipeline default ({pipeline_alias} → {N}%)",
          "bundled default (80%)"]


def _section_1b() -> str:
    text = _read(INIT_FILE)
    return text[text.index("### 1b."):text.index("### 2.")]


def _precedence_sentence() -> str:
    section = _flow(_section_1b())
    assert section.count(PRECEDENCE_LEAD) == 1, "init.md §1b states the precedence in one sentence"
    start = section.index(PRECEDENCE_LEAD)
    return section[start:section.index(". ", start) + 1]


def _lookup_table() -> dict[str, int]:
    """init.md §1b's lookup table: pipeline alias -> default threshold."""
    rows = re.findall(r"^\|\s*`([a-z-]+)`\s*\|\s*(\d+)\s*\|", _section_1b(), re.M)
    return {alias: int(n) for alias, n in rows}


def _ordered_layers() -> list[tuple[str, str]]:
    """Each layer of the sentence, in its order, with the `threshold_source` label written right after it."""
    sentence = _precedence_sentence()
    layers = sorted(LAYERS, key=sentence.index)
    labels = re.findall(r'`"([^"`]+)"`', sentence)
    assert len(labels) == len(layers), (labels, sentence)
    for i, (layer, label) in enumerate(zip(layers, labels)):
        after = sentence.index(f'`"{label}"`')
        assert sentence.index(layer) < after, (layer, label)
        if i + 1 < len(layers):
            assert after < sentence.index(layers[i + 1]), (label, layers[i + 1])
    return list(zip(layers, labels))


def _resolve(run: dict) -> tuple[int, str]:
    """The threshold and its source, taking the layers in the order init.md §1b names them."""
    table = _lookup_table()
    for layer, label in _ordered_layers():
        value = LAYERS[layer](run, table)
        if value is not None:
            return value, label.replace("{N}", str(value)).replace("{pipeline_alias}", str(run.get("alias")))
    raise AssertionError("no layer gave a threshold")


def _bound_default_threshold(merged_value: str) -> int | None:
    """SKILL.md On Activation binds `{defaultThreshold}` only from a non-empty value."""
    return int(merged_value) if str(merged_value).strip() else None


# ---------------------------------------------------------------------------
# init.md §1b — Per-Pipeline Threshold Lookup Table
# ---------------------------------------------------------------------------


class TestInitPipelineThresholdSection:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(INIT_FILE)

    def test_section_1b_exists(self, text: str) -> None:
        assert re.search(r"###?\s+1b\.", text), (
            "init.md must have a §1b section for per-pipeline threshold resolution"
        )

    def test_section_1b_title(self, text: str) -> None:
        assert re.search(
            r"Resolve Per-Pipeline Quality Threshold", text
        ), "§1b must be titled 'Resolve Per-Pipeline Quality Threshold'"

    def test_pipeline_alias_variable_referenced(self, text: str) -> None:
        assert "{pipeline_alias}" in text, (
            "§1b must reference {pipeline_alias} variable"
        )

    def test_pipeline_default_threshold_variable_is_gone(self) -> None:
        """#1189 leanness-8: §1b reads the table in its one sentence, with no variable of its own."""
        for path in sorted(TS_DIR.rglob("*")):
            if path.is_file() and path.suffix in {".md", ".toml"}:
                text = _read(path)
                for gone in ("{pipeline_default_threshold}", "workflow default (", "should be unreachable",
                             "bundled fallback ("):
                    assert gone not in text, (path.name, gone)

    @pytest.mark.parametrize(
        "alias,threshold",
        [
            ("forge-auto", "90"),
            ("forge", "80"),
            ("forge-quick", "80"),
            ("campaign", "90"),
        ],
    )
    def test_lookup_table_entry(self, text: str, alias: str, threshold: str) -> None:
        assert re.search(
            rf"\|\s*`{alias}`\s*\|\s*{threshold}\s*\|", text
        ), f"§1b lookup table must map {alias} → {threshold}"

    def test_lookup_table_has_header(self, text: str) -> None:
        assert re.search(
            r"\|\s*Pipeline Alias\s*\|\s*Default Threshold\s*\|", text
        ), "§1b lookup table must have Pipeline Alias / Default Threshold headers"

    def test_alias_found_in_the_table(self) -> None:
        assert "the table's value for `{pipeline_alias}` when the table lists it" in _precedence_sentence()
        assert _resolve({"alias": "forge-auto"}) == (90, "pipeline default (forge-auto → 90%)")

    @pytest.mark.parametrize("alias", ["maintain", None], ids=["not-in-the-table", "absent"])
    def test_alias_not_in_the_table_or_absent_falls_to_80(self, alias: str | None) -> None:
        """An alias the table does not list, or none (a standalone run), takes the bundled 80."""
        assert alias not in _lookup_table()
        assert _resolve({"alias": alias}) == (80, "bundled default (80%)")

    def test_the_bullets_and_steps_are_gone(self) -> None:
        section = _section_1b()
        for gone in ("present AND found in the table", "present but NOT in the table", "remains unset",
                     "falls through to", "precedence: CLI > pipeline default"):
            assert gone not in section, gone
        assert not re.search(r"^\d+\. ", section, re.M), "§1b numbers no steps"

    def test_section_1b_before_section_2(self, text: str) -> None:
        idx_1b = text.find("### 1b.")
        idx_2 = text.find("### 2.")
        assert idx_1b != -1 and idx_2 != -1 and idx_1b < idx_2, (
            "§1b must appear between §1 and §2 in init.md"
        )

    def test_references_score_md(self, text: str) -> None:
        assert re.search(r"score\.md", text), (
            "§1b must reference score.md as the reader of the resolved threshold"
        )


# ---------------------------------------------------------------------------
# init.md §1b: Four-Layer Threshold Precedence, resolved once
# ---------------------------------------------------------------------------


class TestInitThresholdPrecedence:
    """#1189 customization-2: CLI, then an override, then the pipeline table, then the bundled 80."""

    def test_the_sentence_names_the_four_layers_in_order(self) -> None:
        assert _ordered_layers() == list(zip(LAYERS, LABELS))

    @pytest.mark.parametrize("run, expected", [
        ({"cli": 85, "override": 70, "alias": "forge"}, (85, "CLI override (85%)")),
        ({"override": 70, "alias": "forge"}, (70, "workflow override (70%)")),
        ({"override": 70, "alias": "forge-auto"}, (70, "workflow override (70%)")),
        ({"alias": "forge-quick"}, (80, "pipeline default (forge-quick → 80%)")),
        ({"alias": None}, (80, "bundled default (80%)")),
        ({"alias": "maintain"}, (80, "bundled default (80%)")),
    ], ids=["cli-wins", "override-reaches-a-pipeline", "override-outranks-the-table", "pipeline-default",
            "nothing-set", "nothing-set-maintain"])
    def test_each_case_resolves_as_the_sentence_orders_it(self, run: dict, expected: tuple[int, str]) -> None:
        assert _resolve(run) == expected

    @pytest.mark.parametrize("alias, expected", [
        ("forge-auto", (90, "pipeline default (forge-auto → 90%)")),
        (None, (80, "bundled default (80%)")),
    ], ids=["pipeline", "standalone"])
    def test_the_bundled_value_binds_no_override(self, alias: str | None, expected: tuple[int, str]) -> None:
        """With no override, or when the resolver cannot run and the bundled customize.toml is read alone,
        the empty `default_threshold` leaves `{defaultThreshold}` unbound: the table decides, else 80."""
        bundled = tomllib.loads(_read(CUSTOMIZE_TOML))["workflow"]["default_threshold"]
        assert bundled == ""
        override = _bound_default_threshold(bundled)
        assert override is None
        assert _resolve({"override": override, "alias": alias}) == expected


# ---------------------------------------------------------------------------
# init.md §1b: Threshold Source Logging
# ---------------------------------------------------------------------------


class TestInitThresholdSourceLogging:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(INIT_FILE)

    def test_threshold_source_variable_set(self, text: str) -> None:
        assert "threshold_source" in text, (
            "score.md must set threshold_source variable"
        )

    def test_cli_override_source_format(self, text: str) -> None:
        assert re.search(r'CLI override', text), (
            "threshold_source for CLI must include 'CLI override'"
        )

    def test_pipeline_default_source_format(self, text: str) -> None:
        assert re.search(r'pipeline default', text), (
            "threshold_source for pipeline must include 'pipeline default'"
        )

    def test_workflow_override_source_format(self, text: str) -> None:
        assert '`"workflow override ({N}%)"`' in text, (
            "threshold_source for the override must read 'workflow override'"
        )
        assert "workflow default" not in text

    def test_bundled_default_source_format(self, text: str) -> None:
        assert '`"bundled default (80%)"`' in text, (
            "threshold_source for the last layer must read 'bundled default (80%)'"
        )
        assert "bundled fallback" not in text, "'fallback' names the threshold fallback alone"

    def test_threshold_source_is_written_into_the_report(self, text: str) -> None:
        assert "thresholdSource: '{threshold_source}'" in text, (
            "init.md §6c must write threshold_source into the report frontmatter"
        )
        assert "threshold: '{effective_threshold}%'" in text

    def test_score_reads_the_threshold_back(self) -> None:
        score = _read(SCORE_FILE)
        section = score[score.index("### 1. Read the Pass Threshold"):score.index("### 2.")]
        assert "`effective_threshold` ← `threshold`" in section
        assert "`threshold_source` ← `thresholdSource`" in section
        assert "Never resolve the precedence again here" in section
        assert "--threshold=<N>" not in section, "the precedence lives in init.md §1b alone"


# ---------------------------------------------------------------------------
# score.md §6 — Threshold Source in Report Output
# ---------------------------------------------------------------------------


class TestScoreReportOutput:
    """#1186: score.md §6 writes the section `build-result-context.py settle` prints, whose Threshold Source line is
    the report frontmatter's `thresholdSource`, the source init.md §1b resolved."""

    @staticmethod
    def _section(tmp_path: pathlib.Path, source: str) -> str:
        report = tmp_path / "report.md"
        report.write_bytes((f"---\ntestMode: 'naive'\nhardGate: 'passed'\ntestResult: ''\nscore: ''\n"
                            f"threshold: '80%'\nthresholdSource: '{source}'\nanalysisConfidence: 'full'\n"
                            "toolingStatus: 'ok'\nnextWorkflow: ''\n---\n# R\n").encode("utf-8"))
        scored = _load_compute_score().compute_score({"mode": "naive", "tier": "Deep", "threshold": 80,
                                                      "toolingStatus": "ok", "scores": {
                                                          "exportCoverage": 90, "signatureAccuracy": 90,
                                                          "typeCoverage": 90, "coherence": None,
                                                          "externalValidation": 90}})
        (tmp_path / "score.json").write_bytes(json.dumps(scored).encode("utf-8"))
        (tmp_path / "external.json").write_bytes(b'{"externalScore": 90, "toolsUsed": ["skill-check"]}')
        proc = subprocess.run([sys.executable, str(TS_DIR / "scripts" / "build-result-context.py"), "settle",
                               "--report", str(report), "--score", str(tmp_path / "score.json"), "--external",
                               str(tmp_path / "external.json")], capture_output=True, text=True, encoding="utf-8")
        assert proc.returncode == 0, proc.stderr
        return proc.stdout

    def test_threshold_source_in_completeness_score_section(self, tmp_path: pathlib.Path) -> None:
        section = self._section(tmp_path, "pipeline default (forge-auto → 90%)")
        assert section.startswith("## Completeness Score\n")
        assert "**Threshold Source:**" in section, (
            "Completeness Score section must include **Threshold Source:** line"
        )
        score = _read(SCORE_FILE)
        assert "uv run {resultContextScript} settle" in score[score.find("### 6. Write the Completeness Score"):]

    def test_threshold_source_line_format(self, tmp_path: pathlib.Path) -> None:
        for source in ("CLI override (90%)", "pipeline default (forge → 85%)", "workflow override (70%)",
                       "bundled default (80%)"):
            assert f"\n**Threshold Source:** {source}\n" in self._section(tmp_path, source), (
                "the Threshold Source line must give the frontmatter's thresholdSource"
            )


# ---------------------------------------------------------------------------
# init.md §6c: thresholdSource in the report frontmatter
# ---------------------------------------------------------------------------


class TestReportFrontmatter:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(INIT_FILE)

    def test_threshold_source_in_frontmatter(self, text: str) -> None:
        assert re.search(
            r"thresholdSource:.*threshold_source", text
        ), "init.md §6c frontmatter must include thresholdSource field"

    def test_threshold_source_after_threshold_before_confidence(
        self, text: str
    ) -> None:
        fm_section = text[text.find("workflowType: 'test-skill'"):]
        threshold_idx = fm_section.find("threshold:")
        ts_idx = fm_section.find("thresholdSource:")
        confidence_idx = fm_section.find("analysisConfidence:")
        assert threshold_idx < ts_idx < confidence_idx, (
            "thresholdSource must appear after threshold and before analysisConfidence"
        )

    def test_the_template_and_the_initial_frontmatter_hold_the_same_keys(self, text: str) -> None:
        """#777: §6c's block replaces the template's frontmatter, so the two list the same keys in the same
        order, and §6c says which one the report keeps."""
        template = re.match(r"^---\n(.*?)\n---\n", _read(TEMPLATE_FILE), re.S)
        assert template, "the template has no frontmatter"
        block = re.search(r"```yaml\n---\n(workflowType: 'test-skill'\n.*?)\n---\n```", text, re.S)
        assert block, "init.md §6c has no initial frontmatter block"

        def keys(body: str) -> list[str]:
            return re.findall(r"^([A-Za-z_][A-Za-z0-9_]*):", body, re.M)

        assert keys(block.group(1)) == keys(template.group(1))
        assert "health_check_dispatched: false" in block.group(1), "report.md §4c sets it when it publishes"
        section = re.sub(r"\s+", " ", text[text.index("**6c. Create `{outputFile}`"):text.index("### 7. ")])
        assert "Replace the template's frontmatter with this block (the two hold the same keys)." in section


# ---------------------------------------------------------------------------
# references/invocation-contract.md: Invocation Contract references per-pipeline defaults
# ---------------------------------------------------------------------------


class TestInvocationContract:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(CONTRACT_FILE)

    def test_threshold_flag_references_per_pipeline_defaults(self, text: str) -> None:
        invocation_match = re.search(
            r"## Invocation Contract\b(.*?)(?=^## )",
            text,
            flags=re.MULTILINE | re.DOTALL,
        )
        assert invocation_match, "invocation-contract.md must have an Invocation Contract section"
        section = invocation_match.group(1)
        assert "per-pipeline defaults" in section, (
            "Invocation Contract --threshold description must reference per-pipeline defaults"
        )


class TestSkillMdOnActivation:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(SKILL_MD)

    def test_default_threshold_references_per_pipeline(self, text: str) -> None:
        activation_match = re.search(
            r"## On Activation\b(.*?)(?=^## |\Z)",
            text,
            flags=re.MULTILINE | re.DOTALL,
        )
        assert activation_match, "SKILL.md must have an On Activation section"
        section = re.sub(r"\s+", " ", activation_match.group(1))
        # #1189: the binding is bound only from an override, and the precedence has one home, init.md §1b.
        assert ("- `{defaultThreshold}` ← `workflow.default_threshold` when it is non-empty, which only a team or "
                "personal override makes it (the bundled value is empty); otherwise leave `{defaultThreshold}` "
                "unbound.") in section
        for gone in ("init.md §1b resolves the precedence", "else `80`", "at the usage site in `references/score.md`"):
            assert gone not in section, gone


# ---------------------------------------------------------------------------
# customize.toml — default_threshold comment references full precedence
# ---------------------------------------------------------------------------


class TestCustomizeTomlPrecedence:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(CUSTOMIZE_TOML)

    def test_comment_references_per_pipeline(self, text: str) -> None:
        assert "per-pipeline" in text, (
            "customize.toml default_threshold comment must reference per-pipeline defaults"
        )

    def test_comment_references_init_md_1b(self, text: str) -> None:
        assert "init.md §1b" in text, (
            "customize.toml must reference init.md §1b lookup table"
        )

    @staticmethod
    def _comment(text: str) -> str:
        block = text[text.index("# Pass threshold"):text.index('\ndefault_threshold = ""')]
        return _flow(re.sub(r"(?m)^#\s?", "", block))

    def test_full_precedence_chain_in_comment(self, text: str) -> None:
        assert ("Precedence: CLI `--threshold=<N>` > this scalar > per-pipeline defaults > bundled 80."
                in self._comment(text)), "customize.toml comment must document the order init.md §1b resolves"

    def test_default_threshold_ships_empty(self, text: str) -> None:
        assert re.search(r'^default_threshold = ""$', text, re.MULTILINE), (
            "default_threshold ships empty, so only an override binds {defaultThreshold}")
        assert "Empty (the default) leaves it to the pipeline's default" in self._comment(text)

    def test_a_raised_value_never_turns_a_pass_into_a_fail(self, text: str) -> None:
        """A threshold above 80 is a target: the threshold fallback passes an uncapped run scoring 80 or more
        at any threshold, and a capped run fails at every one."""
        assert ("A value above 80 never turns a PASS into a FAIL: a run scoring 80 or more passes through the "
                "threshold fallback, and a run a cap forced to FAIL stays FAIL at any threshold.") in self._comment(text)
        compute = _load_compute_score().compute_score

        def verdict(threshold: int, tooling: str = "ok") -> str:
            out = compute({"mode": "naive", "tier": "Deep", "threshold": threshold, "toolingStatus": tooling,
                           "scores": {"exportCoverage": 85, "signatureAccuracy": 85, "typeCoverage": 85,
                                      "coherence": None, "externalValidation": 85}})
            return out.get("effectiveResult", out["result"])

        assert verdict(80) == verdict(90) == verdict(100) == "PASS"
        assert verdict(80, "frontmatter-validator-timeout") == verdict(90, "frontmatter-validator-timeout") == "FAIL"


# ---------------------------------------------------------------------------
# Forger SKILL.md — Pipeline Mode §4.c forwards pipeline_alias
# ---------------------------------------------------------------------------


class TestForgerPipelineAlias:
    """pipeline-mode.md step 4c is the one home of the {pipeline_alias} rule;
    the forger's SKILL.md only routes a chain there."""

    @pytest.fixture(scope="class")
    def pipeline_section(self) -> str:
        step = next(
            (line for line in _read(PIPELINE_MODE).splitlines() if "**Invoke the workflow**" in line),
            None,
        )
        assert step, "pipeline-mode.md must have step 4c, Invoke the workflow"
        return step

    def test_skill_md_routes_to_the_procedure(self) -> None:
        m = re.search(r"^## Pipeline Mode\s*$(.*?)(?=^## |\Z)", _read(FORGER_MD), re.M | re.S)
        assert m, "Forger SKILL.md must have a Pipeline Mode section"
        assert "`references/pipeline-mode.md`" in m.group(1)
        assert "{pipeline_alias}" not in m.group(1)

    def test_step_4c_mentions_pipeline_alias(self, pipeline_section: str) -> None:
        assert "{pipeline_alias}" in pipeline_section, (
            "Pipeline Mode §4.c must set {pipeline_alias} in workflow data context"
        )

    def test_step_4c_lists_alias_names(self, pipeline_section: str) -> None:
        for alias in ("forge-auto", "forge", "forge-quick", "maintain"):
            assert alias in pipeline_section, (
                f"Pipeline Mode §4.c must list '{alias}' as a possible alias value"
            )

    def test_null_for_ad_hoc(self, pipeline_section: str) -> None:
        assert re.search(
            r"null.*ad-hoc", pipeline_section, re.IGNORECASE
        ), "Pipeline Mode §4.c must specify null for ad-hoc sequences"


# ---------------------------------------------------------------------------
# pipeline-contracts.md — pipeline_alias in Pipeline State
# ---------------------------------------------------------------------------


class TestPipelineContractsPipelineAlias:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(PIPELINE_CONTRACTS)

    def test_pipeline_state_has_alias_field(self, text: str) -> None:
        state_match = re.search(
            r"## Pipeline State\b(.*?)(?=^## |\Z)",
            text,
            flags=re.MULTILINE | re.DOTALL,
        )
        assert state_match, "pipeline-contracts.md must have a Pipeline State section"
        section = state_match.group(1)
        assert "pipeline_alias" in section, (
            "Pipeline State must document pipeline_alias in data context"
        )

    def test_pipeline_alias_top_level(self, text: str) -> None:
        assert re.search(r"^\| `alias` \|[^\n]*pipeline alias", text, re.IGNORECASE | re.MULTILINE), (
            "Pipeline State must include alias at top level of pipeline state"
        )

    def test_pipeline_alias_in_data_context(self, text: str) -> None:
        assert re.search(
            r"data context carries[^\n]*`pipeline_alias`, the journal's `alias`", text
        ), "Pipeline State must forward the alias as pipeline_alias in each workflow's data context"

    def test_pipeline_alias_references_init_1b(self, text: str) -> None:
        assert re.search(r"init\.md §1b", text), (
            "pipeline-contracts.md must reference init.md §1b for threshold lookup"
        )


class TestPipelineContractsCircuitBreakers:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(PIPELINE_CONTRACTS)

    def test_ts_circuit_breaker_references_per_pipeline(self, text: str) -> None:
        cb_match = re.search(
            r"## Circuit Breakers\b(.*?)(?=^## |\Z)",
            text,
            flags=re.MULTILINE | re.DOTALL,
        )
        assert cb_match, "pipeline-contracts.md must have a Circuit Breakers section"
        section = cb_match.group(1)
        assert re.search(r"per-pipeline defaults", section), (
            "TS circuit breaker row must reference per-pipeline defaults"
        )


# ---------------------------------------------------------------------------
# Hard Gate Independence (AC #4)
# ---------------------------------------------------------------------------


class TestHardGateIndependence:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(HARD_GATE_FILE)

    def test_no_threshold_logic(self, text: str) -> None:
        threshold_refs = [
            (i + 1, line)
            for i, line in enumerate(text.splitlines())
            if "threshold" in line.lower()
            and "null" not in line.lower()
        ]
        assert not threshold_refs, (
            f"step-hard-gate.md must not contain threshold logic "
            f"(found at lines: {[r[0] for r in threshold_refs]})"
        )

    def test_no_pipeline_default_threshold(self, text: str) -> None:
        assert "pipeline_default_threshold" not in text, (
            "step-hard-gate.md must not reference pipeline_default_threshold"
        )

    def test_no_effective_threshold(self, text: str) -> None:
        assert "effective_threshold" not in text, (
            "step-hard-gate.md must not reference effective_threshold"
        )

    def test_no_threshold_source(self, text: str) -> None:
        assert "threshold_source" not in text, (
            "step-hard-gate.md must not reference threshold_source"
        )

    def test_severity_based_only(self, text: str) -> None:
        assert "Critical" in text and "High" in text, (
            "step-hard-gate.md must be severity-based (Critical/High), not threshold-based"
        )


# ---------------------------------------------------------------------------
# Cross-File Consistency
# ---------------------------------------------------------------------------


class TestCrossFileConsistency:
    def test_init_threshold_flag_references_1b(self) -> None:
        text = _read(INIT_FILE)
        threshold_line = [
            line for line in text.splitlines() if "--threshold" in line
        ]
        assert any("§1b" in line for line in threshold_line), (
            "init.md --threshold flag description must reference §1b"
        )

    def test_init_threshold_flag_references_per_pipeline(self) -> None:
        text = _read(INIT_FILE)
        threshold_line = [
            line for line in text.splitlines() if "--threshold" in line
        ]
        assert any("per-pipeline" in line for line in threshold_line), (
            "init.md --threshold flag description must reference per-pipeline defaults"
        )

    @staticmethod
    def _init_thresholds() -> dict[str, int]:
        """init.md §1b's lookup table: pipeline alias -> default threshold."""
        rows = re.findall(r"^\|\s*`([a-z-]+)`\s*\|\s*(\d+)\s*\|", _read(INIT_FILE), re.M)
        return {alias: int(n) for alias, n in rows}

    @staticmethod
    def _ts_min(alias: str) -> int | None:
        plan = parse_pipeline.parse_pipeline(alias)["plan"]
        return next(p["min"] for p in plan if p["code"] == "TS")

    def test_forge_auto_alias_threshold_matches_lookup_table(self) -> None:
        """ALIASES['forge-auto'] gates TS at init.md §1b's forge-auto value."""
        assert "TS[min:90]" in ALIASES["forge-auto"]
        assert self._ts_min("forge-auto") == self._init_thresholds()["forge-auto"] == 90

    def test_alias_gates_agree_with_lookup_table(self) -> None:
        """An alias that pins a TS gate pins the one init.md §1b maps it to;
        the others leave TS to that table (the pipeline default)."""
        table = self._init_thresholds()
        for alias in ALIASES:
            ts_min = self._ts_min(alias)
            if ts_min is not None:
                assert table.get(alias) == ts_min, (alias, ts_min, table.get(alias))

    def test_forge_alias_has_no_min_override(self) -> None:
        assert not any("min:" in token for token in ALIASES["forge"]), (
            "forge alias expansion must not include min: override (relies on pipeline default)"
        )
        assert self._ts_min("forge") is None

    def test_aliases_match_the_contracts_alias_table(self) -> None:
        """pipeline-contracts.md's alias table is the contract a reader sees:
        it must expand every alias as ALIASES, the parser's table, does."""
        rows = re.findall(r"^\|\s*`([a-z-]+)`\s*\|\s*`([^`]+)`\s*\|", _read(PIPELINE_CONTRACTS), re.M)
        assert {alias: expansion.split() for alias, expansion in rows} == ALIASES

    def test_forger_forwards_the_ts_gate_as_threshold(self) -> None:
        """The plan's TS min reaches TS as --threshold, the flag TS takes."""
        invoke = next(line for line in _read(PIPELINE_MODE).splitlines() if "**Invoke the workflow**" in line)
        assert "invoke TS with `--threshold=<min>`" in invoke
        # The flag TS takes is listed in its invocation contract (#600) and read by init.md §1b.
        assert "`--threshold=<N>`" in _read(CONTRACT_FILE) and "`--threshold=<N>`" in _read(INIT_FILE)

    def test_score_md_references_init_md_1b(self) -> None:
        score_text = _read(SCORE_FILE)
        assert "init.md §1b" in score_text, (
            "score.md must reference init.md §1b as the source of the pass threshold"
        )

    def test_init_md_mentions_pipeline_alias_in_the_pipeline_layer(self) -> None:
        layer, label = _ordered_layers()[2]
        assert "{pipeline_alias}" in layer and "{pipeline_alias}" in label, (
            "init.md §1b must reference {pipeline_alias} in the pipeline default layer"
        )

    def test_score_md_and_scoring_rules_restate_no_order(self) -> None:
        """#1189 leanness-8: score.md and scoring-rules.md point at init.md §1b without the old order."""
        score = _flow(_read(SCORE_FILE))
        assert "**The pass threshold was resolved once, at init** (init.md §1b), and init.md §6c wrote it" in score
        assert "CLI > pipeline default" not in score
        rules = _flow(_read(TS_DIR / "references" / "scoring-rules.md"))
        assert ("The pass threshold is the one init.md §1b resolves from `--threshold`, a `{defaultThreshold}` "
                "override, the pipeline's default and the bundled 80, which score.md §1 reads.") in rules
