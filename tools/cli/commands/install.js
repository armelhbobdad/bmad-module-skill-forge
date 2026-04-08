const chalk = require('chalk');
const { Installer } = require('../lib/installer');
const { UI } = require('../lib/ui');

module.exports = {
  command: 'install',
  description: 'Install SKF skills into your project',
  options: [],
  action: async () => {
    try {
      const ui = new UI();
      const config = await ui.promptInstall();

      if (config.cancelled) {
        console.log(chalk.yellow('\nInstallation cancelled.'));
        process.exit(0);
        return;
      }

      const installer = new Installer();
      const result = await installer.install(config);

      if (result && result.success) {
        ui.displaySuccess(config.skfFolder, config.ides, config._action);
        process.exit(0);
      }
    } catch (error) {
      console.error(chalk.red('\nInstallation failed:'), error.message);
      console.error(chalk.dim(error.stack));
      process.exit(1);
    }
  },
};
