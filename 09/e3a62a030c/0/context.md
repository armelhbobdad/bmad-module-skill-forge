# Session Context

## User Prompts

### Prompt 1

read the bug we described in @installation-bug.txt . See @temp/BMAD-METHOD-main/ reference that also generate IDE specfic configurations.

### Prompt 2

yes

### Prompt 3

commits changes please

### Prompt 4

what happen when I try to install the module more than once in the same directory? Here is an sample output:rmel@dzeta:~/Projects/demo/fast$ node /home/armel/Projects/OSS/bmad-module-skill-forge/tools/skf-npx-wrapper.js install
  ____  _  _______ 
 / ___|| |/ /  ___|
 \___ \| ' /| |_   
  ___) | . \|  _|  
 |____/|_|\_\_|    
                   
  Skill Forge
  AST-verified, provenance-backed agent skills from code
  repositories, documentation, and developer discourse

  Target: /home/armel/...

### Prompt 5

Are you sure it works? I just tried it here but look at the `fast` repo: armel@dzeta:~/Projects/demo/fast$ node /home/armel/Projects/OSS/bmad-module-skill-forge/tools/skf-npx-wrapper.js install
  ____  _  _______ 
 / ___|| |/ /  ___|
 \___ \| ' /| |_   
  ___) | . \|  _|  
 |____/|_|\_\_|    
                   
  Skill Forge
  AST-verified, provenance-backed agent skills from code
  repositories, documentation, and developer discourse

  Target: /home/armel/Projects/demo/fast

  Found existi...

### Prompt 6

we still have the .codex and .cursor commands. Is it normal?

### Prompt 7

it works now. commit.

### Prompt 8

now we need to update the installation methods (we have 3 now) in @README.md, @docs/ and @website/src/content/docs.

### Prompt 9

the second methode is not accurate. Here is what i really did: Method 2: While installing bmad using `npx bmad-method install`. Here is the output:

armel@dzeta:~/Projects/demo/quick$ npx bmad-method install
│ ╭─v6.0.4─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ │                                                 ...

### Prompt 10

according to @package.json , we can also install our module with the keyword `skill-forge`. e.g: npx skill-forge install

### Prompt 11

commit

### Prompt 12

do we need to update our internal article @_bmad-output/planning-artifacts/medium-article-skf.md?

### Prompt 13

1-2

### Prompt 14

the agent command has double skf-skf while other as qa, sm, dev, etc..

### Prompt 15

I think, I will better to keep it as a role like (qa, dev, pm,...). What is the best role we can add for our agent? surgeon? forger?

### Prompt 16

yes

### Prompt 17

commit

