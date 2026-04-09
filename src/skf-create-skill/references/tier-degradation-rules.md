# Tier Degradation Rules

## Remote Source at Forge/Deep Tier

When `source_repo` is a remote URL (GitHub URL or owner/repo format) and the tier is Forge or Deep:

- **ast-grep requires local files** — it cannot operate on remote URLs

**Workspace-first clone strategy (preferred):**

1. Check `git` availability (`git --version`). `git` is effectively guaranteed at Deep tier (via `gh` dependency) but NOT guaranteed at Forge tier.
2. If `git` is available: check for an existing workspace checkout at `{workspace_root}/repos/{host}/{owner}/{repo}/`. If found, `git fetch` to update. If not found, clone into the workspace path with `--depth 1 --single-branch`. See `source-resolution-protocols.md` for the full workspace resolution algorithm.
3. The workspace uses a full checkout (no sparse-checkout). Brief `include_patterns` and `exclude_patterns` are applied as file-level filters at extraction time, not at the git level. This allows a single workspace checkout to serve multiple briefs with different scope filters.
4. For update-skill: `changed_files_from_manifest` scoping is applied as file-level filters at extraction time on the full workspace checkout.
5. If workspace clone/fetch succeeds: use the workspace path for AST extraction. All results are T1 with `[AST:...]` citations.
6. If workspace fails: fall back to ephemeral clone (`{system_temp}/skf-ephemeral-{skill-name}-{timestamp}/`). If ephemeral succeeds, use it. Ephemeral clone is deleted after extraction.
7. Workspace checkouts persist across forges — CCC indexes, tool outputs, and the checkout itself are reused.

**Fallback (clone fails or `git` unavailable):**

- The extraction step MUST warn the user explicitly before degrading
- **create-skill:** Warning must include actionable guidance — clone locally and update `source_repo` in the brief to the local path
- **update-skill:** Warning must include actionable guidance — clone locally, re-run [CS] Create Skill with the local path to regenerate provenance data, then re-run the update
- Extraction proceeds using Quick tier strategy (source reading via gh_bridge — resolved as `gh api` commands or direct file I/O; see `knowledge/tool-resolution.md`)
- All results labeled T1-low with `[SRC:...]` citations
- The degradation reason is recorded in the evidence report

Silent degradation is **forbidden**. The user must always know when AST extraction was skipped and why.

## AST Tool Unavailable at Forge/Deep Tier

When the tier is Forge or Deep but ast-grep is not functional:

- The extraction step MUST warn the user explicitly before degrading
- Warning must include actionable guidance: run [SF] Setup Forge to detect tools
- Extraction proceeds using Quick tier strategy
- All results labeled T1-low
- The degradation reason is recorded in the evidence report

## Per-File AST Failure

When ast-grep fails on an individual file (parse error, unsupported syntax):

- Fall back to source reading for **that file only**
- Other files continue with AST extraction
- The affected file's results are labeled T1-low; unaffected files retain T1
- Log a warning noting which file degraded and why
