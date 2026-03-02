/**
 * Rehype plugin to prepend base path to absolute URLs
 *
 * Transforms:
 *   /img/foo.png → /base/img/foo.png (when base is /base/)
 *   /downloads/file.zip → /base/downloads/file.zip
 *   /llms.txt → /base/llms.txt
 *
 * Only affects absolute paths (/) - relative paths and external URLs are unchanged.
 * Does NOT process .md links (those are handled by rehype-markdown-links).
 */

import { visit } from 'unist-util-visit';

/**
 * Create a rehype plugin that prepends the base path to absolute URLs.
 *
 * @param {Object} options - Plugin options
 * @param {string} options.base - The base path to prepend
 * @returns {function} A HAST tree transformer
 */
export default function rehypeBasePaths(options = {}) {
  const base = options.base || '/';

  // Normalize base: ensure it ends with / and doesn't have double slashes
  const normalizedBase = base === '/' ? '/' : base.endsWith('/') ? base : base + '/';

  return (tree) => {
    visit(tree, 'element', (node) => {
      // Process img tags with src attribute
      if (node.tagName === 'img' && node.properties?.src) {
        const src = node.properties.src;

        if (typeof src === 'string' && src.startsWith('/') && !src.startsWith('//')) {
          if (normalizedBase !== '/' && !src.startsWith(normalizedBase)) {
            node.properties.src = normalizedBase + src.slice(1);
          }
        }
      }

      // Process iframe tags with src attribute
      if (node.tagName === 'iframe' && node.properties?.src) {
        const src = node.properties.src;

        if (typeof src === 'string' && src.startsWith('/') && !src.startsWith('//')) {
          if (normalizedBase !== '/' && !src.startsWith(normalizedBase)) {
            node.properties.src = normalizedBase + src.slice(1);
          }
        }
      }

      // Process anchor tags with href attribute
      if (node.tagName === 'a' && node.properties?.href) {
        const href = node.properties.href;

        if (typeof href !== 'string') {
          return;
        }

        if (!href.startsWith('/') || href.startsWith('//')) {
          return;
        }

        if (normalizedBase !== '/' && href.startsWith(normalizedBase)) {
          return;
        }

        // Skip .md links - handled by rehype-markdown-links
        const firstDelimiter = Math.min(
          href.indexOf('?') === -1 ? Infinity : href.indexOf('?'),
          href.indexOf('#') === -1 ? Infinity : href.indexOf('#'),
        );
        const pathPortion = firstDelimiter === Infinity ? href : href.substring(0, firstDelimiter);

        if (pathPortion.endsWith('.md')) {
          return;
        }

        node.properties.href = normalizedBase + href.slice(1);
      }
    });
  };
}
