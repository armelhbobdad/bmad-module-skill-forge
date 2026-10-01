---
nextStepFile: 'severity-classify.md'
outputFile: '{forge_version}/drift-report-{timestamp}.md'
# This run's stage data folder: step 5 classifies the JSON saved here.
auditDataFolder: '{forge_version}/.skf-audit/{timestamp}'
compareConstituentHashesProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-hash-content.py'
  - '{project-root}/src/shared/scripts/skf-hash-content.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 1c: Constituent Freshness

## STEP GOAL:

Audit a compose-mode stack in place of steps 2 to 4: check whether each constituent skill changed since the stack was composed, save the comparison for step 5, and write the Structural Drift section. A compose-mode stack has no source tree to re-index: its provenance entries record the constituent skills it was composed from, so a source diff would read every one of them as removed.

## Rules

- Run only for a compose-mode stack (`{compose_mode_stack}`, step 1 §4): every other skill runs steps 2 to 4
- Do not classify severity (step 5) or suggest remediation (step 6)

## MANDATORY SEQUENCE

### 1. Compare the Constituents' Hashes

Each constituent's `metadata_hash` is the sha256 of its raw `metadata.json` bytes when the stack was composed, which the model cannot compute itself: run the helper.

**Resolve `{compareConstituentHashesHelper}`** from `{compareConstituentHashesProbeOrder}`; first existing path wins. A relative constituent `skill_path` (e.g. `skills/{skill-dir}/`) is project-root-relative, so the helper resolves it against `{project-root}`. Create the stage data folder first (`mkdir -p "{auditDataFolder}"`), then save the comparison in it:

```bash
uv run {compareConstituentHashesHelper} compare-constituent-hashes "{provenanceMap}" --skills-root "{project-root}" > "{auditDataFolder}/constituent-freshness.json"
```

The saved JSON, which step 5 builds its findings from:

```json
{
  "drifted":           [{"skill_name": "...", "skill_path": "...", "stored_hash": "sha256:...", "current_hash": "sha256:..."}],
  "fresh":             [{"skill_name": "..."}],
  "missing":           [{"skill_name": "...", "skill_path": "...", "stored_hash": "sha256:...", "reason": "metadata-not-found|incomplete-record"}],
  "skipped_null_hash": [{"skill_name": "..."}],
  "stats": {"total": N, "drifted": N, "fresh": N, "missing": N, "skipped_null_hash": N}
}
```

- `drifted[]`: a constituent whose live `metadata.json` differs from the one the stack was composed from. Step 5 grades each one HIGH.
- `missing[]`: a constituent whose `metadata.json` cannot be found (`metadata-not-found`), or whose provenance record lacks `skill_name` or `skill_path` (`incomplete-record`). Step 5 grades each one MEDIUM.
- `skipped_null_hash[]`: no hash was recorded when the stack was composed (a references/ cascade), so there is nothing to compare. Never drift.
- `fresh[]`: unchanged.

**If `uv` or the helper cannot execute** (e.g. claude.ai web), or the command exits non-zero: hash by hand instead. For each constituent, read its `metadata.json` at `{constituent.skill_path}/active/{constituent.skill_name}/metadata.json` (resolve `skill_path` against `{project-root}` when relative, and use it as-is when absolute), compute the SHA-256 of its raw bytes with a shell tool (for example `sha256sum`), and compare against `constituent.metadata_hash` (a stored bare-hex form still matches after stripping any `sha256:` prefix from both sides). Sort the constituents into the same four buckets and write them over `{auditDataFolder}/constituent-freshness.json` in the helper's shape, so step 5 reads them as it would the helper's.

If the stage data folder or the file cannot be written, HALT with **exit 4**, `halt_reason: "write-failed"`. When `{headless_mode}`, emit the error envelope on **stderr** (shape per SKILL.md → Result Contract).

### 2. Compile the Structural Drift Section

Append to {outputFile}, taking every count from `stats` (no recount):

```markdown
## Structural Drift

**Comparison:** each constituent skill now vs when the stack was composed ({provenance_generated_at})
**Method:** metadata hash comparison: a compose-mode stack has no source tree to re-index

### Constituent Freshness (drifted {stats.drifted}, missing {stats.missing}, fresh {stats.fresh})

| Constituent | Compose-time Hash | Current Hash |
|-------------|-------------------|--------------|
| {skill_name} | `{stored_hash}` | `{current_hash}` |

**Missing constituents:** {skill_name} ({reason}) for each `missing[]` entry, or none.
**Not compared (no compose-time hash):** {skill_name} for each `skipped_null_hash[]` entry, or none.

## Semantic Drift

**Status:** Skipped: a compose-mode stack has no source tree to compare
```

### 3. Update Report and Auto-Proceed

Update {outputFile} frontmatter: append `'constituent-freshness'` to `stepsCompleted`. Once both sections have been appended, load, read fully, and execute `{nextStepFile}` (severity classification).
