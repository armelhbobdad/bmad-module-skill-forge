/**
 * SKF Quick Update Command
 * Replaces SKF files and recompiles agents without re-prompting.
 * Preserves config.yaml and sidecar state.
 */

const chalk = require('chalk');
const path = require('node:path');
const fs = require('fs-extra');
const yaml = require('js-yaml');
const { Installer } = require('../lib/installer');
const { UI } = require('../lib/ui');

const SKF_FOLDER = '_bmad/skf';

module.exports = {
  command: 'update',
  description: 'Update SKF files and recompile agents (preserves config and sidecar)',
  options: [],
  action: async () => {
    try {
      const projectDir = process.cwd();
      const skfDir = path.join(projectDir, SKF_FOLDER);

      if (!(await fs.pathExists(skfDir))) {
        console.log(chalk.yellow('\n  SKF is not installed in this directory.'));
        console.log(chalk.dim('  Run: npx bmad-module-skill-forge install\n'));
        process.exit(0);
        return;
      }

      console.log('');
      console.log(chalk.hex('#F59E0B').bold('  Skill Forge — Quick Update'));
      console.log(chalk.dim('  Replacing SKF files, preserving config and sidecar.\n'));

      const installer = new Installer();
      const result = await installer.install({
        projectDir,
        skfFolder: SKF_FOLDER,
        _action: 'update',
      });

      if (result && result.success) {
        // Read config to get IDEs for post-update notes
        let ides = [];
        try {
          const configContent = await fs.readFile(path.join(skfDir, 'config.yaml'), 'utf8');
          const config = yaml.load(configContent);
          ides = config?.ides || [];
        } catch {
          /* use empty */
        }
        const ui = new UI();
        ui.displaySuccess(SKF_FOLDER, ides, 'update');
      }

      process.exit(0);
    } catch (error) {
      console.error(chalk.red('\nUpdate failed:'), error.message);
      process.exit(1);
    }
  },
};
