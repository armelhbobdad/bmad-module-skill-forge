# Whole-Language Reference Assembly Overrides

A **whole-language reference** is a compiler/interpreter repo (rustc, CPython, the Go toolchain, TypeScript) enriched with the language's canonical prose (the guide/Book and the standard/library docs). It maps to `scope.type: full-library`, but its value to a skill consumer is the **language**, not the compiler's internal exports. The standard library-export layout of `assets/compile-assembly-rules.md` would foreground compiler-internal signatures and bury the prose; these overrides invert that.

**GATE: apply ONLY when this is a whole-language reference.** The brief carries ≥1 `doc_urls` entry with `source: language-registry` (equivalently, `skf-derive-assembly-shape.py` returns `assembly_shape: "whole-language-reference"`). This is a structured, schema-validated signal, not a `scope.notes` substring, so an ordinary `full-library` library, a parser *library* (pest/lalrpop: its code IS the product, so §6b seeds no corpora), a component-library, a reference-app (including the language/spec-reference DSL sub-shape, which stays `scope.type: reference-app` and is handled by `references/assembly-reference-app.md`), and a docs-only brief all fail the gate. When the gate does not fire, **skip this entire file**: the standard Tier 1 (sections 1–8) and Tier 2 (9–11) layout and the signature-fidelity rule run unchanged, so non-whole-language skills assemble byte-identically.

When the gate fires, the assembler has a `language_guide[]` artifact, which step 5 §1 builds from the registry pages step 3c §4a kept (the retained corpora prose, carved out of the T3-vs-T1 conflict rule). Apply these overrides:

**Empty-guide guard (check first):** If `language_guide[]` is absent or every entry's `prose` is null (all registry corpora failed to fetch), do not emit a thin Language Guide above a full internals section: fall back to the standard layout and record a warning in `evidence-report.md`: "Whole-language reference gated but no Language-Guide prose was retained {an em dash} assembled as a standard library skill." This prevents the inverse-value outcome (prose section empty, compiler internals dominant).

**New Section 1b, Language Guide (Tier 1, foregrounded):** Immediately after Section 1 (Overview) and BEFORE Quick Start, emit the skill's primary content from `language_guide[]`. One subsection per corpus (`{label}`), carrying the retained prose (language concepts, idioms, and usage examples), each block cited `[EXT:{url}]`. This is the section an agent reads to learn the language; it survives split-body as Tier 1.

**Section 2 (Quick Start), language-usage override:** Build the runnable examples from the Language-Guide prose (writing and running code *in* the language: a minimal program, a common idiom), cited `[EXT:{url}]`, not from compiler-internal export call chains. Fall back to the standard signature-only Quick Start only if the guide yields no examples.

**Section 3 (Common Workflows), "Writing {language}" override:** Replace function-call-chain workflows over compiler exports with common language tasks (define a type, handle errors, organize a module), each a short idiom from the guide.

**Section 4 (Key API Summary), demote compiler internals:** Replace the top-of-body compiler-export function table with a one-paragraph "Standard Library & Language Surface" pointer into the Language Guide. Move the AST/compiler-internal exports into a late-ordered Tier 2 subsection `### Compiler Internals (reference only)` with a one-line note: "Internal implementation surface of the {language} toolchain {an em dash} most consumers want the Language Guide above, not these."

**Signature fidelity is preserved (not relaxed):** any compiler signature that appears (in Compiler Internals) follows rule 7 (Signature fidelity) of `assets/compile-assembly-rules.md`'s Assembly Rules.

**metadata.json:** the skill stays `scope.type: full-library`; export-count stats are still emitted. (A whole-language skill's low public-API coverage versus the full compiler surface is expected; coverage-gate semantics for this shape are tracked separately and out of scope here.)
