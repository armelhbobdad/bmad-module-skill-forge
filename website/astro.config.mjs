// @ts-check
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import sitemap from '@astrojs/sitemap';
import mermaid from 'astro-mermaid';
import rehypeMarkdownLinks from './src/rehype-markdown-links.js';
import rehypeBasePaths from './src/rehype-base-paths.js';
import { getSiteUrl } from './src/lib/site-url.js';

const siteUrl = getSiteUrl();
const urlParts = new URL(siteUrl);
// Normalize basePath: ensure trailing slash so links can use `${BASE_URL}path`
const basePath = urlParts.pathname === '/' ? '/' : urlParts.pathname.endsWith('/') ? urlParts.pathname : urlParts.pathname + '/';

export default defineConfig({
  site: `${urlParts.origin}${basePath}`,
  base: basePath,
  outDir: '../build/site',

  // Disable aggressive caching in dev mode
  vite: {
    optimizeDeps: {
      force: true,
    },
    server: {
      watch: {
        usePolling: false,
      },
    },
  },

  markdown: {
    rehypePlugins: [
      [rehypeMarkdownLinks, { base: basePath }],
      [rehypeBasePaths, { base: basePath }],
    ],
  },

  integrations: [
    mermaid(),
    sitemap(),
    starlight({
      title: 'Skill Forge (SKF)',
      tagline: 'Turn code and docs into instructions AI agents can actually follow.',

      logo: {
        src: './public/img/skf-logo.svg',
        alt: 'Skill Forge (SKF)',
        replacesTitle: false,
      },
      favicon: '/favicon.ico',

      // Social links
      social: [
        {
          icon: 'github',
          label: 'GitHub',
          href: 'https://github.com/armelhbobdad/bmad-module-skill-forge',
        },
      ],

      // Show last updated timestamps
      lastUpdated: true,

      // Custom head tags for LLM discovery
      head: [
        {
          tag: 'meta',
          attrs: {
            name: 'ai-terms',
            content: `AI-optimized documentation: ${siteUrl}/llms-full.txt (plain text, complete SKF reference). Index: ${siteUrl}/llms.txt`,
          },
        },
        {
          tag: 'meta',
          attrs: {
            name: 'llms-full',
            content: `${siteUrl}/llms-full.txt`,
          },
        },
        {
          tag: 'meta',
          attrs: {
            name: 'llms',
            content: `${siteUrl}/llms.txt`,
          },
        },
        {
          tag: 'script',
          attrs: {
            src: `${basePath}js/mermaid-lightbox.js`,
            defer: true,
          },
        },
      ],

      // Custom CSS
      customCss: ['./src/styles/custom.css'],

      // Sidebar configuration (flat structure for SKF's 5 docs)
      sidebar: [
        { label: 'Welcome', slug: 'index' },
        { label: 'Getting Started', slug: 'getting-started' },
        { label: 'Concepts', slug: 'concepts' },
        { label: 'How It Works', slug: 'how-it-works' },
        { label: 'Workflows', slug: 'workflows' },
        { label: 'Agents', slug: 'agents' },
        { label: 'Examples', slug: 'examples' },
      ],

      // Credits in footer
      credits: false,

      // Pagination
      pagination: true,

      // Use our docs/404.md instead of Starlight's built-in 404
      disable404Route: true,

      // Custom components
      components: {
        Header: './src/components/Header.astro',
        MobileMenuFooter: './src/components/MobileMenuFooter.astro',
      },

      // Table of contents
      tableOfContents: { minHeadingLevel: 2, maxHeadingLevel: 3 },
    }),
  ],
});
