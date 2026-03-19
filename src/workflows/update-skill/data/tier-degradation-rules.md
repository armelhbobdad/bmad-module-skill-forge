# Tier Degradation Rules

## Remote Source at Forge/Deep Tier

When `source_repo` is a remote URL (GitHub URL or owner/repo format) and the tier is Forge or Deep:

- **ast-grep requires local files** — it cannot operate on remote URLs

**Ephemeral clone strategy (preferred):**

1. Check `git` availability (`git --version`). `git` is effectively guaranteed at Deep tier (via `gh` dependency) but NOT guaranteed at Forge tier.
2. If `git` is available: perform an ephemeral shallow clone to a system temp path (`{system_temp}/skf-ephemeral-{skill-name}-{timestamp}/`).
3. For create-skill: use `--depth 1 --single-branch --filter=blob:none`; if `include_patterns` are specified, apply mode selection: if `exclude_patterns` are absent, use cone mode (convert include_patterns to directory roots; use `--skip-checks` for individual file paths); if `exclude_patterns` are present, use `--no-cone` mode (pass gitignore-style patterns with `!`-prefixed excludes — includes first, then negations). See source-resolution-protocols.md for the full conversion rules.
4. For update-skill: use sparse-checkout with `--skip-checks` scoped to the changed files from the change manifest only (file paths require `--skip-checks`). No `--branch` flag — uses the remote default branch (must match the branch used during original create-skill run).
5. If clone succeeds: use the local clone path for AST extraction. All results are T1 with `[AST:...]` citations.
6. Cleanup: delete the temp directory after extraction inventory is built and all data is in context. The clone never persists beyond the extraction step.

**Fallback (clone fails or `git` unavailable):**

- The extraction step MUST warn the user explicitly before degrading
- **create-skill:** Warning must include actionable guidance — clone locally and update `source_repo` in the brief to the local path
- **update-skill:** Warning must include actionable guidance — clone locally, re-run [CS] Create Skill with the local path to regenerate provenance data, then re-run the update
- Extraction proceeds using Quick tier strategy (source reading via gh_bridge)
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
