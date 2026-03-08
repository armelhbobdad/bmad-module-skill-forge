/**
 * SKF Uninstall Command
 * Clean removal of SKF files, IDE commands, sidecar, and output folders.
 * Uses the manifest to know exactly what to remove.
 */

const chalk = require('chalk');
const path = require('node:path');
const fs = require('fs-extra');
const { confirm, isCancel, spinner, log, outro } = require('@clack/prompts');
const { readManifest, MANIFEST_DIR, MANIFEST_FILE } = require('../lib/manifest');

/**
 * Count files that still exist on disk from manifest lists.
 */
async function countExistingFiles(projectDir, manifest) {
  const allFiles = [
    ...(manifest.files.skf || []),
    ...(manifest.files.sidecar || []),
    ...(manifest.files.ide_commands || []),
    ...(manifest.files.learning || []),
    ...(manifest.files.output || []),
  ];

  let existing = 0;
  for (const file of allFiles) {
    if (await fs.pathExists(path.join(projectDir, file))) {
      existing++;
    }
  }
  return { total: allFiles.length, existing };
}

/**
 * Display what will be removed, grouped by category.
 */
async function displayRemovalPlan(projectDir, manifest) {
  const categories = [
    { key: 'skf', label: 'SKF module files', dir: manifest.skf_folder },
    { key: 'sidecar', label: 'Agent sidecar state', dir: '_bmad/_memory/forger-sidecar' },
    { key: 'ide_commands', label: 'IDE command files' },
    { key: 'learning', label: 'Learning material', dir: '_skf-learn' },
    { key: 'output', label: 'Output folder scaffolding' },
  ];

  const lines = [];
  for (const cat of categories) {
    const files = manifest.files[cat.key] || [];
    if (files.length === 0) continue;

    // Count how many still exist
    let existCount = 0;
    for (const f of files) {
      if (await fs.pathExists(path.join(projectDir, f))) existCount++;
    }

    if (existCount === 0) continue;

    if (cat.dir) {
      lines.push(`${chalk.red('×')} ${cat.label} ${chalk.dim(`(${cat.dir}/ — ${existCount} files)`)}`);
    } else {
      lines.push(`${chalk.red('×')} ${cat.label} ${chalk.dim(`(${existCount} files)`)}`);
    }
  }

  // Manifest itself
  lines.push(`${chalk.red('×')} Installation manifest ${chalk.dim(`(${MANIFEST_DIR}/${MANIFEST_FILE})`)}`);

  log.warn(`The following will be removed:\n${lines.join('\n')}`);
}

/**
 * Remove files listed in the manifest, then clean empty parent directories.
 */
async function removeFiles(projectDir, fileList) {
  let removed = 0;
  for (const file of fileList) {
    const fullPath = path.join(projectDir, file);
    if (await fs.pathExists(fullPath)) {
      await fs.remove(fullPath);
      removed++;
    }
  }
  return removed;
}

/**
 * Remove a directory if it exists and is empty (or force remove).
 */
async function removeEmptyDir(dirPath) {
  if (!(await fs.pathExists(dirPath))) return;
  try {
    const entries = await fs.readdir(dirPath);
    if (entries.length === 0) {
      await fs.remove(dirPath);
    }
  } catch {
    // ignore
  }
}

module.exports = {
  command: 'uninstall',
  description: 'Remove SKF installation from the current project',
  options: [],
  action: async () => {
    try {
      const projectDir = process.cwd();
      const manifest = await readManifest(projectDir);

      if (!manifest) {
        // Check if SKF exists without manifest
        const skfExists = await fs.pathExists(path.join(projectDir, '_bmad/skf'));
        if (skfExists) {
          log.warn(
            'No manifest found. Reinstall first to generate one,\nthen run uninstall again for clean removal.\nRun: npx bmad-module-skill-forge install',
          );
        } else {
          log.warn('SKF is not installed in this directory.');
        }
        process.exit(0);
        return;
      }

      const { existing } = await countExistingFiles(projectDir, manifest);
      if (existing === 0) {
        log.warn('No SKF files found to remove.');
        // Clean up stale manifest
        await fs.remove(path.join(projectDir, MANIFEST_DIR, MANIFEST_FILE));
        process.exit(0);
        return;
      }

      await displayRemovalPlan(projectDir, manifest);

      const shouldProceed = await confirm({
        message: 'Proceed with uninstall?',
        initialValue: false,
      });

      if (isCancel(shouldProceed) || !shouldProceed) {
        log.warn('Uninstall cancelled.');
        process.exit(0);
        return;
      }

      const s = spinner();

      // Remove IDE commands first (scattered across project)
      const ideFiles = manifest.files.ide_commands || [];
      if (ideFiles.length > 0) {
        s.start('Removing IDE commands...');
        const ideRemoved = await removeFiles(projectDir, ideFiles);
        // Clean empty IDE directories
        const cleanedDirs = new Set();
        for (const f of ideFiles) {
          const dir = path.dirname(f);
          if (!cleanedDirs.has(dir)) {
            cleanedDirs.add(dir);
            await removeEmptyDir(path.join(projectDir, dir));
            await removeEmptyDir(path.join(projectDir, path.dirname(dir)));
          }
        }
        s.stop(`Removed ${ideRemoved} IDE command files`);
      }

      // Remove learning material directory
      const learnFiles = manifest.files.learning || [];
      if (learnFiles.length > 0) {
        s.start('Removing learning material...');
        const learnDir = path.join(projectDir, '_skf-learn');
        if (await fs.pathExists(learnDir)) {
          await fs.remove(learnDir);
        }
        s.stop('Learning material removed');
      }

      // Remove output folder scaffolding (.gitkeep only)
      const outputFiles = manifest.files.output || [];
      if (outputFiles.length > 0) {
        s.start('Removing output scaffolding...');
        await removeFiles(projectDir, outputFiles);
        // Remove empty output folders
        for (const folder of [manifest.skills_output_folder, manifest.forge_data_folder]) {
          if (folder) {
            await removeEmptyDir(path.join(projectDir, folder));
          }
        }
        s.stop('Output scaffolding removed');
      }

      // Remove sidecar
      s.start('Removing agent sidecar...');
      const sidecarDir = path.join(projectDir, '_bmad', '_memory', 'forger-sidecar');
      if (await fs.pathExists(sidecarDir)) {
        await fs.remove(sidecarDir);
      }
      await removeEmptyDir(path.join(projectDir, '_bmad', '_memory'));
      s.stop('Agent sidecar removed');

      // Remove SKF module directory
      s.start('Removing SKF module...');
      const skfDir = path.join(projectDir, manifest.skf_folder);
      if (await fs.pathExists(skfDir)) {
        await fs.remove(skfDir);
      }
      s.stop('SKF module removed');

      // Remove manifest
      const manifestPath = path.join(projectDir, MANIFEST_DIR, MANIFEST_FILE);
      if (await fs.pathExists(manifestPath)) {
        await fs.remove(manifestPath);
      }
      // Clean empty _bmad/_config/ and _bmad/ if we were the only occupant
      await removeEmptyDir(path.join(projectDir, MANIFEST_DIR));
      await removeEmptyDir(path.join(projectDir, '_bmad'));

      outro('SKF uninstalled successfully.');

      process.exit(0);
    } catch (error) {
      console.error(chalk.red('\nUninstall failed:'), error.message);
      process.exit(1);
    }
  },
};
