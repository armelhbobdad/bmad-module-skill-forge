/**
 * SKF Uninstall Command
 * Clean removal of SKF files, IDE skill directories, sidecar, and output folders.
 * Uses the manifest to know what to remove, and removes only what the
 * installer wrote: the fixed SKF, sidecar and learning folders, the SKF
 * entries of each IDE skills folder, and each output folder .gitkeep that
 * still holds the installer's text.
 */

const chalk = require('chalk');
const path = require('node:path');
const fs = require('fs-extra');
const { confirm, isCancel, spinner, log, outro } = require('@clack/prompts');
const { readManifest, MANIFEST_DIR, MANIFEST_FILE } = require('../lib/manifest');
const { removeAllSkfSkills, loadPlatforms } = require('../lib/ide-skills');
const { GITKEEP, resolveProjectFolder } = require('../lib/project-folders');

// The SKF module folder the installer writes, whatever the manifest's skf_folder says.
const SKF_FOLDER = '_bmad/skf';

/**
 * The manifest's output entries: a value that is not a list reads as no
 * entries, and an item that is not a string is skipped.
 */
function outputEntries(manifest) {
  const output = manifest.files && manifest.files.output;
  return Array.isArray(output) ? output.filter((entry) => typeof entry === 'string') : [];
}

/**
 * Count files that still exist on disk from manifest lists.
 */
async function countExistingFiles(projectDir, manifest) {
  const allFiles = [
    ...(manifest.files.skf || []),
    ...(manifest.files.sidecar || []),
    ...(manifest.files.ide_skills || []),
    ...(manifest.files.learning || []),
    ...outputEntries(manifest),
  ];

  let existing = 0;
  for (const file of allFiles) {
    if (await fs.pathExists(path.resolve(projectDir, file))) {
      existing++;
    }
  }
  return { total: allFiles.length, existing };
}

/**
 * Sort the manifest's output entries, as absolute paths, into the ones
 * uninstall removes and the ones it keeps. An entry is removed only when it
 * is a regular file named .gitkeep holding exactly the text the installer
 * writes. A missing entry is in neither list; any other entry, or one that
 * cannot be read, is kept. The plan and the removal both read this, so they
 * never disagree.
 */
async function classifyOutputEntries(projectDir, manifest) {
  const remove = [];
  const keep = [];
  const seen = new Set();
  for (const entry of outputEntries(manifest)) {
    const file = path.resolve(projectDir, entry);
    if (seen.has(file)) continue;
    seen.add(file);
    let stat;
    try {
      stat = await fs.lstat(file);
    } catch (error) {
      if (error.code !== 'ENOENT') keep.push(file);
      continue;
    }
    if (path.basename(file) !== '.gitkeep' || !stat.isFile()) {
      keep.push(file);
      continue;
    }
    let text = null;
    try {
      text = await fs.readFile(file, 'utf8');
    } catch {
      // Unreadable: kept below.
    }
    if (text === GITKEEP) remove.push(file);
    else keep.push(file);
  }
  return { remove, keep };
}

/**
 * Whether an entry of an IDE skills folder is one the IDE step removes
 * (the rule cleanSkfSkills in ide-skills.js applies).
 */
function isSkfSkillEntry(name) {
  return name.startsWith('skf-') || name === 'knowledge' || name === 'shared';
}

/**
 * The number of files a folder holds, at any depth (what removing it
 * deletes), or null when it cannot be read.
 */
async function countFolderFiles(dir) {
  try {
    const entries = await fs.readdir(dir, { recursive: true, withFileTypes: true });
    return entries.filter((entry) => !entry.isDirectory()).length;
  } catch {
    return null;
  }
}

function plural(count, one, many) {
  return `${count} ${count === 1 ? one : many}`;
}

function planLine(label, detail) {
  return `${chalk.red('×')} ${label} ${chalk.dim(`(${detail})`)}`;
}

/**
 * The plan line of a folder the action removes when it exists, or null when
 * it does not exist.
 */
async function folderLine(projectDir, label, folder) {
  const dir = path.join(projectDir, folder);
  if (!(await fs.pathExists(dir))) return null;
  const count = await countFolderFiles(dir);
  return planLine(label, count === null ? `${folder}/` : `${folder}/, ${plural(count, 'file', 'files')}`);
}

/**
 * Display what will be removed, one line per removal, each naming its path,
 * shown under the same condition as the step that removes it. Not listed:
 * the command files earlier releases left in each platform's legacy
 * folders, which the IDE step also removes, and the empty folders the
 * cleanup removes. Output entries uninstall keeps are named in a second
 * warning.
 */
async function displayRemovalPlan(projectDir, manifest) {
  const lines = [];

  const skfLine = await folderLine(projectDir, 'SKF module files', SKF_FOLDER);
  if (skfLine) lines.push(skfLine);

  const sidecarLine = await folderLine(projectDir, 'Agent sidecar state', '_bmad/_memory/forger-sidecar');
  if (sidecarLine) lines.push(sidecarLine);

  // Each IDE skills folder holding an entry the IDE step removes.
  for (const platform of Object.values(loadPlatforms().platforms)) {
    const targetDir = platform.installer?.target_dir;
    if (!targetDir) continue;
    let names;
    try {
      names = await fs.readdir(path.join(projectDir, targetDir));
    } catch {
      continue;
    }
    const count = names.filter((name) => isSkfSkillEntry(name)).length;
    if (count > 0) lines.push(planLine('SKF skills', `${targetDir}/, ${plural(count, 'entry', 'entries')}`));
  }

  if ((manifest.files.learning || []).length > 0) {
    const learnLine = await folderLine(projectDir, 'Learning material', '_skf-learn');
    if (learnLine) lines.push(learnLine);
  }

  const { remove, keep } = await classifyOutputEntries(projectDir, manifest);
  for (const file of remove) lines.push(planLine('Output folder scaffolding', file));

  // Manifest itself
  lines.push(planLine('Installation manifest', `${MANIFEST_DIR}/${MANIFEST_FILE}`));

  log.warn(`The following will be removed:\n${lines.join('\n')}`);

  if (keep.length > 0) {
    log.warn(`Left in place, not a .gitkeep the installer wrote:\n${keep.join('\n')}`);
  }
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

/**
 * Remove each output folder .gitkeep the manifest lists that the installer
 * wrote (see classifyOutputEntries), then each output folder left empty: the
 * folder of each removed file (an earlier version's manifest can list one
 * under a literal {project-root} folder) and the folder each output folder
 * value resolves to. A kept or missing entry's folder is not cleaned through
 * that entry, and the project folder itself always stays. Returns the
 * absolute paths removed and kept; it never logs, since it runs under a
 * spinner.
 */
async function removeOutputScaffolding(projectDir, manifest) {
  const { remove, keep } = await classifyOutputEntries(projectDir, manifest);
  const removed = [];
  for (const file of remove) {
    try {
      await fs.unlink(file);
    } catch (error) {
      if (error.code === 'ENOENT') continue;
      throw error;
    }
    removed.push(file);
  }
  const folders = removed.map((file) => path.dirname(file));
  for (const value of [manifest.skills_output_folder, manifest.forge_data_folder]) {
    if (value) folders.push(resolveProjectFolder(projectDir, value));
  }
  const root = path.resolve(projectDir);
  for (const folder of folders) {
    if (folder !== root) await removeEmptyDir(folder);
  }
  return { removed, kept: keep };
}

module.exports = {
  command: 'uninstall',
  description: 'Remove SKF installation from the current project',
  options: [],
  removeOutputScaffolding,
  action: async () => {
    try {
      const projectDir = process.cwd();
      const manifest = await readManifest(projectDir);

      if (!manifest) {
        // Check if SKF exists without manifest
        const skfExists = await fs.pathExists(path.join(projectDir, SKF_FOLDER));
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

      // Remove IDE skill directories from all known platforms (skills + legacy command files)
      s.start('Removing IDE skill directories...');
      const removedIdeDirs = await removeAllSkfSkills(projectDir);
      if (removedIdeDirs.length > 0) {
        s.stop(`Cleaned skills from ${removedIdeDirs.length} IDE target(s)`);
      } else {
        s.stop('No IDE skill directories found');
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

      // Remove output folder scaffolding (the installer's .gitkeep files only)
      if (outputEntries(manifest).length > 0) {
        s.start('Removing output scaffolding...');
        const { removed } = await removeOutputScaffolding(projectDir, manifest);
        s.stop(removed.length > 0 ? 'Output scaffolding removed' : 'No output scaffolding removed');
      }

      // Remove sidecar
      s.start('Removing agent sidecar...');
      const sidecarDir = path.join(projectDir, '_bmad', '_memory', 'forger-sidecar');
      if (await fs.pathExists(sidecarDir)) {
        await fs.remove(sidecarDir);
      }
      await removeEmptyDir(path.join(projectDir, '_bmad', '_memory'));
      s.stop('Agent sidecar removed');

      // Remove SKF module directory: the fixed folder, never the manifest's skf_folder
      s.start('Removing SKF module...');
      const skfDir = path.join(projectDir, SKF_FOLDER);
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
