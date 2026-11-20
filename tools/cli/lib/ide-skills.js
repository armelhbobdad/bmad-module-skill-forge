/**
 * IDE Skill Installer — Verbatim skill directory installation
 *
 * Replaces the legacy command-file generation approach with the BMAD standard:
 * skill directories (containing SKILL.md + supporting files) are copied directly
 * to each IDE's skills/ directory. IDEs read SKILL.md natively.
 *
 * Supports 23+ IDEs via platform-codes.yaml (config-driven, no IDE-specific code).
 */

const path = require('node:path');
const fs = require('fs-extra');
const yaml = require('js-yaml');

const PLATFORM_CODES_PATH = path.join(__dirname, 'platform-codes.yaml');

// OS/editor artifacts to filter during copy
const ARTIFACT_FILTER = new Set(['.DS_Store', 'Thumbs.db', 'desktop.ini', '._.DS_Store']);

// The package's own src/ folder, the one Installer.srcDir names.
const PACKAGE_SRC = path.resolve(__dirname, '..', '..', '..', 'src');

// The support folders an IDE skills folder can hold beside the skf-* skills:
// the installer copies shared/ there, and earlier versions also copied knowledge/.
const SUPPORT_FOLDERS = ['shared', 'knowledge'];

const SHARED_TAKEN_ADVICE =
  'SKF installs its shared/ folder there and needs that name. Rename or move your own shared skill, then run this again. ' +
  'A listed file may also be left from an SKF copy that no list names any more (_bmad/ deleted by hand, or an older ' +
  "version's copy in an IDE folder a reinstall dropped and this install adds back): delete it if so. Nothing was changed.";

/**
 * Load platform configuration from platform-codes.yaml.
 * Returns { platforms: { 'claude-code': { name, preferred, installer: { target_dir, legacy_targets } }, ... } }
 */
function loadPlatforms() {
  const content = fs.readFileSync(PLATFORM_CODES_PATH, 'utf8');
  return yaml.load(content);
}

/**
 * Get available platforms for UI display.
 * Returns array of { value, label, preferred, skillInvocationPrefix }.
 * skillInvocationPrefix is null when the IDE only auto-invokes skills.
 */
function getAvailablePlatforms() {
  const config = loadPlatforms();
  return Object.entries(config.platforms)
    .filter(([, p]) => !p.suspended)
    .map(([code, p]) => ({
      value: code,
      label: p.name,
      preferred: p.preferred || false,
      skillInvocationPrefix: p.skill_invocation_prefix ?? null,
    }))
    .sort((a, b) => {
      // Preferred first, then alphabetical
      if (a.preferred !== b.preferred) return b.preferred ? 1 : -1;
      return a.label.localeCompare(b.label);
    });
}

/**
 * Get IDE auto-detection markers.
 * Returns { 'claude-code': ['.claude'], 'cursor': ['.cursor'], ... }
 *
 * Uses explicit detection_marker from platform config when available,
 * otherwise derives from the top-level directory of target_dir.
 * The derived marker only works when the IDE's config directory exists
 * independently of the installer (e.g. .claude/ exists before SKF install).
 */
function getDetectionMarkers() {
  const config = loadPlatforms();
  const markers = {};
  for (const [code, p] of Object.entries(config.platforms)) {
    if (p.suspended) continue;
    const targetDir = p.installer?.target_dir;
    if (!targetDir) continue;
    if (p.installer.detection_marker) {
      markers[code] = [p.installer.detection_marker];
    } else {
      // Derive from target_dir — works when top-level dir is the IDE's own config dir
      const topDir = '.' + targetDir.split('/')[0].replace(/^\./, '');
      markers[code] = [topDir];
    }
  }
  return markers;
}

/**
 * The paths the manifest's files.ide_skills lists, each normalized. A value
 * that is not a list reads as empty, and an item that is not a string is
 * skipped. The set only marks a file the walk finds inside a support folder:
 * a listed path the walk does not find there is never removed.
 */
function listedIdeFiles(manifest) {
  const list = manifest && typeof manifest === 'object' && manifest.files && manifest.files.ide_skills;
  if (!Array.isArray(list)) return new Set();
  return new Set(list.filter((entry) => typeof entry === 'string').map((entry) => path.normalize(entry)));
}

/**
 * Whether the regular file `file` (its lstat in `stat`) holds the same bytes
 * as `reference`. A reference that is missing, not a file or unreadable, or a
 * file that cannot be read, is no match.
 */
async function sameBytes(file, stat, reference) {
  try {
    const refStat = await fs.stat(reference);
    if (!refStat.isFile() || refStat.size !== stat.size) return false;
    const [bytes, refBytes] = await Promise.all([fs.readFile(file), fs.readFile(reference)]);
    return bytes.equals(refBytes);
  } catch {
    return false;
  }
}

/**
 * Whether a file at `rel` inside a support folder is bytecode or an OS file.
 */
function isArtifact(rel) {
  return rel.split(path.sep).includes('__pycache__') || rel.endsWith('.pyc') || ARTIFACT_FILTER.has(path.basename(rel));
}

/**
 * Sort what the support folder `<targetRel>/<name>` holds into the files SKF
 * installed, which `remove` lists, and every other entry, which `kept` lists,
 * both as project-relative paths. A regular file, found by an lstat walk
 * that never follows a link, is SKF's when its bytes equal the same path
 * under `<moduleDir>/<name>/` or under the package's src/<name>/, or when
 * files.ide_skills lists it. A bytecode or OS file is SKF's when the folder
 * also holds such a file, or holds nothing but folders and bytecode or OS
 * files. Anything else is kept: other bytes, a link, any other non-regular
 * entry and a folder the walk cannot list. The support folder itself is
 * kept whole when it is a link or not a folder. Returns null when it is gone.
 */
async function classifySupportFolder(projectDir, targetRel, name, { moduleDir, listed }) {
  const folderRel = path.join(targetRel, name);
  const folder = path.join(projectDir, folderRel);
  const result = { name, folder: folderRel, remove: [], kept: [] };
  let stat;
  try {
    stat = await fs.lstat(folder);
  } catch (error) {
    if (error.code === 'ENOENT') return null;
    result.kept.push(folderRel);
    return result;
  }
  if (!stat.isDirectory()) {
    result.kept.push(folderRel);
    return result;
  }

  const found = [];
  const others = [];
  const walk = async (relDir) => {
    let entries;
    try {
      entries = (await fs.readdir(path.join(folder, relDir))).sort();
    } catch {
      others.push(path.join(folderRel, relDir));
      return;
    }
    for (const entry of entries) {
      const rel = path.join(relDir, entry);
      const file = path.join(folder, rel);
      let entryStat;
      try {
        entryStat = await fs.lstat(file);
      } catch (error) {
        if (error.code !== 'ENOENT') others.push(path.join(folderRel, rel));
        continue;
      }
      if (entryStat.isDirectory()) {
        await walk(rel);
      } else if (entryStat.isFile()) {
        const matched =
          listed.has(path.normalize(path.join(folderRel, rel))) ||
          (Boolean(moduleDir) && (await sameBytes(file, entryStat, path.join(moduleDir, name, rel)))) ||
          (await sameBytes(file, entryStat, path.join(PACKAGE_SRC, name, rel)));
        found.push({ path: path.join(folderRel, rel), matched, artifact: isArtifact(rel) });
      } else {
        others.push(path.join(folderRel, rel));
      }
    }
  };
  await walk('');

  const artifactsAreSkf = found.some((file) => file.matched) || (others.length === 0 && found.every((file) => file.artifact));
  for (const file of found) {
    if (file.matched || (file.artifact && artifactsAreSkf)) result.remove.push(file.path);
    else result.kept.push(file.path);
  }
  result.kept.push(...others);
  result.kept.sort();
  return result;
}

/**
 * Classify the IDE skills folder `targetRel`: its skf-* entries, removed
 * whole, and, for each support folder it holds, the files SKF installed and
 * the entries kept (see classifySupportFolder). Returns null when the folder
 * does not exist, and throws the read error when it cannot be read.
 */
async function classifyIdeTarget(projectDir, targetRel, { moduleDir, listed }) {
  let names;
  try {
    names = await fs.readdir(path.join(projectDir, targetRel));
  } catch (error) {
    if (error.code === 'ENOENT') return null;
    throw error;
  }
  names.sort();
  const support = [];
  for (const name of SUPPORT_FOLDERS) {
    if (!names.includes(name)) continue;
    const folder = await classifySupportFolder(projectDir, targetRel, name, { moduleDir, listed });
    if (folder) support.push(folder);
  }
  return { targetDir: targetRel, skfEntries: names.filter((name) => name.startsWith('skf-')), support };
}

/**
 * The classification of every platform's IDE skills folder that exists, one
 * per folder. A folder that cannot be read is left out. Uninstall's plan and
 * its removal both read this, so they never disagree.
 *
 * @param {string} projectDir - Project root directory
 * @param {{ moduleDir?: string, manifest?: object|null }} options - the SKF module folder on disk and the manifest read
 */
async function classifyIdeTargets(projectDir, { moduleDir, manifest } = {}) {
  const listed = listedIdeFiles(manifest);
  const seen = new Set();
  const targets = [];
  for (const platform of Object.values(loadPlatforms().platforms)) {
    const targetRel = platform.installer?.target_dir;
    if (!targetRel || seen.has(targetRel)) continue;
    seen.add(targetRel);
    let target;
    try {
      target = await classifyIdeTarget(projectDir, targetRel, { moduleDir, listed });
    } catch {
      continue;
    }
    if (target) targets.push(target);
  }
  return targets;
}

/**
 * The number of entries the IDE step removes from a classified folder: its
 * skf-* entries and each support folder holding a file SKF installed.
 */
function ideTargetEntryCount(target) {
  return target.skfEntries.length + target.support.filter((folder) => folder.remove.length > 0).length;
}

/**
 * Thrown when a selected IDE's shared/ folder holds an entry SKF did not
 * install, before the install changes anything.
 */
class IdeFolderInUseError extends Error {
  constructor(folders) {
    const blocks = folders.map(
      (folder) => `${folder.targetDir}/shared/ holds files SKF did not install:\n${folder.kept.map((entry) => `  ${entry}`).join('\n')}`,
    );
    super(`${blocks.join('\n')}\n${SHARED_TAKEN_ADVICE}`);
    this.name = 'IdeFolderInUseError';
    this.folders = folders;
  }
}

/**
 * Classify the skills folder of each selected IDE, before the install writes
 * anything. Throws IdeFolderInUseError naming each shared/ folder that holds
 * an entry SKF did not install, with every such entry, and rethrows the read
 * error of a skills folder that cannot be read. Returns the classifications,
 * keyed by target_dir, for installSkillsToIdes.
 *
 * @param {string} projectDir - Project root directory
 * @param {string[]} ideCodes - Array of IDE codes (e.g., ['claude-code', 'cursor'])
 * @param {{ moduleDir?: string, manifest?: object|null }} options - the SKF module folder on disk and the manifest read
 * @returns {Promise<Map<string, object|null>>}
 */
async function checkIdeFolders(projectDir, ideCodes, { moduleDir, manifest } = {}) {
  const config = loadPlatforms();
  const listed = listedIdeFiles(manifest);
  const classifications = new Map();
  for (const ideCode of Array.isArray(ideCodes) ? ideCodes : []) {
    const targetRel = config.platforms[ideCode]?.installer?.target_dir;
    if (!targetRel || classifications.has(targetRel)) continue;
    classifications.set(targetRel, await classifyIdeTarget(projectDir, targetRel, { moduleDir, listed }));
  }
  const blocking = [];
  for (const target of classifications.values()) {
    const shared = target && target.support.find((folder) => folder.name === 'shared');
    if (shared && shared.kept.length > 0) blocking.push({ targetDir: target.targetDir, kept: shared.kept });
  }
  if (blocking.length > 0) throw new IdeFolderInUseError(blocking);
  return classifications;
}

/**
 * Remove each folder under `dir` left with no entries, then `dir` itself
 * when it is empty, never following a link. Returns whether `dir` went.
 */
async function removeEmptyFolders(dir) {
  let names;
  try {
    if (!(await fs.lstat(dir)).isDirectory()) return false;
    names = await fs.readdir(dir);
  } catch {
    return false;
  }
  let left = names.length;
  for (const name of names) {
    if (await removeEmptyFolders(path.join(dir, name))) left--;
  }
  if (left > 0) return false;
  try {
    await fs.rmdir(dir);
    return true;
  } catch {
    return false;
  }
}

/**
 * Apply a classification: remove the skf-* entries whole, then the files SKF
 * installed in each support folder, then each folder there left empty. A
 * support folder holding no file SKF installed is not touched, and the
 * skills folder itself always stays. Returns whether anything went, and the
 * entries kept in the support folders files were removed from.
 */
async function cleanIdeTarget(projectDir, target) {
  const dir = path.join(projectDir, target.targetDir);
  let removed = false;
  const kept = [];
  for (const name of target.skfEntries) {
    await fs.remove(path.join(dir, name));
    removed = true;
  }
  for (const folder of target.support) {
    if (folder.remove.length === 0) continue;
    for (const file of folder.remove) {
      try {
        await fs.unlink(path.join(projectDir, file));
      } catch (error) {
        if (error.code !== 'ENOENT') throw error;
      }
    }
    removed = true;
    await removeEmptyFolders(path.join(projectDir, folder.folder));
    kept.push(...folder.kept);
  }
  return { removed, kept };
}

/**
 * Install skill directories to all selected IDEs.
 *
 * @param {string} projectDir - Project root directory
 * @param {string} skfDir - Path to installed SKF module (e.g., {projectDir}/_bmad/skf)
 * @param {string[]} ideCodes - Array of IDE codes (e.g., ['claude-code', 'cursor'])
 * @param {Map<string, object|null>} classifications - what checkIdeFolders returned, read before the install wrote anything
 * @returns {{ installed: number, ides: string[], directories: string[], kept: string[] }}
 */
async function installSkillsToIdes(projectDir, skfDir, ideCodes, classifications = new Map()) {
  if (!ideCodes || ideCodes.length === 0) return { installed: 0, ides: [], directories: [], kept: [] };

  const config = loadPlatforms();
  let totalInstalled = 0;
  const processedIdes = [];
  const allDirectories = [];
  const kept = [];
  const cleaned = new Set();

  // Copy filter: skip OS artifacts
  const copyFilter = (src) => !ARTIFACT_FILTER.has(path.basename(src));

  for (const ideCode of ideCodes) {
    const platform = config.platforms[ideCode];
    if (!platform || !platform.installer?.target_dir) continue;

    const targetDir = path.join(projectDir, platform.installer.target_dir);

    // Clean legacy targets first (old command files from previous SKF installs)
    await cleanLegacyTargets(projectDir, platform);

    // Remove what SKF installed in this IDE before (for update/reinstall), as classified before any write
    const target = classifications.get(platform.installer.target_dir);
    if (target && !cleaned.has(target.targetDir)) {
      cleaned.add(target.targetDir);
      kept.push(...(await cleanIdeTarget(projectDir, target)).kept);
    }

    // Ensure target directory exists
    await fs.ensureDir(targetDir);

    // Copy all skf-* skill directories from the installed module
    if (await fs.pathExists(skfDir)) {
      const entries = await fs.readdir(skfDir, { withFileTypes: true });
      for (const entry of entries) {
        if (!entry.isDirectory()) continue;

        // Copy skill directories (skf-*) and shared/, which their scripts find beside them
        if (entry.name.startsWith('skf-') || entry.name === 'shared') {
          const src = path.join(skfDir, entry.name);
          const dest = path.join(targetDir, entry.name);
          await fs.copy(src, dest, { filter: copyFilter });
          totalInstalled++;
        }
      }
    }

    allDirectories.push(platform.installer.target_dir);
    processedIdes.push(ideCode);
  }

  return { installed: totalInstalled, ides: processedIdes, directories: allDirectories, kept };
}

/**
 * Remove legacy command files from old IDE target directories.
 * Handles migration from command-file approach to skill-directory approach.
 */
async function cleanLegacyTargets(projectDir, platform) {
  const legacyTargets = platform.installer?.legacy_targets || [];

  for (const legacyDir of legacyTargets) {
    const fullPath = path.join(projectDir, legacyDir);
    if (!(await fs.pathExists(fullPath))) continue;

    try {
      const files = await fs.readdir(fullPath);
      for (const file of files) {
        // Remove SKF-specific command files from legacy directories
        if (file.startsWith('bmad-skf-') || file.startsWith('bmad-agent-skf-')) {
          await fs.remove(path.join(fullPath, file));
        }
      }

      // Remove empty directories
      const remaining = await fs.readdir(fullPath);
      if (remaining.length === 0) {
        await fs.remove(fullPath);
        // Also try to remove empty parent
        const parentDir = path.dirname(fullPath);
        try {
          const parentRemaining = await fs.readdir(parentDir);
          if (parentRemaining.length === 0) await fs.remove(parentDir);
        } catch {
          /* ignore */
        }
      }
    } catch {
      /* non-critical, continue */
    }
  }
}

/**
 * Remove what SKF installed from every platform's IDE skills folder that
 * exists (see classifyIdeTargets), and the command files earlier releases
 * left in each one's legacy folders. Used during uninstall. Returns the
 * skills folders something was removed from and the entries kept in the
 * support folders files were removed from, as project-relative paths.
 *
 * @param {string} projectDir - Project root directory
 * @param {{ moduleDir?: string, manifest?: object|null }} options - the SKF module folder on disk and the manifest read
 * @returns {Promise<{ cleaned: string[], kept: string[] }>}
 */
async function removeAllSkfSkills(projectDir, { moduleDir, manifest } = {}) {
  const targets = await classifyIdeTargets(projectDir, { moduleDir, manifest });
  const cleaned = [];
  const kept = [];
  for (const target of targets) {
    const result = await cleanIdeTarget(projectDir, target);
    if (result.removed) cleaned.push(target.targetDir);
    kept.push(...result.kept);
  }
  // Every platform whose skills folder exists, a folder classifyIdeTargets cannot read included.
  for (const platform of Object.values(loadPlatforms().platforms)) {
    const targetRel = platform.installer?.target_dir;
    if (targetRel && (await fs.pathExists(path.join(projectDir, targetRel)))) await cleanLegacyTargets(projectDir, platform);
  }
  return { cleaned, kept };
}

module.exports = {
  installSkillsToIdes,
  getAvailablePlatforms,
  getDetectionMarkers,
  checkIdeFolders,
  classifyIdeTargets,
  ideTargetEntryCount,
  IdeFolderInUseError,
  removeAllSkfSkills,
  loadPlatforms,
};
