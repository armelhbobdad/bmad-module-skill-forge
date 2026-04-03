# Session Context

## User Prompts

### Prompt 1

IT IS CRITICAL THAT YOU FOLLOW THIS COMMAND: LOAD the FULL {project-root}/_bmad/bmb/workflows/module/workflow-edit-module.md, READ its entire contents and follow its directions exactly!

### Prompt 2

@src/

### Prompt 3

Take a look at @_bmad-output/todo. We should fix all of them and also fix missing impacts, regression, bug. Go to party mode for different perspectives

### Prompt 4

IT IS CRITICAL THAT YOU FOLLOW THIS COMMAND: LOAD the FULL {project-root}/_bmad/core/workflows/party-mode/workflow.md, READ its entire contents and follow its directions exactly!


ARGUMENTS: We're reviewing and fixing the SKF module. Key issue: bug-sidecar-path-missing-from-config.md — sidecar_path (prompt: false) is never written to installed config.yaml, causing silent workflow degradation across 8+ workflows. All silently fall back to Quick tier instead of detected tier. We need perspecti...

### Prompt 5

E

### Prompt 6

yes

### Prompt 7

is it a good idea to plan the fix regarding the upstream installer?

### Prompt 8

save it locally first in todo folder.

### Prompt 9

is it not possible to fix it in skf standalone installer?

### Prompt 10

should we revert the previous workaround?

### Prompt 11

do two separate commits

