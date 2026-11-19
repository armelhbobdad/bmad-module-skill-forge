#!/usr/bin/env python3
"""#1253: update-skill's merge restates a joined prior gotchas pitfall's parts as SKILL.md bullets.

export-skill's generate-snippet.md §3a keeps a prior pitfall that joins several pitfalls (a line of more than
3 pieces `gotchas prior` reads whole, the `[CARRIED] a, b, c, d` value it reads back as, or an older `, `-joined
line) only while one T2-future annotation, or one bullet, row or Quick Start call of its source 2, states it
whole. When the merged SKILL.md states its parts only apart or in prose, write.md §5 marks it `[CARRIED]` and
the next export drops every pitfall on it. merge.md §3 Priority 9 runs write.md §5's `gotchas prior` call in
every mode and, for each such pitfall, writes each part SKILL.md still states, in its prior wording and with
the citation of the place that states it, as a bullet of SKILL.md's gotchas section or of a new `## Gotchas`
section before the first `## Full` heading, so §3a gives the bullets back as gotchas. A single prior pitfall
gets nothing: §3a's source 3 keeps it while SKILL.md states it anywhere (#1092).

Step prose is not executed by any test, so these checks pin Priority 9's clauses, run its documented call on
a fixture skill, and model its judgments and §3a's (as test-skf-export-terminal.py does), handing them to the
rebuild helper's `resolve_gotchas` for the update and the next export.

#1269: on an unchanged source detect-changes.md §4 runs the same call before its no-change shortcut and, when
Priority 9 would write a bullet, goes on to step 3 with the empty change manifest; `--detect-only` and
`--dry-run` keep the shortcut and warn `gotchas-not-restated`.
"""

from __future__ import annotations

import importlib.util
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
UPDATE_REFS = REPO / "src" / "skf-update-skill" / "references"
MERGE = UPDATE_REFS / "merge.md"
WRITE = UPDATE_REFS / "write.md"
REBUILD = REPO / "src" / "shared" / "scripts" / "skf-rebuild-managed-sections.py"
_RMS_SPEC = importlib.util.spec_from_file_location("skf_rms_update_restate_gotchas", REBUILD)
rms = importlib.util.module_from_spec(_RMS_SPEC)
_RMS_SPEC.loader.exec_module(rms)

EM_DASH = "\u2014"
P9_START = "**Priority 9:"
P9_END = "### 4. Check for Conflicts"
# write.md §5's `gotchas prior` call, which Priority 9 runs verbatim.
PRIOR_CALL = ('uv run {rebuildManagedSectionsHelper} gotchas prior "{skill_package}/context-snippet.md" '
              '--skills-folder "{skills_output_folder}" --skill {skill_name}')
PRIOR_CALL_RE = re.compile(r"uv run \{rebuildManagedSectionsHelper\} gotchas prior [^`\n]+")

HEADING_CLAUSE = "**Priority 9: Restate the prior snippet's joined gotchas (every mode):**"
RESOLVE_CLAUSE = ("resolve `{rebuildManagedSectionsHelper}` ← first existing path in "
                  "`{rebuildManagedSectionsProbeOrder}`")
BINDING_CLAUSE = "bind `prior_gotchas` ← its `prior_gotchas`"
CARRY_THEN_DROP_CLAUSE = ("otherwise the line carries it once and the next export drops it, although SKILL.md may "
                          "still state each pitfall it joins")
WHICH_CLAUSE = ("each entry, already carried or not, that joins several pitfalls that each warn on their own: one it "
                "marks `read_whole`, the one pitfall such a value reads back as once a run wrote it (its `; ` written "
                "as `, `), or an older line's pitfalls joined with `, `")
STATED_WHOLE_CLAUSE = ("Take it only when no T2-future annotation of `{forge_version}/evidence-report.md` (when it "
                       "does not exist, an older skill's flat `{forge_data_folder}/{skill_name}/evidence-report.md`, "
                       "which merge-write.md §6b copies), and no one such bullet, row or Quick Start call of the "
                       "merged SKILL.md, states it whole.")
ONE_PITFALL_CLAUSE = ("A prior pitfall that is one pitfall needs nothing: generate-snippet.md §3a keeps it while "
                      "SKILL.md states it anywhere.")
PARTS_CLAUSE = "for each pitfall it joins, in its order, one bullet in its prior wording without a `[CARRIED]` marker"
MAIN_CLAIM_CLAUSE = ("when the merged SKILL.md still states its main claim, no place in it contradicts that claim with "
                     "another version or name, and no T2-future annotation or such bullet, row or Quick Start call "
                     "states it yet")
CITATION_CLAUSE = ("End the bullet with the citation (`[AST:]`, `[SRC:]`, `[QMD:]` or `[EXT:]`) of the SKILL.md place "
                   "that states it.")
NOT_RESTATED_CLAUSE = ("Restate no pitfall that SKILL.md no longer states, states only in a `references/*.md` file, "
                       "or states only without a citation")
SECTION_CLAUSE = ("at the end of SKILL.md's level-2 section whose heading names gotchas, before any [MANUAL] block "
                  "that ends it, when one sits before SKILL.md's first `## Full` heading and outside any [MANUAL] "
                  "block")
NOT_4B_CLAUSE = "(never `## Migration & Deprecation Warnings`, which holds T2-future warnings only)"
NEW_SECTION_CLAUSE = ("Otherwise add a new `## Gotchas` section right before SKILL.md's first `## Full` heading (at "
                      "the end of the body when it has none), outside any [MANUAL] block.")
SKILL_MD_ONLY_CLAUSE = ("The bullets go in SKILL.md, a split-body skill's included, never in a `references/*.md` "
                        "file.")
GIVEN_BACK_CLAUSE = "write.md §5 then gives each bullet back as a gotcha, in SKILL.md order"
NO_RECORD_CLAUSE = ("This priority flags no conflict and appends no evidence record: §6 counts its bullets as "
                    "`gotchas_restated`.")
SKIP_CLAUSE = ("**If `prior_gotchas` is null or holds no such pitfall,** or no path resolves, or `gotchas prior` exits "
               "non-zero: skip Priority 9 silently, since write.md §5 runs the same call and halts on its failure.")
P9_CLAUSES = (HEADING_CLAUSE, CARRY_THEN_DROP_CLAUSE, RESOLVE_CLAUSE, PRIOR_CALL, BINDING_CLAUSE, WHICH_CLAUSE,
              STATED_WHOLE_CLAUSE, ONE_PITFALL_CLAUSE, PARTS_CLAUSE, MAIN_CLAIM_CLAUSE, CITATION_CLAUSE,
              NOT_RESTATED_CLAUSE, SECTION_CLAUSE, NOT_4B_CLAUSE, NEW_SECTION_CLAUSE, SKILL_MD_ONLY_CLAUSE,
              GIVEN_BACK_CLAUSE, NO_RECORD_CLAUSE, SKIP_CLAUSE)


def _read(path: Path) -> str:
    assert path.is_file(), f"missing file: {path}"
    return path.read_text(encoding="utf-8")


def _slice(text: str, start: str, end: str | None) -> str:
    """The text from `start`, found exactly once, up to the next `end` (or the end of the text)."""
    assert text.count(start) == 1, f"start marker not found exactly once: {start!r}"
    i = text.index(start)
    if end is None:
        return text[i:]
    j = text.find(end, i + len(start))
    assert j != -1, f"end marker {end!r} not found after {start!r}"
    return text[i:j]


def _frontmatter(text: str) -> str:
    assert text.startswith("---\n"), "no frontmatter"
    return text[4:text.index("\n---\n", 4) + 1]


def _comment_before(frontmatter: str, key: str) -> str:
    """The `#` comment lines right above `key:`, read as one line."""
    lines = frontmatter.splitlines()
    at = lines.index(f"{key}:")
    comment: list[str] = []
    for line in reversed(lines[:at]):
        if not line.startswith("#"):
            break
        comment.insert(0, line.lstrip("#").strip())
    return " ".join(comment)


def _in_order(text: str, *parts: str) -> bool:
    return all(part in text for part in parts) and [text.index(p) for p in parts] == sorted(text.index(p) for p in parts)


def _priority_9() -> str:
    return _slice(_read(MERGE), P9_START, P9_END)


def _regeneration() -> str:
    return _slice(_read(WRITE), "### 5. Regenerate context-snippet.md", None)


def _helper_argv(call: str, values: dict[str, str]) -> list[str]:
    """The argv of a documented `uv run {helper} ...` call, run with this Python."""
    words = shlex.split(re.sub(r"\{([A-Za-z_][\w-]*)\}", lambda m: values[m.group(1)], call))
    assert words[:2] == ["uv", "run"], call
    return [sys.executable, *words[2:]]


def test_merge_declares_the_rebuild_helper():
    """Priority 9 runs `{rebuildManagedSectionsHelper}`, so merge.md declares write.md's probe order for it, right
    after the hash helper's, with a comment that says Priority 9 skips when neither path exists."""
    front = _frontmatter(_read(MERGE))
    keys = list(yaml.safe_load(front))
    probe = yaml.safe_load(front)["rebuildManagedSectionsProbeOrder"]
    assert probe == yaml.safe_load(_frontmatter(_read(WRITE)))["rebuildManagedSectionsProbeOrder"]
    assert probe == ["{project-root}/_bmad/skf/shared/scripts/skf-rebuild-managed-sections.py",
                     "{project-root}/src/shared/scripts/skf-rebuild-managed-sections.py"]
    assert keys.index("rebuildManagedSectionsProbeOrder") == keys.index("hashContentProbeOrder") + 1
    comment = _comment_before(front, "rebuildManagedSectionsProbeOrder")
    assert comment == ("Resolve `{rebuildManagedSectionsHelper}` to the first existing path: §3 Priority 9 reads the "
                       "prior snippet's gotchas line with its `gotchas prior` action, and skips when neither exists "
                       "(write.md §5 halts on the same helper)."), comment


def test_priority_9_restates_a_joined_prior_pitfalls_parts():
    """Priority 9 follows Priority 8b in §3, runs write.md §5's `gotchas prior` call verbatim, binds
    `prior_gotchas`, and states which pitfalls it takes, what it writes and where, and when it skips; it records
    no evidence line, holds no em dash, and §6 and write.md §4's Merge Results count its bullets."""
    merge = _read(MERGE)
    p9 = _priority_9()
    assert merge.index("**Priority 8b:") < merge.index("**If no metadata-update entries:**") < merge.index(P9_START)
    assert merge.index(P9_START) < merge.index(P9_END)
    assert PRIOR_CALL in _regeneration(), "write.md §5 runs the call Priority 9 runs"
    assert PRIOR_CALL_RE.findall(p9) == [PRIOR_CALL]
    assert _in_order(p9, *P9_CLAUSES)
    assert "as one JSON line keyed" not in p9
    assert EM_DASH not in p9
    assert "```" not in p9, "Priority 9 adds no fence"
    six = _slice(merge, "### 6. Compile Merge Results", "In gap-driven mode")
    assert "  exports_renamed: [count]\n  gotchas_restated: [count]\n" in six
    results = _slice(_read(WRITE), "### Merge Results\n", "### Scope and Targeted Re-Extraction\n")
    assert "- Conflicts resolved: {count}\n- Gotchas restated: {count}\n" in results


@pytest.mark.parametrize("line, expected", [
    pytest.param("a; b; c; d", [{"text": "a; b; c; d", "already_carried": False, "read_whole": True}],
                 id="older-line-read-whole"),
    pytest.param("[CARRIED] a, b, c, d", [{"text": "a, b, c, d", "already_carried": True, "read_whole": False}],
                 id="carried-read-back"),
    pytest.param("a, b", [{"text": "a, b", "already_carried": False, "read_whole": False}], id="older-comma-line"),
])
def test_the_priority_9_call_reads_an_older_line_whole(tmp_path, line, expected):
    """Priority 9's documented call, run on a re-exported fixture skill, gives the joined pitfall it restates."""
    [call] = PRIOR_CALL_RE.findall(_priority_9())
    skills = tmp_path / "skills"
    package = skills / "demo" / "1.0.0" / "demo"
    package.mkdir(parents=True)
    (package / "context-snippet.md").write_bytes(
        f"[demo v1.0.0]|root: skills/demo/\n|api: parse()\n|gotchas: {line}\n".encode("utf-8"))
    manifest = {"schema_version": "2", "exports": {"demo": {"active_version": "1.0.0", "versions": {
        "1.0.0": {"ides": ["claude-code"], "last_exported": "2026-09-01", "status": "active"}}}}}
    (skills / ".export-manifest.json").write_bytes(json.dumps(manifest).encode("utf-8"))
    values = {"rebuildManagedSectionsHelper": REBUILD.as_posix(), "skill_package": package.as_posix(),
              "skills_output_folder": skills.as_posix(), "skill_name": "demo"}
    proc = subprocess.run(_helper_argv(call, values), capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    prior = json.loads(proc.stdout)
    assert prior["status"] == "ok" and prior["is_first_export"] is False
    assert prior["prior_gotchas"] == expected


@pytest.mark.parametrize("snippet, manifest, skip_case", [
    pytest.param(b"[demo v1.0.0]|root: skills/demo/\n|api: parse()\n", b'{"schema_version": "2", "exports": {}}',
                 "**If `prior_gotchas` is null", id="no-gotchas-line"),
    pytest.param(None, b'{"schema_version": "2", "exports": {}}', "**If `prior_gotchas` is null", id="no-snippet"),
    pytest.param(b"[demo v1.0.0]|root: skills/demo/\n|gotchas: a; b; c; d\n", b"not json",
                 "or `gotchas prior` exits non-zero", id="unreadable-manifest"),
])
def test_the_priority_9_call_leaves_nothing_to_read(tmp_path, snippet, manifest, skip_case):
    """The matrix's Nothing-to-read row: with no `|gotchas:` line or no snippet the documented call gives a null
    `prior_gotchas`, and with an unreadable export manifest it exits non-zero; Priority 9 skips on each, writing
    no bullet, and leaves the halt to write.md §5's same call."""
    p9 = _priority_9()
    [call] = PRIOR_CALL_RE.findall(p9)
    assert SKIP_CLAUSE in p9 and skip_case in SKIP_CLAUSE
    skills = tmp_path / "skills"
    package = skills / "demo" / "1.0.0" / "demo"
    package.mkdir(parents=True)
    if snippet is not None:
        (package / "context-snippet.md").write_bytes(snippet)
    (skills / ".export-manifest.json").write_bytes(manifest)
    values = {"rebuildManagedSectionsHelper": REBUILD.as_posix(), "skill_package": package.as_posix(),
              "skills_output_folder": skills.as_posix(), "skill_name": "demo"}
    proc = subprocess.run(_helper_argv(call, values), capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert proc.stdout.strip(), proc.stderr
    result = json.loads(proc.stdout)
    if skip_case.startswith("**If"):
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert result["status"] == "ok" and result["prior_gotchas"] is None
    else:
        assert proc.returncode != 0 and result["status"] == "error", proc.stdout + proc.stderr


# --------------------------------------------------------------------------
# Priority 9 and §3a, modelled and placed by the helper's `resolve_gotchas`
# --------------------------------------------------------------------------

# The SKILL.md places §3a's source 2 reads. Source 3 reads every place, these included.
SOURCE_2_PLACES = {"gotchas bullet", "deprecated Key API Summary row", "Quick Start await"}
# A place that carries no citation: the frontmatter description.
UNCITED_PLACES = {"description"}


def _form(text: str) -> str:
    """A pitfall as the line writes it: a place states the same claim whichever way the line wrote its `; `."""
    return rms.write_gotchas([(text.strip(), False)])


def _joined(prior: list[dict], several: tuple[str, ...]) -> set[str]:
    """The forms of the prior pitfalls that join several: each one read whole, and each `several` names, a
    judgment of meaning."""
    return {_form(text) for text in several} | {_form(p["text"]) for p in prior if p["read_whole"]}


def _judgments(prior: list[dict], skill_md: list[tuple[str, str]], report: tuple[str, ...] = (),
               several: tuple[str, ...] = ()) -> tuple[list[bool], list[str]]:
    """§3a's judgments file for `prior` (the `prior_gotchas` entries), as test-skf-export-terminal.py's
    `_judgments` models it: prose backs a prior pitfall that is one pitfall, one that joins several needs one
    annotation or one source-2 place stating it whole, and a prior pitfall a source states is never also new."""
    joined = _joined(prior, several)
    said = {_form(text) for text in report} | {_form(pitfall) for _, pitfall in skill_md}
    sourced = list(report) + [pitfall for place, pitfall in skill_md if place in SOURCE_2_PLACES]
    sourced_forms = {_form(text) for text in sourced}
    prior_forms = [_form(p["text"]) for p in prior]
    backed = [form in (sourced_forms if form in joined else said) for form in prior_forms]
    return backed, [text for text in sourced if _form(text) not in prior_forms]


def _parts(pitfall: dict) -> list[str]:
    """The pitfalls a joined prior pitfall joins, in its order, each without a `[CARRIED]` marker: a value read
    whole splits as the line does, and one written back, or an older line, on its `, ` (the fixtures' parts hold
    none)."""
    pieces = rms.split_gotchas(pitfall["text"]) if pitfall["read_whole"] else pitfall["text"].split(", ")
    parts = [piece.strip() for piece in pieces]
    return [part[len(rms.CARRIED_MARK):].strip() if part.startswith(rms.CARRIED_MARK) else part
            for part in parts if part]


def _restate(prior: list[dict], skill_md: list[tuple[str, str]], report: tuple[str, ...] = (),
             several: tuple[str, ...] = (), contradicted: tuple[str, ...] = ()) -> list[str]:
    """The parts Priority 9 writes as bullets: of each joined prior pitfall no annotation and no source-2 place
    states whole, each part a cited SKILL.md place still states, that nothing contradicts and that no annotation
    or source-2 place states yet."""
    joined = _joined(prior, several)
    sourced = {_form(text) for text in report} | {_form(p) for place, p in skill_md if place in SOURCE_2_PLACES}
    cited = {_form(p) for place, p in skill_md if place not in UNCITED_PLACES}
    restated: list[str] = []
    for pitfall in prior:
        form = _form(pitfall["text"])
        if form not in joined or form in sourced:
            continue
        for part in _parts(pitfall):
            if _form(part) in cited and part not in contradicted and _form(part) not in sourced \
                    and part not in restated:
                restated.append(part)
    return restated


def _merged(skill_md: list[tuple[str, str]], restated: list[str]) -> list[tuple[str, str]]:
    """SKILL.md's places once Priority 9 ran: the restated parts are gotchas bullets after the existing ones, or
    in a new section after the fixtures' other places."""
    bullets = [i for i, (place, _) in enumerate(skill_md) if place == "gotchas bullet"]
    at = bullets[-1] + 1 if bullets else len(skill_md)
    return skill_md[:at] + [("gotchas bullet", part) for part in restated] + skill_md[at:]


def _export(line: str | None, skill_md: list[tuple[str, str]], report: tuple[str, ...],
            several: tuple[str, ...]) -> tuple[list[dict], tuple[str | None, list[str], list[tuple[str, str]]]]:
    """One re-export's `|gotchas:` placement: (the prior pitfalls, (line, left_off, dropped))."""
    prior = rms.read_gotchas(line) if line else []
    backed, new = _judgments(prior, skill_md, report, several)
    placed = rms.resolve_gotchas(prior or None, backed, new, is_first_export=False)
    dropped = [(item["text"], item["reason"]) for item in placed["dropped"]]
    return prior, (placed["line"], placed["left_off"], dropped)


PROSE_ABCD = [("Overview", part) for part in "abcd"]
JOINED = "a; b; c; d"
CARRIED_JOINED = "[CARRIED] a, b, c, d"


@pytest.mark.parametrize("clauses, prior_line, skill_md, report, several, contradicted, restate, restated, "
                         "update, next_export", [
    pytest.param((WHICH_CLAUSE, NEW_SECTION_CLAUSE), JOINED, PROSE_ABCD, (), (), (), True, list("abcd"),
                 ("a; b; c", ["d"], [(JOINED, "no-slot")]), ("a; b; c", ["d"], []), id="joined-prose-only"),
    pytest.param((CARRY_THEN_DROP_CLAUSE,), JOINED, PROSE_ABCD, (), (), (), False, [],
                 ("[CARRIED] a, b, c, d", [], []), (None, [], [("a, b, c, d", "already-carried")]),
                 id="control-without-priority-9"),
    pytest.param((WHICH_CLAUSE,), CARRIED_JOINED, PROSE_ABCD, (), ("a, b, c, d",), (), True, list("abcd"),
                 ("a; b; c", ["d"], [("a, b, c, d", "already-carried")]), ("a; b; c", ["d"], []),
                 id="already-carried"),
    pytest.param((PARTS_CLAUSE,), "a; [CARRIED] b; c; d", PROSE_ABCD, (), (), (), True, list("abcd"),
                 ("a; b; c", ["d"], [("a; [CARRIED] b; c; d", "no-slot")]), ("a; b; c", ["d"], []),
                 id="a-marked-piece-is-restated-unmarked"),
    pytest.param((NOT_RESTATED_CLAUSE,), JOINED, PROSE_ABCD[:3], (), (), (), True, list("abc"),
                 ("a; b; c", [], [(JOINED, "no-slot")]), ("a; b; c", [], []), id="part-gone"),
    pytest.param((MAIN_CLAIM_CLAUSE,), JOINED, PROSE_ABCD + [("Overview", "d at v2")], (), (), ("d",), True,
                 list("abc"), ("a; b; c", [], [(JOINED, "no-slot")]), ("a; b; c", [], []),
                 id="part-contradicted"),
    pytest.param((MAIN_CLAIM_CLAUSE, SECTION_CLAUSE), JOINED, [("gotchas bullet", "d")] + PROSE_ABCD[:3], (), (),
                 (), True, list("abc"), ("d; a; b", ["c"], [(JOINED, "no-slot")]), ("d; a; b", ["c"], []),
                 id="part-already-a-bullet"),
    pytest.param((CITATION_CLAUSE, NOT_RESTATED_CLAUSE), JOINED, [("description", "a")] + PROSE_ABCD[1:], (), (),
                 (), True, list("bcd"), ("b; c; d", [], [(JOINED, "no-slot")]), ("b; c; d", [], []),
                 id="part-uncited"),
    pytest.param((WHICH_CLAUSE,), "a, b", PROSE_ABCD[:2], (), ("a, b",), (), True, list("ab"),
                 ("a; b; [CARRIED] a, b", [], []), ("a; b", [], [("a, b", "already-carried")]), id="older-2-part"),
    pytest.param((ONE_PITFALL_CLAUSE,), "x; y", [("Overview", "x"), ("Overview", "y")], (), (), (), True, [],
                 ("x; y", [], []), ("x; y", [], []), id="single-pitfalls"),
    pytest.param((STATED_WHOLE_CLAUSE,), JOINED, [("gotchas bullet", JOINED)] + PROSE_ABCD, (), (), (), True, [],
                 ("a, b, c, d", [], []), ("a, b, c, d", [], []), id="a-gotchas-bullet-states-it-whole"),
    pytest.param((STATED_WHOLE_CLAUSE,), JOINED, PROSE_ABCD, (JOINED,), (), (), True, [],
                 ("a, b, c, d", [], []), ("a, b, c, d", [], []), id="an-annotation-states-it-whole"),
    pytest.param((STATED_WHOLE_CLAUSE, WHICH_CLAUSE), CARRIED_JOINED, [("gotchas bullet", JOINED)] + PROSE_ABCD, (),
                 ("a, b, c, d",), (), True, [], ("a, b, c, d", [], []), ("a, b, c, d", [], []),
                 id="carried-and-stated-whole"),
])
def test_restated_parts_keep_the_line_through_the_next_export(clauses, prior_line, skill_md, report, several,
                                                              contradicted, restate, restated, update, next_export):
    """The I/O matrix's re-exported rows: Priority 9 restates the parts a joined prior pitfall joins, §3a gives
    them back as gotchas (the first 3 on the line, the rest left off) while the joined value goes, and the next
    export keeps the line; without Priority 9 the joined value rides its one carry and the line is lost."""
    p9 = _priority_9()
    for clause in clauses:
        assert clause in p9, clause
    prior = rms.read_gotchas(prior_line)
    written = _restate(prior, skill_md, report, several, contradicted) if restate else []
    assert written == restated
    assert not any(part.startswith(rms.CARRIED_MARK) for part in written)
    merged = _merged(skill_md, written)
    update_prior, placed = _export(prior_line, merged, report, several)
    assert update_prior == prior and placed == update
    # The next export reads the line the update wrote: a joined value it carried reads back as one pitfall.
    read_back = tuple(_form(p["text"]) for p in prior if _form(p["text"]) in _joined(prior, several))
    assert _export(placed[0], merged, report, several + read_back)[1] == next_export


# --------------------------------------------------------------------------
# #1269: an unchanged source goes on to merge while a joined value waits
# --------------------------------------------------------------------------

DETECT = UPDATE_REFS / "detect-changes.md"
SCHEMA = REPO / "src" / "shared" / "scripts" / "schemas" / "skf-update-result-envelope.v1.json"
WORKFLOWS = REPO / "docs" / "workflows.md"
CONCEPTS = REPO / "docs" / "concepts.md"
BUILD = REPO / "src" / "shared" / "scripts" / "skf-build-change-manifest.py"
SNIPPET = REPO / "src" / "skf-export-skill" / "references" / "generate-snippet.md"

# detect-changes.md §4's gate, each an exact substring of its paragraph.
GATE_HEADING = "**A joined gotchas value goes on to merge.**"
GATE_HOLDS = "The gate holds when its `prior_gotchas`"
GATE_JOINS = ("holds a pitfall that joins several pitfalls that each warn on their own (one marked `read_whole`, "
              "or pitfalls joined with `, `; not one pitfall whose own wording holds a `, `)")
GATE_ANNOTATION = ("that no T2-future annotation of `{forge_version}/evidence-report.md` (else "
                   "`{forge_data_folder}/{skill_name}/evidence-report.md`)")
GATE_WHOLE = ("and no one bullet of a section whose heading names gotchas, deprecations, migration, breaking "
              "changes or import corrections, no one `## Key API Summary` row whose purpose says deprecated or "
              "removed and no one Quick Start `await` call states whole")
GATE_PARTS = ("and `{skill_package}/SKILL.md` states, with a citation and uncontradicted, one of its pitfalls "
              "that no such annotation, bullet, row or call states yet")
GATE_DROP = "a later export drops the joined pitfall"
GATE_NOT_READ_ONLY = "When the gate holds and neither `detect_only_mode` nor `dry_run_mode` is true"
GATE_DISPLAY = ('display "**Source unchanged, but a joined gotchas value is being restated** in SKILL.md, as '
                "gotchas bullets; the next export keeps as many of them as the line's 3 slots hold.\"")
GATE_ROUTE = "load `{nextStepFile}` with this change manifest, skipping §5"
GATE_EMPTY = ("it extracts nothing and writes the empty records merge and step 5 read, Priority 9 writes the "
              "bullets, and the run writes a new version")
GATE_WARNING = ("When the gate holds on a read-only run, add `gotchas-not-restated: {skill_name}'s context "
                "snippet holds a gotchas value that joins several pitfalls, which a later export drops; an "
                "update without --detect-only or --dry-run restates them in SKILL.md` to `warnings[]`")
GATE_SHORTCUT = ("Every run that does not load `{nextStepFile}` here, one whose gate does not hold, a read-only one "
                 "and one whose call exits non-zero or resolves no path included, takes the shortcut:")
# The schema's warnings description names the new code right after the docs-only version notice.
GATE_SCHEMA_ENTRY = ("target-version-not-recorded (report.md §1: a docs-only run named a higher version but no "
                     "document changed, so nothing was written), gotchas-not-restated (detect-changes.md §4: a "
                     "--detect-only or --dry-run run on an unchanged source left a joined gotchas value for a run "
                     "without those flags to restate)")
# Earlier drafts' phrases: untied actions, a slot-blind promise, a SKILL.md-only parts check, an undefined place
# and a joins clause without "that each warn on their own", and a display clause that slots every bullet.
GATE_GONE = ("Unless `detect_only_mode` or `dry_run_mode` is true", "A read-only run adds `gotchas-not-restated",
             "so the next export keeps its pitfalls", "in none of those places yet", "Every other run,",
             "gotchas-type", "joins several (one marked",
             "the next export places within the line's 3 slots")
# generate-snippet.md §3a's drop warning asks for a hand bullet only while SKILL.md does not hold one yet.
DROP_NOT_YET_STATED = ("if one is still relevant and SKILL.md does not state it yet (for one that joins "
                       "several pitfalls, each of them) in a bullet of a section whose heading names gotchas")


def _four() -> str:
    return _slice(_read(DETECT), "### 4. Check for No-Change Shortcut", "### 5.")


def _build(tmp_path: Path, *args: str) -> subprocess.CompletedProcess:
    """One `skf-build-change-manifest.py` call, run with this Python in `tmp_path`; it must exit 0."""
    proc = subprocess.run([sys.executable, str(BUILD), *args], capture_output=True, text=True, encoding="utf-8",
                          cwd=tmp_path, timeout=60)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return proc


def test_an_unchanged_source_goes_on_to_merge_while_a_joined_value_waits():
    """§4 runs Priority 9's `gotchas prior` call before its shortcut; when Priority 9 would write a bullet, a run
    that is not read-only loads re-extract.md with the empty change manifest and a read-only one warns
    `gotchas-not-restated`; every other run takes the shortcut as before. The frontmatter binds the helper as
    merge.md does, the schema names the warning, and the user docs say the new route."""
    four = _four()
    assert _in_order(four, GATE_HEADING, RESOLVE_CLAUSE, PRIOR_CALL, GATE_HOLDS, GATE_JOINS, GATE_ANNOTATION,
                     GATE_WHOLE, GATE_PARTS, GATE_DROP, GATE_NOT_READ_ONLY, GATE_DISPLAY, GATE_ROUTE, GATE_EMPTY,
                     GATE_WARNING, GATE_SHORTCUT, '"**No changes detected.**', "Skip steps 3-5",
                     "A `--detect-only` or `--dry-run` run takes this route too")
    assert PRIOR_CALL_RE.findall(four) == [PRIOR_CALL]
    for gone in GATE_GONE:
        assert gone not in four, gone
    front = _frontmatter(_read(DETECT))
    loaded = yaml.safe_load(front)
    assert loaded["rebuildManagedSectionsProbeOrder"] == \
        yaml.safe_load(_frontmatter(_read(MERGE)))["rebuildManagedSectionsProbeOrder"]
    assert loaded["nextStepFile"] == "re-extract.md"
    assert "Take §4's shortcut when neither exists" in _comment_before(front, "rebuildManagedSectionsProbeOrder")
    assert EM_DASH not in _slice(four, GATE_HEADING, "\n")
    warnings = json.loads(_read(SCHEMA))["properties"]["skf_update"]["properties"]["warnings"]["description"]
    assert GATE_SCHEMA_ENTRY in warnings
    update = _slice(_read(WORKFLOWS), "### Update Skill (US)", "**Agent:**")
    headless = _slice(update, "**Headless:**", "\n")
    for phrase in ("`gotchas-not-restated`", "which a later export would drop", "with the status `success`",
                   "A normal run whose source is unchanged",
                   "goes on instead when SKILL.md still states, with a citation, one of those pitfalls that is not "
                   "yet a gotcha of its own"):
        assert phrase in headless, phrase
    concepts = _read(CONCEPTS)
    assert ("or when, with no document changed, it restates in SKILL.md one or more pitfalls of a `|gotchas:` "
            "value that a later export would drop") in concepts
    assert "Either version is written only when the update finds a changed document;" not in concepts
    assert "it restates in SKILL.md the pitfalls of a" not in concepts


@pytest.mark.parametrize("clauses, read_only", [
    pytest.param((GATE_NOT_READ_ONLY, GATE_ROUTE, GATE_EMPTY), False, id="plain-run"),
    pytest.param((GATE_NOT_READ_ONLY, GATE_WARNING, GATE_SHORTCUT), True, id="read-only"),
])
def test_an_unchanged_source_update_restates_a_carried_value_before_the_next_export(clauses, read_only):
    """The matrix's Carried and Read-only rows: an export carried a joined value whose parts SKILL.md states, and
    the source has not changed. A plain update restates the parts, so the next export keeps the line; a read-only
    one writes nothing, so the next export drops the value. The restate run's own drop warning, which write.md §5
    gives its report, asks for no hand bullet SKILL.md already holds."""
    four = _four()
    for clause in clauses:
        assert clause in four, clause
    assert _export(JOINED, PROSE_ABCD, (), ())[1] == ("[CARRIED] a, b, c, d", [], [])
    several = ("a, b, c, d",)
    assert _restate(rms.read_gotchas(CARRIED_JOINED), PROSE_ABCD, (), several), "the gate fires"
    if read_only:
        assert _export(CARRIED_JOINED, PROSE_ABCD, (), several)[1] == (None, [], [("a, b, c, d", "already-carried")])
        return
    restated = _restate(rms.read_gotchas(CARRIED_JOINED), PROSE_ABCD, (), several)
    assert restated == list("abcd")
    merged = _merged(PROSE_ABCD, restated)
    assert _export(CARRIED_JOINED, merged, (), several)[1] == \
        ("a; b; c", ["d"], [("a, b, c, d", "already-carried")])
    assert _export("a; b; c", merged, (), several)[1] == ("a; b; c", ["d"], [])
    # write.md §5 gives this run's report the drop warning for the joined value Priority 9 just restated.
    assert "add each warning its §3a emits to `warnings[]`" in _read(WRITE)
    assert all(("gotchas bullet", part) in merged for part in "abcd")
    drop = _slice(_read(SNIPPET), "- **When `dropped` is not empty**", "\n")
    assert DROP_NOT_YET_STATED in drop and "update-skill cannot restate it, since" not in drop


@pytest.mark.parametrize("clauses, prior_line, skill_md, report, several, fires", [
    pytest.param((GATE_JOINS,), CARRIED_JOINED, PROSE_ABCD, (), ("a, b, c, d",), True, id="carried-joined"),
    pytest.param((GATE_JOINS,), JOINED, PROSE_ABCD, (), (), True, id="joined-not-yet-carried"),
    pytest.param((GATE_JOINS,), None, PROSE_ABCD, (), (), False, id="no-gotchas-line"),
    pytest.param((GATE_JOINS,), "x; y", [("Overview", "x"), ("Overview", "y")], (), (), False,
                 id="single-pitfalls"),
    pytest.param((GATE_WHOLE,), JOINED, [("gotchas bullet", JOINED)] + PROSE_ABCD, (), (), False, id="stated-whole"),
    pytest.param((GATE_WHOLE,), JOINED, [("deprecated Key API Summary row", JOINED)] + PROSE_ABCD, (), (), False,
                 id="key-api-row-states-it-whole"),
    # One pitfall whose wording holds a `, `: no `several` judgment joins it, so Priority 9 writes nothing.
    pytest.param((GATE_JOINS,), "a, b", [("Overview", "a"), ("Overview", "b")], (), (), False,
                 id="one-pitfall-with-a-comma"),
    pytest.param((GATE_ANNOTATION,), JOINED, PROSE_ABCD, (JOINED,), (), False, id="annotation-states-it-whole"),
    pytest.param((GATE_PARTS,), JOINED, [("gotchas bullet", p) for p in "abcd"], (), (), False,
                 id="parts-already-bullets"),
    pytest.param((GATE_PARTS,), JOINED, [("description", "a")], (), (), False, id="parts-uncited"),
    pytest.param((GATE_PARTS,), JOINED, [], (), (), False, id="parts-gone"),
    # A T2-future annotation states each part, so Priority 9 writes nothing.
    pytest.param((GATE_PARTS,), JOINED, PROSE_ABCD, tuple("abcd"), (), False, id="parts-in-annotations"),
])
def test_the_no_change_branch_fires_only_when_priority_9_writes_a_bullet(clauses, prior_line, skill_md, report,
                                                                        several, fires):
    """The matrix's Nothing-to-restate row: the gate holds only when Priority 9 would write at least one bullet,
    so an unchanged source whose prior line needs nothing takes the shortcut with no new warning."""
    prior = rms.read_gotchas(prior_line) if prior_line else []
    four = _four()
    for clause in clauses + (() if fires else (GATE_SHORTCUT,)):
        assert clause in four, clause
    assert bool(_restate(prior, skill_md, report, several)) is fires


@pytest.mark.parametrize("mode", ["normal", "docs-only"])
def test_the_restate_route_writes_no_provenance_change(tmp_path, mode):
    """The matrix's Docs-only row and the route's empty records: on the empty change manifest step 3's records
    hold no file, and step 5's `apply`, given the manifest, the records and the `--metadata-in` and `--lists-out`
    files write.md §3 passes in every mode, changes no entry and counts nothing."""
    if mode == "normal":
        (tmp_path / "files.json").write_text("[]", encoding="utf-8")
        records = json.loads(_build(tmp_path, "records", "--files-from", "files.json", "-o", "rec.json").stdout)
        assert records["files_extracted"] == 0
        assert json.loads((tmp_path / "rec.json").read_text(encoding="utf-8"))["files"] == []
        (tmp_path / "in.json").write_text(json.dumps({"degraded_mode": False, "update_mode": "normal"}),
                                          encoding="utf-8")
        manifest = _build(tmp_path, "build", "--input", "in.json").stdout
        entry = {"export_name": "parse", "export_type": "function", "params": [], "return_type": "dict",
                 "source_file": "src/a.py", "source_line": 3, "confidence": "T1", "extraction_method": "ast-grep",
                 "ast_node_type": "function_definition", "signature_source": "T1"}
    else:
        compared = {"changed": [], "unchanged": [{"url": "https://example.com/a"}], "fetch_failed": [],
                    "skipped_null_hash": [], "stats": {"total_tracked": 1, "changed": 0, "unchanged": 1}}
        (tmp_path / "cmp.json").write_text(json.dumps(compared), encoding="utf-8")
        manifest = _build(tmp_path, "build", "--doc-hashes", "cmp.json").stdout
        # re-extract.md §1's docs-only records on an empty `changed_urls`.
        (tmp_path / "rec.json").write_text(json.dumps({"mode": "docs-only", "changed_urls": [], "exports": []}),
                                           encoding="utf-8")
        entry = {"export_name": "parse", "export_type": "function", "source_file": "https://example.com/a",
                 "confidence": "T3", "extraction_method": "doc-fetch", "signature_source": "T3"}
    (tmp_path / "man.json").write_text(manifest, encoding="utf-8")
    assert json.loads(manifest)["no_changes"] is True
    (tmp_path / "map.json").write_text(json.dumps({"skill_name": "demo", "entries": [entry]}), encoding="utf-8")
    lists = {"exports": ["parse"], "scripts": [], "assets": []}
    (tmp_path / "meta.json").write_text(json.dumps(lists), encoding="utf-8")
    applied = json.loads(_build(
        tmp_path, "apply", "--update-type", "incremental", "--provenance-map", "map.json", "--manifest", "man.json",
        "--reextract-records", "rec.json", "--skill-name", "demo", "--generation-date", "2026-11-19T00:00:00Z",
        "--confidence-tier", "Forge", "--manual-sections-preserved", "0", "--source-commit", "", "--source-ref", "",
        "--metadata-in", "meta.json", "--lists-out", "lists.json", "-o", "out.json").stdout)
    nothing = {"added": [], "updated": [], "removed": []}
    assert applied["entries"] == nothing and applied["file_entries"] == nothing
    assert applied["signature_source_backfilled"] == {} and applied["warnings"] == []
    out = json.loads((tmp_path / "out.json").read_text(encoding="utf-8"))
    assert out["entries"] == [entry]
    assert out["files_changed"] == 0 and out["exports_affected"] == 0
    assert json.loads((tmp_path / "lists.json").read_text(encoding="utf-8")) == lists


def test_a_changed_source_routes_through_section_5_as_before():
    """The matrix's Source-changed row: the gate sits inside §4's no-change branch, between its condition line and
    the shortcut's display block, so a changed source still reaches §5, whose route to `{nextStepFile}` stands,
    and Priority 9 runs there as before."""
    detect = _read(DETECT)
    assert detect.count(GATE_HEADING) == 1
    four = _four()
    [condition] = [line for line in four.split("\n")
                   if line.startswith("**If zero changes detected across all categories**")]
    assert condition + "\n\n" + GATE_HEADING in four
    assert GATE_SHORTCUT + "\n\n" + '"**No changes detected.**' in four
    five = _slice(detect, "### 5. Display Change Summary and Route", None)
    assert ('- **Otherwise** → display "**Proceeding to re-extraction of {affected_file_count} changes...**" and '
            "load `{nextStepFile}` (re-extract.md) to begin re-extraction.") in five
    assert _in_order(_priority_9(), *P9_CLAUSES)
