/**
 * SKF Installer UI - Banner, prompts, and success message.
 * Uses @clack/prompts for terminal UI.
 */

const { intro, outro, text, select, multiselect, confirm, note, isCancel, cancel, log } = require('@clack/prompts');
const chalk = require('chalk');
const figlet = require('figlet');
const path = require('node:path');
const fs = require('fs-extra');
const yaml = require('js-yaml');

const SKF_FOLDER = '_bmad/skf';

class UI {
  displayBanner() {
    let banner;
    try {
      banner = figlet.textSync('SKF', { font: 'Standard' });
    } catch {
      banner = '\n  S K F';
    }
    const packageJson = require('../../../package.json');
    intro(
      `${chalk.cyan(banner)}\n${chalk.white.bold('  Skill Forge')} ${chalk.dim(`v${packageJson.version}`)}\n${chalk.dim('  AST-verified, provenance-backed agent skills from code\n  repositories, documentation, and developer discourse')}`,
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

    log.info(`Target: ${chalk.cyan(projectDir)}`);

    let action = 'fresh';

    if (detection.type === 'existing') {
      log.warn(`Found existing installation at ${chalk.white(SKF_FOLDER + '/')}`);

      const choice = await select({
        message: 'What would you like to do?',
        options: [
          { label: 'Update — Replace SKF files, keep config.yaml', value: 'update' },
          { label: 'Fresh install — Remove everything and start over', value: 'fresh' },
          { label: 'Cancel', value: 'cancel' },
        ],
      });

      if (isCancel(choice) || choice === 'cancel') {
        cancel('Installation cancelled.');
        return { cancelled: true };
      }
      action = choice;
    } else {
      log.info(`Agents and workflows will be installed in ${chalk.white(skfFolder + '/')}`);
    }

    if (action === 'update') {
      log.info('Existing config.yaml will be preserved.');
      return {
        projectDir,
        skfFolder,
        _detection: detection,
        _action: action,
        cancelled: false,
      };
    }

    // Load saved config to pre-populate defaults on fresh reinstall
    const savedConfig = await this.loadSavedConfig(projectDir, skfFolder);
    if (savedConfig) {
      log.info('Previous configuration detected — defaults pre-populated.');
    }

    const ideOptions = [
      { label: 'Claude Code', value: 'claude-code' },
      { label: 'Cline', value: 'cline' },
      { label: 'Codex', value: 'codex' },
      { label: 'Cursor', value: 'cursor' },
      { label: 'GitHub Copilot', value: 'github-copilot' },
      { label: 'Roo Code', value: 'roo' },
      { label: 'Windsurf', value: 'windsurf' },
      { label: 'Other', value: 'other' },
    ];

    // Pre-check IDEs: saved config takes priority, then auto-detect from directories
    const savedIdes = savedConfig?.ides || [];
    let initialIdes = [];
    if (savedIdes.length > 0) {
      initialIdes = savedIdes;
    } else {
      const detectedIdes = await this.detectIdes(projectDir);
      if (detectedIdes.length > 0) {
        initialIdes = detectedIdes;
        log.info(`Auto-detected IDEs: ${detectedIdes.join(', ')}`);
      }
    }

    // Mark initially selected IDEs
    for (const opt of ideOptions) {
      opt.initialSelected = initialIdes.includes(opt.value);
    }

    // Project name
    const project_name = await text({
      message: 'Project name:',
      initialValue: savedConfig?.project_name || defaultProjectName,
    });
    if (isCancel(project_name)) {
      cancel('Installation cancelled.');
      return { cancelled: true };
    }

    // Skills output folder
    const skills_output_folder = await text({
      message: 'Where should generated skills be saved?',
      initialValue: savedConfig?.skills_output_folder || 'skills',
    });
    if (isCancel(skills_output_folder)) {
      cancel('Installation cancelled.');
      return { cancelled: true };
    }

    // Forge data folder
    const forge_data_folder = await text({
      message: 'Where should forge workspace artifacts be stored?',
      initialValue: savedConfig?.forge_data_folder || 'forge-data',
    });
    if (isCancel(forge_data_folder)) {
      cancel('Installation cancelled.');
      return { cancelled: true };
    }

    // IDE selection
    const ides = await multiselect({
      message: 'Which tools/IDEs are you using?',
      options: ideOptions,
      initialValues: initialIdes,
      required: true,
    });
    if (isCancel(ides)) {
      cancel('Installation cancelled.');
      return { cancelled: true };
    }

    // Learning material
    const install_learning = await confirm({
      message: 'Install learning & reference material?',
      initialValue: true,
    });
    if (isCancel(install_learning)) {
      cancel('Installation cancelled.');
      return { cancelled: true };
    }

    return {
      projectDir,
      project_name,
      skills_output_folder,
      forge_data_folder,
      ides,
      install_learning,
      skfFolder,
      _detection: detection,
      _action: action,
      cancelled: false,
    };
  }

  async detectIdes(projectDir) {
    const markers = {
      'claude-code': ['.claude'],
      cursor: ['.cursor'],
      cline: ['.clinerules'],
      codex: ['.codex'],
      'github-copilot': ['.github/copilot-instructions.md', '.github/prompts'],
      roo: ['.roo', '.roomodes'],
      windsurf: ['.windsurf'],
    };

    const detected = [];
    for (const [ide, paths] of Object.entries(markers)) {
      for (const p of paths) {
        if (await fs.pathExists(path.join(projectDir, p))) {
          detected.push(ide);
          break;
        }
      }
    }
    return detected;
  }

  async loadSavedConfig(projectDir, skfFolder) {
    const configPath = path.join(projectDir, skfFolder, 'config.yaml');
    try {
      if (await fs.pathExists(configPath)) {
        const content = await fs.readFile(configPath, 'utf8');
        return yaml.load(content) || null;
      }
    } catch {
      // ignore parse errors
    }
    return null;
  }

  displaySuccess(skfFolder, ides = [], action = 'fresh') {
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

    let noteTitle;
    let noteBody;

    if (action === 'update') {
      noteTitle = 'Update complete!';
      noteBody = [
        `${chalk.white.bold('What Changed')}`,
        'SKF files and agents have been refreshed.',
        'Your config.yaml and sidecar state are preserved.',
        '',
        `${chalk.white.bold('Next Steps')}`,
        `1. Reload the agent in ${ideDisplay}:`,
        `   ${chalk.cyan(`"Read and activate ${skfFolder}/agents/forger.md"`)}`,
        '2. Run @Ferris SF to re-detect tools if needed',
      ].join('\n');
    } else {
      noteTitle = 'Installation complete!';
      noteBody = [
        `${chalk.white.bold('Get Started')}`,
        `1. Open this folder in ${ideDisplay}`,
        '2. Locate the chat window and type:',
        `   ${chalk.cyan(`"Read and activate ${skfFolder}/agents/forger.md"`)}`,
        '3. Ferris (your Skill Architect) will guide you through',
        '   setting up and forging your first agent skill',
      ].join('\n');
    }

    note(noteBody, noteTitle);

    outro(`Agent: Ferris (Skill Architect & Integrity Guardian)\nDocs: https://github.com/armelhbobdad/bmad-module-skill-forge`);
  }
}

module.exports = { UI };
