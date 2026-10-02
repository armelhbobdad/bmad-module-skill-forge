<!-- Fixed contract for Steps 02-04 (gap-analysis.md, issue-detection.md, improvements.md), and for how Step 05 (compile.md) records a finding its review dropped. No customization replaces it: `workflow.refinement_rules_path` swaps only the house-style references/refinement-rules.md. -->

# Finding Storage (Steps 02-05)

Each analysis step stores its findings two ways: as workflow state for Step 05, and appended to the RA state file `{forge_data_folder}/ra-state-{project_name}.md` as a labeled block, `<!-- [RA-GAPS] ... -->`, `<!-- [RA-ISSUES] ... -->` or `<!-- [RA-IMPROVEMENTS] ... -->`. A block holds the **complete formatted findings**: each finding's full citation as its step formats it, with its type and its tier (a gap has none), the skills it cites, the evidence and the suggestion, never only counts, so Step 05 can rebuild them if context degrades on a long run. The refined document itself is written once, in Step 05; Steps 02-04 never write to it.

A finding that involves a skill or a pair outside the document's scope (Step 02 §2b) goes under the shared `<!-- [RA-OUT-OF-SCOPE] ... -->` block instead: it is listed for awareness only, and Step 05 leaves it out of the refined document.

## Findings a Review Dropped

`{dismissed_findings}` (Step 01 §1b) lists the findings a step 5 review dropped from an earlier refinement of this document, each as `{kind, skills, anchor, title, capability}`; it is empty on a first pass. If it is no longer in context, read it again as Step 01 §1b does.

Compare each in-scope finding with that list before storing it. It matches a record when its kind (`gap`, `issue` or `improvement`) is the record's and it cites the same skills (the same pair for a gap or a synergy, in either order). An issue must also contradict the claim the record's `anchor` holds, or have no claim line when that anchor is `null`, and an improvement must name the capability or API the record's `capability` holds, so one dropped finding never hides another about the same skills. Store a matching finding in full under the shared `<!-- [RA-DISMISSED] ... -->` block instead of under its kind's block, with a one-line title of its own and the `title` of the record it matched: Step 05 lists it at the review and inserts it only if the user takes it back. Report it apart from the step's count, as previously dismissed.

**How Step 05 records a drop.** A feedback round of the step 5 review that drops an entry adds its record, `{"kind", "skills", "anchor", "title", "capability"}` (`title` a line naming the finding, such as its heading; `capability` the `{api}` an improvement's block names, `null` for a gap or an issue), to the list of dropped findings, and a finding the user takes back removes the record it matched. Keep that list in `{run_dir}/dismissed.json`, which the first round that changes it starts from `{dismissedFile}` (`[]` when that file does not exist). It reaches `{dismissedFile}` only at [C], once `promote` exits 0, so [X] leaves the record as it was. To write it there, resolve `{atomicWriteHelper}` from Step 05's `{atomicWriteProbeOrder}` (first existing path wins) and run:

```bash
uv run {atomicWriteHelper} write --target "{dismissedFile}" < "{run_dir}/dismissed.json"
```

If no candidate exists or the command fails, say "The dropped findings were not recorded ({reason}): a later run may raise them again." and go on.
