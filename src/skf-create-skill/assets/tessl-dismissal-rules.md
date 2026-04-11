# tessl Dismissal Rules

This file is the **single source of truth** for tessl review findings that Skill Forge expects and must dismiss. Step-06 §6 loads this file, parses the `tessl skill review` JSON output, and cross-references each finding against the rules below. Matches are dismissed with their rationale logged to the evidence report; non-matches surface to the user via §6b.

**Why this file exists:** Previously, expected tessl behavior was enumerated as prose in step-06 itself. Each time tessl evolved a scorer or added a new rule, step-06 had to be manually patched and the prose re-read by every execution. This file moves the expected behavior into a structured list with stable rule IDs, rationales, and match criteria — one place to update when tessl changes, one place to audit what SKF expects.

---

## Score Thresholds

When parsing tessl output, check these fields against the thresholds below. Violations trigger warnings or errors as specified.

| Field | Threshold | Severity on violation | Rationale |
|---|---|---|---|
| `review_score` (overall) | `>= 60` | warn | Two-tier SKF skills trade some conciseness score for progressive disclosure. 60 is the floor below which something is genuinely wrong. |
| `description_score` | `== 100` | **error — halt** | step-05 §2a sanitizes the description of angle-bracket tokens before validation. A score below 100 indicates the sanitizer missed a case (compilation bug in step-05) or a novel tessl rule not yet accounted for. Do not attempt to rewrite the description at step-06 — fix the sanitizer instead. |
| `content_score` | `>= 60` | warn | Two-tier design deliberately duplicates key API data across Tier 1 and Tier 2. Conciseness scorer penalizes this. 60 is the acceptable floor. |

If `description_score < 100`, halt with: "Description sanitization failed in step-05 §2a — tessl detected content that should have been sanitized. Do not rework the description at step-06. File a health-check issue against step-05 §2a." Do NOT proceed to §6b user prompt.

---

## Suggestion Dismissal Rules

Each rule below describes a tessl suggestion that Skill Forge expects and dismisses automatically. For each `judge_suggestion` in tessl output, check it against these rules in order. If any rule matches, record the dismissal in the evidence report (`rule_id`, `rationale`) and do NOT apply the suggestion. If no rule matches, the suggestion is novel and must surface to the user in §6b.

### Rule: `remove-manual-markers`

- **Scorer:** any
- **Match criteria (any of):**
  - Suggestion text contains `[MANUAL]` AND one of: `remove`, `delete`, `strip`, `clean up`
  - Suggestion text contains `manual marker` AND one of: `remove`, `delete`, `unnecessary`
- **Rationale:** `<!-- [MANUAL] -->` markers delineate author-added content that `skf-update-skill` preserves during merge operations. Removing them would cause update-skill to overwrite author edits on the next run. The markers are a load-bearing contract between create-skill, test-skill, and update-skill.
- **Action:** dismiss.

### Rule: `move-full-api-reference`

- **Scorer:** any
- **Match criteria (all of):**
  - Suggestion text mentions `Full API Reference` OR a `## Full ...` section heading
  - Suggestion text contains one of: `move`, `relocate`, `extract`, `split out`, `separate file`, `external file`
- **Rationale:** The two-tier design (Tier 1 inline + Tier 2 inline) keeps Tier 2 sections inline by default. `skill-check split-body` relocates Tier 2 to `references/` only when the body exceeds size limits — see step-06 §4. Preemptive relocation destroys the standalone SKILL.md that the cited 100% task accuracy (vs. 79% for on-demand retrieval) depends on.
- **Action:** dismiss.

### Rule: `consolidate-duplicate-parameters`

- **Scorer:** `conciseness` or any
- **Match criteria (any of):**
  - Suggestion mentions `duplicate parameter`, `redundant parameter`, `consolidate parameter`
  - Suggestion mentions both `Key API` / `Key API Summary` AND `Full API Reference` and suggests merging them
- **Rationale:** Tier 1 Key API Summary intentionally lists only key parameters for standalone discoverability. Tier 2 Full API Reference provides complete parameter tables, types, defaults, and edge cases. This is progressive disclosure, not duplication. Consolidating would force agents to scroll to Tier 2 for the most common function calls, defeating Tier 1's purpose and breaking the split-body Tier 1 preservation contract in step-06 §4.
- **Action:** dismiss.

### Rule: `conciseness-redundancy-between-tiers`

- **Scorer:** `conciseness`
- **Match criteria (all of):**
  - Scorer is `conciseness`
  - Suggestion or score rationale references redundancy between Tier 1 and Tier 2 sections (typically `Key API` ↔ `Full API` or `Quick Start` ↔ `Full Reference`)
- **Expected score:** 2/3 is normal. 3/3 is only achievable by collapsing the two-tier design.
- **Rationale:** Progressive disclosure is the intentional SKF design. The conciseness scorer has no concept of Tier 1 / Tier 2 and flags the structure as redundancy. Collapsing the two tiers would eliminate standalone discoverability and break split-body behavior.
- **Action:** dismiss. Do not attempt to raise the score above 2/3.

### Rule: `description-xml-tags-guarded-upstream`

- **Scorer:** `description_field` (deterministic validator)
- **Match criteria (any of):**
  - Finding rule ID is `description_field` AND message mentions `XML tag`, `must not contain`, or angle-bracket-related text
- **Expected occurrence:** zero. step-05 §2a sanitizes angle-bracket tokens before SKILL.md is written.
- **Action:** **DO NOT DISMISS.** This is an error, not an expected dismissal. Halt with: "Description sanitization failed in step-05 §2a. tessl detected angle-bracket content that should have been replaced. Fix the sanitizer in step-05 §2a — do not work around by editing the description at step-06."

---

## How Step-06 §6 Uses This File

1. Load this file completely at the start of §6.
2. Run `npx -y tessl skill review <staging-skill-dir>` and parse JSON output.
3. Check score thresholds. For `description_score < 100`: halt per the threshold table above. For other warns: continue, log warnings to evidence report.
4. For each `judge_suggestions[]` entry in the output:
   a. Iterate the rules above in order.
   b. If a rule's match criteria are satisfied, record `{rule_id, rationale, suggestion_text}` in the evidence report under "Dismissed tessl suggestions" and move to the next suggestion.
   c. If no rule matches, add the suggestion to the "Novel tessl suggestions" list that §6b surfaces to the user.
5. Proceed to §6b if any novel suggestions exist, or auto-proceed if all suggestions were dismissed.

---

## Evolving This List

When tessl introduces new rules, changes scorer behavior, or SKF design decisions change:

1. **Add a new rule section** above with `Rule:`, `Scorer:`, `Match criteria`, `Rationale`, `Action`.
2. **Link the rationale** to the concrete SKF design principle it protects (two-tier design, MANUAL markers, sanitization, split-body preservation, etc.). A rationale without a design-principle link is a smell.
3. **Keep score thresholds above current production floors.** Do not lower them to suppress real regressions.
4. **Never embed dismissal logic in step files.** If step-06 needs updated behavior, update this file first and reference it from step-06.

This file is load-bearing: step-06 §6 has no other source of truth for expected tessl behavior.
