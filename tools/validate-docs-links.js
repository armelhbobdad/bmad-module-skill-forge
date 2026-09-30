/**
 * Validate documentation links, in the source AND in the built site.
 *
 * WHY THIS EXISTS
 *
 * `docs/` is read in two places: rendered on GitHub, and published as the
 * site. A link can be valid in one and dead in the other, and nothing fails
 * on it: an href that resolves nowhere is still valid HTML, so Astro builds
 * clean and markdownlint has no opinion. `validate-doc-links.js` covers the
 * source side (site-absolute targets and anchors) but never sees the built
 * output, so a link that is correct in the Markdown and wrong as a route
 * passes every check and ships.
 *
 * A source-only check is therefore NOT sufficient, and that is the lesson
 * this tool encodes. Rewriting happens between the Markdown and the page:
 * `website/src/rehype-markdown-links.js` turns `.md` targets into routes, so
 * a bug there produces hrefs that look right in source and 404 in a browser.
 * Only resolving the BUILT output against the file tree catches that class.
 *
 * So there are two passes:
 *
 *   1. SOURCE  (docs/ *.md, including docs/_internal/, plus CONTRIBUTING.md,
 *              README.md and changes/README.md) - every relative target must
 *              exist on disk, and every `#anchor`, same-file or on a `.md`
 *              target, must match a heading id in that file. Cheap, and
 *              catches a typo or a renamed heading before a build is needed.
 *   2. BUILT   (build/site/ *.html) - every internal href must resolve to a
 *              real file, and its `#fragment` to an id on that page. This is
 *              the pass that catches plugin bugs, base-path bugs, and anything
 *              else that only manifests as a route.
 *
 * The heading-to-id rules live here, in `extractAnchors`, and
 * `validate-doc-links.js` requires them, so both checkers agree on every id.
 *
 * The built pass is skipped with a warning when no build is present, so the
 * tool stays usable locally without a build step. CI builds the site, so the
 * pass runs there. Use --require-build to make a missing build an error.
 *
 * Usage:
 *   node tools/validate-docs-links.js [--strict] [--verbose] [--require-build]
 */

const fs = require('node:fs');
const path = require('node:path');

/** Hosts/schemes that are never local links. */
const EXTERNAL = /^(?:[a-z][a-z0-9+.-]*:|\/\/)/i;

/**
 * Read a `--flag value` pair out of an argv array.
 *
 * @param {string[]} argv - Arguments to search
 * @param {string} name - Flag name, including leading dashes
 * @returns {string|undefined} The value, or undefined when absent
 */
function flagValue(argv, name) {
  const at = argv.indexOf(name);
  return at === -1 ? undefined : argv[at + 1];
}

/**
 * Resolve where to look, from argv, defaulting to this repository.
 *
 * The directory overrides exist so the checks can be pointed at a fixture
 * tree. Without them every path derives from `__dirname` and the tool can
 * only ever inspect its own repo, which makes it untestable: the logic that
 * decides whether a merge is blocked would itself be unverified.
 *
 * @param {string[]} [argv] - Defaults to the real process arguments
 * @returns {{projectRoot: string, docsDir: string, buildDir: string, strict: boolean, verbose: boolean, requireBuild: boolean}} Config
 */
function resolveConfig(argv = process.argv.slice(2)) {
  const projectRoot = flagValue(argv, '--project-root') ?? path.resolve(__dirname, '..');

  return {
    projectRoot,
    docsDir: flagValue(argv, '--docs-dir') ?? path.join(projectRoot, 'docs'),
    buildDir: flagValue(argv, '--build-dir') ?? path.join(projectRoot, 'build', 'site'),
    strict: argv.includes('--strict'),
    verbose: argv.includes('--verbose'),
    requireBuild: argv.includes('--require-build'),
  };
}

/**
 * Recursively collect files with one of the given extensions.
 *
 * @param {string} dir - Directory to walk
 * @param {Set<string>} exts - Extensions to keep, with leading dot
 * @param {string[]} [out] - Accumulator
 * @returns {string[]} Absolute paths
 */
function walk(dir, exts, out = []) {
  let entries;
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch {
    return out;
  }

  for (const entry of entries) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === 'node_modules' || entry.name === '.git') {
        continue;
      }
      walk(full, exts, out);
    } else if (exts.has(path.extname(entry.name))) {
      out.push(full);
    }
  }

  return out;
}

/** Strip the query and anchor from an href, returning the path portion. */
function pathPortion(href) {
  const q = href.indexOf('?');
  const h = href.indexOf('#');
  const first = Math.min(q === -1 ? Infinity : q, h === -1 ? Infinity : h);
  return first === Infinity ? href : href.slice(0, first);
}

/**
 * The decoded fragment of an href, or '' when it has none.
 *
 * Browsers match the percent-decoded fragment against ids, so `#caf%C3%A9`
 * and `#café` name the same heading. A malformed escape is kept as written,
 * which then matches nothing and is reported.
 */
function fragmentOf(href) {
  const at = href.indexOf('#');
  if (at === -1) {
    return '';
  }
  const raw = href.slice(at + 1);
  try {
    return decodeURIComponent(raw);
  } catch {
    return raw;
  }
}

/**
 * Whether a fragment resolves on a page with these ids.
 *
 * An empty fragment and `#top` (any case) scroll to the top of the page by
 * the HTML standard, whether or not an element carries that id.
 */
function fragmentResolves(fragment, ids) {
  return fragment === '' || fragment.toLowerCase() === 'top' || ids.has(fragment);
}

// ---------------------------------------------------------------------------
// Pass 1: source
// ---------------------------------------------------------------------------

/** Markdown inline links: the target inside `](...)`. */
const MD_LINK = /\]\(([^)\s]+)(?:\s+"[^"]*")?\)/g;

/**
 * Blank out fenced code blocks, keeping every other line as it is.
 *
 * Fences are tracked line by line rather than matched as a pair, so an
 * unterminated fence blanks to end of file instead of silently reverting to
 * prose scanning. Line count is preserved, which keeps byte offsets usable if
 * this ever reports positions.
 *
 * @param {string} text - Raw Markdown
 * @returns {string} The same text with fenced blocks blanked
 */
function blankFences(text) {
  let fence = null;

  return text
    .split('\n')
    .map((line) => {
      const marker = line.match(/^\s{0,3}(`{3,}|~{3,})/);

      if (fence) {
        // A closing fence is the same character, and at least as long.
        if (marker && marker[1][0] === fence[0] && marker[1].length >= fence.length) {
          fence = null;
        }
        return '';
      }
      if (marker) {
        fence = marker[1];
        return '';
      }
      return line;
    })
    .join('\n');
}

/**
 * Blank out code so a link that is merely *shown* is not read as a real one.
 *
 * `MD_LINK` is a regex over raw text, so it cannot tell a link from a picture
 * of a link. Without this, documenting the link convention itself, e.g. a
 * ```markdown block containing [label](./example.md), fails the build as a
 * broken link, and the only way to appease it is to create the placeholder
 * file. (`tools/validate-file-refs.js` does NOT do this, so it carries the
 * same latent false positive; worth fixing there too if it ever fires.)
 *
 * Inline spans are only stripped outside a fence, so a stray backtick inside
 * a block cannot pair with one outside it.
 *
 * @param {string} text - Raw Markdown
 * @returns {string} The same text with fenced blocks and code spans blanked
 */
function blankCode(text) {
  return (
    blankFences(text)
      .split('\n')
      // Inline spans: a run of N backticks closes on a run of N.
      .map((line) => line.replaceAll(/(`+)[^`]*\1/g, ' '))
      .join('\n')
  );
}

// ---------------------------------------------------------------------------
// Heading ids
// ---------------------------------------------------------------------------

/**
 * Characters `github-slugger` deletes from a heading: everything except
 * alphabetic characters (letters, letter numbers, and symbols Unicode counts
 * as alphabetic, such as circled letters), marks, decimal digits, connector
 * punctuation (`_`), the ASCII space and the hyphen-minus. Other punctuation
 * (the em dash included), other symbols and emoji, other spaces and control
 * characters all go.
 */
const SLUG_STRIP = /[^\p{Alphabetic}\p{M}\p{Nd}\p{Pc} -]/gu;

/**
 * Convert heading text to the id GitHub gives it, and the site too except
 * for the two cases below.
 *
 * Must match `github-slugger`, which is what both GitHub and Starlight use to
 * generate heading ids. The distinction that matters: it replaces each space
 * INDIVIDUALLY and never collapses runs, so punctuation between words leaves a
 * doubled hyphen. `## Scenario A: Greenfield + BMM Integration` becomes
 * `scenario-a-greenfield--bmm-integration`, with two hyphens where the `+`
 * was. Collapsing them here produced a slug no page ever has, so a correct
 * anchor was reported broken.
 *
 * github-slugger itself is ESM-only and this tool is CommonJS in a synchronous
 * flow, hence the faithful reimplementation rather than a dependency. Its
 * table dates from Unicode 13, so a letter Unicode assigned later is dropped
 * there and kept here; for every other character the two agree.
 *
 * The site's Markdown pipeline (Astro, under Starlight) differs in two ways:
 * it trims one trailing hyphen off the id, and its SmartyPants step turns a
 * `--` outside code into a dash the slug then drops. So a heading that ends
 * in punctuation, or holds a `--`, gets different ids on GitHub and on the
 * site. The source pass checks GitHub's; the built pass reads the ids the
 * site actually carries.
 *
 * @param {string} text - Heading text as rendered, without Markdown syntax
 * @returns {string} The id, before any `-N` suffix for a repeat
 */
function headingToAnchor(text) {
  return text.toLowerCase().replaceAll(SLUG_STRIP, '').replaceAll(' ', '-');
}

/**
 * An ATX heading line: up to three spaces, one to six `#`, then a space or
 * the end of the line. `#tag` is a paragraph, not a heading. The `\r` of a
 * CRLF line ending is trailing space like any other.
 */
const ATX_HEADING = /^ {0,3}#{1,6}(?:[ \t]+(.*?))?[ \t\r]*$/;

/** Named entities a heading is likely to carry; numeric ones are decoded too. */
const ENTITIES = { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: '\u00A0' };

/**
 * Reduce the Markdown of a heading to the text a renderer slugs.
 *
 * Only what changes the id is handled. Characters the slugger deletes anyway
 * (`*`, `~`, brackets) need no care, but the ones it keeps do: a link's URL,
 * an image's alt text (a renderer drops it), an entity's name, and the `_`
 * of emphasis, which survives slugging where `*` does not. Code spans and
 * backslash escapes are literal text, so they are set aside first, behind
 * private-use placeholders that no heading carries.
 *
 * @param {string} raw - Heading content after the `#` markers
 * @returns {string} Plain text
 */
function headingText(raw) {
  const literals = [];
  const keep = (literal) => {
    literals.push(literal);
    return `\uE000${literals.length - 1}\uE001`;
  };
  const text = raw
    // A closing sequence of `#` is syntax when a space precedes it.
    .replace(/(?:^|[ \t]+)#+[ \t]*$/, '')
    // One space is stripped from each side of a code span when both have one.
    .replaceAll(/(`+)(.+?)\1(?!`)/g, (_, _ticks, body) =>
      keep(body.startsWith(' ') && body.endsWith(' ') && body.trim() ? body.slice(1, -1) : body),
    )
    // A backslash-escaped character is literal, never syntax.
    .replaceAll(/\\([!-/:-@[-`{-~])/g, (_, char) => keep(char))
    .replaceAll(/!\[[^\]]*\]\([^)]*\)/g, '')
    .replaceAll(/\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replaceAll(/\[([^\]]*)\]\[[^\]]*\]/g, '$1')
    .replaceAll(/<((?:https?|mailto):[^>\s]*)>/gi, '$1')
    .replaceAll(/<\/?[a-z][^>]*>/gi, '')
    .replaceAll(/(^|[^\p{L}\p{N}_])(__?)(?=\S)(.*?\S)\2(?![\p{L}\p{N}_])/gu, '$1$3')
    .replaceAll(/&(#x[\da-f]+|#\d+|[a-z]+);/gi, (entity, name) => {
      if (name[0] === '#') {
        const code = /x/i.test(name[1]) ? Number.parseInt(name.slice(2), 16) : Number(name.slice(1));
        return code > 0 && code <= 0x10_ff_ff ? String.fromCodePoint(code) : '\uFFFD';
      }
      return ENTITIES[name.toLowerCase()] ?? entity;
    });

  // No trim: the heading line was trimmed already, and space left beside a
  // dropped image or tag is still in the rendered text, so it is in the id.
  return text.replaceAll(/\uE000(\d+)\uE001/g, (_, index) => literals[Number(index)]);
}

/**
 * Blank out a leading YAML front matter block, keeping the line count.
 *
 * Its `# ` lines are YAML comments, not headings.
 */
function blankFrontMatter(text) {
  const lines = text.split('\n');
  if (lines[0].trimEnd() !== '---') {
    return text;
  }
  const end = lines.findIndex((line, index) => index > 0 && /^(?:---|\.\.\.)\s*$/.test(line));
  if (end === -1) {
    return text;
  }
  return lines.map((line, index) => (index <= end ? '' : line)).join('\n');
}

/**
 * Collect the id of every heading in a Markdown file.
 *
 * Repeated headings are disambiguated exactly as github-slugger does: the
 * first occurrence keeps the bare slug and each later one gets `-N` appended,
 * counting from 1, skipping any id an earlier heading already took. A
 * stateless slug function would collect only the first of several same-named
 * headings and report a link to any later one as broken.
 *
 * Fenced code is skipped. A shell comment in a ```bash block starts with `# `
 * like a heading, and reading the raw file counted every one of them, so a
 * link to a comment passed as a link to a section. Front matter is skipped
 * for the same reason. Only ATX headings are read: a setext heading (text
 * underlined with `===` or `---`) gets no id here.
 *
 * @param {string} content - Raw Markdown
 * @returns {Set<string>} Every heading id in the file
 */
function extractAnchors(content) {
  const anchors = new Set();
  const occurrences = new Map();

  for (const line of blankFences(blankFrontMatter(content)).split('\n')) {
    const match = line.match(ATX_HEADING);
    if (!match) {
      continue;
    }
    const base = headingToAnchor(headingText(match[1] ?? ''));
    let id = base;
    while (occurrences.has(id)) {
      const count = occurrences.get(base) + 1;
      occurrences.set(base, count);
      id = `${base}-${count}`;
    }
    occurrences.set(id, 0);
    anchors.add(id);
  }

  return anchors;
}

/**
 * Markdown files outside docs/ that the source pass reads too, relative to
 * the project root, each read when present.
 *
 * GitHub is the only place they render, so no build resolves their links: a
 * moved file or a renamed heading leaves them dead with every other check
 * green. Their relative targets resolve from their own folder, as on GitHub.
 */
const ROOT_DOCS = ['CONTRIBUTING.md', 'README.md', 'changes/README.md'];

/**
 * Check every relative link in the Markdown sources: the target must exist
 * on disk, and a `#anchor` must match a heading id in its file.
 *
 * Any target counts, not only `.md`: a workflow file, a folder or LICENSE is
 * as dead on GitHub when it moves. Anchors are checked on the same file and
 * on `.md` targets; GitHub gives other files line anchors, not heading ids.
 *
 * Deliberately does NOT enforce a `./` prefix. The plugin accepts bare links,
 * and GitHub renders them correctly, so requiring the prefix would be style,
 * not correctness. What matters is that the target exists.
 */
function checkSource({ projectRoot, docsDir }, report) {
  const files = [
    ...new Set([
      ...walk(docsDir, new Set(['.md'])),
      ...ROOT_DOCS.map((rel) => path.join(projectRoot, rel)).filter((file) => fs.existsSync(file)),
    ]),
  ];
  const anchorsByFile = new Map();
  const anchorsOf = (file) => {
    if (!anchorsByFile.has(file)) {
      anchorsByFile.set(file, extractAnchors(fs.readFileSync(file, 'utf8')));
    }
    return anchorsByFile.get(file);
  };

  for (const file of files) {
    const rel = path.relative(projectRoot, file);
    const dir = path.dirname(file);
    const text = blankCode(fs.readFileSync(file, 'utf8'));

    for (const match of text.matchAll(MD_LINK)) {
      const href = match[1];
      const target = pathPortion(href);
      const anchor = fragmentOf(href);

      if (EXTERNAL.test(href)) {
        continue;
      }
      if (!target) {
        if (!fragmentResolves(anchor, anchorsOf(file))) {
          report(rel, `anchor matches no heading in this file: ${href}`);
        }
        continue;
      }
      // Root-absolute targets mean different things on the two surfaces, and
      // this pass owns the GitHub one. GitHub resolves `/x.md` against the
      // REPOSITORY root (it rewrites the href to /<owner>/<repo>/blob/<ref>/x.md),
      // whereas the rewriter treats docs/ as the site root, so `/architecture.md`
      // becomes the valid route /architecture/ while pointing at a repo-root
      // file that does not exist. The built pass only ever sees the route, so
      // it cannot notice. Resolve against the repo root, which is the surface
      // this pass is responsible for.
      //
      // Note `/docs/architecture.md` is CORRECT on both: repo-root
      // docs/architecture.md exists, and the rewriter strips the `/docs`
      // prefix. Existence is the test, not the prefix.
      const resolved = target.startsWith('/') ? path.join(projectRoot, target) : path.resolve(dir, target);

      if (!fs.existsSync(resolved)) {
        report(
          rel,
          target.startsWith('/')
            ? `root-absolute link target does not exist at the repository root, so it is dead on GitHub: ${href}`
            : `link target does not exist: ${href}`,
        );
        continue;
      }
      if (target.endsWith('.md') && fs.statSync(resolved).isFile() && !fragmentResolves(anchor, anchorsOf(resolved))) {
        report(rel, `anchor matches no heading in ${path.relative(projectRoot, resolved)}: ${href}`);
      }
    }
  }

  return files.length;
}

// ---------------------------------------------------------------------------
// Pass 2: built output
// ---------------------------------------------------------------------------

/** Normalize a URL pathname into a base with exactly one trailing slash. */
function asBase(pathname) {
  if (!pathname || pathname === '/') {
    return '/';
  }
  return pathname.endsWith('/') ? pathname : `${pathname}/`;
}

/**
 * Resolve the base path the build on disk was actually produced with.
 *
 * Read from the ARTIFACT, not the environment. The environment can disagree
 * with the build (a site built with SITE_URL set, then validated without it),
 * and that disagreement makes every absolute href look broken: a loud, and
 * entirely false, failure. The root page's canonical URL is written by the
 * build itself, so it cannot drift from the output it describes.
 *
 * Falls back to the environment, then to '/', when no canonical is present.
 *
 * @returns {Promise<string>} The base path, e.g. '/repo/' or '/'
 */
async function resolveBase({ projectRoot, buildDir }) {
  const rootIndex = path.join(buildDir, 'index.html');

  if (fs.existsSync(rootIndex)) {
    const html = fs.readFileSync(rootIndex, 'utf8');
    const canonical =
      html.match(/<link[^>]+rel="canonical"[^>]+href="([^"]+)"/i) || html.match(/<meta[^>]+property="og:url"[^>]+content="([^"]+)"/i);

    if (canonical) {
      try {
        return asBase(new URL(canonical[1]).pathname);
      } catch {
        // Not an absolute URL; fall through to the environment.
      }
    }
  }

  try {
    const mod = await import(`file://${path.join(projectRoot, 'website', 'src', 'lib', 'site-url.js')}`);
    return asBase(new URL(mod.getSiteUrl()).pathname);
  } catch {
    return '/';
  }
}

/**
 * Every URL a page asks the browser to fetch: navigations AND subresources.
 *
 * `href` alone is not the whole surface. A missing `src` is the same defect
 * with a worse symptom: the browser fetches it without the user clicking, and
 * a 404 script or image degrades the page silently. This matters here because
 * assets under `website/public/` are copied verbatim and referenced by
 * hand-written string paths (see `mermaid-lightbox.js` in astro.config.mjs),
 * so renaming one leaves a green build and a dead reference on every page.
 *
 * `srcset` is a comma-separated candidate list where each entry is a URL
 * optionally followed by a width/density descriptor, so it is split apart.
 * The build emits no `srcset` today, only SVGs, but adding one raster image
 * to the docs would change that without touching this file.
 *
 * @param {string} html - Full page source
 * @returns {Array<{attr: string, url: string}>} References, in document order
 */
function assetUrls(html) {
  const refs = [];

  // `src` here never matches `srcset=`, which continues with `set=`.
  for (const match of html.matchAll(/\s(href|src)="([^"]*)"/g)) {
    refs.push({ attr: match[1], url: match[2] });
  }

  for (const match of html.matchAll(/\ssrcset="([^"]*)"/g)) {
    for (const candidate of match[1].split(',')) {
      const url = candidate.trim().split(/\s+/)[0];
      if (url) {
        refs.push({ attr: 'srcset', url });
      }
    }
  }

  return refs;
}

/**
 * Verify every internal reference in the built site resolves to a real file.
 *
 * Covers navigations (`href`) and subresources (`src`, `srcset`) alike: both
 * are URLs the page promises the browser it can fetch.
 *
 * A route ending in `/` must have an `index.html`; anything else must exist
 * as a file. Relative URLs are resolved against the page's own directory,
 * which is precisely how a browser resolves them, and precisely the step that
 * the earlier page-relative bug failed.
 *
 * An href's `#fragment` must match an id on the page it lands on, the same
 * page for a bare `#anchor`. These are the ids the site really carries, which
 * are not always GitHub's (see `headingToAnchor`), so a link that the source
 * pass accepts for GitHub and that misses on the site fails here.
 *
 * @param {string} base - Deployment base path
 * @returns {number} Number of HTML pages checked
 */
function checkBuilt({ projectRoot, buildDir }, base, report) {
  const pages = walk(buildDir, new Set(['.html']));
  const idsByPage = new Map();
  const idsOf = (page) => {
    if (!idsByPage.has(page)) {
      const html = fs.readFileSync(page, 'utf8');
      idsByPage.set(page, new Set(Array.from(html.matchAll(/\sid="([^"]*)"/g), (match) => match[1])));
    }
    return idsByPage.get(page);
  };

  for (const page of pages) {
    const rel = path.relative(projectRoot, page);
    const html = fs.readFileSync(page, 'utf8');
    // The page's URL directory, e.g. build/site/troubleshooting/index.html
    // is served at /troubleshooting/, so relative links resolve from there.
    const pageDir = path.dirname(page);

    const seen = new Set();

    for (const { attr, url: href } of assetUrls(html)) {
      if (!href || EXTERNAL.test(href) || seen.has(href)) {
        continue;
      }
      seen.add(href);

      const target = pathPortion(href);
      if (!target) {
        if (attr === 'href' && !fragmentResolves(fragmentOf(href), idsOf(page))) {
          report(rel, `href matches no id on this page: ${href}`);
        }
        continue;
      }

      let resolved;
      if (target.startsWith('/')) {
        // Root-absolute: strip the base, then read from the build root.
        let withoutBase = target;
        if (base !== '/' && target.startsWith(base)) {
          withoutBase = `/${target.slice(base.length)}`;
        } else if (base !== '/') {
          report(rel, `absolute ${attr} is missing the base path ${base}: ${href}`);
          continue;
        }
        resolved = path.join(buildDir, withoutBase);
      } else {
        resolved = path.resolve(pageDir, target);
      }

      // Never let a link escape the build root.
      if (!resolved.startsWith(buildDir + path.sep)) {
        report(rel, `${attr} escapes the site root: ${href}`);
        continue;
      }

      const candidate = target.endsWith('/') || !path.extname(resolved) ? path.join(resolved, 'index.html') : resolved;

      if (!fs.existsSync(candidate)) {
        report(rel, `${attr} resolves to nothing: ${href} (looked for ${path.relative(buildDir, candidate)})`);
        continue;
      }
      if (attr === 'href' && candidate.endsWith('.html') && !fragmentResolves(fragmentOf(href), idsOf(candidate))) {
        report(rel, `href matches no id on ${path.relative(buildDir, candidate)}: ${href}`);
      }
    }
  }

  return pages.length;
}

// ---------------------------------------------------------------------------

const BUILD_INFRA_INPUTS = [
  'website/src/rehype-markdown-links.js',
  'website/src/rehype-base-paths.js',
  'website/src/lib/site-url.js',
  'website/astro.config.mjs',
  'tools/build-docs.js',
];

/**
 * One sha1 per build input: the flat docs/*.md set plus BUILD_INFRA_INPUTS,
 * the route-shaping infrastructure (BOTH rehype rewriters, the base/site
 * resolver, the Astro config, and the builder itself). Canonical for both the
 * manifest writer in tools/build-docs.js and the freshness check below - the
 * first cut duplicated the list in both tools and both copies missed the
 * second rehype rewriter, which is exactly the drift a single owner prevents.
 */
function collectBuildInputs(projectRoot) {
  const crypto = require('node:crypto');
  const sha1 = (file) => crypto.createHash('sha1').update(fs.readFileSync(file)).digest('hex');
  const inputs = {};
  const docsDir = path.join(projectRoot, 'docs');
  if (fs.existsSync(docsDir)) {
    for (const name of fs.readdirSync(docsDir).sort()) {
      if (name.endsWith('.md')) {
        inputs[`docs/${name}`] = sha1(path.join(docsDir, name));
      }
    }
  }
  for (const rel of BUILD_INFRA_INPUTS) {
    const file = path.join(projectRoot, rel);
    if (fs.existsSync(file)) {
      inputs[rel] = sha1(file);
    }
  }
  return inputs;
}

/**
 * Compare the build-inputs manifest against the tree as it is NOW.
 *
 * Returns {state, changed}: state is 'missing' (no manifest - an older build,
 * nothing to compare), 'match', or 'stale' with the changed inputs listed.
 * A 'match' is deliberately NOT a freshness certificate: Astro's content cache
 * can replay a stale render against unchanged inputs, so a matching manifest
 * proves nothing - only a MISmatch proves staleness. That asymmetry is why the
 * stale branch speaks definitely and the match branch stays hedged.
 */
function buildInputsStatus({ projectRoot, buildDir }) {
  const manifestPath = path.join(path.dirname(buildDir), '.build-inputs.json');
  let manifest;
  try {
    manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf-8'));
  } catch {
    return { state: 'missing', changed: [] };
  }
  if (!manifest || typeof manifest.inputs !== 'object' || manifest.inputs === null) {
    return { state: 'missing', changed: [] };
  }
  const current = collectBuildInputs(projectRoot);
  const changed = [];
  for (const key of new Set([...Object.keys(manifest.inputs), ...Object.keys(current)])) {
    if (manifest.inputs[key] !== current[key]) {
      changed.push(key);
    }
  }
  changed.sort();
  return { state: changed.length > 0 ? 'stale' : 'match', changed };
}

/**
 * Resolve every site-internal link in the built llms.txt against the built
 * tree. This link class is invisible to the HTML pass (llms.txt is not HTML),
 * which is exactly how a deleted page's index entry survived every check.
 *
 * The site root is read off the file's own `Documentation: <url>` header line
 * rather than off the build base, so the check is independent of what base the
 * local render happened to use. No header, or no file: nothing to check -
 * reported as a count of 0, never as a pass over content that was not read.
 */
function checkLlmsIndex({ buildDir }, report) {
  const llmsPath = path.join(buildDir, 'llms.txt');
  let text;
  try {
    text = fs.readFileSync(llmsPath, 'utf-8');
  } catch {
    return 0;
  }
  const rootMatch = text.match(/^Documentation:\s+(\S+)$/m);
  if (!rootMatch) {
    return 0;
  }
  let rootPath;
  try {
    rootPath = new URL(rootMatch[1]).pathname;
  } catch {
    return 0;
  }
  if (!rootPath.endsWith('/')) {
    rootPath += '/';
  }
  let checked = 0;
  for (const match of text.matchAll(/\]\((\S+?)\)/g)) {
    const target = match[1];
    let url;
    try {
      url = new URL(target);
    } catch {
      continue; // relative or malformed: llms.txt only carries absolute links
    }
    if (!url.pathname.startsWith(rootPath)) {
      continue; // external link, not a site route
    }
    checked += 1;
    const route = url.pathname.slice(rootPath.length);
    const candidates =
      route === ''
        ? [path.join(buildDir, 'index.html')]
        : [path.join(buildDir, route.replace(/\/$/, ''), 'index.html'), path.join(buildDir, route)];
    if (!candidates.some((candidate) => fs.existsSync(candidate))) {
      report(
        'build/site/llms.txt',
        `links a route that resolves to nothing: ${target} (looked for ${candidates
          .map((candidate) => path.relative(buildDir, candidate))
          .join(' or ')})`,
      );
    }
  }
  return checked;
}

/**
 * Run both passes and return what happened, without touching the process.
 *
 * Separated from the CLI so tests can drive it against a fixture tree and
 * assert on the result rather than on stdout or an exit code.
 *
 * @param {object} cfg - From resolveConfig()
 * @param {(msg: string) => void} [log] - Output sink; defaults to console.log
 * @returns {Promise<{issues: Array<{file: string, detail: string}>, sourceCount: number, builtCount: number, haveBuild: boolean, missingRequiredBuild: boolean, ok: boolean}>} Outcome
 */
async function run(cfg, log = console.log) {
  const issues = [];
  const report = (file, detail) => issues.push({ file, detail });

  log(`\nValidating documentation links in: ${cfg.projectRoot}`);
  log(`Mode: ${cfg.strict ? 'STRICT (exit 1 on issues)' : 'ADVISORY'}`);
  log('');

  if (!fs.existsSync(cfg.docsDir)) {
    throw new Error(`docs/ not found at ${cfg.docsDir}`);
  }

  const sourceCount = checkSource(cfg, report);
  log(`Source pass:  ${sourceCount} markdown file(s) in docs/, plus ${ROOT_DOCS.join(', ')} where present`);

  let builtCount = 0;
  const haveBuild = fs.existsSync(cfg.buildDir);
  let missingRequiredBuild = false;

  if (haveBuild) {
    const base = await resolveBase(cfg);
    builtCount = checkBuilt(cfg, base, report);
    log(`Built pass:   ${builtCount} page(s) in build/site (base ${base})`);

    const llmsCount = checkLlmsIndex(cfg, report);
    log(`llms.txt:     ${llmsCount} site link(s) checked`);

    // This pass is only as honest as the build it reads. The manifest turns
    // "may be stale" into a definite STALE where inputs provably changed; a
    // matching manifest is still no freshness certificate, because Astro
    // caches rendered content in website/node_modules/.astro and that cache
    // survives both `rm -rf website/.astro` and a rebuild - a stale render can
    // report a clean pass against unchanged inputs (this bit the author while
    // writing this tool). CI is immune because `npm ci` starts cold.
    // Only the hedged branch is suppressed under --require-build (the CI
    // path); a provable STALE always speaks, since a cold CI build that
    // still mismatches its inputs is worth saying out loud.
    const freshness = buildInputsStatus(cfg);
    if (freshness.state === 'stale') {
      log('');
      log(`   STALE BUILD: ${freshness.changed.length} input(s) changed since this render:`);
      for (const name of freshness.changed.slice(0, 5)) {
        log(`     - ${name}`);
      }
      if (freshness.changed.length > 5) {
        log(`     - (and ${freshness.changed.length - 5} more)`);
      }
      log('   This pass validated the OLD render. Rebuild before trusting it:');
      log('     npm run docs:build');
    } else if (!cfg.requireBuild) {
      log('');
      log('   Reading an existing build. If results look impossible, the render');
      log('   may be cached. Clear it and rebuild:');
      log('     rm -rf website/node_modules/.astro website/node_modules/.vite website/.astro build/site');
      log('     npm run docs:build');
    }
  } else if (cfg.requireBuild) {
    missingRequiredBuild = true;
    report('build/site', 'no build found, and --require-build was given. Run `npm run docs:build` first.');
  } else {
    log('Built pass:   SKIPPED (no build/site). This pass is what catches route bugs.');
    log('              Run `npm run docs:build` first, or pass --require-build to enforce it.');
  }

  log('');
  log('\u2500'.repeat(60));
  log('');

  if (issues.length === 0) {
    log('Summary:');
    log(`   Markdown files: ${sourceCount}`);
    log(`   Built pages:    ${builtCount}${haveBuild ? '' : ' (skipped)'}`);
    log('');

    // Never report an unqualified pass when the load-bearing pass did not run.
    // A green line that means "half the checks were skipped" is the exact
    // failure mode this tool exists to prevent, and reading one as a full pass
    // is how the broken links reached production in the first place.
    if (haveBuild) {
      log('   All documentation links valid!');
    } else {
      log('   Source links valid. THE BUILT-OUTPUT PASS DID NOT RUN, so');
      log('   route bugs (the class that shipped 404s) are unchecked here.');
      log('   Run `npm run docs:build` first for the full check. CI always does.');
    }
    log('');
  } else {
    const byFile = new Map();
    for (const issue of issues) {
      if (!byFile.has(issue.file)) {
        byFile.set(issue.file, []);
      }
      byFile.get(issue.file).push(issue.detail);
    }

    log(`Broken documentation links: ${issues.length}\n`);
    for (const [file, details] of byFile) {
      log(`  ${file}`);
      for (const detail of details) {
        log(`    - ${detail}`);
      }
    }
    log('');

    if (cfg.verbose) {
      log('A route that resolves to nothing is still valid HTML, so neither');
      log('Astro nor markdownlint will fail on it. That is why this check exists.\n');
    }
  }

  // --require-build is a fail-closed contract in its own right: the flag exists
  // to turn the skipped built pass into an error, so honouring it must not
  // depend on --strict also being passed. Everything else stays advisory.
  const ok = !(issues.length > 0 && (cfg.strict || missingRequiredBuild));

  return { issues, sourceCount, builtCount, haveBuild, missingRequiredBuild, ok };
}

module.exports = {
  resolveConfig,
  run,
  checkSource,
  checkBuilt,
  resolveBase,
  blankCode,
  blankFences,
  headingToAnchor,
  extractAnchors,
  assetUrls,
  walk,
  buildInputsStatus,
  collectBuildInputs,
  checkLlmsIndex,
};

/* c8 ignore start -- CLI entry point */
if (require.main === module) {
  run(resolveConfig())
    .then((result) => {
      if (!result.ok) {
        process.exit(1);
      }
    })
    .catch((error) => {
      console.error(error.message);
      process.exit(1);
    });
}
/* c8 ignore stop */
