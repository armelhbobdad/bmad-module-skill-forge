#!/usr/bin/env python3
"""skf-brief-drafts.py: the draft and the finished briefs that cover a Brief Skill target.

#1137 (determinism-4, enhancement-4): Brief Skill's draft-resume check found
a draft by grepping the draft files for the target as typed, then compared
`target_repo` or `doc_urls` and sorted by mtime by eye, so a trailing slash,
a `.git` suffix or a GitHub owner's letter case missed a draft, and a draft
beside a finished brief was dropped with no offer to revise that brief. The
helper normalizes the target as skf-resolve-package.py's parse-target reads
it: `find` prints the newest live draft for it, `briefs` the finished
briefs. These checks run it on each target variant, on the files it must
skip, and through the two calls step 1 documents, with a target that holds
a quote and a `$`.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
HELPER = REPO / "src" / "shared" / "scripts" / "skf-brief-drafts.py"
GATHER_INTENT = REPO / "src" / "skf-brief-skill" / "references" / "gather-intent.md"
BASH = shutil.which("bash")
# The documented blocks are POSIX shell; on Windows `bash` may be WSL's launcher.
POSIX_BASH = BASH is not None and sys.platform != "win32"
needs_bash = pytest.mark.skipif(not POSIX_BASH, reason="runs the documented block in a POSIX bash")
# A fenced bash block, at any indent.
BASH_BLOCK_RE = re.compile(r"^(?P<indent>[ \t]*)```bash\n(?P<body>.*?)^(?P=indent)```", re.DOTALL | re.M)

REPO_URL = "https://github.com/org/repo"
DOCS_URL = "https://docs.stripe.com/api"
# 2023-11-14T22:13:20Z and an hour later.
OLDER, NEWER = 1_700_000_000, 1_700_003_600


def _run(command: str, forge: Path, target: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(HELPER), command, "--forge-data", str(forge)],
                          input=target.encode("utf-8"), capture_output=True, timeout=120, check=False, cwd=cwd)


def _result(command: str, forge: Path, target: str, cwd: Path | None = None):
    proc = _run(command, forge, target, cwd)
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    return json.loads(proc.stdout)


def _draft(forge: Path, name: str, draft, mtime: float | None = None) -> Path:
    path = forge / name / ".brief-draft.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(draft if isinstance(draft, str) else json.dumps(draft), encoding="utf-8")
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


def _brief(forge: Path, name: str, text: str, mtime: float | None = None) -> Path:
    path = forge / name / "skill-brief.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


def _utc(stamp: float) -> str:
    return datetime.fromtimestamp(stamp, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------
# find: one normalized target, whatever way it is written
# --------------------------------------------------------------------------


@pytest.mark.parametrize("target", [
    "HTTPS://GitHub.com/Org/Repo.git/",
    "https://github.com/org/repo/",
    "https://github.com/org/repo.git",
    "https://www.github.com/Org/Repo",
    "github.com/org/repo",
    "org/repo",
    "Org/Repo",
    "git@github.com:Org/Repo.git",
    "https://github.com/org/repo/tree/main/packages/core",
    "  https://github.com/org/repo  \n",
])
def test_find_matches_a_github_target_however_it_is_written(tmp_path, target):
    forge = tmp_path / "forge"
    path = _draft(forge, "zod", {"target_repo": REPO_URL, "intent": "the schemas"}, OLDER)
    assert _result("find", forge, target) == {"name": "zod", "path": str(path), "mtime": _utc(OLDER),
                                              "holds_scope": False}


@pytest.mark.parametrize("target", ["https://Docs.Stripe.com/api/", "https://docs.stripe.com/api#charges",
                                    "HTTPS://DOCS.STRIPE.COM/api", "http://docs.stripe.com/api/",
                                    "docs.stripe.com/api"])
def test_find_matches_a_docs_only_target_on_a_doc_url(tmp_path, target):
    forge = tmp_path / "forge"
    _draft(forge, "stripe", {"source_type": "docs-only", "doc_urls": [{"url": "https://example.com/other"},
                                                                       {"url": DOCS_URL, "label": "API"}]})
    assert _result("find", forge, target)["name"] == "stripe"


def test_a_url_only_in_the_intent_or_description_never_matches(tmp_path):
    forge = tmp_path / "forge"
    _draft(forge, "other", {"target_repo": "https://github.com/acme/other", "intent": f"like {REPO_URL}",
                            "description": f"Wraps {DOCS_URL}. Use when ...", "doc_urls": [{"label": DOCS_URL}]})
    assert _result("find", forge, REPO_URL) is None
    assert _result("find", forge, DOCS_URL) is None
    # The path and the query of a docs URL still tell two pages apart.
    _draft(forge, "stripe", {"source_type": "docs-only", "doc_urls": [{"url": DOCS_URL}]})
    assert _result("find", forge, DOCS_URL + "/charges") is None
    assert _result("find", forge, DOCS_URL + "?lang=py") is None


def test_a_source_draft_or_brief_never_matches_on_its_supplemental_doc_urls(tmp_path):
    """A source skill's doc URLs are reading material, not its target: a docs-only target for the page a source
    draft lists, or a repo another draft lists as a doc, is not offered that draft or that brief."""
    forge = tmp_path / "forge"
    _draft(forge, "stripe-node", {"target_repo": "https://github.com/stripe/stripe-node", "source_type": "source",
                                  "doc_urls": [{"url": DOCS_URL}], "scope": {"type": "full-library"}})
    _draft(forge, "repo-plugin", {"target_repo": "https://github.com/acme/repo-plugin",
                                  "doc_urls": [{"url": REPO_URL}]})
    _brief(forge, "stripe-node-done", f"name: stripe-node-done\nsource_repo: https://github.com/stripe/stripe-node\n"
                                      f"doc_urls:\n  - url: {DOCS_URL}\n")
    assert _result("find", forge, DOCS_URL) is None and _result("find", forge, REPO_URL) is None
    assert _result("briefs", forge, DOCS_URL) == []


def test_find_matches_a_local_path_given_relative_or_absolute(tmp_path):
    work = tmp_path / "work"
    library = work / "libs" / "mylib"
    library.mkdir(parents=True)
    forge = tmp_path / "forge"
    _draft(forge, "mylib", {"target_repo": str(library)})
    for target in ("libs/mylib", "./libs/mylib/", str(library), f"file://{library}"):
        assert _result("find", forge, target, cwd=work)["name"] == "mylib", target
    # From another folder the same relative path names another place.
    assert _result("find", forge, "libs/mylib", cwd=tmp_path) is None


def test_find_expands_a_home_folder_target(tmp_path):
    home = tmp_path / "home"
    library = home / "libs" / "mylib"
    library.mkdir(parents=True)
    forge = tmp_path / "forge"
    _draft(forge, "mylib", {"target_repo": str(library)})
    env = {**os.environ, "HOME": str(home), "USERPROFILE": str(home)}  # USERPROFILE is the home folder on Windows
    proc = subprocess.run([sys.executable, str(HELPER), "find", "--forge-data", str(forge)],
                          input=b"~/libs/mylib", capture_output=True, timeout=120, check=False, cwd=tmp_path, env=env)
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    assert json.loads(proc.stdout)["name"] == "mylib"


def test_a_non_ascii_target_is_read_as_utf8_under_a_cp1252_console(tmp_path):
    """A Windows pipe hands stdin over as cp1252: the UTF-8 target step 1 pipes still finds its draft."""
    work = tmp_path / "work"
    library = work / "libs" / "café"
    library.mkdir(parents=True)
    forge = tmp_path / "forge"
    _draft(forge, "cafe", {"target_repo": str(library)})
    env = {**os.environ, "PYTHONIOENCODING": "cp1252"}
    proc = subprocess.run([sys.executable, str(HELPER), "find", "--forge-data", str(forge)],
                          input="libs/café".encode("utf-8"), capture_output=True, timeout=120, check=False,
                          cwd=work, env=env)
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    assert json.loads(proc.stdout.decode("ascii"))["name"] == "cafe"


def test_find_skips_a_folder_that_holds_a_finished_brief(tmp_path):
    forge = tmp_path / "forge"
    _draft(forge, "zod", {"target_repo": REPO_URL})
    _brief(forge, "zod", f"name: zod\nsource_repo: {REPO_URL}\n")
    assert _result("find", forge, REPO_URL) is None
    assert [entry["name"] for entry in _result("briefs", forge, REPO_URL)] == ["zod"]


def test_find_prints_the_newest_draft_then_the_first_name(tmp_path):
    forge = tmp_path / "forge"
    _draft(forge, "zod-old", {"target_repo": REPO_URL}, OLDER)
    _draft(forge, "zod", {"target_repo": "org/repo"}, NEWER)
    assert _result("find", forge, REPO_URL)["name"] == "zod"
    _draft(forge, "zod-old", {"target_repo": REPO_URL}, NEWER + 60)
    assert _result("find", forge, REPO_URL) == {"name": "zod-old", "mtime": _utc(NEWER + 60), "holds_scope": False,
                                               "path": str(forge / "zod-old" / ".brief-draft.json")}
    # Two drafts saved in the same second: the folder name decides, so the pick never depends on the file system.
    _draft(forge, "zod", {"target_repo": REPO_URL}, NEWER + 60)
    assert _result("find", forge, REPO_URL)["name"] == "zod"


@pytest.mark.parametrize("scope,holds", [({"type": "public-api", "include": ["src/**"]}, True), (None, False),
                                         ("public-api", False)])
def test_holds_scope_says_whether_step_three_wrote_the_draft(tmp_path, scope, holds):
    forge = tmp_path / "forge"
    draft = {"target_repo": REPO_URL}
    if scope is not None:
        draft["scope"] = scope
    _draft(forge, "zod", draft)
    assert _result("find", forge, REPO_URL)["holds_scope"] is holds


@pytest.mark.parametrize("content", ["{not json", "[]", '"https://github.com/org/repo"', "null", ""])
def test_a_draft_that_is_not_a_json_object_is_skipped(tmp_path, content):
    forge = tmp_path / "forge"
    _draft(forge, "broken", content, NEWER)
    _draft(forge, "zod", {"target_repo": REPO_URL}, OLDER)
    assert _result("find", forge, REPO_URL)["name"] == "zod"


def test_no_match_and_a_missing_folder_print_null_and_an_empty_list(tmp_path):
    forge = tmp_path / "forge"
    _draft(forge, "other", {"target_repo": "https://github.com/acme/other"})
    _brief(forge, "other", "name: other\nsource_repo: https://github.com/acme/other\n")
    assert _result("find", forge, REPO_URL) is None and _result("briefs", forge, REPO_URL) == []
    missing = tmp_path / "no-such-folder"
    assert _result("find", missing, REPO_URL) is None and _result("briefs", missing, REPO_URL) == []


@pytest.mark.parametrize("command", ["find", "briefs"])
@pytest.mark.parametrize("target", ["", "   \n", "\n\n"])
def test_an_empty_target_exits_two_with_an_error_object(tmp_path, command, target):
    proc = _run(command, tmp_path, target)
    assert proc.returncode == 2 and proc.stdout.strip() == b""
    assert set(json.loads(proc.stderr)) == {"error"}


# --------------------------------------------------------------------------
# briefs: the finished briefs, read as the validator reads them
# --------------------------------------------------------------------------


def test_briefs_lists_every_finished_brief_for_the_target_newest_first(tmp_path):
    forge = tmp_path / "forge"
    _brief(forge, "zod", f"name: zod\nsource_repo: {REPO_URL}.git\nscope:\n  type: full-library\n", OLDER)
    # An SKF 1.x brief closed with `---`, which the validator's reader takes.
    _brief(forge, "zod-v4", "name: zod-v4\nsource_repo: https://GitHub.com/Org/Repo\n---\n", NEWER)
    _brief(forge, "stripe", f"name: stripe\nsource_type: docs-only\ndoc_urls:\n  - url: {DOCS_URL}/\n", NEWER)
    found = _result("briefs", forge, "org/repo")
    assert [entry["name"] for entry in found] == ["zod-v4", "zod"]
    assert found[1] == {"name": "zod", "path": str(forge / "zod" / "skill-brief.yaml"), "mtime": _utc(OLDER)}
    assert [entry["name"] for entry in _result("briefs", forge, "https://Docs.Stripe.com/api")] == ["stripe"]


@pytest.mark.parametrize("text", ["name: [unclosed\n", "- a list\n- not a mapping\n", "", "name: a\n---\nname: b\n"])
def test_a_brief_that_does_not_parse_as_one_mapping_is_skipped(tmp_path, text):
    forge = tmp_path / "forge"
    _brief(forge, "broken", text + f"# {REPO_URL}\n", NEWER)
    _brief(forge, "zod", f"name: zod\nsource_repo: {REPO_URL}\n", OLDER)
    assert [entry["name"] for entry in _result("briefs", forge, REPO_URL)] == ["zod"]


def test_briefs_matches_the_target_fields_only(tmp_path):
    forge = tmp_path / "forge"
    _brief(forge, "other", f"name: other\nsource_repo: https://github.com/acme/other\ndescription: like {REPO_URL}\n")
    assert _result("briefs", forge, REPO_URL) == []


# --------------------------------------------------------------------------
# The two calls step 1 documents
# --------------------------------------------------------------------------


def _documented_blocks() -> dict[str, str]:
    """The command word -> the ```bash block of gather-intent.md that runs the helper with it."""
    blocks = {}
    for match in BASH_BLOCK_RE.finditer(GATHER_INTENT.read_text(encoding="utf-8")):
        body = match.group("body")
        if "{briefDraftsHelper}" in body:
            command = body.split()[3]
            assert command not in blocks, command
            blocks[command] = body
    return blocks


def test_step_one_documents_both_calls_with_the_target_in_a_quoted_heredoc():
    blocks = _documented_blocks()
    assert sorted(blocks) == ["briefs", "find"]
    for command, body in blocks.items():
        assert body == (f'uv run {{briefDraftsHelper}} {command} --forge-data "{{forge_data_folder}}" '
                        "<<'SKF_TARGET'\n{target}\nSKF_TARGET\n"), body
    text = GATHER_INTENT.read_text(encoding="utf-8")
    assert re.search(r"^briefDraftsProbeOrder:\n  - '\{project-root\}/_bmad/skf/shared/scripts/skf-brief-drafts\.py'\n"
                     r"  - '\{project-root\}/src/shared/scripts/skf-brief-drafts\.py'\n", text, re.M)


@needs_bash
def test_the_documented_calls_keep_a_quote_and_a_dollar_in_the_target(tmp_path):
    work = tmp_path / "work"
    library = work / "it's-$HOME"
    library.mkdir(parents=True)
    forge = tmp_path / "forge data"
    _draft(forge, "draft", {"target_repo": str(library), "scope": {"type": "full-library"}})
    _brief(forge, "done", f"name: done\nsource_repo: {json.dumps(str(library))}\n")
    blocks = _documented_blocks()
    out = {}
    for command, body in blocks.items():
        script = (body.replace("uv run {briefDraftsHelper}", f'"{sys.executable}" "{HELPER.as_posix()}"')
                  .replace("{forge_data_folder}", forge.as_posix()).replace("{target}", "./it's-$HOME"))
        proc = subprocess.run([BASH, "-c", script], capture_output=True, text=True, encoding="utf-8", timeout=120,
                              check=False, cwd=work)
        assert proc.returncode == 0, proc.stderr
        out[command] = json.loads(proc.stdout)
    assert out["find"]["name"] == "draft" and out["find"]["holds_scope"] is True
    assert [entry["name"] for entry in out["briefs"]] == ["done"]
