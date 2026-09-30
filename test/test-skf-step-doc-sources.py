"""Structural integration tests for the step-doc-sources.md step file (story 1.3).

Validates the doc-sources step contract: correct pipeline wiring, required
sections, script reference integrity, doc_sources schema completeness in
skill-sections.md, and stages-table positioning.  Chain-reachability tests
cover link resolution; these tests cover the semantic contract.

The README entry §3 adds comes from one skf-detect-docs.py readme-entry
call: the raw GitHub file at the ref step 3 resolved (a file:// URL for a
local source), README.md picked before a translation. Run as the step writes
it, its hash equals what audit-skill's compare-hashes computes for the same
bytes, from a web server or a local file.
"""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import re
import shlex
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CS_DIR = REPO_ROOT / "src" / "skf-create-skill"
STEP_FILE = CS_DIR / "references" / "step-doc-sources.md"
COMPILE_FILE = CS_DIR / "references" / "compile.md"
SKILL_MD = CS_DIR / "SKILL.md"
SECTIONS_FILE = CS_DIR / "assets" / "skill-sections.md"
FETCH_DOCS_FILE = CS_DIR / "references" / "sub" / "fetch-docs.md"
DETECT_DOCS_SCRIPT = REPO_ROOT / "src" / "shared" / "scripts" / "skf-detect-docs.py"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def _frontmatter(path: pathlib.Path) -> str | None:
    text = _read(path)
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    return m.group(1) if m else None


def _next_step_value(path: pathlib.Path) -> str | None:
    fm = _frontmatter(path)
    if fm is None:
        return None
    m = re.search(r"^nextStepFile:\s*['\"]?([^'\"\n]+?)['\"]?\s*$", fm, re.MULTILINE)
    return m.group(1).strip() if m else None


def _section(text: str, heading_regex: str) -> str:
    """Body of the `### <heading>` section whose heading matches heading_regex."""
    m = re.search(
        rf"^###\s+{heading_regex}[^\n]*\n(.*?)(?=^###\s|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert m, f"section not found: {heading_regex}"
    return m.group(1)


# ---------------------------------------------------------------------------
# Step file existence
# ---------------------------------------------------------------------------


def test_step_file_exists() -> None:
    assert STEP_FILE.exists(), "step-doc-sources.md must exist"


# ---------------------------------------------------------------------------
# Pipeline chain values
# ---------------------------------------------------------------------------


class TestPipelineChain:
    def test_compile_points_to_step_doc_sources(self) -> None:
        assert _next_step_value(COMPILE_FILE) == "step-doc-sources.md"

    def test_step_doc_sources_points_to_auto_shard(self) -> None:
        assert _next_step_value(STEP_FILE) == "step-auto-shard.md"

    def test_auto_shard_exists(self) -> None:
        target = (STEP_FILE.parent / "step-auto-shard.md").resolve()
        assert target.exists(), "step-auto-shard.md must exist for the chain to complete"


# ---------------------------------------------------------------------------
# Step file structural contract
# ---------------------------------------------------------------------------


class TestStepFileStructure:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(STEP_FILE)

    def test_has_step_goal_section(self, text: str) -> None:
        assert re.search(r"^##\s+STEP GOAL", text, re.MULTILINE | re.IGNORECASE)

    def test_has_rules_section(self, text: str) -> None:
        assert re.search(r"^##\s+Rules\b", text, re.MULTILINE | re.IGNORECASE)

    def test_has_mandatory_sequence_section(self, text: str) -> None:
        assert re.search(
            r"^##\s+MANDATORY SEQUENCE", text, re.MULTILINE | re.IGNORECASE
        )

    @pytest.mark.parametrize(
        "substep",
        [
            "Check for Upstream Doc Detection Results",
            "Run Doc Detection",
            "Ensure README Entry",
            "Build doc_sources Array",
            "Update metadata.json",
            "Auto-Proceed",
        ],
    )
    def test_mandatory_sequence_substeps(self, text: str, substep: str) -> None:
        assert substep in text, f"MANDATORY SEQUENCE must include substep: {substep}"

    def test_graceful_failure_rule(self, text: str) -> None:
        assert "graceful" in text.lower(), (
            "step must document graceful failure behaviour"
        )

    def test_no_user_interaction_rule(self, text: str) -> None:
        assert re.search(r"auto.proceed|no user interaction", text, re.IGNORECASE), (
            "step must be auto-proceed (no user interaction)"
        )


# ---------------------------------------------------------------------------
# Script reference integrity
# ---------------------------------------------------------------------------


class TestScriptReference:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(STEP_FILE)

    def test_references_detect_docs_script(self, text: str) -> None:
        assert "skf-detect-docs.py" in text, (
            "step must reference the detect-docs script"
        )

    def test_detect_docs_script_exists(self) -> None:
        assert DETECT_DOCS_SCRIPT.exists(), (
            "skf-detect-docs.py must exist on disk"
        )

    def test_references_uv_run_invocation(self, text: str) -> None:
        assert "uv run" in text, "step must invoke script via uv run"

    def test_documents_exit_codes(self, text: str) -> None:
        for code in ("Exit 0", "Exit 1", "Exit 2"):
            assert code in text, f"step must document {code} handling"


# ---------------------------------------------------------------------------
# doc_sources schema in skill-sections.md
# ---------------------------------------------------------------------------


class TestDocSourcesSchema:
    @pytest.fixture(scope="class")
    def schema_text(self) -> str:
        return _read(SECTIONS_FILE)

    def test_doc_sources_field_present(self, schema_text: str) -> None:
        assert "doc_sources" in schema_text

    @pytest.mark.parametrize(
        "field",
        ["url", "detected_via", "content_hash", "recorded_at"],
    )
    def test_schema_has_required_field(self, schema_text: str, field: str) -> None:
        doc_src_line = [
            line for line in schema_text.splitlines() if "doc_sources" in line
        ]
        assert any(field in line for line in doc_src_line), (
            f"doc_sources schema must include field: {field}"
        )

    def test_detected_via_includes_readme_always(self, schema_text: str) -> None:
        assert "readme_always" in schema_text, (
            "doc_sources schema must include readme_always in detected_via enum"
        )

    _EXPECTED_DETECTED_VIA = [
        "homepageUrl",
        "readme_link",
        "pages_api",
        "docs_folder",
        "readme_always",
        "brief_doc_urls",
    ]

    @pytest.mark.parametrize("value", _EXPECTED_DETECTED_VIA)
    def test_detected_via_enum_coverage(self, schema_text: str, value: str) -> None:
        assert value in schema_text, (
            f"doc_sources schema must list detected_via value: {value}"
        )

    def test_doc_sources_before_generated_by(self, schema_text: str) -> None:
        doc_idx = schema_text.find("doc_sources")
        gen_idx = schema_text.find('"generated_by"')
        assert doc_idx < gen_idx, (
            "doc_sources must appear before generated_by in schema ordering"
        )


# ---------------------------------------------------------------------------
# Docs-only branch (#475): doc_sources for a brief with no repository
# ---------------------------------------------------------------------------


class TestDocsOnlyBranch:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(STEP_FILE)

    def test_detection_is_gated_on_source_type(self, text: str) -> None:
        body = _section(text, r"2\.\s+Run Doc Detection")
        assert "docs-only" in body, (
            "§2 must branch on source_type docs-only before invoking detect-docs "
            "(its --repo-url path rejects a documentation-site URL as INVALID_URL)"
        )

    def test_docs_only_branch_hashes_via_hash_urls(self, text: str) -> None:
        body = _section(text, r"2a\.")
        assert "hash-urls" in body, (
            "the docs-only branch must hash the brief's doc_urls through "
            "skf-detect-docs.py hash-urls (byte-symmetric with the audit's compare-hashes)"
        )

    def test_docs_only_branch_records_brief_doc_urls_provenance(self, text: str) -> None:
        assert "brief_doc_urls" in _section(text, r"2a\.")

    def test_docs_only_branch_documents_exit_codes(self, text: str) -> None:
        body = _section(text, r"2a\.")
        for code in ("Exit 0", "Exit 2"):
            assert code in body, f"§2a must document {code} handling"

    def test_readme_entry_is_skipped_for_docs_only(self, text: str) -> None:
        body = _section(text, r"3\.\s+Ensure README Entry")
        assert "docs-only" in body, (
            "§3 must skip the README entry for docs-only briefs — there is no "
            "repository README, and {source_repo}/blob/main/README.md would be fabricated"
        )


# ---------------------------------------------------------------------------
# Docs-only corpus retention (#476): fetch-docs must not delete the only source
# ---------------------------------------------------------------------------


class TestDocsOnlyCorpusRetention:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(FETCH_DOCS_FILE)

    def test_cleanup_is_gated_on_source_type(self, text: str) -> None:
        cleanup_lines = [
            line
            for line in text.splitlines()
            if "rm -rf" in line and "{skill-name}-docs" in line
        ]
        assert len(cleanup_lines) == 1, (
            "expected exactly one staging-directory cleanup instruction in fetch-docs.md"
        )
        assert "docs-only" in cleanup_lines[0], (
            "the cleanup must be gated on source_type so a docs-only corpus is retained"
        )

    def test_rules_forbid_deleting_docs_only_corpus(self, text: str) -> None:
        rules = re.search(r"^## Rules\n(.*?)(?=^## )", text, re.MULTILINE | re.DOTALL)
        assert rules and "docs-only" in rules.group(1), (
            "fetch-docs.md Rules must state that a docs-only staging directory is never deleted"
        )


# ---------------------------------------------------------------------------
# Stages table in SKILL.md
# ---------------------------------------------------------------------------


class TestStagesTable:
    @pytest.fixture(scope="class")
    def stages_section(self) -> str:
        text = _read(SKILL_MD)
        m = re.search(
            r"^## Stages\b(.*?)(?=^## )", text, flags=re.MULTILINE | re.DOTALL
        )
        assert m, "SKILL.md must have a ## Stages section"
        return m.group(1)

    def test_step_5a_present(self, stages_section: str) -> None:
        assert re.search(
            r"\|\s*5a\s*\|", stages_section
        ), "Stages table must include step 5a"

    def test_step_5a_name_is_doc_sources(self, stages_section: str) -> None:
        assert re.search(
            r"\|\s*5a\s*\|\s*Doc Sources\s*\|", stages_section
        ), "Step 5a must be named 'Doc Sources'"

    def test_step_5a_file_path(self, stages_section: str) -> None:
        assert re.search(
            r"\|\s*5a\s*\|.*references/step-doc-sources\.md", stages_section
        ), "Step 5a must reference references/step-doc-sources.md"

    def test_step_5a_between_compile_and_validate(self, stages_section: str) -> None:
        rows = [
            line.strip()
            for line in stages_section.splitlines()
            if line.strip().startswith("|") and not line.strip().startswith("|-")
        ]
        step_nums = []
        for row in rows:
            m = re.match(r"\|\s*(\w+)\s*\|", row)
            if m and m.group(1) not in ("#", "---"):
                step_nums.append(m.group(1))
        assert "5a" in step_nums, "Step 5a must be in the stages table"
        idx_5a = step_nums.index("5a")
        idx_5 = step_nums.index("5") if "5" in step_nums else None
        idx_6 = step_nums.index("6") if "6" in step_nums else None
        assert idx_5 is not None and idx_5 < idx_5a, (
            "Step 5a must come after step 5 (Compile)"
        )
        assert idx_6 is not None and idx_5a < idx_6, (
            "Step 5a must come before step 6 (Validate)"
        )


# ---------------------------------------------------------------------------
# README entry (#592): the raw file at the resolved ref, built by readme-entry
# ---------------------------------------------------------------------------


def _readme_section() -> str:
    return _section(_read(STEP_FILE), r"3\.\s+Ensure README Entry")


def _readme_command() -> str:
    """The fenced readme-entry command §3 runs."""
    [fence] = re.findall(r"```bash\n(.*?)```", _readme_section(), re.DOTALL)
    return fence.strip()


def _documented_argv(source_repo: str, source_ref: str, source_root: str | None) -> list[str]:
    """§3's command filled in as its "Pass `--local-root`" sentence says, without `uv run {detectDocsHelper}`."""
    command = _readme_command().replace("uv run {detectDocsHelper} ", "", 1)
    command = re.sub(r"\[([^\[\]]*)\]", lambda m: m.group(1) if source_root is not None else "", command)
    for key, value in {"{source_repo}": source_repo, "{source_ref}": source_ref,
                       "{source_root}": source_root or ""}.items():
        command = command.replace(key, value)
    assert "{" not in command, command
    return shlex.split(command)


def _no_proxy_env() -> dict:
    env = {k: v for k, v in os.environ.items() if k.lower() not in ("http_proxy", "https_proxy", "all_proxy")}
    env["NO_PROXY"] = env["no_proxy"] = "*"
    return env


def _helper(*argv: str, stdin: str = "", raw_base: str | None = None) -> dict:
    """Run skf-detect-docs.py; with raw_base, its GitHub raw-file host is that local server."""
    if raw_base is None:
        command = [sys.executable, str(DETECT_DOCS_SCRIPT), *argv]
    else:
        code = (
            "import importlib.util, sys\n"
            f"spec = importlib.util.spec_from_file_location('skf_detect_docs', {str(DETECT_DOCS_SCRIPT)!r})\n"
            "m = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(m)\n"
            f"m.RAW_GITHUB = {raw_base!r}\n"
            f"sys.argv = ['skf-detect-docs.py', *{list(argv)!r}]\n"
            "raise SystemExit(m.main())\n"
        )
        command = [sys.executable, "-c", code]
    proc = subprocess.run(command, input=stdin.encode("utf-8"), capture_output=True, env=_no_proxy_env(),
                          timeout=60)
    assert proc.returncode == 0, proc.stderr.decode("utf-8", errors="replace")
    return json.loads(proc.stdout.decode("utf-8"))


def _audit(entries: list) -> dict:
    """What audit-skill's doc-drift step runs on the recorded entries."""
    return _helper("compare-hashes", "-", stdin=json.dumps({"doc_sources": entries}))


def _detect_docs():
    spec = importlib.util.spec_from_file_location("skf_detect_docs_readme", DETECT_DOCS_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def raw_host():
    """A local stand-in for raw.githubusercontent.com: path -> bytes, served as they are."""
    files: dict[str, bytes] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 (http.server's name)
            body = files.get(self.path)
            self.send_response(200 if body is not None else 404)
            self.end_headers()
            self.wfile.write(body if body is not None else b"404: Not Found")

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", files
    finally:
        server.shutdown()
        server.server_close()


def _tree(root: pathlib.Path, files: dict[str, bytes]) -> pathlib.Path:
    root.mkdir(parents=True)
    for name, body in files.items():
        (root / name).write_bytes(body)
    return root


class TestReadmeEntry:
    def test_one_helper_call_builds_and_hashes_the_entry(self) -> None:
        section = _readme_section()
        assert _readme_command() == ('uv run {detectDocsHelper} readme-entry --source-repo "{source_repo}" '
                                     '--ref "{source_ref}" [--local-root "{source_root}"]')
        assert "Pass `--local-root` when `{source_root}` is a local folder" in section
        assert "add each entry of its `doc_sources`, at most one, as the helper wrote it" in section
        assert "When `skip_reason` is `not-github`, `doc_sources` is empty" in section
        # The helper parses the repository, picks the README and builds the URL: none of it is prose.
        for by_hand in ("hexdigest", "base64-decode", "repos/{owner}/{repo}", "sha256", "raw.githubusercontent",
                        "{readme_name}", "{readme_url}", "{owner}", "hash-urls"):
            assert by_hand not in section, by_hand
        for code in ("**Exit 0:**", "**Exit 2:**"):
            assert code in section, code
        assert "/blob/main/" not in _read(STEP_FILE)

    def test_detection_gets_no_path_into_the_private_tree(self) -> None:
        detection = _section(_read(STEP_FILE), r"2\.\s+Run Doc Detection")
        assert "--local-path" not in re.search(r"```bash\n(.*?)```", detection, re.DOTALL).group(1)
        assert "Pass no `--local-path`" in detection
        assert "{source_path}" not in _read(STEP_FILE)

    @pytest.mark.parametrize("source_repo", [
        "https://github.com/acme/lib", "https://github.com/acme/lib.git", "https://github.com/acme/lib/",
        "http://www.github.com/acme/lib", "git@github.com:acme/lib.git", "ssh://git@github.com/acme/lib.git",
        "github.com/acme/lib", "acme/lib",
    ], ids=["https", "dot-git", "slash", "www", "scp", "ssh", "no-scheme", "shorthand"])
    def test_every_github_form_names_the_repository(self, source_repo: str) -> None:
        assert _detect_docs().parse_github_repo(source_repo) == ("acme", "lib")

    def test_a_repository_name_keeps_its_dots_and_other_hosts_are_not_github(self) -> None:
        detect_docs = _detect_docs()
        assert detect_docs.parse_github_repo("https://github.com/vercel/next.js") == ("vercel", "next.js")
        for other in ("https://gitlab.com/acme/lib", "https://github.com/acme/lib/tree/main", "./packages/lib"):
            assert detect_docs.parse_github_repo(other) is None, other

    @pytest.mark.parametrize("names, picked", [
        (["README-zh_CN.md", "README.md", "README-ja.md"], "README.md"),
        (["README.zh-CN.md", "readme.md"], "readme.md"),
        (["README-ja.md", "README.rst"], "README.rst"),
        (["README-ja.md", "README"], "README"),
        (["README.en.md", "README-ja.md"], "README-ja.md"),
        (["setup.py", "LICENSE"], None),
    ], ids=["md-over-translations", "any-case", "plain-rst", "no-extension", "translations-only", "none"])
    def test_readme_md_comes_before_a_translation(self, names: list[str], picked: str | None) -> None:
        assert _detect_docs().pick_readme(names) == picked

    def test_name_order_alone_would_pick_the_translation(self) -> None:
        """`-` sorts before `.`: the first README by name is README-zh_CN.md, not README.md."""
        names = ["README.md", "README-zh_CN.md"]
        assert sorted(names)[0] == "README-zh_CN.md"
        assert _detect_docs().pick_readme(names) == "README.md"

    def test_github_source_records_the_raw_file_at_the_resolved_ref(self, raw_host, tmp_path) -> None:
        base, files = raw_host
        tree = _tree(tmp_path / "tree", {"README.md": b"# lib\r\n\nUse `lib.run()`.\n", "README-zh_CN.md": b"zh\n"})
        files["/acme/lib/v1.2.0/README.md"] = b"# lib\r\n\nUse `lib.run()`.\n"
        out = _helper(*_documented_argv("https://github.com/acme/lib.git", "v1.2.0", tree.as_posix()),
                      raw_base=base)
        [entry] = out["doc_sources"]
        assert out["skip_reason"] is None
        assert entry["url"] == f"{base}/acme/lib/v1.2.0/README.md"
        assert entry["detected_via"] == "readme_always" and entry["content_hash"].startswith("sha256:")
        assert set(entry) == {"url", "detected_via", "content_hash", "recorded_at"}
        assert _audit([entry])["stats"]["unchanged"] == 1
        files["/acme/lib/v1.2.0/README.md"] = b"# lib\n\nUse `lib.start()`.\n"
        assert [c["url"] for c in _audit([entry])["changed"]] == [entry["url"]]

    def test_a_scoped_tag_stays_readable_in_the_url(self, tmp_path) -> None:
        tree = _tree(tmp_path / "tree", {"README.rst": b"lib\n"})
        url = _detect_docs().readme_url("acme/lib", "lib@2.0.0", tree.as_posix())
        assert url == "https://raw.githubusercontent.com/acme/lib/lib@2.0.0/README.rst"

    def test_missing_readme_gets_a_null_hash_the_audit_skips(self, raw_host, tmp_path) -> None:
        base, _files = raw_host
        tree = _tree(tmp_path / "tree", {"setup.py": b""})
        out = _helper(*_documented_argv("acme/lib", "HEAD", tree.as_posix()), raw_base=base)
        [entry] = out["doc_sources"]
        assert entry["url"] == f"{base}/acme/lib/HEAD/README.md" and entry["content_hash"] is None
        assert _audit([entry])["skipped_null_hash"] == [{"url": entry["url"]}]

    def test_local_readme_round_trips_through_a_file_url(self, tmp_path) -> None:
        source = _tree(tmp_path / "src dir", {"README.rst": b"lib\n===\n", "README-ja.rst": b"ja\n"})
        out = _helper(*_documented_argv(source.as_posix(), "local", source.as_posix()))
        [entry] = out["doc_sources"]
        # Written as the helper reads it back: the path after file://, never percent-encoded.
        assert entry["url"] == "file://" + (source / "README.rst").as_posix()
        assert entry["content_hash"].startswith("sha256:")
        assert _audit([entry])["stats"]["unchanged"] == 1
        (source / "README.rst").write_bytes(b"lib 2\n=====\n")
        assert _audit([entry])["stats"]["changed"] == 1

    def test_another_host_gets_no_entry(self) -> None:
        out = _helper(*_documented_argv("https://gitlab.com/acme/lib", "v1.0.0", None))
        assert out["skip_reason"] == "not-github"
        assert out["doc_sources"] == [] and out["fetch_failed"] == []

    def test_without_a_local_folder_github_lists_the_top_level(self, monkeypatch) -> None:
        detect_docs = _detect_docs()
        calls = []

        def fake_gh(args):
            calls.append(args)
            return "README-ja.md\nREADME.rst\nsetup.py"

        monkeypatch.setattr(detect_docs, "_run_gh", fake_gh)
        assert detect_docs.readme_url("acme/lib", "lib@2.0.0") == (
            "https://raw.githubusercontent.com/acme/lib/lib@2.0.0/README.rst")
        assert calls[-1][:2] == ["api", "repos/acme/lib/contents?ref=lib%402.0.0"]
        assert detect_docs.readme_url("acme/lib", "HEAD").endswith("/acme/lib/HEAD/README.rst")
        assert calls[-1][1] == "repos/acme/lib/contents"
        monkeypatch.setattr(detect_docs, "_run_gh", lambda args: None)
        assert detect_docs.readme_url("acme/lib", "") == "https://raw.githubusercontent.com/acme/lib/HEAD/README.md"
