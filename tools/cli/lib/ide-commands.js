/**
 * IDE Command Generator - Creates IDE-specific command/skill files
 * for each selected IDE so workflows and agents appear in command palettes.
 */

const path = require('node:path');
const fs = require('fs-extra');
const yaml = require('js-yaml');

/**
 * IDE target directory mapping.
 * Maps IDE code -> relative directory where command files are written.
 */
const IDE_TARGETS = {
  'claude-code': '.claude/commands',
  cursor: '.cursor/commands',
  cline: '.clinerules/workflows',
  codex: '.codex/prompts',
  'github-copilot': '.github/prompts',
  roo: '.roo/commands',
  windsurf: '.windsurf/workflows',
};

/**
 * Generate the agent command file content.
 */
function renderAgentCommand(agentName, description, agentPath) {
  return `---
name: '${agentName}'
description: '${agentName} agent'
---

You must fully embody this agent's persona and follow all activation instructions exactly as specified. NEVER break character until given an exit command.

<agent-activation CRITICAL="TRUE">
1. LOAD the FULL agent file from {project-root}/${agentPath}
2. READ its entire contents - this contains the complete agent persona, menu, and instructions
3. FOLLOW every step in the <activation> section precisely
4. DISPLAY the welcome/greeting as instructed
5. PRESENT the numbered menu
6. WAIT for user input before proceeding
</agent-activation>
`;
}

/**
 * Generate a workflow command file content.
 */
function renderWorkflowCommand(description, workflowPath) {
  return `---
description: '${description}'
---

IT IS CRITICAL THAT YOU FOLLOW THIS COMMAND: LOAD the FULL {project-root}/${workflowPath}, READ its entire contents and follow its directions exactly!
`;
}

/**
 * Collect agent artifacts from the installed SKF directory.
 * Returns array of { name, description, relativePath }.
 */
async function collectAgents(skfDir, skfFolder) {
  const agentsDir = path.join(skfDir, 'agents');
  const agents = [];

  if (!(await fs.pathExists(agentsDir))) return agents;

  const files = await fs.readdir(agentsDir);
  for (const file of files) {
    // Look for compiled .md agent files (not .agent.yaml source)
    if (!file.endsWith('.md')) continue;

    const agentName = file.replace('.md', '');
    const filePath = path.join(agentsDir, file);

    // Try to extract description from the compiled markdown frontmatter
    let description = `${agentName} agent`;
    try {
      const content = await fs.readFile(filePath, 'utf8');
      const fmMatch = content.match(/^---\s*\n([\s\S]*?)\n---/);
      if (fmMatch) {
        const fm = yaml.load(fmMatch[1]);
        if (fm && fm.title) description = fm.title;
      }
    } catch {
      /* use default description */
    }

    agents.push({
      name: agentName,
      description,
      relativePath: `${skfFolder}/agents/${file}`,
    });
  }

  return agents;
}

/**
 * Collect workflow artifacts from the installed SKF directory.
 * Returns array of { name, description, relativePath }.
 */
async function collectWorkflows(skfDir, skfFolder) {
  const workflowsDir = path.join(skfDir, 'workflows');
  const workflows = [];

  if (!(await fs.pathExists(workflowsDir))) return workflows;

  // Recursively find workflow.md files
  const walkDir = async (dir, relBase) => {
    const entries = await fs.readdir(dir, { withFileTypes: true });
    for (const entry of entries) {
      if (entry.isDirectory()) {
        await walkDir(path.join(dir, entry.name), `${relBase}/${entry.name}`);
      } else if (entry.name === 'workflow.md') {
        const filePath = path.join(dir, entry.name);
        const workflowName = path.basename(path.dirname(filePath));

        // Extract description from frontmatter
        let description = workflowName;
        try {
          const content = await fs.readFile(filePath, 'utf8');
          const fmMatch = content.match(/^---\s*\n([\s\S]*?)\n---/);
          if (fmMatch) {
            const fm = yaml.load(fmMatch[1]);
            if (fm && fm.description) description = fm.description;
          }
        } catch {
          /* use default */
        }

        workflows.push({
          name: workflowName,
          description,
          relativePath: `${skfFolder}/workflows${relBase}/workflow.md`,
        });
      }
    }
  };

  await walkDir(workflowsDir, '');
  return workflows;
}

/**
 * Remove SKF-related command files from an IDE target directory.
 * Only removes files matching the bmad-skf-* and bmad-agent-skf-* patterns.
 */
async function cleanSkfCommands(targetDir) {
  if (!(await fs.pathExists(targetDir))) return 0;

  const files = await fs.readdir(targetDir);
  let removed = 0;
  for (const file of files) {
    if (file.startsWith('bmad-skf-') || file.startsWith('bmad-agent-skf-')) {
      await fs.remove(path.join(targetDir, file));
      removed++;
    }
  }

  // Remove empty parent directories (e.g. .cursor/commands/ then .cursor/)
  if (removed > 0) {
    const remaining = await fs.readdir(targetDir);
    if (remaining.length === 0) {
      await fs.remove(targetDir);
      const parentDir = path.dirname(targetDir);
      const parentRemaining = await fs.readdir(parentDir);
      if (parentRemaining.length === 0) {
        await fs.remove(parentDir);
      }
    }
  }

  return removed;
}

/**
 * Remove stale SKF command files from all known IDE directories.
 * Called before generating new commands to handle IDE selection changes.
 */
async function cleanAllSkfCommands(projectDir) {
  for (const targetRelDir of Object.values(IDE_TARGETS)) {
    const targetDir = path.join(projectDir, targetRelDir);
    await cleanSkfCommands(targetDir);
  }
}

/**
 * Generate IDE command files for all selected IDEs.
 *
 * @param {string} projectDir - Project root directory
 * @param {string} skfFolder - Relative path to SKF dir (e.g. '_bmad/skf')
 * @param {string[]} ides - Array of IDE codes (e.g. ['claude-code', 'cursor'])
 * @returns {{ generated: number, ides: string[] }}
 */
async function generateIdeCommands(projectDir, skfFolder, ides) {
  // Always clean old SKF commands from all IDEs first
  await cleanAllSkfCommands(projectDir);

  if (!ides || ides.length === 0) return { generated: 0, ides: [] };

  const skfDir = path.join(projectDir, skfFolder);
  const moduleCode = 'skf';

  // Collect artifacts
  const agents = await collectAgents(skfDir, skfFolder);
  const workflows = await collectWorkflows(skfDir, skfFolder);

  let totalGenerated = 0;
  const processedIdes = [];
  const generatedFiles = [];

  for (const ide of ides) {
    const targetRelDir = IDE_TARGETS[ide];
    if (!targetRelDir) continue; // Skip unknown IDEs (e.g. 'other')

    const targetDir = path.join(projectDir, targetRelDir);
    await fs.ensureDir(targetDir);

    // Generate agent commands
    for (const agent of agents) {
      const fileName = `bmad-agent-${moduleCode}-${agent.name}.md`;
      const content = renderAgentCommand(agent.name, agent.description, agent.relativePath);
      await fs.writeFile(path.join(targetDir, fileName), content, 'utf8');
      totalGenerated++;
      generatedFiles.push(`${targetRelDir}/${fileName}`);
    }

    // Generate workflow commands
    for (const workflow of workflows) {
      const fileName = `bmad-${moduleCode}-${workflow.name}.md`;
      const content = renderWorkflowCommand(workflow.description, workflow.relativePath);
      await fs.writeFile(path.join(targetDir, fileName), content, 'utf8');
      totalGenerated++;
      generatedFiles.push(`${targetRelDir}/${fileName}`);
    }

    processedIdes.push(ide);
  }

  return { generated: totalGenerated, ides: processedIdes, files: generatedFiles };
}

module.exports = { generateIdeCommands };
