/**
 * SKF Quick Update Command
 * Replaces SKF files and reinstalls agent skill without re-prompting.
 * Preserves config.yaml and sidecar state.
 */

const chalk = require('chalk');
const path = require('node:path');
const fs = require('fs-extra');
const yaml = require('js-yaml');
const { Installer } = require('../lib/installer');
const { startToolCheck } = require('../lib/tool-check');
const { UI } = require('../lib/ui');

const SKF_FOLDER = '_bmad/skf';

module.exports = {
  command: 'update',
  description: 'Update SKF files and reinstall agent skill (preserves config and sidecar)',
  options: [],
  // Returns rather than exiting, so skf-cli.js prints the update notice after
  // it; a failure sets process.exitCode.
  action: async () => {
    // The tool probes run while the files copy.
    const printToolReport = startToolCheck();
    try {
      const projectDir = process.cwd();
      const skfDir = path.join(projectDir, SKF_FOLDER);

      if (!(await fs.pathExists(skfDir))) {
        console.log(chalk.yellow('\n  SKF is not installed in this directory.'));
        console.log(chalk.dim('  Run: npx bmad-module-skill-forge install\n'));
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
        await printToolReport();
      } else {
        console.error(chalk.red('\nUpdate failed.'));
        process.exitCode = 1;
      }
    } catch (error) {
      console.error(chalk.red('\nUpdate failed:'), error.message);
      process.exitCode = 1;
    } finally {
      // An update that fails, or finds no SKF here, prints no report: stop the probes still running.
      printToolReport.stop();
    }
  },
};
