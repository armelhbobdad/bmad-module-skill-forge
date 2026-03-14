# Progressive Capability

## Principle

Every capability tier — Quick, Forge, and Deep — produces legitimate, useful skills. Tiers describe what tools are available, not a quality hierarchy. A Quick skill is complete at its tier; a Deep skill adds depth, not correctness. Framing is always positive: describe what each tier enables, never what it lacks.

## Rationale

Skill Forge operates in diverse environments. Some users have ast-grep, GitHub CLI, and QMD installed; others have none. The progressive capability model ensures Ferris adapts to the environment without making users feel their setup is insufficient.

Without progressive capability:
- Users without ast-grep see error messages or degraded output
- Quick tier skills feel like failures rather than valid deliverables
- Workflow steps contain conditional logic for missing tools scattered throughout

With progressive capability:
- Each tier has a clear identity and positive capability description
- Workflow behavior adapts cleanly based on the detected tier
- Users understand what their tier enables and what upgrading would add

## Tier Definitions

| Tier | Requirements | Capabilities | Identity |
| --- | --- | --- | --- |
| Quick | No tools required | Fast, template-driven, package-name resolution | Speed-first skill creation |
| Forge | ast-grep available | AST-backed structural analysis, line-level citations | Precision-focused compilation |
| Deep | ast-grep + gh + qmd | AST + GitHub exploration + QMD synthesis, maximum provenance | Full intelligence pipeline |

## Pattern Examples

### Example 1: Tool Detection and Tier Assignment

**Context:** The setup-forge workflow detects available tools and assigns a tier.

**Implementation:** Each tool is verified by executing its version command — presence in PATH is insufficient. The tier is the highest level where all required tools pass verification:

```
ast-grep --version  → required for Forge
gh --version        → required for Deep
qmd status          → required for Deep
```

If ast-grep passes but gh fails, the tier is Forge (not a "degraded Deep").

**Key Points:**
- Tools must be functional, not just installed
- Tier assignment is deterministic — no ambiguity
- The result is written to `forge-tier.yaml` in the sidecar and persists across sessions

### Example 2: Positive Tier Framing

**Context:** Reporting the detected tier to the user.

**Implementation:**
```
Quick:  "Fast, template-driven skill creation — package-name resolution and
         source reading. Skills ready in minutes."

Forge:  "AST-backed structural analysis — line-level citations with verified
         signatures. Precision-focused compilation."

Deep:   "Full intelligence pipeline — AST verification plus GitHub exploration
         and QMD knowledge synthesis. Maximum provenance depth."
```

**Key Points:**
- Each description leads with what the tier does, not what it misses
- No tier mentions another tier's capabilities as something it lacks
- Quick is "fast" not "limited"; Forge is "precise" not "partial"

### Example 3: Tier-Adaptive Extraction

**Context:** The create-skill extraction step adapts its strategy based on the forge tier.

**Implementation:**
- **Quick:** Reads source files, applies pattern matching for exports and signatures, produces T1-low citations. Uses `gh_bridge` for file structure when available as a convenience, not a requirement.
- **Forge:** Uses `ast_bridge.scan_definitions()` for structural parsing, produces T1 citations with exact AST node types. Falls back to source reading for files ast-grep cannot parse.
- **Deep:** Identical extraction to Forge, plus QMD enrichment in a separate step. T2 annotations layer on top of the T1 base without replacing it.

**Key Points:**
- Extraction quality increases with tier, but every tier produces complete output
- Forge and Deep share the same extraction core — Deep adds enrichment, not better parsing
- Fallback within a tier (e.g., ast-grep fails on one file) degrades gracefully to T1-low for that file only

### Example 4: Tier-Adaptive Scoring

**Context:** The test-skill workflow adjusts scoring weights based on the forge tier.

**Implementation:**
- **Quick (Naive mode):** Export Coverage 45%, Signature Accuracy 25%, Type Coverage 20%, External Validation 10%. No coherence check — AST verification unavailable. When external validation tools (skill-check, tessl) are unavailable, their 10% is redistributed proportionally across the remaining categories.
- **Forge (Contextual mode):** Export Coverage 40%, Signature Accuracy 25%, Type Coverage 15%, Coherence 20%. Full AST-backed verification.
- **Deep (Contextual mode):** Same weights as Forge, plus cross-repo verification and QMD coherence checks feed into the coherence score.

**Key Points:**
- Pass threshold (80%) is the same across all tiers — quality bar is tier-independent
- Weight redistribution reflects what each tier can actually measure
- A Quick skill scoring 85% and a Deep skill scoring 85% both pass — different measurements, same bar

## Graceful Degradation

When a tool becomes unavailable mid-session (e.g., ast-grep uninstalled between runs):
1. Setup-forge re-detects and downgrades the tier
2. Existing skills retain their original citations — they don't retroactively lose confidence
3. New extractions use the current tier's capabilities
4. The tier change is logged in the sidecar for audit trail

When source is remote (GitHub URL) and tier is Forge or Deep:
1. AST extraction requires local files — ast-grep cannot operate on remote URLs
2. The extraction step attempts an **ephemeral shallow clone** to a system temp path (if `git` is available)
3. If the clone succeeds: AST extraction proceeds on the local clone, then the temp directory is cleaned up
4. If the clone fails (or `git` is unavailable): the step warns the user explicitly and degrades to source reading (T1-low) with actionable guidance
5. Silent degradation is forbidden — the user must always know when AST extraction was skipped and why

## Anti-Patterns

- Describing Quick tier as "basic" or "limited" — it is fast and legitimate
- Requiring ast-grep for workflows that work fine without it (setup-forge, brief-skill)
- Mixing tier capabilities in a single extraction (e.g., T1 citations when only source reading was used)
- Failing a workflow because the tier is "too low" — adapt behavior instead
- Silent degradation when source is remote at Forge/Deep tier — always warn with actionable guidance

## Related Fragments

- [confidence-tiers.md](confidence-tiers.md) — how tier determines available confidence levels
- [skill-lifecycle.md](skill-lifecycle.md) — how tier affects workflow selection and artifact flow
- [zero-hallucination.md](zero-hallucination.md) — Quick tier has lower confidence but the same integrity standard

_Source: distilled from forge-tier.yaml, tier-rules.md, and setup-forge workflow_
