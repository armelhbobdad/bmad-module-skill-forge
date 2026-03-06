/**
 * SKF Installer UI - Banner, prompts, and success message.
 */

const chalk = require('chalk');
const figlet = require('figlet');
const inquirer = require('inquirer').default || require('inquirer');
const path = require('node:path');
const fs = require('fs-extra');

const SKF_FOLDER = '_bmad/skf';

class UI {
  displayBanner() {
    try {
      const banner = figlet.textSync('SKF', { font: 'Standard' });
      console.log(chalk.cyan(banner));
    } catch {
      console.log(chalk.cyan.bold('\n  S K F'));
    }
    console.log(chalk.white.bold('  Skill Forge'));
    console.log(
      chalk.dim('  AST-verified, provenance-backed agent skills from code\n  repositories, documentation, and developer discourse\n'),
    );
  }

  async detectInstallation(projectDir) {
    const hasBmadSkf = await fs.pathExists(path.join(projectDir, SKF_FOLDER));
    const hasBmadDir = await fs.pathExists(path.join(projectDir, '_bmad'));

    if (hasBmadSkf) {
      return { type: 'existing', folder: SKF_FOLDER };
    }
    if (hasBmadDir) {
      return { type: 'bmad-ready', folder: SKF_FOLDER };
    }
    return { type: 'fresh', folder: SKF_FOLDER };
  }

  async promptInstall() {
    this.displayBanner();

    const projectDir = process.cwd();
    const defaultProjectName = path.basename(projectDir);
    const detection = await this.detectInstallation(projectDir);
    const skfFolder = detection.folder;

    console.log(chalk.white(`  Target: ${chalk.cyan(projectDir)}`));

    let action = 'fresh';

    if (detection.type === 'existing') {
      console.log(chalk.dim(`\n  Found existing installation at ${chalk.white(SKF_FOLDER + '/')}\n`));

      const { choice } = await inquirer.prompt([
        {
          type: 'list',
          name: 'choice',
          message: 'What would you like to do?',
          choices: [
            { name: 'Update - Replace SKF files, keep config.yaml', value: 'update' },
            { name: 'Fresh install - Remove everything and start over', value: 'fresh' },
            { name: 'Cancel', value: 'cancel' },
          ],
        },
      ]);

      if (choice === 'cancel') return { cancelled: true };
      action = choice;
    } else {
      console.log(chalk.dim(`  Agents and workflows will be installed in ${chalk.white(skfFolder + '/')}\n`));
    }

    if (action === 'update') {
      console.log(chalk.dim('  Existing config.yaml will be preserved.\n'));
      return {
        projectDir,
        skfFolder,
        _detection: detection,
        _action: action,
        cancelled: false,
      };
    }

    const answers = await inquirer.prompt([
      {
        type: 'input',
        name: 'project_name',
        message: 'Project name:',
        default: defaultProjectName,
      },
      {
        type: 'input',
        name: 'skills_output_folder',
        message: 'Where should generated skills be saved?',
        default: 'skills',
      },
      {
        type: 'input',
        name: 'forge_data_folder',
        message: 'Where should forge workspace artifacts be stored?',
        default: 'forge-data',
      },
      {
        type: 'checkbox',
        name: 'ides',
        message: 'Which tools/IDEs are you using? (use spacebar to select)',
        choices: [
          { name: 'Claude Code', value: 'claude-code' },
          { name: 'Cline', value: 'cline' },
          { name: 'Codex', value: 'codex' },
          { name: 'Cursor', value: 'cursor' },
          { name: 'GitHub Copilot', value: 'github-copilot' },
          { name: 'Roo Code', value: 'roo' },
          { name: 'Windsurf', value: 'windsurf' },
          { name: 'Other', value: 'other' },
        ],
        validate: (answers) => {
          if (!answers || answers.length === 0) {
            return 'At least one IDE must be selected';
          }
          return true;
        },
      },
      {
        type: 'confirm',
        name: 'install_learning',
        message: 'Install learning & reference material?',
        default: true,
      },
    ]);

    return {
      projectDir,
      ...answers,
      skfFolder,
      _detection: detection,
      _action: action,
      cancelled: false,
    };
  }

  displaySuccess(skfFolder, ides = []) {
    const ideNames = {
      'claude-code': 'Claude Code',
      cline: 'Cline',
      codex: 'Codex',
      cursor: 'Cursor',
      'github-copilot': 'GitHub Copilot',
      roo: 'Roo Code',
      windsurf: 'Windsurf',
      other: 'your IDE',
    };

    let ideDisplay;
    if (!ides || ides.length === 0) {
      ideDisplay = 'your IDE';
    } else if (ides.length === 1) {
      ideDisplay = ideNames[ides[0]] || 'your IDE';
    } else {
      ideDisplay = ides.map((ide) => ideNames[ide] || ide).join(' or ');
    }

    console.log('');
    console.log(chalk.green.bold('  Installation complete!'));
    console.log('');
    console.log(chalk.white.bold('  Get Started'));
    console.log('');
    console.log(chalk.white(`  1. Open this folder in ${ideDisplay}`));
    console.log('');
    console.log(chalk.white('  2. Locate the chat window and type:'));
    console.log('');
    console.log(chalk.cyan(`     "Read and activate ${skfFolder}/agents/skf.md"`));
    console.log('');
    console.log(chalk.white('  3. Ferris (your Skill Architect) will guide you through'));
    console.log(chalk.white('     setting up and forging your first agent skill'));
    console.log('');
    console.log(chalk.dim('  ───────────────────────────────────────────────────────'));
    console.log('');
    console.log(chalk.dim('  Agent: Ferris (Skill Architect & Integrity Guardian)'));
    console.log(chalk.dim('  Docs: https://github.com/armelhbobdad/bmad-module-skill-forge'));
    console.log('');
  }
}

module.exports = { UI };
