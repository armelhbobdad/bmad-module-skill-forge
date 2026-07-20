/**
 * Unit tests for website/src/rehype-markdown-links.js
 *
 * The plugin turns Markdown `.md` links into site routes. Its contract is
 * narrow but load-bearing: a wrong route ships a 404 that nothing else in the
 * build catches, because an unresolvable href is still valid HTML.
 *
 * The regression these tests exist for: the plugin used to emit page-relative
 * routes (`./architecture/`). Astro builds with `format: 'directory'`, so a
 * page lives at `/troubleshooting/` and the browser resolved that href to
 * `/troubleshooting/architecture/`, which 404s. Routes are now root-absolute.
 */

const assert = require('node:assert');
const path = require('node:path');

const REPO_ROOT = path.resolve(__dirname, '..');
const PLUGIN = path.join(REPO_ROOT, 'website', 'src', 'rehype-markdown-links.js');

let passed = 0;
let failed = 0;

function test(name, fn) {
  try {
    fn();
    passed += 1;
    console.log(`\u001B[32m✓\u001B[0m ${name}`);
  } catch (error) {
    failed += 1;
    console.log(`\u001B[31m✗\u001B[0m ${name}`);
    console.log(`  ${error.message}`);
  }
}

/** Minimal HAST anchor node. */
function anchor(href) {
  return { type: 'element', tagName: 'a', properties: { href }, children: [] };
}

/**
 * Run the plugin over a single anchor and return the resulting href.
 *
 * @param {function} plugin - The transformer factory
 * @param {string} href - Starting href
 * @param {string} sourcePath - Absolute source path of the containing page
 * @param {string} base - Deployment base path
 * @returns {string} The rewritten href
 */
function rewrite(plugin, href, sourcePath, base = '/site/') {
  const node = anchor(href);
  const tree = { type: 'root', children: [node] };
  plugin({ base })(tree, { path: sourcePath });
  return node.properties.href;
}

async function main() {
  const { default: rehypeMarkdownLinks } = await import(`file://${PLUGIN}`);

  const TOP = '/repo/website/src/content/docs/troubleshooting.md';
  const NESTED = '/repo/website/src/content/docs/_internal/STABILITY.md';

  // --- the shipped regression -----------------------------------------

  test('sibling link becomes a root-absolute route, not page-relative', () => {
    const out = rewrite(rehypeMarkdownLinks, './architecture.md', TOP);
    assert.strictEqual(out, '/site/architecture/');
    assert.ok(!out.startsWith('./'), 'must not emit a page-relative route');
  });

  test('a bare sibling link is rewritten too (GitHub-valid, previously shipped raw)', () => {
    assert.strictEqual(rewrite(rehypeMarkdownLinks, 'workflows.md', TOP), '/site/workflows/');
  });

  test('route does not nest under the current page directory', () => {
    // The exact 404 that shipped: /site/troubleshooting/architecture/
    const out = rewrite(rehypeMarkdownLinks, './architecture.md', TOP);
    assert.ok(!out.includes('troubleshooting'), `route nested under its own page: ${out}`);
  });

  // --- nesting ---------------------------------------------------------

  test('a nested page resolves ../ against the content root', () => {
    assert.strictEqual(rewrite(rehypeMarkdownLinks, '../architecture.md', NESTED), '/site/architecture/');
  });

  test('a nested page resolves a sibling within its own directory', () => {
    assert.strictEqual(rewrite(rehypeMarkdownLinks, './RELEASING.md', NESTED), '/site/_internal/RELEASING/');
  });

  test('segments escaping the content root are clamped, never emitted', () => {
    const out = rewrite(rehypeMarkdownLinks, '../../../etc/passwd.md', TOP);
    assert.ok(!out.includes('..'), `escaped the root: ${out}`);
    assert.ok(out.startsWith('/site/'), `lost its base: ${out}`);
  });

  // --- suffixes --------------------------------------------------------

  test('anchor is preserved', () => {
    assert.strictEqual(rewrite(rehypeMarkdownLinks, './workflows.md#thresholds', TOP), '/site/workflows/#thresholds');
  });

  test('query is preserved', () => {
    assert.strictEqual(rewrite(rehypeMarkdownLinks, './workflows.md?v=2', TOP), '/site/workflows/?v=2');
  });

  test('query and anchor together are preserved in order', () => {
    assert.strictEqual(rewrite(rehypeMarkdownLinks, './x.md?v=2#top', TOP), '/site/x/?v=2#top');
  });

  // --- index.md --------------------------------------------------------

  test('index.md collapses to its directory', () => {
    assert.strictEqual(rewrite(rehypeMarkdownLinks, './guide/index.md', TOP), '/site/guide/');
  });

  test('root index.md collapses to the base itself', () => {
    assert.strictEqual(rewrite(rehypeMarkdownLinks, './index.md', TOP), '/site/');
  });

  test('a page merely ENDING in "index.md" is not treated as an index', () => {
    // Regression: endsWith('index.md') matched any such filename and sliced
    // off the last 8 characters, so these silently became '/site/my' and
    // '/site/re'. Only a whole basename is an index.
    assert.strictEqual(rewrite(rehypeMarkdownLinks, './myindex.md', TOP), '/site/myindex/');
    assert.strictEqual(rewrite(rehypeMarkdownLinks, 'reindex.md', TOP), '/site/reindex/');
    assert.strictEqual(rewrite(rehypeMarkdownLinks, './guide/subindex.md', TOP), '/site/guide/subindex/');
  });

  // --- absolute forms --------------------------------------------------

  test('/docs/ prefix is stripped and based', () => {
    assert.strictEqual(rewrite(rehypeMarkdownLinks, '/docs/architecture.md', TOP), '/site/architecture/');
  });

  test('root-absolute .md is based', () => {
    assert.strictEqual(rewrite(rehypeMarkdownLinks, '/architecture.md', TOP), '/site/architecture/');
  });

  // --- base handling ---------------------------------------------------

  test('root deployment emits a single leading slash', () => {
    assert.strictEqual(rewrite(rehypeMarkdownLinks, './architecture.md', TOP, '/'), '/architecture/');
  });

  test('base without trailing slash is normalized', () => {
    assert.strictEqual(rewrite(rehypeMarkdownLinks, './architecture.md', TOP, '/site'), '/site/architecture/');
  });

  test('no route ever contains a doubled slash', () => {
    for (const b of ['/', '/site', '/site/']) {
      for (const h of ['./index.md', './architecture.md', '/docs/architecture.md']) {
        const out = rewrite(rehypeMarkdownLinks, h, TOP, b);
        assert.ok(!out.slice(1).includes('//'), `doubled slash for base ${b}, href ${h}: ${out}`);
      }
    }
  });

  // --- things it must not touch ---------------------------------------

  test('external links are untouched', () => {
    for (const u of ['https://example.com/x.md', 'mailto:a@b.c', 'tel:+1234']) {
      assert.strictEqual(rewrite(rehypeMarkdownLinks, u, TOP), u);
    }
  });

  test('non-.md targets are untouched', () => {
    for (const u of ['./image.png', './script.js', '#anchor-only', './assets/']) {
      assert.strictEqual(rewrite(rehypeMarkdownLinks, u, TOP), u);
    }
  });

  test('a missing source path still yields a usable top-level route', () => {
    const node = anchor('./architecture.md');
    const tree = { type: 'root', children: [node] };
    rehypeMarkdownLinks({ base: '/site/' })(tree, {});
    assert.strictEqual(node.properties.href, '/site/architecture/');
  });

  console.log(`\n  Passed: \u001B[32m${passed}\u001B[0m`);
  console.log(`  Failed: \u001B[31m${failed}\u001B[0m`);

  if (failed > 0) {
    process.exit(1);
  }
  console.log('\u001B[32mAll rehype-markdown-links tests passed!\u001B[0m');
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
