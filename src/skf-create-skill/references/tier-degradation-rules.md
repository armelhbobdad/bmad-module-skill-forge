# Tier Degradation Rules

## Remote Source at Forge/Deep Tier

When `source_repo` is a remote URL (GitHub URL or owner/repo format) and the tier is Forge or Deep:

- **ast-grep requires local files** — it cannot operate on remote URLs

**Private tree at the resolved commit (preferred):**

1. `skf-source-tree.py resolve` reads the resolved commit into a private tree of the run's own, from the workspace checkout at `{workspace_root}/repos/{host}/{owner}/{repo}/` when it holds the commit and from the remote otherwise. It then moves that workspace checkout to the same commit, cloning it first when it is missing, after the git hygiene check (it undoes the `.gitignore` edit `ccc init` made there and keeps ccc's index folder and SKF's lock file out of `git status`). See `source-resolution-protocols.md` for the full resolution algorithm.
2. When `git` is missing, resolve reports `git-unavailable` and reads no tree, and the run falls back to source reading (below). `git` is effectively guaranteed at Deep tier (via the `gh` dependency) but not at Forge tier.
3. The workspace uses a full checkout (no sparse-checkout). Brief `include_patterns` and `exclude_patterns` are applied as file-level filters at extraction time, not at the git level. This allows a single workspace checkout to serve multiple briefs with different scope filters.
4. For update-skill: a skill forged from a remote repository is read from a checkout of the skill's commit that update-skill prepares for each run (from the workspace clone's objects or the remote), never from the workspace clone as it stands, and `changed_files_from_manifest` scoping is applied as file-level filters at extraction time; a gap-driven repair reads the workspace clone after checking that it holds the skill's pinned commit.
5. If `resolve` reads the tree: use the tree for AST extraction. Each export an ast-grep rule matches is T1 with an `[AST:...]` citation; an export read by eye stays T1-low (see Source Read by Choice below).
6. If the remote cannot be reached, or the fetch or checkout fails, no tree is read: fall back to source reading (below). A tree that was read is removed at the end of the run.
7. Workspace checkouts persist across forges — CCC indexes, tool outputs, and the checkout itself are reused.

**Fallback (no tree can be read, or `git` is unavailable):**

- The extraction step warns the user explicitly before degrading — a silent drop from AST (T1) to source reading (T1-low) would leave them trusting a lower-confidence result without knowing it changed
- **create-skill:** the warning includes actionable guidance — clone locally and update `source_repo` in the brief to the local path
- **update-skill:** does not degrade to source reading for a remote skill: when it cannot get the commit to read, it stops before change detection (`init:source-tree`), since reading any other tree would compare the skill with the wrong code; when only the network is down, it reads the pinned commit from the workspace clone.
- Extraction proceeds using Quick tier strategy (source reading via gh_bridge — resolved as `gh api` commands or direct file I/O; see `knowledge/tool-resolution.md`)
- All results labeled T1-low with `[SRC:...]` citations
- The degradation reason is recorded in the evidence report

## AST Tool Unavailable at Forge/Deep Tier

When the tier is Forge or Deep but ast-grep is not functional:

- The extraction step warns the user explicitly before degrading
- The warning includes actionable guidance: run [SF] Setup Forge to detect tools
- Extraction proceeds using Quick tier strategy
- All results labeled T1-low
- The degradation reason is recorded in the evidence report

## Per-File AST Failure

When ast-grep fails on an individual file (parse error, unsupported syntax):

- Fall back to source reading for **that file only**
- Other files continue with AST extraction
- The affected file's results are labeled T1-low with `[SRC:...]` citations, `extraction_method: source-read` and `ast_node_type: null`; exports ast-grep matched in other files stay T1
- Log a warning noting which file degraded and why

## Source Read by Choice

When ast-grep works but an export is read by eye anyway (a file read to confirm a signature, a re-export the rules did not match, a symbol found while reading a neighbouring file):

- Label the export by the tool that produced it, not by the tier: T1-low with a `[SRC:{file}:L{line}]` citation
- Record `extraction_method: source-read`, `ast_node_type: null` and a `signature_source` other than T1
- Only an export an ast-grep rule matched is T1, with an `[AST:...]` citation, `extraction_method: ast-grep` and, as `ast_node_type`, the `kind` its recipe declares in `extraction-patterns.md`, or the kind the ast-grep Patterns table in `extraction-patterns-by-hand.md` gives a `find_code` pattern
- This is not a degradation: no warning is needed, and other exports keep their own labels
