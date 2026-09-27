"""Suite-wide pytest setup: keep a hook's git environment away from the tests.

git exports GIT_INDEX_FILE to its hooks (an absolute path for
`git commit -a` and `git commit <path>`), plus GIT_DIR when the hook runs
in a linked worktree; `git rebase --exec` and `!` aliases export them too.
`.husky/pre-commit` runs `npm test`, so a fixture running
`git -C <tmp repo>` would read and write the commit's index, or the
repository itself. `git commit` also exports the author's name, email and
date, which would become every fixture commit's author.

The repository, config and identity variables are dropped here, before any
test module is imported. Every git child also gets no system config and a
global config that only points git's global ignore and attributes files at
an empty file, so a developer's signing, hooks path, `git -c` settings,
~/.config/git/ignore or ~/.config/git/attributes never reach a fixture.
A hook also receives GIT_EDITOR (a no-op editor) and GIT_EXEC_PATH (the
running git's helper folder); both are harmless and stay.

git discovery also stops at pytest's base temp folder, so a plain folder a
test creates is never taken for part of a repository that happens to hold
the temp root (a home folder under git, a TMPDIR or --basetemp inside a
checkout).

pytest loads this file for every test file under test/, including the
explicit file list in package.json test:python; only --noconftest skips it.
"""

from __future__ import annotations

import os

import pytest

# `git rev-parse --local-env-vars` (git 2.47) plus GIT_NAMESPACE. Must
# cover GIT_LOCATION_VARS in skf-check-workspace-drift.py,
# skf-merge-ccc-exclusions.py and skf-ccc-git-hygiene.py;
# test/test-skf-conftest.py checks them all.
SCRUBBED_GIT_VARS = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_PREFIX",
    "GIT_COMMON_DIR",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_NAMESPACE",
    "GIT_CONFIG",
    "GIT_CONFIG_PARAMETERS",
    "GIT_CONFIG_COUNT",
    "GIT_IMPLICIT_WORK_TREE",
    "GIT_GRAFT_FILE",
    "GIT_NO_REPLACE_OBJECTS",
    "GIT_REPLACE_REF_BASE",
    "GIT_SHALLOW_FILE",
)

# The author variables `git commit` exports to its hooks, and their
# committer counterparts: a fixture commit takes its identity from the
# fixture repository's own config and its date from the clock.
SCRUBBED_IDENTITY_VARS = (
    "GIT_AUTHOR_NAME",
    "GIT_AUTHOR_EMAIL",
    "GIT_AUTHOR_DATE",
    "GIT_COMMITTER_NAME",
    "GIT_COMMITTER_EMAIL",
    "GIT_COMMITTER_DATE",
)

for _var in (*SCRUBBED_GIT_VARS, *SCRUBBED_IDENTITY_VARS):
    os.environ.pop(_var, None)


def _config_path(path) -> str:
    """A path as a quoted git config value (forward slashes, escaped)."""
    text = path.as_posix().replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


@pytest.fixture(autouse=True, scope="session")
def _hermetic_git_config(tmp_path_factory):
    """Give every git child a near-empty global config and no system config,
    and stop its repository discovery at the base temp folder.

    git reads $XDG_CONFIG_HOME/git/ignore and git/attributes (else the same
    files under ~/.config) whatever GIT_CONFIG_GLOBAL names, so the global
    config sets core.excludesFile and core.attributesFile to an empty file.
    XDG_CONFIG_HOME itself is left alone because git is not its only reader:
    the real tool probes some tests run (ccc, qmd) would see it too.

    GIT_CEILING_DIRECTORIES names the base temp folder: git never moves up
    into it, so a repository a test creates at or below its own tmp_path is
    still found, and a folder that is not one never resolves to a repository
    above the base temp folder. A test may set its own, lower ceiling.
    """
    folder = tmp_path_factory.mktemp("git-config")
    empty = folder / "empty"
    empty.write_bytes(b"")
    global_config = folder / "gitconfig"
    global_config.write_bytes(
        (
            "[core]\n"
            f"\texcludesFile = {_config_path(empty)}\n"
            f"\tattributesFile = {_config_path(empty)}\n"
        ).encode("utf-8")
    )
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("GIT_CONFIG_GLOBAL", str(global_config))
        mp.setenv("GIT_CONFIG_NOSYSTEM", "1")
        mp.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path_factory.getbasetemp()))
        yield
