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
