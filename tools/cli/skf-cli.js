const { program } = require('commander');
const installCommand = require('./commands/install');
const statusCommand = require('./commands/status');
const uninstallCommand = require('./commands/uninstall');
const updateCommand = require('./commands/update');
const { startVersionCheck } = require('./lib/version-check');

// Fix for stdin issues when running through npm on Windows
if (process.stdin.isTTY) {
  try {
    process.stdin.resume();
    process.stdin.setEncoding('utf8');
    if (process.platform === 'win32') {
      process.stdin.on('error', () => {});
    }
  } catch {
    // Silently ignore - some environments may not support these operations
  }
}

const packageJson = require('../../package.json');

// Start async version check (non-blocking)
const printUpdateNotice = startVersionCheck(packageJson.version);

program.version(packageJson.version).description('Skill Forge — Evidence-Based Agent Skills Compiler');

for (const command of [installCommand, updateCommand, statusCommand, uninstallCommand]) {
  const cmd = program.command(command.command).description(command.description);
  for (const option of command.options || []) {
    cmd.option(...option);
  }
  // Wrap action to print update notice after command completes
  const originalAction = command.action;
  cmd.action(async (...args) => {
    await originalAction(...args);
    await printUpdateNotice();
  });
}

program.parse(process.argv);

if (process.argv.slice(2).length === 0) {
  program.outputHelp();
}
