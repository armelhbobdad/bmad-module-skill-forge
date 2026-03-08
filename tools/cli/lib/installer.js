/**
 * SKF Installer - Core orchestrator
 * Copies SKF source files, compiles agents, creates folder structure.
 */

const path = require('node:path');
const fs = require('fs-extra');
const ora = require('ora');
const yaml = require('js-yaml');
const { compileAgentFile } = require('./compiler');
const { generateIdeCommands } = require('./ide-commands');

class Installer {
  constructor() {
    // Resolve directories relative to this file (tools/cli/lib/ -> up 3 levels)
    const repoRoot = path.resolve(__dirname, '..', '..', '..');
    this.srcDir = path.join(repoRoot, 'src');
    this.docsDir = path.join(repoRoot, 'docs');
  }

  async install(config) {
    const { projectDir, skfFolder } = config;
    const skfDir = path.join(projectDir, skfFolder);
    const action = config._action || 'fresh';

    // Handle update vs fresh for existing installation
    if (action === 'update' && (await fs.pathExists(skfDir))) {
      const configPath = path.join(skfDir, 'config.yaml');
      if (!config._savedConfigYaml && (await fs.pathExists(configPath))) {
        config._savedConfigYaml = await fs.readFile(configPath, 'utf8');
      }

      // On update, extract settings from saved config
      if (config._savedConfigYaml) {
        try {
          const savedData = yaml.load(config._savedConfigYaml);
          if (!config.ides && savedData.ides) config.ides = savedData.ides;
          if (!config.skills_output_folder && savedData.skills_output_folder) config.skills_output_folder = savedData.skills_output_folder;
          if (!config.forge_data_folder && savedData.forge_data_folder) config.forge_data_folder = savedData.forge_data_folder;
        } catch {
          /* ignore parse errors, defaults will apply */
        }
      }

      const removeSpinner = ora('Updating SKF files...').start();
      await fs.remove(skfDir);
      removeSpinner.succeed('Old files cleared');
    } else if (action === 'fresh' && (await fs.pathExists(skfDir))) {
      const removeSpinner = ora('Removing existing SKF installation...').start();
      await fs.remove(skfDir);
      removeSpinner.succeed('Old installation removed');
    }

    // Ensure parent directory exists (for _bmad/skf/)
    await fs.ensureDir(path.dirname(skfDir));

    console.log('');

    // Step 1: Copy source files
    const spinner = ora('Copying SKF files...').start();
    try {
      await this.copySrcFiles(skfDir);
      spinner.succeed('SKF files copied');
    } catch (error) {
      spinner.fail('Failed to copy SKF files');
      throw error;
    }

    // Step 2: Setup agent sidecar
    const sidecarSpinner = ora('Setting up agent sidecar...').start();
    try {
      await this.setupSidecar(projectDir);
      sidecarSpinner.succeed('Agent sidecar initialized');
    } catch (error) {
      sidecarSpinner.fail('Failed to setup sidecar');
      throw error;
    }

    // Step 3: Write config.yaml
    const configSpinner = ora('Writing configuration...').start();
    try {
      await this.writeConfig(skfDir, config);
      configSpinner.succeed('Configuration saved');
    } catch (error) {
      configSpinner.fail('Failed to write configuration');
      throw error;
    }

    // Step 4: Compile agents
    const agentSpinner = ora('Compiling agents...').start();
    try {
      const agents = await this.compileAgents(skfDir, skfFolder);
      agentSpinner.succeed(`Compiled ${agents.length} agent${agents.length === 1 ? '' : 's'}`);
    } catch (error) {
      agentSpinner.fail('Failed to compile agents');
      throw error;
    }

    // Step 5: Create output folders
    const foldersSpinner = ora('Creating project folders...').start();
    try {
      await this.createOutputFolders(projectDir, config);
      foldersSpinner.succeed('Project folders created');
    } catch (error) {
      foldersSpinner.fail('Failed to create project folders');
      throw error;
    }

    // Step 6: Copy learning material (optional)
    if (config.install_learning !== false) {
      const learnSpinner = ora('Copying learning & reference material...').start();
      try {
        await this.copyLearningMaterial(projectDir);
        learnSpinner.succeed('Learning material added to _skf-learn/ (safe to remove when no longer needed)');
      } catch (error) {
        learnSpinner.fail('Failed to copy learning material');
        throw error;
      }
    }

    // Step 7: Generate IDE command files
    const selectedIdes = config.ides || [];
    if (selectedIdes.length > 0 && !selectedIdes.every((ide) => ide === 'other')) {
      const ideSpinner = ora('Generating IDE commands...').start();
      try {
        const ideResult = await generateIdeCommands(projectDir, skfFolder, selectedIdes);
        if (ideResult.generated > 0) {
          ideSpinner.succeed(`IDE commands generated for ${ideResult.ides.join(', ')}`);
        } else {
          ideSpinner.info('No IDE commands to generate');
        }
      } catch (error) {
        ideSpinner.fail('Failed to generate IDE commands');
        throw error;
      }
    }

    return { success: true, skfDir, projectDir };
  }

  /**
   * Copy src/ content into the target SKF directory.
   * Workflows are placed under a skillforge/ subdirectory to match agent path references.
   */
  async copySrcFiles(skfDir) {
    // Copy agents and knowledge directly
    for (const dir of ['agents', 'knowledge']) {
      const src = path.join(this.srcDir, dir);
      const dest = path.join(skfDir, dir);
      if (await fs.pathExists(src)) {
        await fs.copy(src, dest);
      }
    }

    // Workflows go under workflows/skillforge/ to match agent YAML paths
    const workflowsSrc = path.join(this.srcDir, 'workflows');
    const workflowsDest = path.join(skfDir, 'workflows', 'skillforge');
    if (await fs.pathExists(workflowsSrc)) {
      await fs.copy(workflowsSrc, workflowsDest);
    }

    // Copy module.yaml and module-help.csv
    for (const file of ['module.yaml', 'module-help.csv']) {
      const src = path.join(this.srcDir, file);
      if (await fs.pathExists(src)) {
        await fs.copy(src, path.join(skfDir, file));
      }
    }
  }

  /**
   * Setup the ferris sidecar directory with template files.
   * Existing sidecar files are preserved (they contain user state).
   */
  async setupSidecar(projectDir) {
    const sidecarDir = path.join(projectDir, '_bmad', '_memory', 'forger-sidecar');
    await fs.ensureDir(sidecarDir);

    const forgerSrc = path.join(this.srcDir, 'forger');
    if (await fs.pathExists(forgerSrc)) {
      const files = await fs.readdir(forgerSrc);
      for (const file of files) {
        if (file.endsWith('.yaml') || file.endsWith('.yml')) {
          const dest = path.join(sidecarDir, file);
          // Don't overwrite existing sidecar files (preserves user state)
          if (!(await fs.pathExists(dest))) {
            await fs.copy(path.join(forgerSrc, file), dest);
          }
        }
      }
    }
  }

  async writeConfig(skfDir, config) {
    // On update, restore the user's existing config
    if (config._savedConfigYaml) {
      await fs.writeFile(path.join(skfDir, 'config.yaml'), config._savedConfigYaml, 'utf8');
      return;
    }

    // Get user name from git or system
    const getUserName = () => {
      try {
        const { execSync } = require('node:child_process');
        return execSync('git config user.name', { encoding: 'utf8' }).trim() || 'Developer';
      } catch {
        return 'Developer';
      }
    };

    const configData = {
      user_name: getUserName(),
      project_name: config.project_name || 'Untitled Project',
      communication_language: 'en',
      document_output_language: 'en',
      skills_output_folder: config.skills_output_folder || 'skills',
      forge_data_folder: config.forge_data_folder || 'forge-data',
      skf_folder: config.skfFolder,
      ides: config.ides || [],
    };

    const yamlStr = yaml.dump(configData, { lineWidth: -1 });
    await fs.writeFile(path.join(skfDir, 'config.yaml'), `# SKF Configuration - Generated by installer\n${yamlStr}`, 'utf8');
  }

  async compileAgents(skfDir, skfFolder) {
    const agentsDir = path.join(skfDir, 'agents');
    const files = await fs.readdir(agentsDir);
    const agentFiles = files.filter((f) => f.endsWith('.agent.yaml'));
    const results = [];

    for (const file of agentFiles) {
      const yamlPath = path.join(agentsDir, file);
      const result = compileAgentFile(yamlPath, { skfFolder });
      results.push(result);
    }

    return results;
  }

  async createOutputFolders(projectDir, config) {
    const skillsFolder = config.skills_output_folder || 'skills';
    const forgeDataFolder = config.forge_data_folder || 'forge-data';

    for (const folder of [skillsFolder, forgeDataFolder]) {
      const folderPath = path.join(projectDir, folder);
      if (!(await fs.pathExists(folderPath))) {
        await fs.ensureDir(folderPath);
        await fs.writeFile(path.join(folderPath, '.gitkeep'), '# This file ensures the directory is tracked by git\n');
      }
    }
  }

  async copyLearningMaterial(projectDir) {
    const learnDir = path.join(projectDir, '_skf-learn');
    if (await fs.pathExists(this.docsDir)) {
      await fs.copy(this.docsDir, learnDir, {
        filter: (srcPath) => {
          // Skip website-specific files
          return !path.basename(srcPath).startsWith('404');
        },
      });
    }
  }
}

module.exports = { Installer };
