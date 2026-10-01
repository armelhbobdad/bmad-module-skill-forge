const chalk = require('chalk');
const { Installer } = require('../lib/installer');
const { startToolCheck } = require('../lib/tool-check');
const { UI } = require('../lib/ui');

module.exports = {
  command: 'install',
  description: 'Install SKF skills into your project',
  options: [],
  // Returns rather than exiting, so skf-cli.js prints the update notice after
  // it; a failure sets process.exitCode.
  action: async () => {
    // The tool probes run while the user answers the prompts and the files copy.
    const printToolReport = startToolCheck();
    try {
      const ui = new UI();
      const config = await ui.promptInstall();

      if (config.cancelled) {
        console.log(chalk.yellow('\nInstallation cancelled.'));
        return;
      }

      const installer = new Installer();
      const result = await installer.install(config);

      if (result && result.success) {
        ui.displaySuccess(config.skfFolder, config.ides, config._action);
        await printToolReport();
      } else {
        console.error(chalk.red('\nInstallation failed.'));
        process.exitCode = 1;
      }
    } catch (error) {
      console.error(chalk.red('\nInstallation failed:'), error.message);
      console.error(chalk.dim(error.stack));
      process.exitCode = 1;
    } finally {
      // A cancelled or failed install prints no report: stop the probes still running.
      printToolReport.stop();
    }
  },
};
