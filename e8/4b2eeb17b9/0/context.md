# Session Context

## User Prompts

### Prompt 1

I got this message after installing `entire cli` tool: Warning: Husky detected (.husky/)

  Husky may overwrite hooks installed by Entire on npm install.
  To make Entire hooks permanent, add these lines to your Husky hook files:

    .husky/prepare-commit-msg:
      entire hooks git prepare-commit-msg "$1" "$2" 2>/dev/null || true

    .husky/commit-msg:
      entire hooks git commit-msg "$1" || exit 1

    .husky/post-commit:
      entire hooks git post-commit 2>/dev/null || true

    .husk...

### Prompt 2

commit everything

