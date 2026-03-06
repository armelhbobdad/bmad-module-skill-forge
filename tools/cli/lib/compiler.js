/**
 * SKF Agent Compiler
 * Compiles agent YAML to activated Markdown with embedded XML.
 * Adapted from BMAD's standard agent compilation pipeline.
 */

const yaml = require('js-yaml');
const fs = require('node:fs');
const path = require('node:path');

// --- XML Utility ---

function escapeXml(text) {
  if (!text) return '';
  return text.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&apos;');
}

// --- XML Builder Functions ---

function buildFrontmatter(metadata, agentName) {
  const nameFromFile = agentName.replaceAll('-', ' ');
  const description = metadata.title || 'SKF Agent';

  return `---
name: "${nameFromFile}"
description: "${description}"
---

You must fully embody this agent's persona and follow all activation instructions exactly as specified. NEVER break character until given an exit command.

`;
}

function buildPersonaXml(persona) {
  if (!persona) return '';

  let xml = '  <persona>\n';

  const fields = ['role', 'identity', 'communication_style', 'working_style'];
  for (const field of fields) {
    if (persona[field]) {
      const text = persona[field].trim().replaceAll(/\n+/g, ' ').replaceAll(/\s+/g, ' ');
      xml += `    <${field}>${escapeXml(text)}</${field}>\n`;
    }
  }

  if (persona.principles) {
    let principlesText;
    if (Array.isArray(persona.principles)) {
      principlesText = persona.principles.join(' ');
    } else {
      principlesText = persona.principles.trim().replaceAll(/\n+/g, ' ');
    }
    xml += `    <principles>${escapeXml(principlesText)}</principles>\n`;
  }

  xml += '  </persona>\n';
  return xml;
}

function buildPromptsXml(prompts) {
  if (!prompts || prompts.length === 0) return '';

  let xml = '  <prompts>\n';
  for (const prompt of prompts) {
    xml += `    <prompt id="${prompt.id || ''}">\n`;
    xml += '      <content>\n';
    xml += `${prompt.content || ''}\n`;
    xml += '      </content>\n';
    xml += '    </prompt>\n';
  }
  xml += '  </prompts>\n';
  return xml;
}

function buildMemoriesXml(memories) {
  if (!memories || memories.length === 0) return '';

  let xml = '  <memories>\n';
  for (const memory of memories) {
    xml += `    <memory>${escapeXml(String(memory))}</memory>\n`;
  }
  xml += '  </memories>\n';
  return xml;
}

function detectUsedHandlers(menuItems) {
  const used = new Set();
  if (!menuItems) return used;

  for (const item of menuItems) {
    if (item.workflow) used.add('workflow');
    if (item.exec) used.add('exec');
    if (item.data) used.add('data');
    if (item.action) used.add('action');
    if (item.multi) used.add('multi');
  }
  return used;
}

function buildActivationBlock(agent, skfFolder) {
  const criticalActions = agent.critical_actions || [];

  let stepNum = 4;
  let agentSteps = '';
  for (const action of criticalActions) {
    agentSteps += `    <step n="${stepNum}">${action}</step>\n`;
    stepNum++;
  }

  const menuStep = stepNum;
  const haltStep = stepNum + 1;
  const inputStep = stepNum + 2;
  const executeStep = stepNum + 3;

  let xml = `  <activation critical="MANDATORY">
    <step n="1">Load persona from this current agent file (already in context)</step>
    <step n="2">IMMEDIATE ACTION REQUIRED - BEFORE ANY OUTPUT:
        - Load and read {project-root}/${skfFolder}/config.yaml NOW
        - Store ALL fields as session variables: {user_name}, {communication_language}, {skills_output_folder}, {forge_data_folder}, {project_name}
        - VERIFY: If config not loaded, STOP and report error to user
        - DO NOT PROCEED to step 3 until config is successfully loaded and variables stored
    </step>
    <step n="3">Remember: user's name is {user_name}</step>
${agentSteps}    <step n="${menuStep}">Show greeting using {user_name} from config, communicate in {communication_language}, then display numbered list of ALL menu items from menu section</step>
    <step n="${haltStep}">STOP and WAIT for user input - do NOT execute menu items automatically - accept number or cmd trigger or fuzzy command match</step>
    <step n="${inputStep}">On user input: Number -> execute menu item[n] | Text -> case-insensitive substring match | Multiple matches -> ask user to clarify | No match -> show "Not recognized"</step>
    <step n="${executeStep}">When executing a menu item: Check menu-handlers section below - extract any attributes from the selected menu item (workflow, exec, data, action) and follow the corresponding handler instructions</step>

    <menu-handlers>
      <handlers>
`;

  const used = detectUsedHandlers(agent.menu);

  if (used.has('workflow')) {
    xml += `    <handler type="workflow">
      When menu item has: workflow="path/to/workflow.md":
      1. Load and read the complete workflow file at the specified path
      2. Follow all steps and instructions within the workflow file precisely
      3. Save outputs after completing EACH workflow step (never batch multiple steps together)
      4. If workflow path is "todo", inform user the workflow hasn't been implemented yet
    </handler>
`;
  }

  if (used.has('exec')) {
    xml += `    <handler type="exec">
      When menu item or handler has: exec="path/to/file.md":
      1. Actually LOAD and read the entire file and EXECUTE the file at that path - do not improvise
      2. Read the complete file and follow all instructions within it
      3. If there is data="some/path/data-foo.md" with the same item, pass that data path to the executed file as context.
    </handler>
`;
  }

  if (used.has('data')) {
    xml += `    <handler type="data">
      When menu item has: data="path/to/file.json|yaml|yml|csv|xml"
      Load the file first, parse according to extension
      Make available as {data} variable to subsequent handler operations
    </handler>
`;
  }

  if (used.has('action')) {
    xml += `    <handler type="action">
      When menu item has: action="#id" -> Find prompt with id="id" in current agent XML, execute its content
      When menu item has: action="text" -> Execute the text directly as an inline instruction
    </handler>
`;
  }

  if (used.has('multi')) {
    xml += `    <handler type="multi">
       When menu item has: type="multi" with nested handlers
       1. Display the multi item text as a single menu option
       2. Parse all nested handlers within the multi item
       3. For each nested handler:
          - Use the 'match' attribute for fuzzy matching user input (or Exact Match of character code in brackets [])
          - Execute based on handler attributes (exec, workflow, action)
       4. When user input matches a handler's 'match' pattern:
          - For exec="path/to/file.md": follow the handler type="exec" instructions
          - For workflow="path/to/workflow.md": follow the handler type="workflow" instructions
          - For action="...": Perform the specified action directly
       5. Support both exact matches and fuzzy matching based on the match attribute
       6. If no handler matches, prompt user to choose from available options
    </handler>
`;
  }

  xml += `      </handlers>
    </menu-handlers>

    <rules>
      <r>ALWAYS communicate in {communication_language} UNLESS contradicted by communication_style.</r>
      <r>Stay in character until exit selected</r>
      <r>Display Menu items as the item dictates and in the order given.</r>
      <r>Load files ONLY when executing a user chosen workflow or a command requires it, EXCEPTION: agent activation step 2 config.yaml</r>
    </rules>

    <output-discipline critical="MANDATORY">
      <r>Keep responses focused: address ONE topic per message, then invite follow-up.</r>
      <r>Be concise: use bullet points over paragraphs. If a response exceeds 300 words, split into parts.</r>
      <r>Lead with the actionable content. Place context and rationale AFTER the main point.</r>
      <r>Never repeat information the user already confirmed. Reference it, do not restate it.</r>
      <r>When presenting options, use numbered lists. Maximum 5 options before asking to narrow scope.</r>
    </output-discipline>
  </activation>
`;

  return xml;
}

function buildMenuXml(menuItems) {
  let xml = '  <menu>\n';
  xml += '    <item cmd="MH or fuzzy match on menu or help">[MH] Redisplay Menu Help</item>\n';

  if (menuItems && menuItems.length > 0) {
    for (const item of menuItems) {
      if (item.trigger) {
        const attrs = [`cmd="${item.trigger}"`];
        if (item.workflow) attrs.push(`workflow="${item.workflow}"`);
        if (item.exec) attrs.push(`exec="${item.exec}"`);
        if (item.data) attrs.push(`data="${item.data}"`);
        if (item.action) attrs.push(`action="${escapeXml(typeof item.action === 'string' ? item.action : JSON.stringify(item.action))}"`);
        xml += `    <item ${attrs.join(' ')}>${escapeXml(item.description || '')}</item>\n`;
      }
    }
  }

  xml += '    <item cmd="DA or fuzzy match on exit, leave, goodbye or dismiss agent">[DA] Dismiss Agent</item>\n';
  xml += '  </menu>\n';
  return xml;
}

// --- Path Rewriting ---

function rewritePaths(content, skfFolder) {
  let result = content;
  // Handle {bmad_folder} variable form
  result = result.replaceAll('{bmad_folder}/skf/', `${skfFolder}/`);
  result = result.replaceAll('{project-root}/{bmad_folder}/skf/', `{project-root}/${skfFolder}/`);
  // Handle hardcoded _bmad/skf/ form
  result = result.replaceAll('_bmad/skf/', `${skfFolder}/`);
  return result;
}

// --- Main Compilation ---

function compileAgentFile(yamlPath, options = {}) {
  const skfFolder = options.skfFolder || '_bmad/skf';
  const rawContent = fs.readFileSync(yamlPath, 'utf8');

  // Rewrite paths before parsing
  const rewrittenContent = rewritePaths(rawContent, skfFolder);
  const agentYaml = yaml.load(rewrittenContent);
  const agent = agentYaml.agent;
  const meta = agent.metadata;

  const basename = path.basename(yamlPath, '.agent.yaml');

  let output = '';

  // Frontmatter
  output += buildFrontmatter(meta, meta.name || basename);

  // Start XML code fence
  output += '```xml\n';

  // Agent opening tag
  const agentId = `${skfFolder}/agents/${basename}.md`;
  const agentAttrs = [`id="${agentId}"`, `name="${meta.name || ''}"`, `title="${meta.title || ''}"`, `icon="${meta.icon || ''}"`];
  output += `<agent ${agentAttrs.join(' ')}>\n`;

  // Activation block
  output += buildActivationBlock(agent, skfFolder);

  // Persona
  output += buildPersonaXml(agent.persona);

  // Prompts
  if (agent.prompts && agent.prompts.length > 0) {
    output += buildPromptsXml(agent.prompts);
  }

  // Memories
  if (agent.memories && agent.memories.length > 0) {
    output += buildMemoriesXml(agent.memories);
  }

  // Menu
  output += buildMenuXml(agent.menu || []);

  // Close
  output += '</agent>\n';
  output += '```\n';

  // Write output
  const outputPath = options.outputPath || yamlPath.replace('.agent.yaml', '.md');
  fs.writeFileSync(outputPath, output, 'utf8');

  return { outputPath, metadata: meta, agentName: basename };
}

module.exports = { compileAgentFile };
