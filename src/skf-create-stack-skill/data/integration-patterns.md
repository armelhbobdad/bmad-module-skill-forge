# Integration Pattern Detection Rules

## Co-Import Detection

A co-import is detected when two or more confirmed libraries are imported in the same source file.

### Detection Method

1. For each file in the codebase, extract all import statements
2. Map imports to confirmed library list
3. If a file imports 2+ confirmed libraries → co-import detected
4. Record: file path, library pair, line numbers

### Minimum Threshold

- A library pair must co-appear in **2+ files** to qualify as an integration pattern
- Single file co-imports may be incidental

## Integration Pattern Types

### Type 1: Middleware Chain
Libraries connected in a processing pipeline.
- **Signal:** Sequential function calls passing output of one library to another
- **Example:** `express` + `cors` — cors middleware registered on express app

### Type 2: Shared Types
Libraries exchanging type definitions or data structures.
- **Signal:** Type imports from one library used as parameters/returns in another
- **Example:** `react` + `react-router` — Router components accepting React elements

### Type 3: Configuration Bridge
One library configuring or initializing another.
- **Signal:** Config objects or initialization calls referencing both libraries
- **Example:** `next` + `tailwindcss` — Tailwind configured via next.config

### Type 4: Event Handler
Libraries connected through event emission/handling patterns.
- **Signal:** Event listeners from one library triggering actions in another
- **Example:** `socket.io` + `redis` — Redis pub/sub driving socket events

### Type 5: Adapter/Wrapper
One library wrapping another to provide a unified interface.
- **Signal:** Thin wrapper functions delegating to underlying library
- **Example:** `prisma` + `zod` — Zod schemas validating Prisma model inputs

### Type 6: State Sharing
Libraries sharing application state or context.
- **Signal:** Shared state stores, context providers, or global singletons
- **Example:** `react` + `zustand` — Zustand stores consumed in React components

## Output Format

For each detected integration:
```
Library A + Library B
  Type: [pattern type]
  Files: [count] files with co-imports
  Key files: [top 3 files by integration density]
  Pattern: [brief description of how they integrate]
  Confidence: [T1/T1-low based on detection method]
```
