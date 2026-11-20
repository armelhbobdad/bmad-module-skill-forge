/**
 * CLI Integration Tests - Install/Update/Uninstall Flows
 *
 * End-to-end tests using temp directories to verify:
 * - Fresh install creates all expected files
 * - Update preserves config.yaml and replaces SKF files
 * - Uninstall, run through its real action with its confirm prompt stubbed:
 *   declined, it removes nothing; accepted, it removes the install and
 *   leaves each IDE skills folder in place, empty; with no manifest,
 *   whether or not an SKF folder is there, it removes nothing and never
 *   asks; with a stale manifest, it removes only the manifest; each run
 *   exits 0
 * - IDE skill installation for each target
 * - Manifest accuracy
 * - Folder values that start with {project-root}, as a BMAD Method install
 *   writes them: install, update, status and uninstall read them as the
 *   project root, and install and update remove the literal {project-root}
 *   folder earlier versions left when it holds only the installer's .gitkeep
 *   files
 * - The tool report (tools/cli/lib/tool-check.js), against stub tools on a
 *   PATH the test sets: each tool's version and status against its minimum,
 *   a stub that hangs, a stub in the project folder that never runs, .cmd
 *   shims on Windows, install and update returning (not exiting) so the
 *   update notice prints after them, a run that prints no report leaving no
 *   probe running, and the versions of skill-check (from its package.json)
 *   and tessl (from the name of the binary it installed), read without
 *   running either, and snyk-agent-scan, which SKF runs through uvx and the
 *   report never probes
 * - Uninstall removes only what the installer wrote: an output entry goes
 *   only when it is a regular .gitkeep holding the installer's text, the
 *   fixed _bmad/skf goes whatever skf_folder says, and the action, run with
 *   its confirm prompt stubbed, prints a plan naming the path of each
 *   removal and a warning naming each output entry it keeps
 * - The shared/ and knowledge/ folders of each IDE skills folder: install,
 *   update and uninstall remove only the files SKF installed there (the
 *   bytes of _bmad/skf/ or src/, a path the manifest lists, and bytecode and
 *   OS files beside them), never follow a link, and name the files they keep;
 *   install and update stop, changing nothing, when a selected IDE's shared/
 *   holds anything else; no IDE folder gets a knowledge/ copy any more; and
 *   uninstall still removes the command files earlier releases left in a
 *   platform's legacy folders
 *
 * Usage: node test/test-cli-integration.js
 */

const path = require('node:path');
const os = require('node:os');
const crypto = require('node:crypto');
const { spawnSync } = require('node:child_process');
const fs = require('fs-extra');
const yaml = require('js-yaml');

// ANSI colors
const colors = {
  reset: '\u001B[0m',
  green: '\u001B[32m',
  red: '\u001B[31m',
  yellow: '\u001B[33m',
  cyan: '\u001B[36m',
  dim: '\u001B[2m',
};

let passed = 0;
let failed = 0;

function assert(condition, testName, errorMessage = '') {
  if (condition) {
    console.log(`${colors.green}✓${colors.reset} ${testName}`);
    passed++;
  } else {
    console.log(`${colors.red}✗${colors.reset} ${testName}`);
    if (errorMessage) {
      console.log(`  ${colors.dim}${errorMessage}${colors.reset}`);
    }
    failed++;
  }
}

/**
 * Create a temp directory for a test case.
 */
async function makeTempDir(label) {
  const dir = path.join(os.tmpdir(), `skf-test-${label}-${Date.now()}`);
  await fs.ensureDir(dir);
  return dir;
}

/**
 * Suppress ora spinners, console.log, and stderr writes during install to keep test output clean.
 */
function suppressConsole() {
  const origLog = console.log;
  const origStdoutWrite = process.stdout.write;
  const origStderrWrite = process.stderr.write;
  console.log = () => {};
  process.stdout.write = () => true;
  process.stderr.write = () => true;
  return () => {
    console.log = origLog;
    process.stdout.write = origStdoutWrite;
    process.stderr.write = origStderrWrite;
  };
}

// ============================================================
// Test Suites
// ============================================================

async function testFreshInstall() {
  console.log(`${colors.yellow}Test Suite 1: Fresh Install${colors.reset}\n`);

  const projectDir = await makeTempDir('fresh');

  try {
    const { Installer } = require('../tools/cli/lib/installer');
    const installer = new Installer();

    const config = {
      projectDir,
      skfFolder: '_bmad/skf',
      project_name: 'test-project',
      skills_output_folder: 'skills',
      forge_data_folder: 'forge-data',
      ides: ['claude-code'],
      install_learning: true,
      _action: 'fresh',
    };

    const restore = suppressConsole();
    const result = await installer.install(config);
    restore();

    assert(result.success === true, 'install returns success');

    // Verify SKF directory structure
    const skfDir = path.join(projectDir, '_bmad/skf');
    assert(await fs.pathExists(skfDir), 'SKF directory created');
    assert(await fs.pathExists(path.join(skfDir, 'knowledge')), 'knowledge/ directory created');
    assert(await fs.pathExists(path.join(skfDir, 'shared')), 'shared/ directory created');

    // Verify at least one skf-* skill directory was created
    const skfEntries = (await fs.readdir(skfDir)).filter((e) => e.startsWith('skf-'));
    assert(skfEntries.length > 0, `skill directories created (found ${skfEntries.length})`);

    // Verify config.yaml
    const configPath = path.join(skfDir, 'config.yaml');
    assert(await fs.pathExists(configPath), 'config.yaml created');
    const configContent = yaml.load(await fs.readFile(configPath, 'utf8'));
    assert(configContent.project_name === 'test-project', 'config.yaml has correct project_name');
    assert(configContent.skills_output_folder === 'skills', 'config.yaml has correct skills_output_folder');
    assert(configContent.output_folder === '_bmad-output', 'config.yaml has output_folder (inherited from core config)');
    assert(Array.isArray(configContent.ides) && configContent.ides.includes('claude-code'), 'config.yaml has IDEs');

    // Verify skills installed to IDE directory (.claude/skills/)
    const claudeSkillsDir = path.join(projectDir, '.claude', 'skills');
    assert(await fs.pathExists(path.join(claudeSkillsDir, 'skf-forger', 'SKILL.md')), 'agent skill installed to .claude/skills/');
    assert(await fs.pathExists(path.join(claudeSkillsDir, 'skf-create-skill', 'SKILL.md')), 'workflow skill installed to .claude/skills/');
    // knowledge/ stays in _bmad/skf/ alone: every workflow reads it there, so no IDE folder gets a copy.
    assert(!(await fs.pathExists(path.join(claudeSkillsDir, 'knowledge'))), 'knowledge/ is not copied to .claude/skills/');

    // Verify sidecar
    const sidecarDir = path.join(projectDir, '_bmad/_memory/forger-sidecar');
    assert(await fs.pathExists(sidecarDir), 'sidecar directory created');

    // Verify output folders
    assert(await fs.pathExists(path.join(projectDir, 'skills')), 'skills/ output folder created');
    assert(await fs.pathExists(path.join(projectDir, 'forge-data')), 'forge-data/ output folder created');
    assert(await fs.pathExists(path.join(projectDir, 'skills/.gitkeep')), 'skills/.gitkeep created');
    assert(await fs.pathExists(path.join(projectDir, 'forge-data/.gitkeep')), 'forge-data/.gitkeep created');

    // Verify learning material
    assert(await fs.pathExists(path.join(projectDir, '_skf-learn')), '_skf-learn/ directory created');

    // Verify manifest
    const manifestPath = path.join(projectDir, '_bmad/_config/skf-manifest.yaml');
    assert(await fs.pathExists(manifestPath), 'manifest created');
    const manifest = yaml.load(await fs.readFile(manifestPath, 'utf8'));
    assert(manifest.module === 'skf', 'manifest has module: skf');
    assert(manifest.action === 'fresh', 'manifest has action: fresh');
    assert(Array.isArray(manifest.files.skf) && manifest.files.skf.length > 0, 'manifest tracks SKF files');
    assert(Array.isArray(manifest.files.sidecar) && manifest.files.sidecar.length > 0, 'manifest tracks sidecar files');

    // Verify IDE skills
    const claudeSkillsDirManifest = path.join(projectDir, '.claude/skills');
    assert(await fs.pathExists(claudeSkillsDirManifest), '.claude/skills/ created');
    const skillEntries = await fs.readdir(claudeSkillsDirManifest);
    const agentSkills = skillEntries.filter((f) => f.startsWith('skf-') && f.includes('forger'));
    const workflowSkills = skillEntries.filter((f) => f.startsWith('skf-') && !f.includes('forger'));
    assert(agentSkills.length > 0, `agent skill directories installed (found ${agentSkills.length})`);
    assert(workflowSkills.length > 0, `workflow skill directories installed (found ${workflowSkills.length})`);

    // Verify manifest tracks IDE files
    assert(Array.isArray(manifest.files.ide_skills) && manifest.files.ide_skills.length > 0, 'manifest tracks IDE skill files');
    const ideKnowledge = path.join('.claude', 'skills', 'knowledge');
    assert(
      !manifest.files.ide_skills.some((file) => file === ideKnowledge || file.startsWith(`${ideKnowledge}${path.sep}`)),
      'manifest lists no IDE skill file under .claude/skills/knowledge/',
    );
  } catch (error) {
    assert(false, 'fresh install completes without error', error.message);
  } finally {
    await fs.remove(projectDir);
  }

  console.log('');
}

async function testUpdatePreservesConfig() {
  console.log(`${colors.yellow}Test Suite 2: Update Preserves Config${colors.reset}\n`);

  const projectDir = await makeTempDir('update');

  try {
    const { Installer } = require('../tools/cli/lib/installer');
    const installer = new Installer();

    // Step 1: Fresh install
    const config = {
      projectDir,
      skfFolder: '_bmad/skf',
      project_name: 'original-name',
      skills_output_folder: 'skills',
      forge_data_folder: 'forge-data',
      ides: ['cursor'],
      install_learning: false,
      _action: 'fresh',
    };

    let restore = suppressConsole();
    await installer.install(config);
    restore();

    // Verify initial config
    const skfDir = path.join(projectDir, '_bmad/skf');
    const configPath = path.join(skfDir, 'config.yaml');
    const origConfig = await fs.readFile(configPath, 'utf8');
    assert(origConfig.includes('original-name'), 'initial config has original project name');

    // Add a marker file to sidecar to verify it persists
    const sidecarMarker = path.join(projectDir, '_bmad/_memory/forger-sidecar/user-state.yaml');
    await fs.writeFile(sidecarMarker, 'custom: state\n', 'utf8');

    // Step 2: Update
    const updateConfig = {
      projectDir,
      skfFolder: '_bmad/skf',
      _action: 'update',
    };

    restore = suppressConsole();
    const result = await installer.install(updateConfig);
    restore();

    assert(result.success === true, 'update returns success');

    // Config should be preserved
    const updatedConfig = await fs.readFile(configPath, 'utf8');
    assert(updatedConfig.includes('original-name'), 'config.yaml preserved after update');

    // SKF files should still exist
    const skfDirsAfterUpdate = (await fs.readdir(skfDir)).filter((e) => e.startsWith('skf-'));
    assert(skfDirsAfterUpdate.length > 0, 'skill directories exist after update');
    assert(await fs.pathExists(path.join(skfDir, 'knowledge')), 'knowledge/ exists after update');

    // Sidecar user state should persist (sidecar files are not overwritten)
    assert(await fs.pathExists(sidecarMarker), 'sidecar user state preserved after update');

    // Manifest should reflect update action
    const manifestPath = path.join(projectDir, '_bmad/_config/skf-manifest.yaml');
    const manifest = yaml.load(await fs.readFile(manifestPath, 'utf8'));
    assert(manifest.action === 'update', 'manifest action is update');
  } catch (error) {
    assert(false, 'update flow completes without error', error.message);
  } finally {
    await fs.remove(projectDir);
  }

  console.log('');
}

async function testUninstallCleansUp() {
  console.log(`${colors.yellow}Test Suite 3: Uninstall, Through Its Real Action${colors.reset}\n`);

  const { readManifest, MANIFEST_DIR, MANIFEST_FILE } = require('../tools/cli/lib/manifest');
  // Every file and folder under `dir`, at any depth, sorted.
  const listing = async (dir) => (await fs.readdir(dir, { recursive: true })).sort();
  const exitedZero = (run) => JSON.stringify(run.exits) === '[0]';
  // One confirm call, asking whether to proceed, with No as the default, so Enter answers No.
  const askedOnce = (run) =>
    run.confirmCalls.length === 1 &&
    run.confirmCalls[0].message === 'Proceed with uninstall?' &&
    run.confirmCalls[0].initialValue === false;

  const projectDir = await makeTempDir('uninstall');

  try {
    const { Installer } = require('../tools/cli/lib/installer');
    const installer = new Installer();

    // Install first
    const config = {
      projectDir,
      skfFolder: '_bmad/skf',
      project_name: 'uninstall-test',
      skills_output_folder: 'skills',
      forge_data_folder: 'forge-data',
      ides: ['claude-code', 'cursor'],
      install_learning: true,
      _action: 'fresh',
    };

    const restore = suppressConsole();
    await installer.install(config);
    restore();

    // Verify files exist before uninstall
    assert(await fs.pathExists(path.join(projectDir, '_bmad/skf')), 'SKF dir exists before uninstall');
    assert(await fs.pathExists(path.join(projectDir, '_skf-learn')), '_skf-learn exists before uninstall');
    assert(await fs.pathExists(path.join(projectDir, '.claude/skills')), '.claude/skills exists before uninstall');
    assert(await fs.pathExists(path.join(projectDir, '.cursor/skills')), '.cursor/skills exists before uninstall');

    // Read manifest
    const manifest = await readManifest(projectDir);
    assert(manifest !== null, 'manifest exists before uninstall');

    // Decline first, so the accept run below also shows a declined run leaves a working install.
    const before = await listing(projectDir);
    const declined = await runUninstallAction(projectDir, { answer: false });
    assert(exitedZero(declined), 'decline: the action exits 0', JSON.stringify(declined.exits) + declined.output);
    assert(
      askedOnce(declined),
      'decline: the action asks once, "Proceed with uninstall?", with No as the default',
      JSON.stringify(declined.confirmCalls),
    );
    assert(
      declined.output.includes('The following will be removed:') && declined.output.includes('Uninstall cancelled.'),
      'decline: the action prints the plan, then "Uninstall cancelled."',
      declined.output,
    );
    const after = await listing(projectDir);
    assert(
      JSON.stringify(after) === JSON.stringify(before),
      'decline: nothing in the project changes',
      `gone: ${before.filter((entry) => !after.includes(entry)).join(', ')}; new: ${after.filter((entry) => !before.includes(entry)).join(', ')}`,
    );

    const accepted = await runUninstallAction(projectDir, { answer: true });
    assert(exitedZero(accepted), 'accept: the action exits 0', JSON.stringify(accepted.exits) + accepted.output);
    assert(askedOnce(accepted), 'accept: the action asks once', JSON.stringify(accepted.confirmCalls));
    assert(
      accepted.output.includes('SKF uninstalled successfully.'),
      'accept: the action prints "SKF uninstalled successfully."',
      accepted.output,
    );

    // Verify everything is cleaned up
    assert(!(await fs.pathExists(path.join(projectDir, '_bmad/skf'))), 'SKF dir removed');
    assert(!(await fs.pathExists(path.join(projectDir, '_skf-learn'))), '_skf-learn removed');
    assert(!(await fs.pathExists(path.join(projectDir, 'skills'))), 'skills/ output folder removed');
    assert(!(await fs.pathExists(path.join(projectDir, 'forge-data'))), 'forge-data/ output folder removed');
    // _bmad/ goes only through the empty-folder cleanup, so this also shows the cleanup ran last.
    assert(!(await fs.pathExists(path.join(projectDir, '_bmad'))), '_bmad/ cleaned up (empty)');
    // The IDE step removes the SKF entries of each IDE skills folder, never the folder.
    for (const ide of ['.claude/skills', '.cursor/skills']) {
      const dir = path.join(projectDir, ide);
      const left = (await fs.pathExists(dir)) ? await fs.readdir(dir) : null;
      assert(left !== null && left.length === 0, `uninstall: ${ide}/ stays, empty`, String(left));
    }
    // All the accepted run leaves: each IDE skills folder in its parent, and the
    // .gitignore the installer wrote, which uninstall never edits.
    const leftOver = await listing(projectDir);
    const expectedLeftOver = ['.claude', path.join('.claude', 'skills'), '.cursor', path.join('.cursor', 'skills'), '.gitignore'].sort();
    assert(
      JSON.stringify(leftOver) === JSON.stringify(expectedLeftOver),
      'accept: only the IDE skills folders and .gitignore are left',
      leftOver.join(', '),
    );
  } catch (error) {
    assert(false, 'uninstall flow completes without error', error.message);
  } finally {
    await fs.remove(projectDir);
  }

  await inProject('uninstall-no-manifest', 'uninstall with an SKF folder and no manifest', async (dir) => {
    const skfConfig = path.join(dir, '_bmad', 'skf', 'config.yaml');
    await fs.ensureDir(path.dirname(skfConfig));
    await fs.writeFile(skfConfig, 'user_name: Tester\n');

    const run = await runUninstallAction(dir);
    assert(exitedZero(run), 'no manifest, SKF folder: the action exits 0', JSON.stringify(run.exits) + run.output);
    assert(
      run.output.includes('No manifest found') && run.output.includes('Run: npx bmad-module-skill-forge install'),
      'no manifest, SKF folder: the action says no manifest was found and how to reinstall',
      run.output,
    );
    assert(run.confirmCalls.length === 0, 'no manifest, SKF folder: the action never asks', JSON.stringify(run.confirmCalls));
    assert(await fs.pathExists(skfConfig), 'no manifest, SKF folder: _bmad/skf/config.yaml stays');
  });

  await inProject('uninstall-not-installed', 'uninstall with no manifest and no SKF folder', async (dir) => {
    const readme = path.join(dir, 'README.md');
    await fs.writeFile(readme, '# mine\n');

    const run = await runUninstallAction(dir);
    assert(exitedZero(run), 'no manifest, nothing: the action exits 0', JSON.stringify(run.exits) + run.output);
    assert(
      run.output.includes('SKF is not installed in this directory.'),
      'no manifest, nothing: the action says SKF is not installed',
      run.output,
    );
    assert(run.confirmCalls.length === 0, 'no manifest, nothing: the action never asks', JSON.stringify(run.confirmCalls));
    assert(await fs.pathExists(readme), 'no manifest, nothing: README.md stays');
  });

  await inProject('uninstall-stale', 'uninstall with a stale manifest', async (dir) => {
    const readme = path.join(dir, 'README.md');
    await fs.writeFile(readme, '# mine\n');
    // Every file it lists is gone from disk.
    const manifestPath = path.join(dir, MANIFEST_DIR, MANIFEST_FILE);
    await fs.ensureDir(path.dirname(manifestPath));
    await fs.writeFile(
      manifestPath,
      yaml.dump({
        skf_folder: '_bmad/skf',
        files: {
          skf: ['_bmad/skf/config.yaml'],
          sidecar: [],
          ide_skills: ['.claude/skills/skf-setup/SKILL.md'],
          learning: [],
          output: ['skills/.gitkeep'],
        },
      }),
    );

    const before = await listing(dir);
    const run = await runUninstallAction(dir);
    assert(exitedZero(run), 'stale manifest: the action exits 0', JSON.stringify(run.exits) + run.output);
    assert(run.output.includes('No SKF files found to remove.'), 'stale manifest: the action says no SKF files were found', run.output);
    assert(run.confirmCalls.length === 0, 'stale manifest: the action never asks', JSON.stringify(run.confirmCalls));
    assert(!(await fs.pathExists(manifestPath)), 'stale manifest: the manifest goes');
    assert(await fs.pathExists(readme), 'stale manifest: README.md stays');
    // The stale path removes the manifest file alone, so _bmad/_config/ and _bmad/ stay, now empty.
    const after = await listing(dir);
    assert(
      JSON.stringify(after) === JSON.stringify(before.filter((entry) => entry !== path.join(MANIFEST_DIR, MANIFEST_FILE))),
      'stale manifest: nothing but the manifest goes',
      `before: ${before.join(', ')}; after: ${after.join(', ')}`,
    );
  });

  console.log('');
}

async function testIdeCommandGeneration() {
  console.log(`${colors.yellow}Test Suite 4: IDE Skill Installation${colors.reset}\n`);

  const projectDir = await makeTempDir('ide-cmds');

  try {
    const { Installer } = require('../tools/cli/lib/installer');
    const installer = new Installer();

    // Test with a subset of IDEs (claude-code and cursor represent the pattern)
    const testIdes = ['claude-code', 'cursor'];

    const config = {
      projectDir,
      skfFolder: '_bmad/skf',
      project_name: 'ide-test',
      skills_output_folder: 'skills',
      forge_data_folder: 'forge-data',
      ides: testIdes,
      install_learning: false,
      _action: 'fresh',
    };

    const restore = suppressConsole();
    await installer.install(config);
    restore();

    // Verify each IDE got skill directories (not command files)
    const ideSkillDirs = {
      'claude-code': '.claude/skills',
      cursor: '.cursor/skills',
    };

    for (const [ide, targetDir] of Object.entries(ideSkillDirs)) {
      const fullDir = path.join(projectDir, targetDir);
      const exists = await fs.pathExists(fullDir);
      assert(exists, `${ide}: ${targetDir}/ created`);

      if (exists) {
        const entries = await fs.readdir(fullDir);
        const skillDirs = entries.filter((e) => e.startsWith('skf-'));
        assert(skillDirs.length > 0, `${ide}: has skill directories`);
        assert(skillDirs.includes('skf-forger'), `${ide}: has skf-forger agent skill`);
        assert(skillDirs.includes('skf-create-skill'), `${ide}: has skf-create-skill workflow skill`);

        // shared/ is copied beside the skills, whose scripts find it there; knowledge/ is not
        assert(!entries.includes('knowledge'), `${ide}: has no knowledge/ directory`);
        assert(entries.includes('shared'), `${ide}: has shared/ directory`);
      }
    }

    // Verify SKILL.md exists in agent skill directory
    const agentSkillMd = path.join(projectDir, '.claude/skills/skf-forger/SKILL.md');
    assert(await fs.pathExists(agentSkillMd), 'agent SKILL.md exists in .claude/skills/');

    // Verify a workflow skill has SKILL.md with Overview section (workflow.md consolidated into SKILL.md)
    const workflowSkillDir = path.join(projectDir, '.claude/skills/skf-create-skill');
    assert(await fs.pathExists(path.join(workflowSkillDir, 'SKILL.md')), 'workflow has SKILL.md');
    const workflowContent = await fs.readFile(path.join(workflowSkillDir, 'SKILL.md'), 'utf8');
    assert(workflowContent.includes('## Overview'), 'workflow SKILL.md has Overview section');

    // knowledge/ stays in _bmad/skf/, where every workflow reads it, and the manifest lists no IDE copy of it
    assert(await fs.pathExists(path.join(projectDir, '_bmad/skf/knowledge')), 'knowledge/ is in _bmad/skf/');
    const { readManifest } = require('../tools/cli/lib/manifest');
    const ideSkills = (await readManifest(projectDir)).files.ide_skills;
    const underKnowledge = ideSkills.filter((file) =>
      Object.values(ideSkillDirs).some((dir) => file.startsWith(`${path.join(dir, 'knowledge')}${path.sep}`)),
    );
    assert(
      ideSkills.length > 0 && underKnowledge.length === 0,
      'manifest lists no IDE skill file under an IDE knowledge/',
      underKnowledge.join(', '),
    );
  } catch (error) {
    assert(false, 'IDE command generation completes without error', error.message);
  } finally {
    await fs.remove(projectDir);
  }

  console.log('');
}

async function testManifestAccuracy() {
  console.log(`${colors.yellow}Test Suite 5: Manifest Accuracy${colors.reset}\n`);

  const projectDir = await makeTempDir('manifest');

  try {
    const { Installer } = require('../tools/cli/lib/installer');
    const { readManifest } = require('../tools/cli/lib/manifest');
    const installer = new Installer();

    const config = {
      projectDir,
      skfFolder: '_bmad/skf',
      project_name: 'manifest-test',
      skills_output_folder: 'my-skills',
      forge_data_folder: 'my-forge',
      ides: ['claude-code'],
      install_learning: true,
      _action: 'fresh',
    };

    const restore = suppressConsole();
    await installer.install(config);
    restore();

    const manifest = await readManifest(projectDir);
    assert(manifest !== null, 'manifest readable');

    // Verify every file in manifest actually exists on disk
    let allExist = true;
    let missingFiles = [];
    const allFiles = [
      ...manifest.files.skf,
      ...manifest.files.sidecar,
      ...manifest.files.ide_skills,
      ...manifest.files.learning,
      ...manifest.files.output,
    ];

    for (const file of allFiles) {
      if (!(await fs.pathExists(path.join(projectDir, file)))) {
        allExist = false;
        missingFiles.push(file);
      }
    }
    assert(allExist, `all ${allFiles.length} manifest files exist on disk`, missingFiles.join(', '));

    // Verify manifest metadata
    assert(manifest.skf_folder === '_bmad/skf', 'manifest has correct skf_folder');
    assert(manifest.skills_output_folder === 'my-skills', 'manifest has correct skills_output_folder');
    assert(manifest.forge_data_folder === 'my-forge', 'manifest has correct forge_data_folder');
    assert(typeof manifest.version === 'string' && manifest.version.length > 0, 'manifest has version');
    assert(typeof manifest.installed_at === 'string', 'manifest has installed_at timestamp');

    // Verify directories list
    assert(Array.isArray(manifest.directories), 'manifest has directories array');
    assert(manifest.directories.includes('_bmad/skf'), 'directories includes SKF folder');
    assert(manifest.directories.includes('_bmad/_memory/forger-sidecar'), 'directories includes sidecar');
  } catch (error) {
    assert(false, 'manifest accuracy test completes without error', error.message);
  } finally {
    await fs.remove(projectDir);
  }

  console.log('');
}

async function testFreshInstallWithoutLearning() {
  console.log(`${colors.yellow}Test Suite 6: Install Without Learning Material${colors.reset}\n`);

  const projectDir = await makeTempDir('no-learn');

  try {
    const { Installer } = require('../tools/cli/lib/installer');
    const installer = new Installer();

    const config = {
      projectDir,
      skfFolder: '_bmad/skf',
      project_name: 'no-learn-test',
      skills_output_folder: 'skills',
      forge_data_folder: 'forge-data',
      ides: [],
      install_learning: false,
      _action: 'fresh',
    };

    const restore = suppressConsole();
    await installer.install(config);
    restore();

    assert(!(await fs.pathExists(path.join(projectDir, '_skf-learn'))), 'no _skf-learn when learning disabled');

    // Manifest should have empty learning files list
    const { readManifest } = require('../tools/cli/lib/manifest');
    const manifest = await readManifest(projectDir);
    assert(manifest.files.learning.length === 0, 'manifest has no learning files');
    assert(manifest.files.ide_skills.length === 0, 'manifest has no IDE skill files (no IDEs selected)');
  } catch (error) {
    assert(false, 'install without learning completes without error', error.message);
  } finally {
    await fs.remove(projectDir);
  }

  console.log('');
}

async function testGitignoreEntries() {
  console.log(`${colors.yellow}Test Suite 7: .gitignore Entries${colors.reset}\n`);

  // Case A: No .gitignore — creates one
  const dirA = await makeTempDir('gitignore-new');
  try {
    const { Installer } = require('../tools/cli/lib/installer');
    const installer = new Installer();
    const config = {
      projectDir: dirA,
      skfFolder: '_bmad/skf',
      project_name: 'gi-test',
      skills_output_folder: 'skills',
      forge_data_folder: 'forge-data',
      ides: [],
      install_learning: false,
      _action: 'fresh',
    };
    const restore = suppressConsole();
    await installer.install(config);
    restore();

    const giPath = path.join(dirA, '.gitignore');
    assert(await fs.pathExists(giPath), 'creates .gitignore when none exists');
    const content = await fs.readFile(giPath, 'utf8');
    assert(content.includes('_bmad/_memory/'), '.gitignore contains _bmad/_memory/');
  } catch (error) {
    assert(false, 'gitignore creation test', error.message);
  } finally {
    await fs.remove(dirA);
  }

  // Case B: Existing .gitignore without entry — appends
  const dirB = await makeTempDir('gitignore-append');
  try {
    const { Installer } = require('../tools/cli/lib/installer');
    const installer = new Installer();
    await fs.writeFile(path.join(dirB, '.gitignore'), 'node_modules/\n.env\n', 'utf8');
    const config = {
      projectDir: dirB,
      skfFolder: '_bmad/skf',
      project_name: 'gi-test',
      skills_output_folder: 'skills',
      forge_data_folder: 'forge-data',
      ides: [],
      install_learning: false,
      _action: 'fresh',
    };
    const restore = suppressConsole();
    await installer.install(config);
    restore();

    const content = await fs.readFile(path.join(dirB, '.gitignore'), 'utf8');
    assert(content.includes('node_modules/'), 'preserves existing entries');
    assert(content.includes('_bmad/_memory/'), 'appends _bmad/_memory/ entry');
    const occurrences = content.split('_bmad/_memory/').length - 1;
    assert(occurrences === 1, 'entry appears exactly once');
  } catch (error) {
    assert(false, 'gitignore append test', error.message);
  } finally {
    await fs.remove(dirB);
  }

  // Case C: .gitignore already has entry — no duplicate
  const dirC = await makeTempDir('gitignore-dup');
  try {
    const { Installer } = require('../tools/cli/lib/installer');
    const installer = new Installer();
    await fs.writeFile(path.join(dirC, '.gitignore'), 'node_modules/\n_bmad/_memory/\n', 'utf8');
    const config = {
      projectDir: dirC,
      skfFolder: '_bmad/skf',
      project_name: 'gi-test',
      skills_output_folder: 'skills',
      forge_data_folder: 'forge-data',
      ides: [],
      install_learning: false,
      _action: 'fresh',
    };
    const restore = suppressConsole();
    await installer.install(config);
    restore();

    const content = await fs.readFile(path.join(dirC, '.gitignore'), 'utf8');
    const occurrences = content.split('_bmad/_memory/').length - 1;
    assert(occurrences === 1, 'does not duplicate existing entry');
  } catch (error) {
    assert(false, 'gitignore no-duplicate test', error.message);
  } finally {
    await fs.remove(dirC);
  }

  // Case D: .gitignore without trailing newline — appends cleanly
  const dirD = await makeTempDir('gitignore-nonl');
  try {
    const { Installer } = require('../tools/cli/lib/installer');
    const installer = new Installer();
    await fs.writeFile(path.join(dirD, '.gitignore'), 'node_modules/', 'utf8');
    const config = {
      projectDir: dirD,
      skfFolder: '_bmad/skf',
      project_name: 'gi-test',
      skills_output_folder: 'skills',
      forge_data_folder: 'forge-data',
      ides: [],
      install_learning: false,
      _action: 'fresh',
    };
    const restore = suppressConsole();
    await installer.install(config);
    restore();

    const content = await fs.readFile(path.join(dirD, '.gitignore'), 'utf8');
    assert(!content.includes('node_modules/_bmad'), 'entry on its own line (not appended to previous)');
    assert(content.includes('_bmad/_memory/'), 'entry present after no-newline file');
  } catch (error) {
    assert(false, 'gitignore no-trailing-newline test', error.message);
  } finally {
    await fs.remove(dirD);
  }

  console.log('');
}

// ============================================================
// Tool report (tools/cli/lib/tool-check.js)
// ============================================================

const IS_WINDOWS = process.platform === 'win32';
const TOOL_LIST = path.join(__dirname, '..', 'src', 'shared', 'tool-requirements.yaml');
// eslint-disable-next-line no-control-regex -- the report is colored with chalk
const ANSI = /\u001B\[\d+(?:;\d+)*m/g;

/**
 * A stub tool in `dir`: a shell script on POSIX, a .cmd batch file on
 * Windows. `out` lines are echoed whatever the arguments; `posix` and
 * `windows` replace the script body.
 */
async function writeStub(dir, name, { out = [], posix, windows } = {}) {
  await fs.ensureDir(dir);
  if (IS_WINDOWS) {
    const body = windows ?? out.map((line) => `echo ${line}`);
    await fs.writeFile(path.join(dir, `${name}.cmd`), ['@echo off', ...body, ''].join('\r\n'));
    return;
  }
  const file = path.join(dir, name);
  await fs.writeFile(file, ['#!/bin/sh', ...(posix ?? out.map((line) => `echo '${line}'`)), ''].join('\n'));
  await fs.chmod(file, 0o755);
}

/**
 * A skill-check install in `dir` that, like skill-check 1.2.0, answers no
 * --version: run with any arguments, it writes `ran` to `marker` and exits 2.
 * The `link` layout is npm's global one on POSIX: the binary on PATH is a
 * symlink into `<dir>/../<install>/lib/node_modules/skill-check/bin/`. The
 * `shim` layout is npm's on Windows: the binary sits next to
 * `node_modules/skill-check/`. `name`, `version` and `bin` fill the
 * package.json, which `name: null` leaves out; `nameless` adds a
 * package.json with no name next to the linked binary, as a
 * `{"type": "module"}` file is.
 */
async function writeSkillCheck(
  dir,
  {
    marker,
    layout = IS_WINDOWS ? 'shim' : 'link',
    name = 'skill-check',
    version = '1.2.0',
    bin = 'bin/skill-check.js',
    nameless = false,
    install = 'global',
  },
) {
  const body = { posix: [`echo ran > '${marker}'`, 'exit 2'], windows: [`echo ran> "${marker}"`, 'exit /b 2'] };
  const manifest = name === null ? null : JSON.stringify({ name, version, bin: { 'skill-check': bin } });
  if (layout === 'shim') {
    await writeStub(dir, 'skill-check', body);
    const pkg = path.join(dir, 'node_modules', 'skill-check');
    await fs.ensureDir(pkg);
    if (manifest) await fs.writeFile(path.join(pkg, 'package.json'), manifest);
    return;
  }
  const pkg = path.join(path.dirname(dir), install, 'lib', 'node_modules', 'skill-check');
  await writeStub(path.join(pkg, 'bin'), 'skill-check.js', body);
  if (manifest) await fs.writeFile(path.join(pkg, 'package.json'), manifest);
  if (nameless) await fs.writeFile(path.join(pkg, 'bin', 'package.json'), JSON.stringify({ type: 'module' }));
  await fs.ensureDir(dir);
  await fs.symlink(path.join(pkg, 'bin', 'skill-check.js'), path.join(dir, 'skill-check'));
}

/** process.env with PATH replaced (every spelling of its name, for Windows). */
function envWithPath(...dirs) {
  const env = {};
  for (const [key, value] of Object.entries(process.env)) {
    if (key.toUpperCase() !== 'PATH') env[key] = value;
  }
  env.PATH = dirs.join(path.delimiter);
  return env;
}

function byKey(rows) {
  return Object.fromEntries(rows.map((row) => [row.key, row]));
}

/** The status a found version has against the shipped minimum of `key`. */
function expectedStatus(list, key, version) {
  const { compareVersions } = require('../tools/cli/lib/version-check');
  const minimum = list.tools[key].minimum;
  return minimum && compareVersions(version, minimum.includes('.') ? minimum : `${minimum}.0`) ? 'upgrade' : 'ok';
}

/** A POSIX stub that writes its process id to `pidFile`, then hangs as that same process. */
async function writePidStub(dir, name, pidFile) {
  await writeStub(dir, name, { posix: [`echo $$ > '${pidFile}'`, 'exec /bin/sleep 30'] });
}

/** The process id a stub wrote to `pidFile`, or null when none is written within `ms`. */
async function readPid(pidFile, ms = 5000) {
  const deadline = Date.now() + ms;
  while (Date.now() < deadline) {
    const text = await fs.readFile(pidFile, 'utf8').catch(() => '');
    if (/^\d+\n$/.test(text)) return Number(text.trim());
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  return null;
}

/** True once process `pid` has ended (a zombie has ended too), polling for up to `ms`. POSIX only. */
async function processEnded(pid, ms = 3000) {
  const deadline = Date.now() + ms;
  for (;;) {
    const ps = spawnSync('ps', ['-o', 'stat=', '-p', String(pid)], { encoding: 'utf8' });
    if (ps.status !== 0 || ps.stdout.trim().startsWith('Z')) return true;
    if (Date.now() >= deadline) return false;
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
}

/** Kill a stub a failed check left running. */
function killStub(pid) {
  try {
    process.kill(pid, 'SIGKILL');
  } catch {
    // Already gone
  }
}

/**
 * A --require preload for a CLI run: the registry check answers `version`
 * with no network and, when SKF_TEST_SPAWN_LOG is set, each process the CLI
 * spawns is logged there as "<pid> <file>" the moment it starts.
 */
async function writeCliPreload(file, version) {
  await fs.writeFile(
    file,
    [
      "const fs = require('node:fs');",
      "const https = require('node:https');",
      "const childProcess = require('node:child_process');",
      "const { EventEmitter } = require('node:events');",
      'https.get = (url, options, callback) => {',
      '  const request = new EventEmitter();',
      '  request.destroy = () => {};',
      '  process.nextTick(() => {',
      '    const response = new EventEmitter();',
      '    response.statusCode = 200;',
      '    response.resume = () => {};',
      '    callback(response);',
      `    response.emit('data', JSON.stringify({ version: '${version}' }));`,
      "    response.emit('end');",
      '  });',
      '  return request;',
      '};',
      'const spawn = childProcess.spawn;',
      'childProcess.spawn = function (file, ...rest) {',
      '  const child = spawn.call(this, file, ...rest);',
      '  if (process.env.SKF_TEST_SPAWN_LOG && child.pid) {',
      String.raw`    fs.appendFileSync(process.env.SKF_TEST_SPAWN_LOG, child.pid + ' ' + file + '\n');`,
      '  }',
      '  return child;',
      '};',
      '',
    ].join('\n'),
  );
}

/** A folder of stub tools: every tool of the list but qmd, tessl and python3. */
async function writeToolStubs(dir) {
  await writeStub(dir, 'uv', {
    posix: [
      'case "$1" in',
      '  python) echo 3.12.4 ;;',
      String.raw`  tool) printf 'ruff v0.6.0\n- ruff\ncocoindex-code v0.2.41\n- ccc\n' ;;`,
      "  *) echo 'uv 0.12.15 (stub)' ;;",
      'esac',
    ],
    windows: [
      'if "%1"=="python" (echo 3.12.4& exit /b 0)',
      'if "%1"=="tool" (echo ruff v0.6.0& echo - ruff& echo cocoindex-code v0.2.41& echo - ccc& exit /b 0)',
      'echo uv 0.12.15 (stub)',
    ],
  });
  await writeStub(dir, 'git', { out: ['git version 1.9.5'] });
  await writeStub(dir, 'gh', { out: ['gh: no version here'] });
  await writeStub(dir, 'ast-grep', { out: ['ast-grep 0.1.0'] });
  await writeStub(dir, 'ccc', { posix: ['exit 0'], windows: ['exit /b 0'] });
  await writeSkillCheck(dir, { marker: path.join(path.dirname(dir), 'skill-check-ran') });
}

async function testToolReport() {
  console.log(`${colors.yellow}Test Suite 8: Tool Report${colors.reset}\n`);

  const root = await makeTempDir('tools');
  try {
    const { checkTools, formatReport } = require('../tools/cli/lib/tool-check');
    const list = yaml.load(await fs.readFile(TOOL_LIST, 'utf8'));
    const stubs = path.join(root, 'stubs');
    await writeToolStubs(stubs);
    const project = path.join(root, 'project');
    await fs.ensureDir(project);

    const rows = await checkTools({ projectDir: project, env: envWithPath(stubs), timeoutMs: 10_000 });
    assert(
      rows.map((row) => row.key).join(',') === Object.keys(list.tools).join(','),
      'one row per tool, in the order of tool-requirements.yaml',
      rows.map((row) => row.key).join(','),
    );
    const found = byKey(rows);
    const check = (key, version, status, label) => {
      const row = found[key];
      const ok = row && row.version === version && row.status === status && (label === undefined || row.label === label);
      assert(ok, `${key}: ${version ?? '-'} ${label ?? status}`, JSON.stringify(row));
    };
    check('node', process.versions.node, expectedStatus(list, 'node', process.versions.node));
    check('python', '3.12.4', 'ok', 'ok');
    check('uv', '0.12.15', 'ok', 'ok');
    check('git', '1.9.5', 'upgrade', `upgrade to >= ${list.tools.git.minimum}`);
    check('gh_cli', null, 'unknown', 'installed, version unknown');
    check('ast_grep', '0.1.0', 'upgrade', `upgrade to >= ${list.tools.ast_grep.minimum}`);
    check('ccc', '0.2.41', 'ok', 'ok');
    check('qmd', null, 'optional', `optional, ${list.tools.qmd.tiers[0]} tier`);
    check('tessl', null, 'optional', 'optional, runs through npx');
    check('skill_check', '1.2.0', 'ok', 'ok');
    assert(!(await fs.pathExists(path.join(root, 'skill-check-ran'))), 'skill-check is not run: its version comes from its package.json');
    // SKF runs the scanner through uvx at the version skf-security-scan.py pins, so nothing is probed (#892).
    check('snyk_agent_scan', null, 'optional', 'optional, runs through uvx');
    assert(found.ast_grep.hint === list.tools.ast_grep.upgrade, 'a tool below its minimum names its upgrade command');
    assert(found.qmd.hint === list.tools.qmd.install_url, 'a missing tier tool names its install page');
    assert(found.gh_cli.hint === undefined, 'a tool with no minimum and an unreadable version gets no upgrade line');

    const lines = formatReport(rows).map((line) => line.replaceAll(ANSI, ''));
    const astLine = lines.find((line) => line.includes('ast-grep'));
    assert(lines[0].trim() === 'Tools', 'the report opens with its heading', lines[0]);
    assert(
      /^ {4}ast-grep +0\.1\.0 +upgrade to >= \S+ +npm install -g @ast-grep\/cli@latest$/.test(astLine),
      'a report line holds the tool, its version, its status and how to upgrade',
      astLine,
    );

    // The project's copy of the list (the SKF version its workflows run) decides the minimums.
    const copy = path.join(project, '_bmad', 'skf', 'shared', 'tool-requirements.yaml');
    await fs.ensureDir(path.dirname(copy));
    await fs.writeFile(copy, 'schema_version: 1\ntools:\n  ast_grep:\n    minimum: "0.1"\n');
    const pinned = byKey(await checkTools({ projectDir: project, env: envWithPath(stubs), timeoutMs: 10_000 }));
    assert(pinned.ast_grep.status === 'ok', "the project's copy of the list sets the minimums", JSON.stringify(pinned.ast_grep));
    assert(pinned.git.status === 'ok', 'a tool the copy gives no minimum has none', JSON.stringify(pinned.git));
  } catch (error) {
    assert(false, 'tool report completes without error', error.stack);
  } finally {
    await fs.remove(root);
  }

  console.log('');
}

async function testToolReportHangingStub() {
  console.log(`${colors.yellow}Test Suite 9: Tool Report With a Tool That Hangs${colors.reset}\n`);

  const root = await makeTempDir('tools-hang');
  try {
    const { checkTools, startToolCheck } = require('../tools/cli/lib/tool-check');
    const stubs = path.join(root, 'stubs');
    await writeStub(stubs, 'ast-grep', {
      posix: ['exec /bin/sleep 30'],
      windows: [String.raw`"%SystemRoot%\System32\ping.exe" -n 30 127.0.0.1 >nul`],
    });
    const options = { projectDir: path.join(root, 'project'), env: envWithPath(stubs) };
    const started = Date.now();
    const rows = await checkTools(options);
    const elapsed = Date.now() - started;
    const astGrep = byKey(rows).ast_grep;
    assert(astGrep.status === 'unknown', 'a probe that hangs reads as version unknown', JSON.stringify(astGrep));
    assert(elapsed < 6000, `the report waits about 3 s for a tool that hangs, not 30 s (${elapsed} ms)`);

    const printed = [];
    const origLog = console.log;
    console.log = (...args) => printed.push(args.join(' '));
    let thrown = null;
    try {
      await startToolCheck({ ...options, timeoutMs: 500 })();
    } catch (error) {
      thrown = error;
    } finally {
      console.log = origLog;
    }
    assert(thrown === null, 'printing the report never throws', thrown && thrown.message);
    assert(printed.join('\n').includes('ast-grep'), 'the report still prints every tool');

    if (!IS_WINDOWS) {
      // A command that ends without the report stops the probes instead. The
      // probe timeout is long here, so only stop() can end the stub in time.
      const pidFile = path.join(root, 'qmd.pid');
      await writePidStub(path.join(root, 'hang'), 'qmd', pidFile);
      const report = startToolCheck({ ...options, env: envWithPath(path.join(root, 'hang')), timeoutMs: 60_000 });
      const pid = await readPid(pidFile);
      report.stop();
      assert(pid !== null && (await processEnded(pid)), 'stop() ends a probe still running, with no report', `pid ${pid}`);
      if (pid) killStub(pid);
      assert(report.stop() === undefined, 'stop() can be called again');
    }
  } catch (error) {
    assert(false, 'hanging stub test completes without error', error.stack);
  } finally {
    await fs.remove(root);
  }

  console.log('');
}

async function testToolReportIgnoresProjectBinaries() {
  console.log(`${colors.yellow}Test Suite 10: Tool Report Never Runs a Binary in the Project${colors.reset}\n`);

  const root = await makeTempDir('tools-planted');
  try {
    const { checkTools, resolveOutsideProject } = require('../tools/cli/lib/tool-check');
    const project = path.join(root, 'project');
    const marker = path.join(root, 'planted-stub-ran');
    const planted = {
      posix: [`: > '${marker}'`, "echo 'ast-grep 9.9.9'"],
      windows: [`type nul > "${marker}"`, 'echo ast-grep 9.9.9'],
    };
    await writeStub(project, 'ast-grep', planted);
    await writeStub(path.join(project, 'node_modules', '.bin'), 'ast-grep', planted);
    const outside = path.join(root, 'outside');
    await writeStub(outside, 'ast-grep', { out: ['ast-grep 0.45.3'] });
    const dirs = [project, path.join(project, 'node_modules', '.bin'), 'bin'];
    if (!IS_WINDOWS) {
      // A PATH folder outside the project that links into it is the project's too.
      const linked = path.join(root, 'linked');
      await fs.symlink(path.join(project, 'node_modules', '.bin'), linked);
      dirs.unshift(linked);
    }
    const env = envWithPath(...dirs, outside);
    const rows = byKey(await checkTools({ projectDir: project, env, timeoutMs: 10_000 }));
    assert(rows.ast_grep.version === '0.45.3', 'the binary outside the project answers', JSON.stringify(rows.ast_grep));
    assert(!(await fs.pathExists(marker)), 'no stub in the project folder ran');
    const resolved = resolveOutsideProject('ast-grep', { env, projectDir: project });
    assert(resolved !== null && path.dirname(resolved) === outside, 'resolution skips the project and relative PATH entries', resolved);
    assert(
      resolveOutsideProject('ast-grep', { env: envWithPath(project), projectDir: project }) === null,
      'a binary only in the project is missing',
    );
  } catch (error) {
    assert(false, 'project-binary test completes without error', error.stack);
  } finally {
    await fs.remove(root);
  }

  console.log('');
}

async function testToolReportWindowsShims() {
  console.log(`${colors.yellow}Test Suite 11: .cmd Shims Run Through cmd.exe${colors.reset}\n`);

  const { commandFor } = require('../tools/cli/lib/tool-check');
  const env = { ComSpec: String.raw`C:\Windows\system32\cmd.exe` };
  const shim = commandFor(String.raw`C:\npm\ast-grep.CMD`, ['--version'], 'win32', env);
  assert(
    JSON.stringify(shim) ===
      JSON.stringify({
        file: String.raw`C:\Windows\system32\cmd.exe`,
        args: ['/d', '/s', '/c', String.raw`""C:\npm\ast-grep.CMD" --version"`],
        options: { windowsVerbatimArguments: true },
      }),
    'a .cmd shim runs through cmd.exe with a fixed command line',
    JSON.stringify(shim),
  );
  assert(commandFor(String.raw`C:\100%\ast-grep.cmd`, ['--version'], 'win32', env) === null, 'a shim path cmd.exe would expand is not run');
  assert(commandFor(String.raw`C:\npm\ast-grep.bat`, ['a b'], 'win32', env) === null, 'an argument that is not a plain word is refused');
  const exe = commandFor(String.raw`C:\bin\uv.exe`, ['--version'], 'win32', env);
  assert(exe.file === String.raw`C:\bin\uv.exe` && exe.args[0] === '--version', 'an .exe runs as it is');
  assert(commandFor('/usr/bin/ast-grep', ['--version'], 'linux').file === '/usr/bin/ast-grep', 'POSIX binaries run as they are');

  if (IS_WINDOWS) {
    // Suite 8's stubs are .cmd files on Windows: a real run through cmd.exe.
    const root = await makeTempDir('tools-cmd');
    try {
      const { checkTools } = require('../tools/cli/lib/tool-check');
      await writeStub(root, 'ast-grep', { out: ['ast-grep 0.45.3'] });
      const rows = byKey(await checkTools({ projectDir: path.join(root, 'project'), env: envWithPath(root), timeoutMs: 10_000 }));
      assert(
        rows.ast_grep.version === '0.45.3' || rows.ast_grep.status === 'unknown',
        'a .cmd stub on PATH gives its version, or version unknown',
        JSON.stringify(rows.ast_grep),
      );
    } catch (error) {
      assert(false, '.cmd stub run never throws', error.stack);
    } finally {
      await fs.remove(root);
    }
  }

  console.log('');
}

async function testCompareVersions() {
  console.log(`${colors.yellow}Test Suite 12: compareVersions Reads x.y or x.y.z${colors.reset}\n`);

  const { compareVersions, findVersion } = require('../tools/cli/lib/version-check');
  const cases = [
    ['0.45', '0.45.3', true],
    ['ast-grep 0.42.2', '0.45.3', true],
    ['0.45.3', '0.45.3', false],
    ['0.46.0', '0.45.3', false],
    ['gh version 2.101.0 (2026-09-15)', '2.15', false],
    ['2.2.0', '3.0.0-rc.1', true],
    ['3.0.0-rc.1', '3.0.0', false],
    ['v2.9.0', '2.10.0', true],
    ['no version', '1.0', false],
  ];
  for (const [current, latest, newer] of cases) {
    assert(compareVersions(current, latest) === newer, `compareVersions('${current}', '${latest}') is ${newer}`);
  }
  assert(findVersion('qmd 2.8.3 (facd35e)') === '2.8.3' && findVersion('Usage: qmd') === null, 'findVersion takes the first x.y or x.y.z');

  console.log('');
}

/**
 * Run `fn` with console output collected, PATH set to `pathDirs` and
 * process.exit refused: each call is recorded in `exits`, since the action's
 * own catch may swallow the error the refusal throws.
 */
async function captureRun(fn, pathDirs) {
  const printed = [];
  const exits = [];
  const orig = { log: console.log, error: console.error, out: process.stdout.write, err: process.stderr.write, exit: process.exit };
  const origPath = process.env.PATH;
  console.log = (...args) => printed.push(args.join(' '));
  console.error = (...args) => printed.push(args.join(' '));
  process.stdout.write = () => true;
  process.stderr.write = () => true;
  process.exit = (code) => {
    exits.push(code);
    throw new Error(`process.exit(${code}) was called`);
  };
  process.env.PATH = pathDirs.join(path.delimiter);
  let thrown = null;
  try {
    await fn();
  } catch (error) {
    thrown = error;
  } finally {
    console.log = orig.log;
    console.error = orig.error;
    process.stdout.write = orig.out;
    process.stderr.write = orig.err;
    process.exit = orig.exit;
    process.env.PATH = origPath;
  }
  return { printed: printed.join('\n').replaceAll(ANSI, ''), thrown, exits };
}

async function testInstallAndUpdateReturn() {
  console.log(`${colors.yellow}Test Suite 13: Install and Update Return, So the Update Notice Prints${colors.reset}\n`);

  const root = await makeTempDir('returns');
  const origCwd = process.cwd();
  const { UI } = require('../tools/cli/lib/ui');
  const { Installer } = require('../tools/cli/lib/installer');
  const origPrompt = UI.prototype.promptInstall;
  const origSuccess = UI.prototype.displaySuccess;
  const origInstall = Installer.prototype.install;
  try {
    const installCommand = require('../tools/cli/commands/install');
    const updateCommand = require('../tools/cli/commands/update');
    const stubs = path.join(root, 'stubs');
    await writeStub(stubs, 'ast-grep', { out: ['ast-grep 0.1.0'] });
    const project = path.join(root, 'project');
    await fs.ensureDir(project);
    process.chdir(project);
    UI.prototype.displaySuccess = () => {};
    const config = {
      projectDir: project,
      skfFolder: '_bmad/skf',
      project_name: 'returns-test',
      skills_output_folder: 'skills',
      forge_data_folder: 'forge-data',
      ides: [],
      install_learning: false,
      _action: 'fresh',
    };

    UI.prototype.promptInstall = async () => config;
    process.exitCode = undefined;
    const installed = await captureRun(() => installCommand.action(), [stubs]);
    assert(
      installed.thrown === null && installed.exits.length === 0,
      'install returns instead of calling process.exit',
      `${installed.thrown && installed.thrown.message} exits: ${installed.exits}`,
    );
    assert(process.exitCode === undefined, 'a successful install leaves the exit code alone');
    assert(/\bTools\b/.test(installed.printed) && installed.printed.includes('ast-grep'), 'install prints the tool report');

    // On POSIX a qmd stub that hangs is still running when a run ends without
    // the report. Its probe's own 3 s timeout would end it too, so the checks
    // below wait well under 3 s.
    const hang = path.join(root, 'hang');
    const pidFile = path.join(root, 'qmd.pid');
    if (!IS_WINDOWS) await writePidStub(hang, 'qmd', pidFile);
    let probePid = null;
    const probeStarted = async () => {
      if (!IS_WINDOWS) probePid = await readPid(pidFile);
    };
    const probeStopped = async () => probePid !== null && (await processEnded(probePid, 1500));

    UI.prototype.promptInstall = async () => {
      await probeStarted();
      return { cancelled: true };
    };
    const cancelled = await captureRun(() => installCommand.action(), [stubs, hang]);
    assert(
      cancelled.thrown === null && cancelled.exits.length === 0 && process.exitCode === undefined,
      'a cancelled install returns with exit code 0',
    );
    assert(!/\bTools\b/.test(cancelled.printed), 'a cancelled install prints no tool report');
    if (!IS_WINDOWS) {
      assert(await probeStopped(), 'a cancelled install stops the probes still running', `pid ${probePid}`);
      if (probePid) killStub(probePid);
    }

    const updated = await captureRun(() => updateCommand.action(), [stubs]);
    assert(
      updated.thrown === null && updated.exits.length === 0,
      'update returns instead of calling process.exit',
      `${updated.thrown && updated.thrown.message} exits: ${updated.exits}`,
    );
    assert(process.exitCode === undefined, 'a successful update leaves the exit code alone');
    assert(updated.printed.includes('ast-grep'), 'update prints the tool report');

    await fs.remove(pidFile);
    probePid = null;
    Installer.prototype.install = async () => {
      await probeStarted();
      throw new Error('disk full');
    };
    const failed = await captureRun(() => updateCommand.action(), [stubs, hang]);
    assert(
      failed.thrown === null && failed.exits.length === 0 && process.exitCode === 1,
      'a failed update returns with exit code 1',
      failed.printed,
    );
    assert(!/\bTools\b/.test(failed.printed), 'a failed update prints no tool report');
    if (!IS_WINDOWS) {
      assert(await probeStopped(), 'a failed update stops the probes still running', `pid ${probePid}`);
      if (probePid) killStub(probePid);
    }
    process.exitCode = undefined;
  } catch (error) {
    assert(false, 'install and update return without error', error.stack);
  } finally {
    UI.prototype.promptInstall = origPrompt;
    UI.prototype.displaySuccess = origSuccess;
    Installer.prototype.install = origInstall;
    process.exitCode = undefined;
    process.chdir(origCwd);
    await fs.remove(root);
  }

  console.log('');
}

async function testCliPrintsReportAndNotice() {
  console.log(`${colors.yellow}Test Suite 14: The CLI Prints the Tool Report, Then the Update Notice${colors.reset}\n`);

  const root = await makeTempDir('cli-notice');
  try {
    const stubs = path.join(root, 'stubs');
    await writeStub(stubs, 'ast-grep', { out: ['ast-grep 0.1.0'] });
    // The registry check, answered here with a newer version: no network.
    const preload = path.join(root, 'fake-registry.js');
    await writeCliPreload(preload, '999.0.0');
    const project = path.join(root, 'project');
    await fs.ensureDir(project);
    const { Installer } = require('../tools/cli/lib/installer');
    const restore = suppressConsole();
    await new Installer().install({
      projectDir: project,
      skfFolder: '_bmad/skf',
      project_name: 'notice-test',
      skills_output_folder: 'skills',
      forge_data_folder: 'forge-data',
      ides: [],
      install_learning: false,
      _action: 'fresh',
    });
    restore();

    const cli = path.join(__dirname, '..', 'tools', 'cli', 'skf-cli.js');
    for (const command of ['update', 'status']) {
      const run = spawnSync(process.execPath, ['--require', preload, cli, command], {
        cwd: project,
        env: envWithPath(stubs),
        encoding: 'utf8',
        timeout: 120_000,
      });
      const stdout = (run.stdout || '').replaceAll(ANSI, '');
      const stderr = (run.stderr || '').replaceAll(ANSI, '');
      assert(run.status === 0, `${command} exits 0`, `${run.status} ${run.error || ''} ${stderr}`);
      assert(/\n {2}Tools\n/.test(stdout) && /ast-grep +0\.1\.0 +upgrade to >= /.test(stdout), `${command} prints the tool report`, stdout);
      assert(stderr.includes('Update available') && stderr.includes('999.0.0'), `the update notice prints after ${command}`, stderr);
    }
  } catch (error) {
    assert(false, 'CLI report and notice test completes without error', error.stack);
  } finally {
    await fs.remove(root);
  }

  console.log('');
}

async function testCliStopsProbesWithoutReport() {
  console.log(`${colors.yellow}Test Suite 15: A CLI Run That Prints No Tool Report Leaves No Probe Running${colors.reset}\n`);

  if (IS_WINDOWS) {
    // libuv's kill-on-close job object ends every child with the CLI on Windows.
    console.log(`${colors.dim}  skipped on Windows${colors.reset}\n`);
    return;
  }
  const root = await makeTempDir('cli-no-report');
  const left = [];
  try {
    const stubs = path.join(root, 'stubs');
    await writeStub(stubs, 'qmd', { posix: ['exec /bin/sleep 30'] });
    const qmd = path.join(stubs, 'qmd');
    const preload = path.join(root, 'cli-preload.js');
    await writeCliPreload(preload, '0.0.1');
    // update in a folder without SKF, and status where _bmad/skf is a file, which it cannot read.
    const bare = path.join(root, 'bare');
    const broken = path.join(root, 'broken');
    await fs.ensureDir(bare);
    await fs.outputFile(path.join(broken, '_bmad', 'skf'), 'not a folder\n');

    const cli = path.join(__dirname, '..', 'tools', 'cli', 'skf-cli.js');
    for (const [command, cwd, status] of [
      ['update', bare, 0],
      ['status', broken, 1],
    ]) {
      const log = path.join(root, `${command}-spawned.log`);
      const run = spawnSync(process.execPath, ['--require', preload, cli, command], {
        cwd,
        env: { ...envWithPath(stubs), SKF_TEST_SPAWN_LOG: log },
        encoding: 'utf8',
        timeout: 60_000,
      });
      assert(run.status === status, `${command} exits ${status}`, `${run.status} ${run.error || ''} ${run.stderr}`);
      const spawned = (await fs.readFile(log, 'utf8').catch(() => '')).split('\n');
      const pid = Number(spawned.find((line) => line.endsWith(` ${qmd}`))?.split(' ')[0]) || null;
      if (pid) left.push(pid);
      assert(pid !== null, `${command} starts the qmd probe`, spawned.join('\n'));
      assert(
        pid !== null && (await processEnded(pid)),
        `${command} stops the probe still running when it ends without the report`,
        `pid ${pid}`,
      );
    }
  } catch (error) {
    assert(false, 'CLI probe stop test completes without error', error.stack);
  } finally {
    for (const pid of left) killStub(pid);
    await fs.remove(root);
  }

  console.log('');
}

async function testSkillCheckVersionFromPackage() {
  console.log(`${colors.yellow}Test Suite 16: skill-check's Version Comes From Its package.json, Never From a Run${colors.reset}\n`);

  const root = await makeTempDir('tools-skill-check');
  try {
    const { checkTools } = require('../tools/cli/lib/tool-check');
    const marker = path.join(root, 'skill-check-ran');
    const project = path.join(root, 'project');
    await fs.ensureDir(project);
    const rowFor = async (dir) => byKey(await checkTools({ projectDir: project, env: envWithPath(dir), timeoutMs: 10_000 })).skill_check;
    const cases = [
      { label: 'the package next to the shim (npm on Windows)', layout: 'shim', expected: '1.3.4' },
      { label: 'another package named in the package.json', name: 'skill-checker', expected: null },
      { label: 'no package.json', name: null, expected: null },
    ];
    // The link layout needs a symlink, which Windows runners may not allow.
    if (!IS_WINDOWS) {
      cases.unshift(
        { label: 'the package the linked binary is in (npm, yarn and bun)', layout: 'link', expected: '1.3.4' },
        { label: 'a package.json with no name next to the binary is skipped', layout: 'link', nameless: true, expected: '1.3.4' },
        { label: 'a skill-check package that does not declare this binary', layout: 'link', bin: 'bin/other.js', expected: null },
      );
    }
    for (const [index, { label, layout, name, bin, nameless, expected }] of cases.entries()) {
      const dir = path.join(root, `case-${index}`, 'bin');
      await writeSkillCheck(dir, { marker, layout, name, bin, nameless, version: '1.3.4', install: `install-${index}` });
      const row = await rowFor(dir);
      const ok = expected
        ? row.version === expected && row.status === 'ok'
        : row.version === null && row.label === 'installed, version unknown';
      assert(ok, `${label}: ${expected ?? 'version unknown'}`, JSON.stringify(row));
    }
    const missing = await rowFor(path.join(root, 'empty'));
    assert(
      missing.status === 'optional' && missing.label === 'optional, runs through npx',
      'no skill-check on PATH reads as optional',
      JSON.stringify(missing),
    );
    assert(!(await fs.pathExists(marker)), 'skill-check never runs');
  } catch (error) {
    assert(false, 'skill-check version test completes without error', error.stack);
  } finally {
    await fs.remove(root);
  }

  console.log('');
}

async function testTesslVersionFromItsBinary() {
  console.log(`${colors.yellow}Test Suite 17: tessl's Version Comes From the Binary It Installed, Never From a Run${colors.reset}\n`);

  const root = await makeTempDir('tools-tessl');
  try {
    const { checkTools } = require('../tools/cli/lib/tool-check');
    const marker = path.join(root, 'tessl-ran');
    const project = path.join(root, 'project');
    await fs.ensureDir(project);
    const exe = IS_WINDOWS ? 'tessl.exe' : 'tessl';
    const runs = { posix: [`echo ran > '${marker}'`, 'exit 3'], windows: [`echo ran> "${marker}"`, 'exit /b 3'] };
    // A tessl binary that writes `ran` to the marker if it is ever run; `pad` changes its size.
    const binary = async (file, pad = '') => {
      await fs.ensureDir(path.dirname(file));
      await fs.writeFile(file, ['#!/bin/sh', ...runs.posix, `# ${pad}`, ''].join('\n'));
      await fs.chmod(file, 0o755);
    };
    // tessl `version` installed in `home` the way tessl installs it: a symlink
    // .local/bin/tessl to .local/share/tessl/versions/tessl-<version>-linux-x64,
    // or on Windows a copy tessl\bin\tessl.exe of tessl\versions\tessl-<version>-win32-x64.exe.
    // Returns the folder that holds the PATH entry.
    const native = async (home, version) => {
      if (IS_WINDOWS) {
        const source = path.join(home, 'tessl', 'versions', `tessl-${version}-win32-x64.exe`);
        await binary(source);
        await fs.ensureDir(path.join(home, 'tessl', 'bin'));
        await fs.copyFile(source, path.join(home, 'tessl', 'bin', 'tessl.exe'));
        return path.join(home, 'tessl', 'bin');
      }
      const source = path.join(home, '.local', 'share', 'tessl', 'versions', `tessl-${version}-linux-x64`);
      await binary(source);
      await fs.ensureDir(path.join(home, '.local', 'bin'));
      await fs.symlink(source, path.join(home, '.local', 'bin', 'tessl'));
      return path.join(home, '.local', 'bin');
    };
    // The npm or Homebrew launcher package `name` at `version` in `dir`: its
    // binary next to node_modules/<name>/ (npm's layout on Windows), or, with
    // `link`, a symlink into <package>/bin/tessl.js (npm and Homebrew on Linux and macOS).
    const launcher = async (dir, { name = '@tessl/cli', version = '0.119.0', link = false } = {}) => {
      const manifest = JSON.stringify({ name, version, bin: { tessl: 'bin/tessl.js' } });
      if (!link) {
        await writeStub(dir, 'tessl', runs);
        await fs.ensureDir(path.join(dir, 'node_modules', name));
        await fs.writeFile(path.join(dir, 'node_modules', name, 'package.json'), manifest);
        return dir;
      }
      const pkg = path.join(dir, 'lib', 'node_modules', name);
      await writeStub(path.join(pkg, 'bin'), 'tessl.js', runs);
      await fs.writeFile(path.join(pkg, 'package.json'), manifest);
      await fs.ensureDir(path.join(dir, 'bin'));
      await fs.symlink(path.join(pkg, 'bin', 'tessl.js'), path.join(dir, 'bin', 'tessl'));
      return path.join(dir, 'bin');
    };
    // A <folder>\bin copy and the <folder>\versions folder it was copied from (tessl's layout on Windows).
    const copied = async (dir, sizes, folder = 'tessl') => {
      const base = path.join(dir, folder);
      for (const [version, pad] of Object.entries(sizes)) await binary(path.join(base, 'versions', `tessl-${version}-win32-x64.exe`), pad);
      await fs.ensureDir(path.join(base, 'bin'));
      await fs.copyFile(path.join(base, 'versions', 'tessl-0.119.0-win32-x64.exe'), path.join(base, 'bin', exe));
      return path.join(base, 'bin');
    };
    const cases = [
      {
        label: String.raw`a tessl\bin copy takes the version of the versions file of its size (Windows)`,
        expected: '0.119.0',
        setup: (dir) => copied(dir, { '0.119.0': '', '0.111.0': 'longer' }),
      },
      {
        label: 'a copy that two versions files match in size',
        expected: null,
        setup: (dir) => copied(dir, { '0.119.0': '', '0.111.0': '' }),
      },
      {
        label: 'a copy in a bin folder that is not in a tessl folder',
        expected: null,
        setup: (dir) => copied(dir, { '0.119.0': '' }, 'tools'),
      },
      {
        label: 'the npm launcher: the version of the binary it runs, not its own',
        expected: '0.111.0',
        setup: async (dir, home) => {
          await native(home, '0.111.0');
          return launcher(path.join(dir, 'npm'));
        },
      },
      { label: 'a launcher that has not installed its binary yet', expected: null, setup: (dir) => launcher(path.join(dir, 'npm')) },
      {
        label: '@tessl/cli before 0.63.0 is the CLI itself',
        expected: '0.62.2',
        setup: async (dir, home) => {
          await native(home, '0.111.0');
          return launcher(path.join(dir, 'npm'), { version: '0.62.2' });
        },
      },
      {
        label: 'a tessl in a folder tessl did not install (winget)',
        expected: null,
        setup: async (dir) => {
          await binary(path.join(dir, 'Programs', 'Tessl', exe));
          return path.join(dir, 'Programs', 'Tessl');
        },
      },
    ];
    // The symlink layouts need symlinks, which Windows runners may not allow.
    if (!IS_WINDOWS) {
      cases.unshift(
        {
          label: "the binary tessl's installer links (Linux and macOS)",
          expected: '0.119.0',
          setup: (dir, home) => native(home, '0.119.0'),
        },
        {
          label: 'a dangling link in the versions folder does not hide the copied file',
          expected: '0.119.0',
          setup: async (dir) => {
            const bin = await copied(dir, { '0.119.0': '' });
            await fs.symlink(path.join(dir, 'gone'), path.join(dir, 'tessl', 'versions', 'tessl-0.118.0-win32-x64.exe'));
            return bin;
          },
        },
        {
          label: 'the npm launcher linked from its package',
          expected: '0.111.0',
          setup: async (dir, home) => {
            await native(home, '0.111.0');
            return launcher(path.join(dir, 'npm'), { link: true });
          },
        },
        {
          label: 'the Homebrew launcher',
          expected: '0.111.0',
          setup: async (dir, home) => {
            await native(home, '0.111.0');
            return launcher(path.join(dir, 'Cellar', 'tessl', '0.119.0', 'libexec'), { name: 'tessl', link: true });
          },
        },
      );
    }
    for (const [index, { label, expected, setup }] of cases.entries()) {
      const dir = path.join(root, `case-${index}`);
      const home = path.join(dir, 'home');
      const bin = await setup(dir, home);
      // The launchers run the binary in the user's home: HOME, or LOCALAPPDATA on Windows.
      const env = Object.fromEntries(
        Object.entries(envWithPath(bin)).filter(([key]) => !['HOME', 'LOCALAPPDATA', 'USERPROFILE'].includes(key.toUpperCase())),
      );
      Object.assign(env, { HOME: home, LOCALAPPDATA: home, USERPROFILE: home });
      const row = byKey(await checkTools({ projectDir: project, env, timeoutMs: 10_000 })).tessl;
      const ok = expected
        ? row.version === expected && row.status === 'ok'
        : row.version === null && row.label === 'installed, version unknown';
      assert(ok, `${label}: ${expected ?? 'version unknown'}`, JSON.stringify(row));
    }
    assert(!(await fs.pathExists(marker)), 'tessl never runs');
  } catch (error) {
    assert(false, 'tessl version test completes without error', error.stack);
  } finally {
    await fs.remove(root);
  }

  console.log('');
}

// ============================================================
// Folder values that start with {project-root}
// ============================================================

// The text of the .gitkeep every installer version wrote in an output folder it created.
const INSTALLER_GITKEEP = '# This file ensures the directory is tracked by git\n';

/**
 * Write _bmad/skf/config.yaml with `values`, each written with JSON.stringify
 * so a backslash survives YAML. Returns the text written.
 */
async function writeSavedConfig(projectDir, values) {
  const lines = ['user_name: Tester', 'project_name: placeholder-test'];
  for (const [key, value] of Object.entries(values)) lines.push(`${key}: ${JSON.stringify(value)}`);
  const text = `${lines.join('\n')}\n`;
  const configPath = path.join(projectDir, '_bmad', 'skf', 'config.yaml');
  await fs.ensureDir(path.dirname(configPath));
  await fs.writeFile(configPath, text, 'utf8');
  return text;
}

/**
 * Run the installer with its output suppressed.
 */
async function runInstall(config) {
  const { Installer } = require('../tools/cli/lib/installer');
  const restore = suppressConsole();
  try {
    return await new Installer().install(config);
  } finally {
    restore();
  }
}

/**
 * Run `run` in a new temp project, removed after it.
 */
async function inProject(label, description, run) {
  const projectDir = await makeTempDir(label);
  try {
    await run(projectDir);
  } catch (error) {
    assert(false, `${description} completes without error`, error.stack);
  } finally {
    await fs.remove(projectDir);
  }
}

/**
 * The names in the project folder that start with {project-root}.
 */
async function literalEntries(projectDir) {
  return (await fs.readdir(projectDir)).filter((name) => name.startsWith('{project-root}'));
}

async function testProjectRootFolderValues() {
  console.log(`${colors.yellow}Test Suite 18: Folder Values That Start With {project-root}${colors.reset}\n`);

  const { readManifest } = require('../tools/cli/lib/manifest');
  // The values a BMAD Method install writes, one with a backslash.
  const bmadMethodValues = {
    skills_output_folder: '{project-root}/skf-skills',
    forge_data_folder: String.raw`{project-root}\forge-data`,
    ides: [],
    install_learning: false,
  };
  // Update a BMAD Method install: a real skf-skills/ holding a skill, no forge-data/.
  const updateBmadMethodProject = async (projectDir) => {
    const saved = await writeSavedConfig(projectDir, bmadMethodValues);
    await fs.ensureDir(path.join(projectDir, 'skf-skills', 'demo'));
    await fs.writeFile(path.join(projectDir, 'skf-skills', 'demo', 'SKILL.md'), '# demo\n');
    await runInstall({ projectDir, skfFolder: '_bmad/skf', _action: 'update' });
    return saved;
  };

  await inProject('root-update', 'update with {project-root} values', async (projectDir) => {
    const saved = await updateBmadMethodProject(projectDir);
    const literal = await literalEntries(projectDir);
    assert(literal.length === 0, 'update: no folder named {project-root} in the project', literal.join(', '));
    const skills = await fs.readdir(path.join(projectDir, 'skf-skills'));
    assert(JSON.stringify(skills) === '["demo"]', 'update: the real skf-skills/ is left as it is, with no .gitkeep', skills.join(', '));
    assert(
      await fs.pathExists(path.join(projectDir, 'forge-data', '.gitkeep')),
      'update: the missing forge-data/ is created with a .gitkeep',
    );
    const configText = await fs.readFile(path.join(projectDir, '_bmad', 'skf', 'config.yaml'), 'utf8');
    assert(configText.startsWith(saved), 'update: config.yaml keeps the saved values');
    const manifest = await readManifest(projectDir);
    const output = JSON.stringify(manifest.files.output);
    assert(output === JSON.stringify([path.join('forge-data', '.gitkeep')]), 'update: the manifest lists forge-data/.gitkeep only', output);
    assert(
      manifest.skills_output_folder === bmadMethodValues.skills_output_folder &&
        manifest.forge_data_folder === bmadMethodValues.forge_data_folder,
      'update: the manifest keeps the raw folder values',
    );
  });

  await inProject('root-absolute', 'an install with an absolute skills folder', async (projectDir) => {
    const elsewhere = await makeTempDir('root-elsewhere');
    try {
      const skills = path.join(elsewhere, 'skills');
      await runInstall({
        projectDir,
        skfFolder: '_bmad/skf',
        project_name: 'absolute-test',
        skills_output_folder: skills,
        forge_data_folder: 'forge-data',
        ides: [],
        install_learning: false,
        _action: 'fresh',
      });
      const gitkeep = path.join(skills, '.gitkeep');
      assert(await fs.pathExists(gitkeep), 'absolute value: the .gitkeep is created at that path');
      // The first segment of the absolute path: `tmp` on Linux, the drive letter on Windows.
      const first = skills.split(/[/\\]/).find(Boolean).replace(':', '');
      assert(!(await fs.pathExists(path.join(projectDir, first))), `absolute value: nothing is nested under the project (${first}/)`);
      const manifest = await readManifest(projectDir);
      assert(
        manifest.files.output.includes(path.relative(projectDir, gitkeep)),
        'absolute value: the manifest lists that .gitkeep relative to the project',
        JSON.stringify(manifest.files.output),
      );
    } finally {
      await fs.remove(elsewhere);
    }
  });

  await inProject('root-fresh', 'a fresh install with {project-root} answers', async (projectDir) => {
    await runInstall({
      projectDir,
      skfFolder: '_bmad/skf',
      project_name: 'fresh-placeholder',
      skills_output_folder: '{project-root}/my-skills',
      forge_data_folder: '{project-root}/my-forge',
      ides: [],
      install_learning: false,
      _action: 'fresh',
    });
    assert(
      (await fs.pathExists(path.join(projectDir, 'my-skills', '.gitkeep'))) &&
        (await fs.pathExists(path.join(projectDir, 'my-forge', '.gitkeep'))),
      'fresh install: my-skills/ and my-forge/ are created at the project root',
    );
    const literal = await literalEntries(projectDir);
    assert(literal.length === 0, 'fresh install: no folder named {project-root} in the project', literal.join(', '));
    const manifest = await readManifest(projectDir);
    const listed = Object.values(manifest.files).flat();
    const missing = [];
    for (const file of listed) {
      if (!(await fs.pathExists(path.resolve(projectDir, file)))) missing.push(file);
    }
    assert(listed.length > 0 && missing.length === 0, 'fresh install: every file the manifest lists exists', missing.join(', '));
  });

  await inProject('root-alone', 'an install with a {project-root} value alone', async (projectDir) => {
    // A .gitkeep of the user's own in the project folder.
    await fs.writeFile(path.join(projectDir, '.gitkeep'), 'mine\n');
    await runInstall({
      projectDir,
      skfFolder: '_bmad/skf',
      project_name: 'root-alone',
      skills_output_folder: '{project-root}',
      forge_data_folder: 'forge-data',
      ides: [],
      install_learning: false,
      _action: 'fresh',
    });
    const literal = await literalEntries(projectDir);
    assert(literal.length === 0, '{project-root} alone: nothing is created for it', literal.join(', '));
    assert(
      (await fs.readFile(path.join(projectDir, '.gitkeep'), 'utf8')) === 'mine\n',
      "{project-root} alone: the project folder's own .gitkeep is untouched",
    );
    const output = JSON.stringify((await readManifest(projectDir)).files.output);
    assert(
      output === JSON.stringify([path.join('forge-data', '.gitkeep')]),
      "{project-root} alone: the manifest does not list the project folder's .gitkeep",
      output,
    );
  });

  try {
    const { resolveProjectFolder } = require('../tools/cli/lib/project-folders');
    const root = path.resolve(os.tmpdir(), 'skf-root');
    const elsewhere = path.resolve(os.tmpdir(), 'skf-elsewhere', 'skills');
    const forms = [
      ['{project-root}/skills', '{project-root}/skills', path.resolve(root, 'skills')],
      [String.raw`{project-root}\skills`, String.raw`{project-root}\skills`, path.resolve(root, 'skills')],
      ['{project-root}//skills/', '{project-root}//skills/', path.resolve(root, 'skills')],
      ['./skills', './skills', path.resolve(root, 'skills')],
      ['skills', 'skills', path.join(root, 'skills')],
      ['{project-root} alone', '{project-root}', root],
      ['an absolute path', elsewhere, elsewhere],
      // With no separator after it, {project-root} is a folder name, as preflight reads it.
      ['{project-root}_bmad/x', '{project-root}_bmad/x', path.join(root, '{project-root}_bmad', 'x')],
    ];
    for (const [label, value, expected] of forms) {
      const resolved = resolveProjectFolder(root, value);
      assert(resolved === expected, `resolveProjectFolder: ${label}`, `got ${resolved}, expected ${expected}`);
    }
  } catch (error) {
    assert(false, 'resolveProjectFolder resolves every form', error.stack);
  }

  await inProject('root-status', 'status with {project-root} values', async (projectDir) => {
    const { getStatus } = require('../tools/cli/commands/status');
    await writeSavedConfig(projectDir, {
      skills_output_folder: '{project-root}/skf-skills',
      forge_data_folder: '{project-root}/forge-data',
    });
    await fs.ensureDir(path.join(projectDir, 'skf-skills'));
    await fs.ensureDir(path.join(projectDir, 'forge-data'));
    const status = await getStatus(projectDir);
    assert(status.skillsFolderExists === true && status.forgeDataFolderExists === true, 'status: both real folders are marked present');
    assert(
      status.skillsFolder === '{project-root}/skf-skills' && status.forgeDataFolder === '{project-root}/forge-data',
      'status: the folder labels keep the raw values',
    );
  });

  await inProject('root-uninstall', 'uninstall after an update with {project-root} values', async (projectDir) => {
    const { removeOutputScaffolding } = require('../tools/cli/commands/uninstall');
    await updateBmadMethodProject(projectDir);
    const result = await removeOutputScaffolding(projectDir, await readManifest(projectDir));
    assert(!(await fs.pathExists(path.join(projectDir, 'forge-data'))), 'uninstall: the forge-data/ the installer created goes');
    assert(await fs.pathExists(path.join(projectDir, 'skf-skills', 'demo', 'SKILL.md')), 'uninstall: skf-skills/ holding a skill stays');
    assert(
      JSON.stringify(result) === JSON.stringify({ removed: [path.join(projectDir, 'forge-data', '.gitkeep')], kept: [] }),
      "uninstall: the installer's .gitkeep is listed as removed, and nothing as kept",
      JSON.stringify(result),
    );
  });

  await inProject('root-uninstall-empty', 'uninstall with an empty real output folder', async (projectDir) => {
    const { removeOutputScaffolding } = require('../tools/cli/commands/uninstall');
    await updateBmadMethodProject(projectDir);
    // The skill is gone, so skf-skills/ is empty, and the manifest lists no file in it.
    await fs.remove(path.join(projectDir, 'skf-skills', 'demo'));
    await removeOutputScaffolding(projectDir, await readManifest(projectDir));
    assert(
      !(await fs.pathExists(path.join(projectDir, 'skf-skills'))),
      'uninstall: a real output folder left empty goes, though the manifest lists no file in it',
    );
  });

  await inProject('root-uninstall-earlier', 'uninstall with an earlier manifest', async (projectDir) => {
    const { removeOutputScaffolding } = require('../tools/cli/commands/uninstall');
    // An earlier version joined the value to the project folder as it stood.
    const listed = path.join('{project-root}', 'skf-skills', '.gitkeep');
    await fs.ensureDir(path.join(projectDir, '{project-root}', 'skf-skills'));
    await fs.writeFile(path.join(projectDir, listed), INSTALLER_GITKEEP);
    await removeOutputScaffolding(projectDir, {
      skills_output_folder: '{project-root}/skf-skills',
      forge_data_folder: '{project-root}/forge-data',
      files: { output: [listed] },
    });
    assert(
      !(await fs.pathExists(path.join(projectDir, '{project-root}', 'skf-skills'))),
      "uninstall: an earlier manifest's literal {project-root}/skf-skills/ goes",
    );
  });

  await inProject('root-uninstall-alone', 'uninstall with a {project-root} value alone', async (projectDir) => {
    const { removeOutputScaffolding } = require('../tools/cli/commands/uninstall');
    await removeOutputScaffolding(projectDir, {
      skills_output_folder: '{project-root}',
      forge_data_folder: 'forge-data',
      files: { output: [] },
    });
    assert(await fs.pathExists(projectDir), 'uninstall: a {project-root} value alone never removes the project folder');
  });

  await inProject('root-user-gitkeep', "an update over a real folder holding the user's own .gitkeep", async (projectDir) => {
    const { removeOutputScaffolding } = require('../tools/cli/commands/uninstall');
    await writeSavedConfig(projectDir, bmadMethodValues);
    const own = path.join(projectDir, 'skf-skills', '.gitkeep');
    await fs.ensureDir(path.dirname(own));
    await fs.writeFile(own, 'mine\n');
    await runInstall({ projectDir, skfFolder: '_bmad/skf', _action: 'update' });
    const manifest = await readManifest(projectDir);
    const output = JSON.stringify(manifest.files.output);
    assert(
      output === JSON.stringify([path.join('forge-data', '.gitkeep')]),
      'update: the manifest does not list a .gitkeep the installer did not write',
      output,
    );
    await removeOutputScaffolding(projectDir, manifest);
    assert(
      (await fs.pathExists(own)) && (await fs.readFile(own, 'utf8')) === 'mine\n',
      "uninstall: the user's own .gitkeep in a real output folder stays",
    );
  });

  await inProject('root-uninstall-absolute', 'uninstall with an absolute output entry', async (projectDir) => {
    const { removeOutputScaffolding } = require('../tools/cli/commands/uninstall');
    // The manifest entry for a folder on another Windows drive is absolute: path.relative returns it whole.
    const elsewhere = await makeTempDir('root-uninstall-elsewhere');
    try {
      const skills = path.join(elsewhere, 'skills');
      await fs.ensureDir(skills);
      await fs.writeFile(path.join(skills, '.gitkeep'), INSTALLER_GITKEEP);
      const result = await removeOutputScaffolding(projectDir, {
        skills_output_folder: skills,
        forge_data_folder: 'forge-data',
        files: { output: [path.join(skills, '.gitkeep')] },
      });
      assert(!(await fs.pathExists(skills)), 'uninstall: an absolute output entry is removed where it points, with its emptied folder');
      assert(
        JSON.stringify(result.removed) === JSON.stringify([path.join(skills, '.gitkeep')]) && result.kept.length === 0,
        'uninstall: the absolute output entry is listed as removed, and nothing as kept',
        JSON.stringify(result),
      );
    } finally {
      await fs.remove(elsewhere);
    }
  });

  // Not through inProject: `..` from its project is the system temp folder. Here the
  // project is home/project, so every entry points inside the home this test creates.
  const refusedHome = await makeTempDir('root-uninstall-refused');
  try {
    const { removeOutputScaffolding } = require('../tools/cli/commands/uninstall');
    const projectDir = path.join(refusedHome, 'project');
    const victim = path.join(refusedHome, 'victim');
    const absFolder = path.join(refusedHome, 'abs-folder');
    const otherGitkeep = path.join(refusedHome, 'other', '.gitkeep');
    const notes = path.join(projectDir, 'notes.txt');
    const missingFolder = path.join(projectDir, 'missing');
    const target = path.join(refusedHome, 'target.txt');
    const link = path.join(projectDir, 'skills', '.gitkeep');
    await fs.ensureDir(path.join(victim, 'inner'));
    await fs.writeFile(path.join(victim, 'inner', 'data.txt'), 'victim\n');
    await fs.ensureDir(absFolder);
    await fs.writeFile(path.join(absFolder, 'data.txt'), 'absolute\n');
    await fs.ensureDir(path.dirname(otherGitkeep));
    await fs.writeFile(otherGitkeep, 'mine\n');
    await fs.ensureDir(projectDir);
    await fs.writeFile(notes, INSTALLER_GITKEEP);
    // The folder of the missing entry exists and is empty.
    await fs.ensureDir(missingFolder);
    // `notes` names notes.txt a second time, as an absolute path: it is listed once.
    const entries = [path.join('..', 'victim'), absFolder, otherGitkeep, 'notes.txt', path.join('missing', '.gitkeep'), notes];
    const expectedKept = [victim, absFolder, otherGitkeep, notes];
    if (!IS_WINDOWS) {
      await fs.writeFile(target, INSTALLER_GITKEEP);
      await fs.ensureDir(path.dirname(link));
      await fs.symlink(target, link);
      entries.push(path.join('skills', '.gitkeep'));
      expectedKept.push(link);
      // Under a regular file, so lstat fails with ENOTDIR, not ENOENT: kept and named.
      entries.push(path.join('notes.txt', '.gitkeep'));
      expectedKept.push(path.join(notes, '.gitkeep'));
    }
    const result = await removeOutputScaffolding(projectDir, { files: { output: entries } });
    assert(
      (await fs.readFile(path.join(victim, 'inner', 'data.txt'), 'utf8')) === 'victim\n',
      'uninstall: a folder entry outside the project stays with its contents',
    );
    assert(
      (await fs.readFile(path.join(absFolder, 'data.txt'), 'utf8')) === 'absolute\n',
      'uninstall: an absolute folder entry stays with its contents',
    );
    assert((await fs.readFile(otherGitkeep, 'utf8')) === 'mine\n', "uninstall: a .gitkeep holding other text than the installer's stays");
    assert(
      (await fs.readFile(notes, 'utf8')) === INSTALLER_GITKEEP,
      "uninstall: a file holding the installer's text under another name than .gitkeep stays",
    );
    assert(await fs.pathExists(missingFolder), "uninstall: a missing entry's folder is not cleaned through it");
    if (!IS_WINDOWS) {
      assert(
        (await fs.lstat(link)).isSymbolicLink() && (await fs.readFile(target, 'utf8')) === INSTALLER_GITKEEP,
        'uninstall: a .gitkeep symlink stays a link, and its target stays',
      );
    }
    assert(result.removed.length === 0, 'uninstall: no entry the installer did not write is listed as removed', JSON.stringify(result));
    assert(
      JSON.stringify(result.kept) === JSON.stringify(expectedKept),
      'uninstall: each entry it keeps is listed as kept, by its resolved path, and the missing one is in neither list',
      JSON.stringify(result.kept),
    );
  } catch (error) {
    assert(false, 'uninstall with output entries the installer did not write completes without error', error.stack);
  } finally {
    await fs.remove(refusedHome);
  }

  await inProject('root-uninstall-not-list', 'uninstall with an output value that is not a list', async (projectDir) => {
    const { removeOutputScaffolding } = require('../tools/cli/commands/uninstall');
    // Letters only: code that iterates the string resolves each character against the
    // project, and `.`, `/` or `\` would name the project, the filesystem root or a drive root.
    for (const name of ['a', 'b']) {
      await fs.ensureDir(path.join(projectDir, name));
      await fs.writeFile(path.join(projectDir, name, 'data.txt'), 'mine\n');
    }
    const result = await removeOutputScaffolding(projectDir, { files: { output: 'ab' } });
    assert(
      (await fs.pathExists(path.join(projectDir, 'a', 'data.txt'))) && (await fs.pathExists(path.join(projectDir, 'b', 'data.txt'))),
      'uninstall: an output value that is not a list removes nothing',
    );
    assert(
      result.removed.length === 0 && result.kept.length === 0,
      'uninstall: an output value that is not a list reads as no entries',
      JSON.stringify(result),
    );
  });

  console.log('');
}

async function testLeftoverProjectRootFolder() {
  console.log(`${colors.yellow}Test Suite 19: The {project-root} Folder an Earlier Version Left${colors.reset}\n`);

  const values = {
    skills_output_folder: '{project-root}/skf-skills',
    forge_data_folder: '{project-root}/forge-data',
    ides: [],
    install_learning: false,
  };
  const literal = (projectDir, ...parts) => path.join(projectDir, '{project-root}', ...parts);
  // What an update with these values left before this fix.
  const writeLeftover = async (projectDir, text = INSTALLER_GITKEEP) => {
    for (const folder of ['skf-skills', 'forge-data']) {
      await fs.ensureDir(literal(projectDir, folder));
      await fs.writeFile(literal(projectDir, folder, '.gitkeep'), text);
    }
  };
  const realFoldersCreated = async (projectDir) =>
    (await fs.pathExists(path.join(projectDir, 'skf-skills', '.gitkeep'))) &&
    (await fs.pathExists(path.join(projectDir, 'forge-data', '.gitkeep')));

  await inProject('leftover-update', 'an update over the leftover', async (projectDir) => {
    await writeSavedConfig(projectDir, values);
    await writeLeftover(projectDir);
    await runInstall({ projectDir, skfFolder: '_bmad/skf', _action: 'update' });
    assert(!(await fs.pathExists(literal(projectDir))), "update: a {project-root}/ holding only the installer's .gitkeep files goes");
    assert(await realFoldersCreated(projectDir), 'update: the real skf-skills/ and forge-data/ are created');
  });

  await inProject('leftover-fresh', 'a fresh install over the leftover', async (projectDir) => {
    await writeLeftover(projectDir);
    await runInstall({ projectDir, skfFolder: '_bmad/skf', project_name: 'leftover-fresh', ...values, _action: 'fresh' });
    assert(
      !(await fs.pathExists(literal(projectDir))),
      "fresh install: a {project-root}/ holding only the installer's .gitkeep files goes",
    );
    assert(await realFoldersCreated(projectDir), 'fresh install: the real skf-skills/ and forge-data/ are created');
  });

  await inProject('leftover-user-file', 'an update over a leftover holding a user file', async (projectDir) => {
    await writeSavedConfig(projectDir, values);
    await writeLeftover(projectDir);
    const notes = literal(projectDir, 'forge-data', 'notes.md');
    await fs.writeFile(notes, 'mine\n');
    await runInstall({ projectDir, skfFolder: '_bmad/skf', _action: 'update' });
    assert(
      (await fs.pathExists(notes)) && (await fs.readFile(literal(projectDir, 'forge-data', '.gitkeep'), 'utf8')) === INSTALLER_GITKEEP,
      'update: a leftover folder holding a user file stays, with its .gitkeep',
    );
    assert(await fs.pathExists(literal(projectDir)), 'update: {project-root}/ stays while a folder in it holds a user file');
    assert(!(await fs.pathExists(literal(projectDir, 'skf-skills'))), 'update: the other leftover folder, holding only its .gitkeep, goes');
  });

  await inProject('leftover-other-text', 'an update over a .gitkeep the installer did not write', async (projectDir) => {
    await writeSavedConfig(projectDir, values);
    await writeLeftover(projectDir, 'kept by hand\n');
    await runInstall({ projectDir, skfFolder: '_bmad/skf', _action: 'update' });
    assert(
      (await fs.pathExists(literal(projectDir, 'skf-skills', '.gitkeep'))) &&
        (await fs.pathExists(literal(projectDir, 'forge-data', '.gitkeep'))),
      "update: a .gitkeep holding other text than the installer's stays",
    );
  });

  await inProject('leftover-outside', 'an update with a value whose literal path leaves the project', async (root) => {
    // The project is two levels down, so the literal path and the resolved one both stay in this temp folder.
    const projectDir = path.join(root, 'a', 'project');
    const outside = path.join(root, 'a', 'shared');
    await fs.ensureDir(outside);
    await fs.writeFile(path.join(outside, '.gitkeep'), INSTALLER_GITKEEP);
    await writeSavedConfig(projectDir, { ...values, skills_output_folder: '{project-root}/../../shared' });
    await runInstall({ projectDir, skfFolder: '_bmad/skf', _action: 'update' });
    assert(
      await fs.pathExists(path.join(outside, '.gitkeep')),
      'update: a folder outside the project that the literal path names stays, though it holds only the .gitkeep',
    );
  });

  console.log('');
}

// ============================================================
// Uninstall run through its action
// ============================================================

// Every escape sequence the plan and the spinner write: colors, cursor hide and show, line erases.
// eslint-disable-next-line no-control-regex -- clack and chalk write these
const TERMINAL_ESCAPES = /\u001B\[[\d;?]*[A-Za-z]/g;

// The warning uninstall, install and update print for the entries they keep in an IDE skills folder.
const IDE_KEPT_HEADER = 'Left in place in IDE skills folders, not files SKF installed:';

/**
 * The lines a @clack/prompts warning prints under the line holding `header`,
 * each without the bar clack puts before it (`│`, or `|` where the terminal
 * has no unicode), up to the first empty one. Empty when no line holds `header`.
 */
function warnedLines(output, header) {
  const lines = output.split(/\r?\n/);
  const start = lines.findIndex((line) => line.includes(header));
  if (start === -1) return [];
  const found = [];
  for (const line of lines.slice(start + 1)) {
    const text = line.replace(/^\s*[│|]\s*/, '').trimEnd();
    if (!/^\s*[│|]/.test(line) || text === '') break;
    found.push(text);
  }
  return found;
}

/**
 * Run a command's action `fn` in `projectDir` with PATH set to `pathDirs`,
 * collecting console, stdout and stderr output with every escape sequence
 * stripped, and refusing process.exit (each call is recorded, then throws).
 * process.exitCode is cleared before the run and after it. Returns the exit
 * code the action set, the process.exit calls, the error thrown and the output.
 */
async function captureCommand(projectDir, fn, pathDirs) {
  const printed = [];
  const exits = [];
  const orig = {
    cwd: process.cwd(),
    log: console.log,
    error: console.error,
    out: process.stdout.write,
    err: process.stderr.write,
    exit: process.exit,
    path: process.env.PATH,
  };
  const collect = (chunk) => {
    printed.push(String(chunk));
    return true;
  };
  let thrown = null;
  let exitCode;
  process.exitCode = undefined;
  try {
    process.chdir(projectDir);
    console.log = (...args) => printed.push(`${args.join(' ')}\n`);
    console.error = (...args) => printed.push(`${args.join(' ')}\n`);
    process.stdout.write = collect;
    process.stderr.write = collect;
    process.exit = (code) => {
      exits.push(code);
      throw new Error(`process.exit(${code}) was called`);
    };
    process.env.PATH = pathDirs.join(path.delimiter);
    await fn();
  } catch (error) {
    thrown = error;
  } finally {
    console.log = orig.log;
    console.error = orig.error;
    process.stdout.write = orig.out;
    process.stderr.write = orig.err;
    process.exit = orig.exit;
    process.env.PATH = orig.path;
    process.chdir(orig.cwd);
    exitCode = process.exitCode;
    process.exitCode = undefined;
  }
  return { exitCode, exits, thrown, output: printed.join('').replaceAll(TERMINAL_ESCAPES, '') };
}

/**
 * Run the uninstall action in `projectDir`, the confirm prompt answering
 * `answer`. @clack/prompts is ESM-only, so its namespace cannot be patched:
 * a Module._load hook hands uninstall.js a copy whose confirm records the
 * call and returns `answer`, and uninstall.js is loaded fresh for the run
 * and dropped from the cache after it. Console and stdout output is
 * collected, and process.exit is recorded without stopping the run, since
 * each exit in the action is followed by a return or the end of the action.
 * Returns the exit codes, the output with every escape sequence stripped,
 * the cwd the action ran in and the confirm calls.
 */
async function runUninstallAction(projectDir, { answer = true } = {}) {
  const Module = require('node:module');
  const modulePath = require.resolve('../tools/cli/commands/uninstall');
  const exits = [];
  const printed = [];
  const confirmCalls = [];
  const orig = {
    load: Module._load,
    cwd: process.cwd(),
    log: console.log,
    error: console.error,
    out: process.stdout.write,
    err: process.stderr.write,
    exit: process.exit,
  };
  let cwd = null;
  try {
    Module._load = (request, ...rest) => {
      const loaded = orig.load.call(Module, request, ...rest);
      if (request !== '@clack/prompts') return loaded;
      return {
        ...loaded,
        confirm: async (options) => {
          confirmCalls.push(options);
          return answer;
        },
      };
    };
    delete require.cache[modulePath];
    const uninstall = require(modulePath);
    process.chdir(projectDir);
    cwd = process.cwd();
    const collect = (chunk) => {
      printed.push(String(chunk));
      return true;
    };
    console.log = (...args) => printed.push(`${args.join(' ')}\n`);
    console.error = (...args) => printed.push(`${args.join(' ')}\n`);
    process.stdout.write = collect;
    process.stderr.write = collect;
    process.exit = (code) => {
      exits.push(code);
    };
    await uninstall.action();
  } finally {
    console.log = orig.log;
    console.error = orig.error;
    process.stdout.write = orig.out;
    process.stderr.write = orig.err;
    process.exit = orig.exit;
    process.chdir(orig.cwd);
    Module._load = orig.load;
    delete require.cache[modulePath];
  }
  return { exits, output: printed.join('').replaceAll(TERMINAL_ESCAPES, ''), cwd, confirmCalls };
}

async function testUninstallGuardedRemoval() {
  console.log(`${colors.yellow}Test Suite 20: Uninstall Removes Only What the Installer Wrote${colors.reset}\n`);

  const { MANIFEST_DIR, MANIFEST_FILE } = require('../tools/cli/lib/manifest');
  const skfConfig = path.join('_bmad', 'skf', 'config.yaml');

  // Run `run` with a new temp folder `home` and the project `home/project`, so `..`
  // from the project is `home` and every target sits in a folder this test creates.
  // `home` goes after the run, once the helper has restored the cwd.
  const inHome = async (description, run) => {
    const home = await makeTempDir('uninstall-guarded');
    try {
      const projectDir = path.join(home, 'project');
      await fs.ensureDir(projectDir);
      await run(home, projectDir);
    } catch (error) {
      assert(false, `${description} completes without error`, error.stack);
    } finally {
      await fs.remove(home);
    }
  };
  const writeFile = async (file, text) => {
    await fs.ensureDir(path.dirname(file));
    await fs.writeFile(file, text);
  };
  const writeTestManifest = async (projectDir, manifest) => {
    const text = yaml.dump({ version: 'test', module: 'skf', ides: [], ...manifest });
    await writeFile(path.join(projectDir, MANIFEST_DIR, MANIFEST_FILE), text);
  };
  const files = (lists) => ({ skf: [], sidecar: [], ide_skills: [], learning: [], output: [], ...lists });
  // The plan lines, each from its `×` on.
  const planLines = (output) =>
    output
      .split('\n')
      .filter((line) => line.includes('×'))
      .map((line) => line.slice(line.indexOf('×')).trimEnd());
  const exitedOnce = (run) => JSON.stringify(run.exits) === '[0]' && run.confirmCalls.length === 1;

  const skfFolderCases = [
    { label: '..', value: () => '..' },
    { label: '.', value: () => '.' },
    { label: 'src', value: () => 'src' },
    { label: 'an absolute sibling folder', value: (home) => path.join(home, 'sibling') },
    { label: 'absent', value: () => null },
  ];
  for (const { label, value } of skfFolderCases) {
    await inHome(`uninstall with skf_folder ${label}`, async (home, projectDir) => {
      const skfFolder = value(home);
      await writeFile(path.join(projectDir, skfConfig), 'user_name: Tester\n');
      // The file each skf_folder value names a folder of: home, the project, src/ and the sibling.
      const own = [
        path.join(home, 'outside.txt'),
        path.join(projectDir, 'README.md'),
        path.join(projectDir, 'src', 'index.js'),
        path.join(home, 'sibling', 'keep.txt'),
      ];
      for (const file of own) await writeFile(file, 'mine\n');
      const manifest = { files: files({ skf: [skfConfig] }) };
      if (skfFolder !== null) manifest.skf_folder = skfFolder;
      await writeTestManifest(projectDir, manifest);

      const run = await runUninstallAction(projectDir);
      assert(exitedOnce(run), `skf_folder ${label}: the action asks once and exits 0`, JSON.stringify(run.exits) + run.output);
      const skfLines = planLines(run.output).filter((line) => line.includes('SKF module files'));
      assert(
        skfLines.length === 1 && skfLines[0] === '× SKF module files (_bmad/skf/, 1 file)',
        `skf_folder ${label}: the plan names _bmad/skf/, not the raw value`,
        skfLines.join(' | '),
      );
      assert(!(await fs.pathExists(path.join(projectDir, '_bmad', 'skf'))), `skf_folder ${label}: _bmad/skf/ goes`);
      const missing = [];
      for (const file of own) {
        if (!(await fs.pathExists(file))) missing.push(file);
      }
      assert(missing.length === 0, `skf_folder ${label}: the folder it names stays with its files`, missing.join(', '));
    });
  }

  await inHome('uninstall with an installer .gitkeep and a folder as output entries', async (home, projectDir) => {
    await writeFile(path.join(projectDir, skfConfig), 'user_name: Tester\n');
    await writeFile(path.join(projectDir, 'skills', '.gitkeep'), INSTALLER_GITKEEP);
    await writeFile(path.join(home, 'victim', 'data.txt'), 'victim\n');
    await writeTestManifest(projectDir, {
      skf_folder: '_bmad/skf',
      skills_output_folder: 'skills',
      forge_data_folder: 'forge-data',
      files: files({ skf: [skfConfig], output: [path.join('skills', '.gitkeep'), path.join('..', 'victim')] }),
    });

    const run = await runUninstallAction(projectDir);
    const gitkeep = path.join(run.cwd, 'skills', '.gitkeep');
    const victim = path.resolve(run.cwd, '..', 'victim');
    const lines = planLines(run.output);
    assert(exitedOnce(run), 'output entries: the action asks once and exits 0', JSON.stringify(run.exits) + run.output);
    assert(
      lines.includes(`× Output folder scaffolding (${gitkeep})`),
      "output entries: the plan names the installer's .gitkeep by its absolute path",
      lines.join(' | '),
    );
    const header = 'Left in place, not a .gitkeep the installer wrote:';
    const kept = run.output.includes(header) ? run.output.slice(run.output.indexOf(header) + header.length).split('\n')[1] : '';
    assert(
      kept.trimEnd().endsWith(victim) && !lines.some((line) => line.includes(victim)),
      'output entries: the warning, not the plan, names the resolved ../victim',
      run.output,
    );
    assert(
      !(await fs.pathExists(path.join(projectDir, 'skills'))),
      "output entries: the installer's .gitkeep goes with its emptied folder",
    );
    assert(
      (await fs.readFile(path.join(home, 'victim', 'data.txt'), 'utf8')) === 'victim\n',
      'output entries: ../victim stays with its contents',
    );
  });

  await inHome('uninstall with an empty skf list and an IDE skills folder', async (home, projectDir) => {
    await writeFile(path.join(projectDir, skfConfig), 'user_name: Tester\n');
    await writeFile(path.join(projectDir, '_bmad', 'skf', 'shared', 'notes.md'), '# shared\n');
    await writeFile(path.join(projectDir, '_bmad', 'skf', 'knowledge', 'notes.md'), '# knowledge\n');
    const skills = path.join(projectDir, '.claude', 'skills');
    await writeFile(path.join(skills, 'skf-demo', 'SKILL.md'), '# skf-demo\n');
    // In knowledge/ and shared/ the IDE step removes the files SKF installed, each
    // the same bytes as its _bmad/skf/ copy, and keeps the user's SKILL.md beside them.
    await writeFile(path.join(skills, 'knowledge', 'notes.md'), '# knowledge\n');
    await writeFile(path.join(skills, 'shared', 'notes.md'), '# shared\n');
    await writeFile(path.join(skills, 'shared', 'SKILL.md'), '# my shared skill\n');
    await writeFile(path.join(skills, 'mine', 'SKILL.md'), '# mine\n');
    await writeTestManifest(projectDir, {
      skf_folder: '_bmad/skf',
      files: files({ ide_skills: [path.join('.claude', 'skills', 'skf-demo', 'SKILL.md')] }),
    });

    const run = await runUninstallAction(projectDir);
    const lines = planLines(run.output);
    assert(exitedOnce(run), 'empty skf list: the action asks once and exits 0', JSON.stringify(run.exits) + run.output);
    assert(
      lines.includes('× SKF module files (_bmad/skf/, 3 files)'),
      'empty skf list: the plan still names _bmad/skf/ with the files it holds',
      lines.join(' | '),
    );
    assert(
      lines.includes('× SKF skills (.claude/skills/, 3 entries, shared/ and knowledge/ among them)'),
      'empty skf list: the plan names .claude/skills/ with skf-demo/, shared/ and knowledge/ counted',
      lines.join(' | '),
    );
    const kept = warnedLines(run.output, IDE_KEPT_HEADER);
    assert(
      JSON.stringify(kept) === JSON.stringify([path.join('.claude', 'skills', 'shared', 'SKILL.md')]),
      "empty skf list: the warning names the user's shared/SKILL.md alone",
      run.output,
    );
    assert(
      !(await fs.pathExists(path.join(skills, 'knowledge'))) && !(await fs.pathExists(path.join(skills, 'shared', 'notes.md'))),
      'empty skf list: both notes go, and knowledge/ with them',
    );
    assert(
      (await fs.readFile(path.join(skills, 'shared', 'SKILL.md'), 'utf8')) === '# my shared skill\n',
      "empty skf list: the user's shared/SKILL.md stays with its folder",
    );
    assert(
      lines.length > 0 && lines.every((line) => /\((?!\d)[^)]+\)$/.test(line)),
      'empty skf list: every plan line names a path, none is a bare count',
      lines.join(' | '),
    );
    assert(!(await fs.pathExists(path.join(projectDir, '_bmad', 'skf'))), 'empty skf list: _bmad/skf/ goes');
    assert(
      !(await fs.pathExists(path.join(skills, 'skf-demo'))) && (await fs.pathExists(path.join(skills, 'mine', 'SKILL.md'))),
      "empty skf list: skf-demo/ goes and the user's mine/ stays",
    );
  });

  await inHome('uninstall with the sidecar and learning folders', async (home, projectDir) => {
    await writeFile(path.join(projectDir, skfConfig), 'user_name: Tester\n');
    await writeFile(path.join(projectDir, '_bmad', '_memory', 'forger-sidecar', 'user-state.yaml'), 'tier: Quick\n');
    const learnFile = path.join('_skf-learn', 'x.md');
    await writeFile(path.join(projectDir, learnFile), '# x\n');
    await writeTestManifest(projectDir, { skf_folder: '_bmad/skf', files: files({ skf: [skfConfig], learning: [learnFile] }) });

    const run = await runUninstallAction(projectDir);
    const lines = planLines(run.output);
    assert(exitedOnce(run), 'sidecar and learning: the action asks once and exits 0', JSON.stringify(run.exits) + run.output);
    assert(
      lines.includes('× Agent sidecar state (_bmad/_memory/forger-sidecar/, 1 file)'),
      'sidecar and learning: the plan names the sidecar folder with the files it holds',
      lines.join(' | '),
    );
    assert(
      lines.includes('× Learning material (_skf-learn/, 1 file)'),
      'sidecar and learning: the plan names _skf-learn/ when the learning list is not empty',
      lines.join(' | '),
    );
    assert(
      !(await fs.pathExists(path.join(projectDir, '_bmad', '_memory', 'forger-sidecar'))) &&
        !(await fs.pathExists(path.join(projectDir, '_skf-learn'))),
      'sidecar and learning: both folders the plan names go',
    );
  });

  await inHome('uninstall with an empty learning list', async (home, projectDir) => {
    await writeFile(path.join(projectDir, skfConfig), 'user_name: Tester\n');
    await writeFile(path.join(projectDir, '_skf-learn', 'x.md'), '# x\n');
    await writeTestManifest(projectDir, { skf_folder: '_bmad/skf', files: files({ skf: [skfConfig] }) });

    const run = await runUninstallAction(projectDir);
    assert(exitedOnce(run), 'empty learning list: the action asks once and exits 0', JSON.stringify(run.exits) + run.output);
    assert(
      !planLines(run.output).some((line) => line.includes('Learning material')),
      'empty learning list: the plan has no learning line',
      run.output,
    );
    assert(await fs.pathExists(path.join(projectDir, '_skf-learn', 'x.md')), 'empty learning list: _skf-learn/ stays, as the plan said');
  });

  // An output value that is not a list, or a list holding a number, as a hand-edited
  // manifest can: the action runs to the end and says what the output step removed.
  const outputValueCases = [
    { label: 'an object', output: () => ({ a: 1 }), gitkeep: null, stop: null },
    {
      label: "a number and the installer's .gitkeep",
      output: () => [42, path.join('skills', '.gitkeep')],
      gitkeep: INSTALLER_GITKEEP,
      stop: 'Output scaffolding removed',
    },
    {
      label: "a number and a .gitkeep of the user's",
      output: () => [42, path.join('skills', '.gitkeep')],
      gitkeep: 'mine\n',
      stop: 'No output scaffolding removed',
    },
  ];
  for (const { label, output, gitkeep, stop } of outputValueCases) {
    await inHome(`uninstall with files.output ${label}`, async (home, projectDir) => {
      await writeFile(path.join(projectDir, skfConfig), 'user_name: Tester\n');
      const gitkeepFile = path.join(projectDir, 'skills', '.gitkeep');
      if (gitkeep !== null) await writeFile(gitkeepFile, gitkeep);
      await writeTestManifest(projectDir, { skf_folder: '_bmad/skf', files: files({ skf: [skfConfig], output: output() }) });

      const run = await runUninstallAction(projectDir);
      assert(exitedOnce(run), `files.output ${label}: the action asks once and exits 0`, JSON.stringify(run.exits) + run.output);
      assert(!(await fs.pathExists(path.join(projectDir, '_bmad', 'skf'))), `files.output ${label}: _bmad/skf/ goes`);
      const stops = ['Output scaffolding removed', 'No output scaffolding removed'].filter((message) => run.output.includes(message));
      assert(
        JSON.stringify(stops) === JSON.stringify(stop === null ? [] : [stop]),
        `files.output ${label}: the output step reports ${stop === null ? 'nothing' : `"${stop}"`}`,
        run.output,
      );
      if (gitkeep !== null && gitkeep !== INSTALLER_GITKEEP) {
        assert((await fs.readFile(gitkeepFile, 'utf8')) === gitkeep, `files.output ${label}: the user's .gitkeep stays`);
      }
    });
  }

  // Windows has no mode bit that stops a folder being read, and root reads any folder.
  if (IS_WINDOWS || (typeof process.getuid === 'function' && process.getuid() === 0)) {
    console.log(`${colors.dim}  unreadable IDE skills folder: skipped on Windows and as root${colors.reset}`);
  } else {
    await inHome('uninstall with an IDE skills folder it cannot read', async (home, projectDir) => {
      await writeFile(path.join(projectDir, skfConfig), 'user_name: Tester\n');
      const unreadable = path.join(projectDir, '.claude', 'skills');
      await writeFile(path.join(unreadable, 'skf-demo', 'SKILL.md'), '# skf-demo\n');
      await writeFile(path.join(projectDir, '.cursor', 'skills', 'skf-demo', 'SKILL.md'), '# skf-demo\n');
      await writeTestManifest(projectDir, { skf_folder: '_bmad/skf', files: files({ skf: [skfConfig] }) });

      let run;
      await fs.chmod(unreadable, 0o000);
      try {
        run = await runUninstallAction(projectDir, { answer: false });
      } finally {
        // Restored before the home folder goes, which needs to read it.
        await fs.chmod(unreadable, 0o755);
      }
      const lines = planLines(run.output);
      assert(exitedOnce(run), 'unreadable IDE folder: the action asks once and exits 0', JSON.stringify(run.exits) + run.output);
      assert(
        lines.includes('× SKF skills (.cursor/skills/, 1 entry)') && !lines.some((line) => line.includes('.claude/skills')),
        'unreadable IDE folder: the plan leaves it out and still names a folder it can read',
        lines.join(' | '),
      );
      assert(
        (await fs.pathExists(path.join(projectDir, skfConfig))) && (await fs.pathExists(path.join(unreadable, 'skf-demo', 'SKILL.md'))),
        'unreadable IDE folder: answering no removes nothing',
      );
    });
  }

  console.log('');
}

async function testIdeSkillFoldersKeepUserFiles() {
  console.log(`${colors.yellow}Test Suite 21: IDE Skills Folders Keep the User's shared/ and knowledge/ Files${colors.reset}\n`);

  const { readManifest, MANIFEST_DIR, MANIFEST_FILE } = require('../tools/cli/lib/manifest');
  const { UI } = require('../tools/cli/lib/ui');
  const installCommand = require('../tools/cli/commands/install');
  const updateCommand = require('../tools/cli/commands/update');
  const srcDir = path.join(__dirname, '..', 'src');
  const skfConfig = path.join('_bmad', 'skf', 'config.yaml');
  const claudeShared = path.join('.claude', 'skills', 'shared');
  const claudeKnowledge = path.join('.claude', 'skills', 'knowledge');
  // Windows has no symlink without a privilege, no mode bit that stops a folder being read, and root reads any folder.
  const noLinks = IS_WINDOWS;
  const noChmod = IS_WINDOWS || (typeof process.getuid === 'function' && process.getuid() === 0);
  const origPrompt = UI.prototype.promptInstall;
  const origSuccess = UI.prototype.displaySuccess;
  UI.prototype.displaySuccess = () => {};

  // Run `run` with a new temp folder `home`, the project `home/project` and an empty
  // `home/bin` for PATH, so every link target and every removal stays in a folder this test creates.
  const inHome = async (description, run) => {
    const home = await makeTempDir('ide-folders');
    try {
      const projectDir = path.join(home, 'project');
      await fs.ensureDir(projectDir);
      await fs.ensureDir(path.join(home, 'bin'));
      await run(home, projectDir);
    } catch (error) {
      assert(false, `${description} completes without error`, error.stack);
    } finally {
      await fs.remove(home);
    }
  };
  const writeFile = async (file, text) => {
    await fs.ensureDir(path.dirname(file));
    await fs.writeFile(file, text);
  };
  const copyFromSrc = async (rel, dest) => {
    await fs.ensureDir(path.dirname(dest));
    await fs.copy(path.join(srcDir, rel), dest);
  };
  const writeTestManifest = async (projectDir) => {
    await writeFile(path.join(projectDir, skfConfig), 'user_name: Tester\n');
    const files = { skf: [skfConfig], sidecar: [], ide_skills: [], learning: [], output: [] };
    await writeFile(path.join(projectDir, MANIFEST_DIR, MANIFEST_FILE), yaml.dump({ version: 'test', module: 'skf', ides: [], files }));
  };
  const editManifest = async (projectDir, edit) => {
    const file = path.join(projectDir, MANIFEST_DIR, MANIFEST_FILE);
    const manifest = yaml.load(await fs.readFile(file, 'utf8'));
    edit(manifest);
    await fs.writeFile(file, yaml.dump(manifest, { lineWidth: -1 }));
  };
  // Every entry under `dir`, sorted, found by an lstat walk: a folder by its name, a
  // file by its bytes' hash, a link by its readlink text (never followed).
  const snapshot = async (dir) => {
    const entries = [];
    const walk = async (rel) => {
      for (const name of (await fs.readdir(path.join(dir, rel))).sort()) {
        const entryRel = path.join(rel, name);
        const entry = path.join(dir, entryRel);
        const stat = await fs.lstat(entry);
        if (stat.isSymbolicLink()) {
          entries.push(`${entryRel} -> ${await fs.readlink(entry)}`);
        } else if (stat.isDirectory()) {
          entries.push(`${entryRel}${path.sep}`);
          await walk(entryRel);
        } else if (stat.isFile()) {
          entries.push(
            `${entryRel} ${crypto
              .createHash('sha256')
              .update(await fs.readFile(entry))
              .digest('hex')}`,
          );
        } else {
          entries.push(`${entryRel} (other)`);
        }
      }
    };
    await walk('');
    return entries;
  };
  const sameSnapshot = (before, after) => JSON.stringify(before) === JSON.stringify(after);
  const snapshotDiff = (before, after) =>
    `gone: ${before.filter((entry) => !after.includes(entry)).join(', ')}; new: ${after.filter((entry) => !before.includes(entry)).join(', ')}`;
  const realInstall = (projectDir, ides) =>
    runInstall({
      projectDir,
      skfFolder: '_bmad/skf',
      project_name: 'ide-folders-test',
      skills_output_folder: 'skills',
      forge_data_folder: 'forge-data',
      ides,
      install_learning: false,
      _action: 'fresh',
    });
  // The install command, its prompt answering a fresh install for `ides` unless `config` says otherwise.
  const installRun = (home, projectDir, ides, config = {}) => {
    UI.prototype.promptInstall = async () => ({
      projectDir,
      skfFolder: '_bmad/skf',
      project_name: 'ide-folders-test',
      skills_output_folder: 'skills',
      forge_data_folder: 'forge-data',
      ides,
      install_learning: false,
      _action: 'fresh',
      cancelled: false,
      ...config,
    });
    return captureCommand(projectDir, () => installCommand.action(), [path.join(home, 'bin')]);
  };
  const updateRun = (home, projectDir) => captureCommand(projectDir, () => updateCommand.action(), [path.join(home, 'bin')]);
  const planLines = (output) =>
    output
      .split('\n')
      .filter((line) => line.includes('×'))
      .map((line) => line.slice(line.indexOf('×')).trimEnd());
  const exitedZero = (run) => JSON.stringify(run.exits) === '[0]';
  const succeeded = (run) => run.exitCode === undefined && run.thrown === null;
  // A refused command: exit code 1, the folder and each entry named, the fixed advice, and no stack trace.
  const refused = (run, entries) =>
    run.exitCode === 1 &&
    run.thrown === null &&
    run.output.includes(`${claudeShared.split(path.sep).join('/')}/ holds files SKF did not install:`) &&
    entries.every((entry) => run.output.includes(`\n  ${entry}\n`)) &&
    run.output.includes('Nothing was changed.') &&
    !run.output.includes('IdeFolderInUseError');

  try {
    await inHome('uninstall with user skills in other IDE folders', async (home, projectDir) => {
      await realInstall(projectDir, ['claude-code']);
      const cursorShared = path.join(projectDir, '.cursor', 'skills', 'shared');
      await writeFile(path.join(cursorShared, 'SKILL.md'), '# my cursor shared skill\n');
      await writeFile(path.join(cursorShared, '.DS_Store'), 'finder\n');
      await writeFile(path.join(cursorShared, 'scripts', '__pycache__', 'x.pyc'), Buffer.from([0x0d, 0x0a, 0x00, 0x01]));
      await writeFile(path.join(projectDir, '.cursor', 'skills', 'knowledge', 'SKILL.md'), '# my cursor knowledge skill\n');
      await writeFile(path.join(projectDir, '.agents', 'skills', 'shared', 'SKILL.md'), '# my codex shared skill\n');
      await writeFile(path.join(projectDir, '.github', 'skills', 'shared', 'SKILL.md'), '# my copilot shared skill\n');
      await fs.ensureDir(path.join(projectDir, '.agents', 'skills', 'knowledge'));
      const userFolders = ['.cursor', '.agents', '.github'];
      const before = await Promise.all(userFolders.map((folder) => snapshot(path.join(projectDir, folder))));

      const run = await runUninstallAction(projectDir);
      const lines = planLines(run.output);
      assert(exitedZero(run), 'other IDE folders: the action exits 0', JSON.stringify(run.exits) + run.output);
      const after = await Promise.all(userFolders.map((folder) => snapshot(path.join(projectDir, folder))));
      assert(
        sameSnapshot(before, after) && after.every((entries) => entries.length > 0),
        'other IDE folders: all five user folders stay with every file and its bytes',
        snapshotDiff(before.flat(), after.flat()),
      );
      assert(
        !lines.some((line) => /\.(cursor|agents|github)\/skills/.test(line)),
        'other IDE folders: the plan has no line for .cursor/, .agents/ or .github/skills/',
        lines.join(' | '),
      );
      assert(
        !warnedLines(run.output, IDE_KEPT_HEADER).some((line) => /^\.(cursor|agents|github)/.test(line)),
        'other IDE folders: the warning names none of their files',
        run.output,
      );
      const claudeLine = lines.find((line) => line.includes('(.claude/skills/,'));
      assert(
        claudeLine !== undefined && claudeLine.endsWith('entries, shared/ among them)'),
        "other IDE folders: the .claude/skills/ line counts SKF's shared/ among its entries",
        lines.join(' | '),
      );
      const claudeLeft = await fs.readdir(path.join(projectDir, '.claude', 'skills'));
      assert(claudeLeft.length === 0, 'other IDE folders: .claude/skills/ is left empty', claudeLeft.join(', '));
    });

    await inHome('uninstall with a knowledge/ copy matching only the running src/', async (home, projectDir) => {
      await writeTestManifest(projectDir);
      const knowledge = path.join(projectDir, '.cursor', 'skills', 'knowledge');
      await copyFromSrc(path.join('knowledge', 'zero-hallucination.md'), path.join(knowledge, 'zero-hallucination.md'));
      await writeFile(path.join(knowledge, 'overview.md'), '# my own overview\n');

      const run = await runUninstallAction(projectDir);
      assert(exitedZero(run), 'src/ match: the action exits 0', JSON.stringify(run.exits) + run.output);
      assert(
        planLines(run.output).includes('× SKF skills (.cursor/skills/, 1 entry, knowledge/ among them)'),
        'src/ match: the plan counts knowledge/ as the one entry',
        run.output,
      );
      assert(!(await fs.pathExists(path.join(knowledge, 'zero-hallucination.md'))), 'src/ match: the copy of src/knowledge/ goes');
      assert(
        (await fs.readFile(path.join(knowledge, 'overview.md'), 'utf8')) === '# my own overview\n',
        'src/ match: overview.md with other bytes stays',
      );
      assert(
        JSON.stringify(warnedLines(run.output, IDE_KEPT_HEADER)) ===
          JSON.stringify([path.join('.cursor', 'skills', 'knowledge', 'overview.md')]),
        'src/ match: the warning names overview.md',
        run.output,
      );
    });

    const userSkill = path.join(claudeShared, 'SKILL.md');
    await inHome('a first install with a user shared/ skill', async (home, projectDir) => {
      await writeFile(path.join(projectDir, userSkill), '# my shared skill\n');
      const before = await snapshot(projectDir);
      const run = await installRun(home, projectDir, ['claude-code']);
      assert(refused(run, [userSkill]), 'first install: exit code 1, the folder and its file named, no stack trace', run.output);
      const after = await snapshot(projectDir);
      assert(sameSnapshot(before, after), 'first install: nothing in the project changes', snapshotDiff(before, after));
      assert(!(await fs.pathExists(path.join(projectDir, '_bmad'))), 'first install: _bmad/ does not exist');
    });

    await inHome("skf update with a user file in SKF's shared/", async (home, projectDir) => {
      await realInstall(projectDir, ['claude-code']);
      await writeFile(path.join(projectDir, userSkill), '# my shared skill\n');
      const before = await snapshot(projectDir);
      const run = await updateRun(home, projectDir);
      assert(refused(run, [userSkill]), 'update: exit code 1, the folder and its file named', run.output);
      const after = await snapshot(projectDir);
      assert(sameSnapshot(before, after), 'update: nothing in the project changes', snapshotDiff(before, after));
    });

    await inHome("a Fresh install with a user file in SKF's shared/", async (home, projectDir) => {
      await realInstall(projectDir, ['claude-code']);
      await writeFile(path.join(projectDir, userSkill), '# my shared skill\n');
      const before = await snapshot(projectDir);
      const run = await installRun(home, projectDir, ['claude-code']);
      assert(refused(run, [userSkill]), 'Fresh install: exit code 1, the folder and its file named', run.output);
      const after = await snapshot(projectDir);
      assert(sameSnapshot(before, after), 'Fresh install: nothing in the project changes', snapshotDiff(before, after));
    });

    await inHome('a first install for two IDEs whose shared/ each hold a user skill', async (home, projectDir) => {
      const cursorSkill = path.join('.cursor', 'skills', 'shared', 'SKILL.md');
      await writeFile(path.join(projectDir, userSkill), '# my claude shared skill\n');
      await writeFile(path.join(projectDir, cursorSkill), '# my cursor shared skill\n');
      const before = await snapshot(projectDir);
      const run = await installRun(home, projectDir, ['claude-code', 'cursor']);
      assert(
        refused(run, [userSkill, cursorSkill]) && run.output.includes('.cursor/skills/shared/ holds files SKF did not install:'),
        'two IDEs: exit code 1, both shared/ folders and both files named',
        run.output,
      );
      const after = await snapshot(projectDir);
      assert(sameSnapshot(before, after), 'two IDEs: nothing in the project changes', snapshotDiff(before, after));
    });

    await inHome('an install for an IDE whose shared/ is a user skill with bytecode and an OS file', async (home, projectDir) => {
      const cursorShared = path.join('.cursor', 'skills', 'shared');
      const entries = [
        path.join(cursorShared, '.DS_Store'),
        path.join(cursorShared, 'SKILL.md'),
        path.join(cursorShared, 'scripts', '__pycache__', 'x.pyc'),
      ];
      for (const entry of entries) await writeFile(path.join(projectDir, entry), `${entry}\n`);
      const before = await snapshot(projectDir);
      const run = await installRun(home, projectDir, ['cursor']);
      assert(
        run.exitCode === 1 &&
          run.output.includes('.cursor/skills/shared/ holds files SKF did not install:') &&
          entries.every((entry) => run.output.includes(`\n  ${entry}\n`)),
        'user skill with bytecode: exit code 1, all three files named',
        run.output,
      );
      const after = await snapshot(projectDir);
      assert(sameSnapshot(before, after), 'user skill with bytecode: nothing in the project changes', snapshotDiff(before, after));
    });

    await inHome("bytecode in SKF's shared/", async (home, projectDir) => {
      await realInstall(projectDir, ['claude-code']);
      const pyc = path.join(projectDir, claudeShared, 'scripts', '__pycache__', 'skf-test.cpython-314.pyc');
      await writeFile(pyc, Buffer.from([0x0d, 0x0a, 0x00, 0x02]));
      const run = await updateRun(home, projectDir);
      assert(succeeded(run), 'bytecode: skf update succeeds', run.output);
      await writeFile(pyc, Buffer.from([0x0d, 0x0a, 0x00, 0x03]));
      const uninstall = await runUninstallAction(projectDir);
      assert(exitedZero(uninstall), 'bytecode: uninstall exits 0', JSON.stringify(uninstall.exits) + uninstall.output);
      assert(!(await fs.pathExists(path.join(projectDir, claudeShared))), 'bytecode: uninstall removes .claude/skills/shared/');
    });

    // The knowledge/ copy an earlier version installed, and one file there with other
    // bytes that an earlier manifest lists, as it listed every file of that copy.
    const earlierKnowledge = async (projectDir, { listed = true, mine = null } = {}) => {
      await fs.copy(path.join(projectDir, '_bmad', 'skf', 'knowledge'), path.join(projectDir, claudeKnowledge));
      if (listed) {
        const older = path.join(claudeKnowledge, 'older-fragment.md');
        await writeFile(path.join(projectDir, older), '# a fragment an older version shipped\n');
        await editManifest(projectDir, (manifest) => manifest.files.ide_skills.push(older));
      }
      if (mine !== null) await writeFile(path.join(projectDir, claudeKnowledge, 'mine.md'), mine);
    };
    await inHome("an earlier version's knowledge/ copy", async (home, projectDir) => {
      await realInstall(projectDir, ['claude-code']);
      await earlierKnowledge(projectDir);
      const run = await updateRun(home, projectDir);
      assert(succeeded(run), 'earlier knowledge/: skf update succeeds', run.output);
      assert(!(await fs.pathExists(path.join(projectDir, claudeKnowledge))), 'earlier knowledge/: skf update removes it and copies none');
      await earlierKnowledge(projectDir);
      const uninstall = await runUninstallAction(projectDir);
      assert(exitedZero(uninstall), 'earlier knowledge/: uninstall exits 0', JSON.stringify(uninstall.exits) + uninstall.output);
      assert(!(await fs.pathExists(path.join(projectDir, claudeKnowledge))), 'earlier knowledge/: uninstall removes it');
    });

    await inHome("an earlier version's knowledge/ copy holding a user file", async (home, projectDir) => {
      await realInstall(projectDir, ['claude-code']);
      await earlierKnowledge(projectDir, { listed: false, mine: '# mine\n' });
      const mine = path.join(claudeKnowledge, 'mine.md');
      const run = await updateRun(home, projectDir);
      assert(succeeded(run), 'knowledge/ with mine.md: skf update succeeds', run.output);
      assert(
        JSON.stringify(await fs.readdir(path.join(projectDir, claudeKnowledge))) === '["mine.md"]',
        'knowledge/ with mine.md: only mine.md stays',
      );
      assert(
        JSON.stringify(warnedLines(run.output, IDE_KEPT_HEADER)) === JSON.stringify([mine]),
        'knowledge/ with mine.md: the update names mine.md',
        run.output,
      );
      const underKnowledge = (await readManifest(projectDir)).files.ide_skills.filter((file) =>
        file.startsWith(`${claudeKnowledge}${path.sep}`),
      );
      assert(underKnowledge.length === 0, 'knowledge/ with mine.md: the new manifest lists no path under it', underKnowledge.join(', '));
      const second = await updateRun(home, projectDir);
      assert(succeeded(second), 'knowledge/ with mine.md: a second skf update succeeds', second.output);
      const uninstall = await runUninstallAction(projectDir);
      assert(exitedZero(uninstall), 'knowledge/ with mine.md: uninstall exits 0', JSON.stringify(uninstall.exits) + uninstall.output);
      assert(
        (await fs.readFile(path.join(projectDir, mine), 'utf8')) === '# mine\n',
        'knowledge/ with mine.md: mine.md is still there with its bytes',
      );
    });

    await inHome('a first install with a user knowledge/ skill', async (home, projectDir) => {
      const skill = path.join(claudeKnowledge, 'SKILL.md');
      await writeFile(path.join(projectDir, skill), '# my knowledge skill\n');
      const run = await installRun(home, projectDir, ['claude-code']);
      assert(succeeded(run), 'user knowledge/: the install succeeds', run.output);
      assert(
        (await fs.readFile(path.join(projectDir, skill), 'utf8')) === '# my knowledge skill\n',
        'user knowledge/: its SKILL.md stays with its bytes',
      );
      assert(!(await readManifest(projectDir)).files.ide_skills.includes(skill), 'user knowledge/: files.ide_skills does not list it');
    });

    await inHome('uninstall after _bmad/skf/ was removed by hand', async (home, projectDir) => {
      await realInstall(projectDir, ['claude-code']);
      await fs.remove(path.join(projectDir, '_bmad', 'skf'));
      await editManifest(projectDir, (manifest) => {
        manifest.files.ide_skills = [];
      });
      const run = await runUninstallAction(projectDir);
      assert(exitedZero(run), 'no _bmad/skf/: uninstall exits 0', JSON.stringify(run.exits) + run.output);
      assert(
        !(await fs.pathExists(path.join(projectDir, claudeShared))),
        'no _bmad/skf/: .claude/skills/shared/ goes, matched against src/shared/',
      );
    });

    if (noLinks) {
      console.log(`${colors.dim}  linked shared/ and knowledge/ entries: skipped on Windows${colors.reset}`);
    } else {
      await inHome('uninstall with linked shared/ and knowledge/ entries', async (home, projectDir) => {
        await writeTestManifest(projectDir);
        const skills = path.join(projectDir, '.cursor', 'skills');
        const sharedTarget = path.join(home, 'linked-shared');
        const knowledgeTarget = path.join(home, 'linked-knowledge');
        await copyFromSrc(path.join('shared', 'health-check.md'), path.join(sharedTarget, 'health-check.md'));
        await copyFromSrc(path.join('knowledge', 'overview.md'), path.join(knowledgeTarget, 'overview.md'));
        // An empty folder inside a link target: the cleanup of emptied folders must not reach it.
        await fs.ensureDir(path.join(knowledgeTarget, 'assets'));
        await fs.ensureDir(skills);
        await fs.symlink(sharedTarget, path.join(skills, 'shared'));
        await copyFromSrc(path.join('knowledge', 'zero-hallucination.md'), path.join(skills, 'knowledge', 'zero-hallucination.md'));
        await fs.symlink(knowledgeTarget, path.join(skills, 'knowledge', 'linked'));

        const run = await runUninstallAction(projectDir);
        assert(exitedZero(run), 'links: uninstall exits 0', JSON.stringify(run.exits) + run.output);
        assert(
          planLines(run.output).includes('× SKF skills (.cursor/skills/, 1 entry, knowledge/ among them)'),
          'links: the plan counts knowledge/ alone',
          run.output,
        );
        assert(
          (await fs.lstat(path.join(skills, 'shared'))).isSymbolicLink() &&
            (await fs.pathExists(path.join(sharedTarget, 'health-check.md'))) &&
            (await fs.pathExists(path.join(knowledgeTarget, 'overview.md'))) &&
            (await fs.pathExists(path.join(knowledgeTarget, 'assets'))),
          'links: the shared link, both targets, their files and the empty folder in a target stay',
        );
        assert(!(await fs.pathExists(path.join(skills, 'knowledge', 'zero-hallucination.md'))), 'links: the knowledge copy goes');
        assert((await fs.lstat(path.join(skills, 'knowledge', 'linked'))).isSymbolicLink(), 'links: knowledge/linked stays, a link');
        assert(
          JSON.stringify(warnedLines(run.output, IDE_KEPT_HEADER)) ===
            JSON.stringify([path.join('.cursor', 'skills', 'knowledge', 'linked')]),
          'links: the warning names knowledge/linked',
          run.output,
        );
      });

      await inHome('uninstall with a linked SKILL.md and bytecode in a user shared/', async (home, projectDir) => {
        await writeTestManifest(projectDir);
        const shared = path.join(projectDir, '.cursor', 'skills', 'shared');
        await writeFile(path.join(home, 'my-skill', 'SKILL.md'), '# my linked shared skill\n');
        await fs.ensureDir(shared);
        await fs.symlink(path.join(home, 'my-skill', 'SKILL.md'), path.join(shared, 'SKILL.md'));
        await writeFile(path.join(shared, 'scripts', '__pycache__', 'x.cpython-314.pyc'), Buffer.from([0x0d, 0x0a, 0x00, 0x05]));
        const before = await snapshot(path.join(projectDir, '.cursor'));
        const run = await runUninstallAction(projectDir);
        assert(exitedZero(run), 'linked SKILL.md and bytecode: uninstall exits 0', JSON.stringify(run.exits) + run.output);
        assert(
          !planLines(run.output).some((line) => line.includes('.cursor/skills')),
          'linked SKILL.md and bytecode: the plan has no .cursor/skills/ line',
          run.output,
        );
        const after = await snapshot(path.join(projectDir, '.cursor'));
        assert(
          sameSnapshot(before, after) &&
            (await fs.readFile(path.join(home, 'my-skill', 'SKILL.md'), 'utf8')) === '# my linked shared skill\n',
          'linked SKILL.md and bytecode: the link, its target and the bytecode stay',
          snapshotDiff(before, after),
        );
      });
    }

    // A .claude/skills/shared before a first install that SKF did not write: the
    // install stops, names the entry, and changes nothing.
    const sharedCases = [
      {
        label: 'a link to a temp folder',
        skip: noLinks,
        entry: claudeShared,
        make: async (home, projectDir) => {
          await writeFile(path.join(home, 'elsewhere', 'SKILL.md'), '# elsewhere\n');
          await fs.ensureDir(path.join(projectDir, '.claude', 'skills'));
          await fs.symlink(path.join(home, 'elsewhere'), path.join(projectDir, claudeShared));
        },
      },
      {
        label: 'a plain file',
        entry: claudeShared,
        make: (home, projectDir) => writeFile(path.join(projectDir, claudeShared), 'not a folder\n'),
      },
      {
        label: 'a folder holding health-check.md with other bytes',
        entry: path.join(claudeShared, 'health-check.md'),
        make: (home, projectDir) => writeFile(path.join(projectDir, claudeShared, 'health-check.md'), '# my health check\n'),
      },
      {
        label: 'a folder holding an unreadable folder',
        skip: noChmod,
        entry: path.join(claudeShared, 'locked'),
        make: (home, projectDir) => writeFile(path.join(projectDir, claudeShared, 'locked', 'notes.md'), '# locked\n'),
        lock: path.join(claudeShared, 'locked'),
      },
    ];
    for (const { label, skip, entry, make, lock } of sharedCases) {
      if (skip) {
        console.log(`${colors.dim}  first install, shared/ ${label}: skipped${colors.reset}`);
        continue;
      }
      await inHome(`a first install with .claude/skills/shared ${label}`, async (home, projectDir) => {
        await make(home, projectDir);
        const before = await snapshot(projectDir);
        let run;
        if (lock) await fs.chmod(path.join(projectDir, lock), 0o000);
        try {
          run = await installRun(home, projectDir, ['claude-code']);
        } finally {
          // Restored before the snapshot and before the home folder goes, which both need to read it.
          if (lock) await fs.chmod(path.join(projectDir, lock), 0o755);
        }
        assert(refused(run, [entry]), `shared/ ${label}: exit code 1, ${entry} named`, run.output);
        const after = await snapshot(projectDir);
        assert(sameSnapshot(before, after), `shared/ ${label}: nothing in the project changes`, snapshotDiff(before, after));
      });
    }

    await inHome('a first install with bytecode and an OS file alone in .claude/skills/shared/', async (home, projectDir) => {
      const leftovers = [path.join(claudeShared, '.DS_Store'), path.join(claudeShared, 'scripts', '__pycache__', 'x.cpython-314.pyc')];
      for (const entry of leftovers) await writeFile(path.join(projectDir, entry), `${entry}\n`);
      const run = await installRun(home, projectDir, ['claude-code']);
      assert(succeeded(run), 'bytecode alone: the install succeeds', run.output);
      const left = [];
      for (const entry of leftovers) {
        if (await fs.pathExists(path.join(projectDir, entry))) left.push(entry);
      }
      assert(left.length === 0, 'bytecode alone: both files go', left.join(', '));
      assert(await fs.pathExists(path.join(projectDir, claudeShared, 'health-check.md')), "bytecode alone: shared/ holds SKF's copy");
    });

    await inHome('a first install with an empty .claude/skills/shared/', async (home, projectDir) => {
      await fs.ensureDir(path.join(projectDir, claudeShared));
      const run = await installRun(home, projectDir, ['claude-code']);
      assert(succeeded(run), 'empty shared/: the install succeeds', run.output);
      const copied = path.join(projectDir, claudeShared, 'health-check.md');
      assert(
        (await fs.pathExists(copied)) &&
          (await fs.readFile(copied)).equals(await fs.readFile(path.join(srcDir, 'shared', 'health-check.md'))),
        "empty shared/: the folder holds SKF's copy",
      );
    });

    if (noChmod) {
      console.log(`${colors.dim}  first install, unreadable .claude/skills/: skipped on Windows and as root${colors.reset}`);
    } else {
      await inHome('a first install with an unreadable .claude/skills/', async (home, projectDir) => {
        const skills = path.join(projectDir, '.claude', 'skills');
        await writeFile(path.join(skills, 'mine', 'SKILL.md'), '# mine\n');
        let run;
        await fs.chmod(skills, 0o000);
        try {
          run = await installRun(home, projectDir, ['claude-code']);
        } finally {
          await fs.chmod(skills, 0o755);
        }
        assert(run.exitCode === 1 && run.thrown === null, 'unreadable skills folder: exit code 1', run.output);
        assert(!(await fs.pathExists(path.join(projectDir, '_bmad'))), 'unreadable skills folder: _bmad/ does not exist');
      });
    }

    await inHome('uninstall after a Fresh install dropped an IDE', async (home, projectDir) => {
      await realInstall(projectDir, ['claude-code', 'cursor']);
      await realInstall(projectDir, ['claude-code']);
      const run = await runUninstallAction(projectDir);
      assert(exitedZero(run), 'dropped IDE: uninstall exits 0', JSON.stringify(run.exits) + run.output);
      const left = await fs.readdir(path.join(projectDir, '.cursor', 'skills'));
      assert(
        !left.some((name) => name.startsWith('skf-') || name === 'shared' || name === 'knowledge'),
        'dropped IDE: .cursor/skills/ holds no skf-*, shared or knowledge entry',
        left.join(', '),
      );
    });

    await inHome('uninstall with command files an earlier release left', async (home, projectDir) => {
      await writeTestManifest(projectDir);
      await writeFile(path.join(projectDir, '.claude', 'skills', 'skf-demo', 'SKILL.md'), '# skf demo\n');
      const commands = path.join(projectDir, '.claude', 'commands');
      await writeFile(path.join(commands, 'bmad-skf-old.md'), '# an earlier release command\n');
      await writeFile(path.join(commands, 'mine.md'), '# my command\n');
      const run = await runUninstallAction(projectDir);
      assert(exitedZero(run), 'legacy commands: uninstall exits 0', JSON.stringify(run.exits) + run.output);
      assert(!(await fs.pathExists(path.join(commands, 'bmad-skf-old.md'))), 'legacy commands: bmad-skf-old.md goes');
      assert(
        (await fs.readFile(path.join(commands, 'mine.md'), 'utf8')) === '# my command\n',
        'legacy commands: mine.md stays with its bytes',
      );
    });

    // The matrix cells the cases above leave open: a listed shared/ file and an OS
    // file beside SKF's copy, bytecode alone at uninstall, a first install after
    // _bmad/ was deleted by hand, IDE folders an install does not select, an SKF
    // path holding other bytes in a knowledge/ copy, and a plain-file shared and
    // unreadable folders at uninstall.
    await inHome("a listed shared/ file and an OS file beside SKF's copy", async (home, projectDir) => {
      await realInstall(projectDir, ['claude-code']);
      const retired = path.join(claudeShared, 'retired.md');
      const dsStore = path.join(claudeShared, '.DS_Store');
      const plant = async () => {
        await writeFile(path.join(projectDir, retired), '# a file an older version shipped\n');
        await writeFile(path.join(projectDir, dsStore), 'finder\n');
        await editManifest(projectDir, (manifest) => manifest.files.ide_skills.push(retired));
      };
      await plant();
      const run = await updateRun(home, projectDir);
      assert(succeeded(run), 'listed shared/ file: skf update succeeds', run.output);
      assert(
        !(await fs.pathExists(path.join(projectDir, retired))) && !(await fs.pathExists(path.join(projectDir, dsStore))),
        'listed shared/ file: skf update removes it and the OS file beside it',
      );
      const copied = path.join(projectDir, claudeShared, 'health-check.md');
      assert(
        (await fs.pathExists(copied)) &&
          (await fs.readFile(copied)).equals(await fs.readFile(path.join(srcDir, 'shared', 'health-check.md'))),
        "listed shared/ file: skf update copies SKF's shared/ back",
      );
      await plant();
      const uninstall = await runUninstallAction(projectDir);
      assert(exitedZero(uninstall), 'listed shared/ file: uninstall exits 0', JSON.stringify(uninstall.exits) + uninstall.output);
      assert(!(await fs.pathExists(path.join(projectDir, claudeShared))), 'listed shared/ file: uninstall removes .claude/skills/shared/');
      assert(
        warnedLines(uninstall.output, IDE_KEPT_HEADER).length === 0,
        'listed shared/ file: uninstall names no kept file',
        uninstall.output,
      );
    });

    await inHome('uninstall with bytecode and an OS file alone in a shared/', async (home, projectDir) => {
      await writeTestManifest(projectDir);
      const skills = path.join(projectDir, '.cursor', 'skills');
      await writeFile(path.join(skills, 'shared', '.DS_Store'), 'finder\n');
      await writeFile(path.join(skills, 'shared', 'scripts', '__pycache__', 'a.cpython-314.pyc'), Buffer.from([0x0d, 0x0a, 0x00, 0x04]));
      const run = await runUninstallAction(projectDir);
      assert(exitedZero(run), 'bytecode alone at uninstall: the action exits 0', JSON.stringify(run.exits) + run.output);
      assert(
        planLines(run.output).includes('× SKF skills (.cursor/skills/, 1 entry, shared/ among them)'),
        'bytecode alone at uninstall: the plan counts shared/ as the one entry',
        run.output,
      );
      assert(
        !(await fs.pathExists(path.join(skills, 'shared'))) && (await fs.pathExists(skills)),
        'bytecode alone at uninstall: shared/ goes and .cursor/skills/ stays',
      );
      assert(warnedLines(run.output, IDE_KEPT_HEADER).length === 0, 'bytecode alone at uninstall: no kept file is named', run.output);
    });

    await inHome('a first install after _bmad/ was deleted by hand', async (home, projectDir) => {
      await realInstall(projectDir, ['claude-code']);
      await fs.remove(path.join(projectDir, '_bmad'));
      const run = await installRun(home, projectDir, ['claude-code']);
      assert(succeeded(run), "no _bmad/: the install succeeds, the IDE's shared/ matched against src/shared/", run.output);
      const copied = path.join(projectDir, claudeShared, 'health-check.md');
      assert(
        (await fs.pathExists(copied)) &&
          (await fs.readFile(copied)).equals(await fs.readFile(path.join(srcDir, 'shared', 'health-check.md'))),
        "no _bmad/: shared/ holds SKF's copy again",
      );
    });

    await inHome('skf update with an unlisted IDE copy matching the installed _bmad/skf/ alone', async (home, projectDir) => {
      await realInstall(projectDir, ['claude-code', 'cursor']);
      // The installed version's health-check.md, other bytes than src/: only _bmad/skf/ matches the cursor copy.
      const older = '# health check as the installed version shipped it\n';
      await fs.writeFile(path.join(projectDir, '_bmad', 'skf', 'shared', 'health-check.md'), older);
      const cursorCopy = path.join(projectDir, '.cursor', 'skills', 'shared', 'health-check.md');
      await fs.writeFile(cursorCopy, older);
      const cursorDir = path.join('.cursor', 'skills');
      await editManifest(projectDir, (manifest) => {
        manifest.files.ide_skills = manifest.files.ide_skills.filter((file) => !file.startsWith(`${cursorDir}${path.sep}`));
      });
      const run = await updateRun(home, projectDir);
      assert(succeeded(run), 'installed bytes: skf update succeeds, the cursor copy matched against _bmad/skf/', run.output);
      assert(
        (await fs.readFile(cursorCopy)).equals(await fs.readFile(path.join(srcDir, 'shared', 'health-check.md'))),
        "installed bytes: the cursor copy is replaced with src/'s",
      );
    });

    await inHome('skf update with user files in IDE folders it does not install into', async (home, projectDir) => {
      await realInstall(projectDir, ['claude-code', 'cursor']);
      await realInstall(projectDir, ['claude-code']);
      await writeFile(path.join(projectDir, '.cursor', 'skills', 'shared', 'mine.md'), '# mine, in the dropped IDE\n');
      await writeFile(path.join(projectDir, '.github', 'skills', 'shared', 'SKILL.md'), '# my copilot shared skill\n');
      const others = ['.cursor', '.github'];
      const before = await Promise.all(others.map((folder) => snapshot(path.join(projectDir, folder))));
      const run = await updateRun(home, projectDir);
      assert(succeeded(run), 'unselected IDE folders: skf update succeeds', run.output);
      const after = await Promise.all(others.map((folder) => snapshot(path.join(projectDir, folder))));
      assert(
        sameSnapshot(before, after),
        'unselected IDE folders: skf update changes nothing in them',
        snapshotDiff(before.flat(), after.flat()),
      );
    });

    await inHome('skf update with an SKF path holding other bytes in a knowledge/ copy', async (home, projectDir) => {
      await realInstall(projectDir, ['claude-code']);
      await fs.copy(path.join(projectDir, '_bmad', 'skf', 'knowledge'), path.join(projectDir, claudeKnowledge));
      const overview = path.join(claudeKnowledge, 'overview.md');
      await fs.writeFile(path.join(projectDir, overview), '# my own overview\n');
      const run = await updateRun(home, projectDir);
      assert(succeeded(run), 'knowledge/ path with other bytes: skf update succeeds', run.output);
      assert(
        JSON.stringify(await fs.readdir(path.join(projectDir, claudeKnowledge))) === '["overview.md"]' &&
          (await fs.readFile(path.join(projectDir, overview), 'utf8')) === '# my own overview\n',
        'knowledge/ path with other bytes: the matching files go and overview.md stays with its bytes',
      );
      assert(
        JSON.stringify(warnedLines(run.output, IDE_KEPT_HEADER)) === JSON.stringify([overview]),
        'knowledge/ path with other bytes: the update names overview.md',
        run.output,
      );
    });

    await inHome('uninstall with a plain-file shared and unreadable folders in support folders', async (home, projectDir) => {
      await writeTestManifest(projectDir);
      const cursor = path.join(projectDir, '.cursor', 'skills');
      await writeFile(path.join(cursor, 'shared'), 'not a folder\n');
      await copyFromSrc(path.join('knowledge', 'zero-hallucination.md'), path.join(cursor, 'knowledge', 'zero-hallucination.md'));
      const locked = [path.join('.cursor', 'skills', 'knowledge', 'locked'), path.join('.github', 'skills', 'shared', 'locked')];
      for (const folder of locked) await writeFile(path.join(projectDir, folder, 'notes.md'), '# locked\n');
      let run;
      if (!noChmod) for (const folder of locked) await fs.chmod(path.join(projectDir, folder), 0o000);
      try {
        run = await runUninstallAction(projectDir);
      } finally {
        // Restored before the checks and before the home folder goes, which need to read it.
        if (!noChmod) for (const folder of locked) await fs.chmod(path.join(projectDir, folder), 0o755);
      }
      const lines = planLines(run.output);
      assert(exitedZero(run), 'plain file and unreadable folders: uninstall exits 0', JSON.stringify(run.exits) + run.output);
      assert(
        lines.includes('× SKF skills (.cursor/skills/, 1 entry, knowledge/ among them)') &&
          !lines.some((line) => line.includes('.github/skills')),
        'plain file and unreadable folders: the plan counts knowledge/ alone and has no .github/skills/ line',
        lines.join(' | '),
      );
      // Where a folder cannot be made unreadable (Windows, root), its notes.md is the kept user file instead.
      const keptEntry = noChmod ? path.join(locked[0], 'notes.md') : locked[0];
      assert(
        JSON.stringify(warnedLines(run.output, IDE_KEPT_HEADER)) === JSON.stringify([keptEntry]),
        'plain file and unreadable folders: the warning names knowledge/locked alone',
        run.output,
      );
      assert(
        (await fs.readFile(path.join(cursor, 'shared'), 'utf8')) === 'not a folder\n' &&
          !(await fs.pathExists(path.join(cursor, 'knowledge', 'zero-hallucination.md'))) &&
          (await Promise.all(locked.map((folder) => fs.pathExists(path.join(projectDir, folder, 'notes.md'))))).every(Boolean),
        'plain file and unreadable folders: the shared file and both locked folders stay, the knowledge copy goes',
      );
    });
  } finally {
    UI.prototype.promptInstall = origPrompt;
    UI.prototype.displaySuccess = origSuccess;
  }

  console.log('');
}

// ============================================================
// Runner
// ============================================================

async function runTests() {
  console.log(`${colors.cyan}========================================`);
  console.log('SKF CLI Integration Tests');
  console.log(`========================================${colors.reset}\n`);

  await testFreshInstall();
  await testUpdatePreservesConfig();
  await testUninstallCleansUp();
  await testIdeCommandGeneration();
  await testManifestAccuracy();
  await testFreshInstallWithoutLearning();
  await testGitignoreEntries();
  await testToolReport();
  await testToolReportHangingStub();
  await testToolReportIgnoresProjectBinaries();
  await testToolReportWindowsShims();
  await testCompareVersions();
  await testInstallAndUpdateReturn();
  await testCliPrintsReportAndNotice();
  await testCliStopsProbesWithoutReport();
  await testSkillCheckVersionFromPackage();
  await testTesslVersionFromItsBinary();
  await testProjectRootFolderValues();
  await testLeftoverProjectRootFolder();
  await testUninstallGuardedRemoval();
  await testIdeSkillFoldersKeepUserFiles();

  console.log(`${colors.cyan}========================================`);
  console.log('Test Results:');
  console.log(`  Passed: ${colors.green}${passed}${colors.reset}`);
  console.log(`  Failed: ${colors.red}${failed}${colors.reset}`);
  console.log(`========================================${colors.reset}\n`);

  if (failed === 0) {
    console.log(`${colors.green}✨ All CLI integration tests passed!${colors.reset}\n`);
    process.exit(0);
  } else {
    console.log(`${colors.red}❌ Some CLI integration tests failed${colors.reset}\n`);
    process.exit(1);
  }
}

runTests().catch((error) => {
  console.error(`${colors.red}Test runner failed:${colors.reset}`, error.message);
  console.error(error.stack);
  process.exit(1);
});
