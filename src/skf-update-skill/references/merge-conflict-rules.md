# Merge Conflict Rules

## Change Categories

### Category 1: Modified Exports (signature/type change)

- **Action:** Re-extract affected export with fresh AST analysis
- **Merge:** Replace generated content for that export; preserve adjacent [MANUAL] blocks
- **Confidence:** Same tier as original (T1/T1-low/T2)

### Category 2: New Exports (added since last generation)

- **Action:** Extract new export with full AST analysis
- **Merge:** Append to appropriate section based on export type (function, type, class, constant)
- **Confidence:** Label with extraction tier confidence
- **[MANUAL] impact:** None — new content, no existing [MANUAL] blocks

### Category 3: Deleted Exports (removed from source)

- **Action:** Remove generated content for that export
- **Merge:** Check for attached [MANUAL] blocks before deletion
- **If [MANUAL] attached:** Flag as orphan, present to user for decision
- **If no [MANUAL]:** Auto-remove generated content

### Category 4: Moved Exports (file relocated)

- **Action:** Update provenance map file references
- **Merge:** Update file:line citations in generated content
- **Confidence:** Retain original tier if AST structure unchanged; downgrade to T1-low if structure changed
- **[MANUAL] impact:** Preserve — content unchanged, only provenance metadata updates

### Category 5: Renamed Exports (identifier changed)

- **Action:** Re-extract with new identifier
- **Merge:** Replace old identifier references in generated content
- **[MANUAL] impact:** Flag if [MANUAL] blocks reference old identifier name

## Merge Priority Order

1. Process deleted exports first (remove generated content, flag [MANUAL] orphans)
2. Process moved exports second (update references only)
3. Process renamed exports third (update identifiers)
4. Process modified exports fourth (re-extract and replace)
5. Process new exports last (append to sections)

## Stack Skill Merge Rules

For stack skills with multi-file outputs:

1. **SKILL.md:** Apply standard merge rules above
2. **references/{library}.md:** Merge per-library, preserving [MANUAL] blocks within each
3. **references/integrations/{pair}.md:** Merge per-integration-pair
4. **metadata.json:** Regenerate completely (no [MANUAL] support in JSON)
5. **context-snippet.md:** Regenerate completely (no [MANUAL] support — too concise)

## Conflict Resolution Strategies

| Strategy     | When                                | Action                                    |
|--------------|-------------------------------------|-------------------------------------------|
| Auto-resolve | No [MANUAL] conflicts, clean merge  | Proceed without user input                |
| User-resolve | [MANUAL] conflicts detected         | Halt, present conflicts, require decision |
| Abort        | Critical structural incompatibility | Stop workflow, recommend full re-creation |
