/**
 * SKF Installer UI - Banner, prompts, and success message.
 * Uses @clack/prompts for terminal UI.
 *
 * Brand palette (from skf-logo.svg):
 *   amber  #F59E0B  — primary (anvil top)
 *   gold   #FBBF24  — accent, highlights (anvil horn)
 *   dark   #D97706  — frame, deep emphasis (anvil body)
 *   spark  #FCD34D  — sparks, icons
 */

const { intro, outro, text, select, multiselect, confirm, note, isCancel, cancel, log } = require('@clack/prompts');
const chalk = require('chalk');
const figlet = require('figlet');
const path = require('node:path');
const fs = require('fs-extra');
const yaml = require('js-yaml');

const SKF_FOLDER = '_bmad/skf';

// Brand colors derived from skf-logo.svg
const brand = {
  amber: chalk.hex('#F59E0B'),
  gold: chalk.hex('#FBBF24'),
  dark: chalk.hex('#D97706'),
  spark: chalk.hex('#FCD34D'),
};

class UI {
  displayBanner() {
    const packageJson = require('../../../package.json');
    const version = packageJson.version;

    let logoLines;
    try {
      logoLines = figlet.textSync('SKF', { font: 'ANSI Shadow' }).trimEnd().split('\n');
      // Remove trailing empty lines from figlet output
      while (logoLines.length > 0 && !logoLines.at(-1).trim()) logoLines.pop();
    } catch {
      logoLines = ['  S K F'];
    }

    const w = 54;
    const frame = brand.dark;
    const top = frame('  ╔' + '═'.repeat(w) + '╗');
    const mid = frame('  ╟' + '─'.repeat(w) + '╢');
    const bottom = frame('  ╚' + '═'.repeat(w) + '╝');
    const row = (content) => {
      // eslint-disable-next-line no-control-regex -- stripping ANSI escape codes for visual width calculation
      const stripped = content.replaceAll(/\u001B\[\d+(?:;\d+)*m/g, '');
      const pad = Math.max(0, w - stripped.length - 2);
      return frame('  ║ ') + content + ' '.repeat(pad) + frame(' ║');
    };

    console.log();
    console.log(top);
    for (const line of logoLines) {
      console.log(row(brand.amber.bold(line.replace(/\s+$/, ''))));
    }
    console.log(mid);
    console.log(row(chalk.white.bold('Skill Forge') + chalk.dim(` v${version}`)));
    console.log(row(chalk.dim('Agent Skill Compiler') + ' '.repeat(15) + brand.spark('⚒')));
    console.log(mid);
    console.log(row(chalk.dim('Code · Docs · Discourse → Verified agent skills')));
    console.log(bottom);
    console.log();

    intro(brand.amber('Skill Forge Installer'));
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

    log.info(`Target: ${brand.gold(projectDir)}`);

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
        log.info(`Auto-detected IDEs: ${brand.gold(detectedIdes.join(', '))}`);
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

    const activateCmd = brand.gold('/bmad-agent-skf-forger');

    if (action === 'update') {
      noteTitle = brand.amber.bold('Update complete!');
      noteBody = [
        `${chalk.white.bold('What Changed')}`,
        'SKF files and agents have been refreshed.',
        'Your config.yaml and sidecar state are preserved.',
        '',
        `${chalk.white.bold('Next Steps')}`,
        `1. Reload the agent in ${ideDisplay}:  ${activateCmd}`,
        '2. Run @Ferris SF to re-detect tools if needed',
      ].join('\n');
    } else {
      noteTitle = brand.amber.bold('Installation complete!');
      noteBody = [
        `${chalk.white.bold('Get Started')}`,
        `1. Open this folder in ${ideDisplay}`,
        `2. Activate Ferris:  ${activateCmd}`,
        '3. Ferris (your Skill Architect) will guide you through',
        '   setting up and forging your first agent skill',
      ].join('\n');
    }

    note(noteBody, noteTitle);

    outro(
      `${brand.spark('⚒')}  Agent: ${chalk.white('Ferris')} ${chalk.dim('(Skill Architect & Integrity Guardian)')}\n${brand.dark('⚡')} Docs: ${brand.amber('https://armelhbobdad.github.io/bmad-module-skill-forge')}`,
    );
  }
}

module.exports = { UI };
