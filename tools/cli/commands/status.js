/**
 * SKF Status Command
 * Shows installation state, version, tier, configured IDEs, and sidecar status.
 */

const chalk = require('chalk');
const path = require('node:path');
const fs = require('fs-extra');
const yaml = require('js-yaml');
const { readManifest } = require('../lib/manifest');

const SKF_FOLDER = '_bmad/skf';
const SIDECAR_FOLDER = '_bmad/_memory/forger-sidecar';

const IDE_NAMES = {
  'claude-code': 'Claude Code',
  cline: 'Cline',
  codex: 'Codex',
  cursor: 'Cursor',
  'github-copilot': 'GitHub Copilot',
  roo: 'Roo Code',
  windsurf: 'Windsurf',
  other: 'Other',
};

async function readYaml(filePath) {
  try {
    const content = await fs.readFile(filePath, 'utf8');
    return yaml.load(content) || {};
  } catch {
    return null;
  }
}

async function getStatus(projectDir) {
  const skfDir = path.join(projectDir, SKF_FOLDER);
  const sidecarDir = path.join(projectDir, SIDECAR_FOLDER);

  const installed = await fs.pathExists(skfDir);
  if (!installed) {
    return { installed: false };
  }

  // Read config
  const config = await readYaml(path.join(skfDir, 'config.yaml'));

  // Read forge tier
  const forgeTier = await readYaml(path.join(sidecarDir, 'forge-tier.yaml'));

  // Read preferences
  const preferences = await readYaml(path.join(sidecarDir, 'preferences.yaml'));

  // Check agent file
  const agentFile = path.join(skfDir, 'agents', 'forger.md');
  const agentCompiled = await fs.pathExists(agentFile);

  // Count workflows
  const workflowsDir = path.join(skfDir, 'workflows', 'skillforge');
  let workflowCount = 0;
  if (await fs.pathExists(workflowsDir)) {
    const entries = await fs.readdir(workflowsDir);
    for (const entry of entries) {
      const wfPath = path.join(workflowsDir, entry, 'workflow.md');
      if (await fs.pathExists(wfPath)) {
        workflowCount++;
      }
    }
  }

  // Check output folders
  const skillsFolder = config?.skills_output_folder || 'skills';
  const forgeDataFolder = config?.forge_data_folder || 'forge-data';
  const skillsFolderExists = await fs.pathExists(path.join(projectDir, skillsFolder));
  const forgeDataFolderExists = await fs.pathExists(path.join(projectDir, forgeDataFolder));

  // Check sidecar state
  const sidecarExists = await fs.pathExists(sidecarDir);
  const tierDetected = forgeTier?.tier != null;

  // Read manifest
  const manifest = await readManifest(projectDir);

  return {
    installed: true,
    config,
    forgeTier,
    preferences,
    agentCompiled,
    workflowCount,
    skillsFolder,
    skillsFolderExists,
    forgeDataFolder,
    forgeDataFolderExists,
    sidecarExists,
    tierDetected,
    manifest,
  };
}

function displayStatus(status, version) {
  console.log('');
  console.log(chalk.hex('#F59E0B').bold('  Skill Forge — Status'));
  console.log(chalk.dim(`  v${version}`));
  console.log('');

  if (!status.installed) {
    console.log(chalk.yellow('  Not installed.'));
    console.log(chalk.dim('  Run: npx bmad-module-skill-forge install'));
    console.log('');
    return;
  }

  const config = status.config || {};

  // Installation
  const manifest = status.manifest;
  console.log(chalk.white.bold('  Installation'));
  console.log(`    Project:      ${chalk.hex('#FBBF24')(config.project_name || '(unknown)')}`);
  console.log(`    SKF folder:   ${chalk.dim(SKF_FOLDER + '/')}`);
  console.log(`    Agent:        ${status.agentCompiled ? chalk.green('compiled') : chalk.yellow('not compiled')}`);
  console.log(`    Workflows:    ${chalk.white(status.workflowCount)}`);
  if (manifest) {
    console.log(
      `    Installed:    ${chalk.dim(manifest.installed_at ? new Date(manifest.installed_at).toLocaleDateString() : '(unknown)')}`,
    );
    console.log(`    Manifest:     ${chalk.green('present')}`);
  } else {
    console.log(`    Manifest:     ${chalk.yellow('missing')} ${chalk.dim('(reinstall to generate)')}`);
  }
  console.log('');

  // IDEs
  const ides = config.ides || [];
  console.log(chalk.white.bold('  IDEs'));
  if (ides.length > 0) {
    for (const ide of ides) {
      console.log(`    ${chalk.green('●')} ${IDE_NAMES[ide] || ide}`);
    }
  } else {
    console.log(chalk.dim('    None configured'));
  }
  console.log('');

  // Forge Tier
  const ft = status.forgeTier || {};
  const tools = ft.tools || {};
  console.log(chalk.white.bold('  Forge Tier'));
  if (status.tierDetected) {
    const tierColors = { Quick: chalk.yellow, Forge: chalk.hex('#F59E0B'), Deep: chalk.hex('#FCD34D') };
    const tierColor = tierColors[ft.tier] || chalk.white;
    console.log(`    Tier:         ${tierColor(ft.tier)}`);
    console.log(`    Detected:     ${chalk.dim(ft.tier_detected_at || '(unknown)')}`);
  } else {
    console.log(chalk.dim('    Not detected yet — run @Ferris SF'));
  }
  console.log(`    ast-grep:     ${formatTool(tools.ast_grep)}`);
  console.log(`    gh CLI:       ${formatTool(tools.gh_cli)}`);
  console.log(`    QMD:          ${formatTool(tools.qmd)}`);
  console.log('');

  // Output Folders
  console.log(chalk.white.bold('  Output Folders'));
  console.log(`    Skills:       ${status.skillsFolder}/ ${status.skillsFolderExists ? chalk.green('✓') : chalk.yellow('missing')}`);
  console.log(`    Forge data:   ${status.forgeDataFolder}/ ${status.forgeDataFolderExists ? chalk.green('✓') : chalk.yellow('missing')}`);
  console.log('');

  // Sidecar
  console.log(chalk.white.bold('  Sidecar'));
  console.log(`    State:        ${status.sidecarExists ? chalk.green('initialized') : chalk.yellow('missing')}`);
  console.log(`    Location:     ${chalk.dim(SIDECAR_FOLDER + '/')}`);
  console.log('');
}

function formatTool(value) {
  if (value === true || value === 'available') return chalk.green('available');
  if (value == null) return chalk.dim('not detected');
  return chalk.yellow(String(value));
}

module.exports = {
  command: 'status',
  description: 'Show SKF installation state, version, tier, and configuration',
  options: [],
  action: async () => {
    try {
      const projectDir = process.cwd();
      const packageJson = require('../../../package.json');
      const status = await getStatus(projectDir);
      displayStatus(status, packageJson.version);
    } catch (error) {
      console.error(chalk.red('\nFailed to read status:'), error.message);
      process.exit(1);
    }
  },
};
