# Doc Fetcher

## Purpose

T3 external documentation fetching retrieves content from URLs specified in the extraction brief. It serves as the primary extraction source in Scenario D (docs-only, SaaS, closed-source) where no source code is available, and as a supplemental source when a brief includes `doc_urls` alongside a source repository.

## Tool-Agnostic Principle

`doc_fetcher` is not a wrapper around any specific CLI tool. The LLM agent uses whatever web fetching capability is available in its environment — Firecrawl MCP, WebFetch, curl, browser automation tools, or any other URL retrieval mechanism. The extraction workflow never assumes a particular fetching tool exists; it discovers available capabilities at runtime and uses the best option present.

## T3 Quarantine Rules

All content obtained through doc fetching is classified as **external, untrusted** and subject to quarantine constraints:

1. **Citation format** — every doc-fetched claim uses `[EXT:{url}]` citation format
2. **Conflict resolution priority** — T3 has the lowest priority: `T1 > T1-low > T2 > T3`
3. **Source authority cap** — T3 content forces `source_authority: community` in metadata; it never qualifies as `official`
4. **No structural claims** — T3 cannot assert verified signatures or line-level precision

## When to Use

| Scenario | Role | Example |
| --- | --- | --- |
| Scenario D — docs-only / SaaS / closed-source | **Primary source** | Stripe API, Twilio SDK docs |
| Brief includes `doc_urls` alongside source repo | **Supplemental enrichment** | README links, hosted API reference |

When used as supplemental enrichment, T3 content adds context but never overrides T1 or T1-low claims extracted from the actual source code.

## Security Considerations

- URLs specified in the brief are transmitted to external services for content extraction — the agent must inform the user which URLs will be fetched before initiating retrieval
- Fetched content should not be trusted as authoritative; it may be outdated, modified, or incorrect
- The agent should not follow redirects to unexpected domains without user confirmation

## Interaction with Other Tiers

- **T3 never replaces T1 (AST) or T2 (QMD)** content for the same export — quarantine rules enforce this
- **Deep tier**: T3 content can be enriched by QMD (T2 annotations layered onto a T3 base), producing richer output while preserving the T3 confidence label on the base claim
- **Forge tier**: T3 content exists alongside T1 AST content; T1 takes precedence for any overlapping claims
- **Quick tier**: T3 may be the only external enrichment available, but T1-low source-read claims still outrank it

## Anti-Patterns

- Citing doc-fetched content with `[AST:...]` or `[SRC:...]` format — always use `[EXT:{url}]`
- Promoting T3 claims to `source_authority: official` regardless of the documentation source
- Fetching URLs without informing the user which external services will be contacted
- Using T3 content to override a contradicting T1 or T1-low extraction

## Related Fragments

- [confidence-tiers.md](confidence-tiers.md) — tier definitions, citation formats, and precedence rules
- [progressive-capability.md](progressive-capability.md) — how capability tiers determine available extraction methods
- [zero-hallucination.md](zero-hallucination.md) — the foundational principle that T3 quarantine enforces

_Source: consolidated from extraction brief schema, create-skill Scenario D handling, and confidence tier conflict resolution rules_
