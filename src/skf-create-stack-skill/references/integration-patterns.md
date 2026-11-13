<!-- Config: communicate in {communication_language}. -->

# Integration Pattern Detection Rules

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
