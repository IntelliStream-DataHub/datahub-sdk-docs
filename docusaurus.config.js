// @ts-check
import {themes as prismThemes} from 'prism-react-renderer';

/** @type {import('@docusaurus/types').Config} */
const config = {
  title: 'DataHub SDK',
  tagline: 'Java, Python & Rust client for the DataHub Platform',
  favicon: 'img/favicon.ico',

  url: 'https://docs.intellistream.ai',
  baseUrl: '/',
  organizationName: 'intellistream',
  projectName: 'datahub-sdk',
  onBrokenLinks: 'warn',
  // v4 form (the top-level onBrokenMarkdownLinks is deprecated under future.v4)
  markdown: { hooks: { onBrokenMarkdownLinks: 'warn' } },

  i18n: { defaultLocale: 'en', locales: ['en'] },

  presets: [
    [
      'classic',
      /** @type {import('@docusaurus/preset-classic').Options} */
      ({
        docs: {
          sidebarPath: './sidebars.js',
          routeBasePath: '/',          // docs at site root, GitBook-style
        },
        blog: false,                    // SDK docs site — no blog
        theme: { customCss: './src/css/custom.css' },
      }),
    ],
  ],

  themes: [
    [
      '@easyops-cn/docusaurus-search-local',
      /** @type {import('@easyops-cn/docusaurus-search-local').PluginOptions} */
      ({
        hashed: true,
        indexDocs: true,
        indexBlog: false,
        docsRouteBasePath: '/',
        highlightSearchTermsOnTargetPage: true,
      }),
    ],
  ],

  themeConfig:
    /** @type {import('@docusaurus/preset-classic').ThemeConfig} */
    ({
      colorMode: { respectPrefersColorScheme: true },
      navbar: {
        title: 'DataHub SDK',
        logo: { alt: 'IntelliStream', src: 'img/logo.svg', srcDark: 'img/logo-dark.svg' },
        items: [
          { type: 'docSidebar', sidebarId: 'tutorialSidebar', position: 'left', label: 'Docs' },
          // A real deploy adds the mike-equivalent version dropdown here via
          // `docs:version`; Docusaurus renders a docsVersionDropdown automatically.
          { href: 'https://git.intellistream.ai/olavgg/datahub-sdk', label: 'Source', position: 'right' },
        ],
      },
      footer: {
        style: 'light',
        links: [
          { title: 'Docs', items: [
            { label: 'Quick start', to: '/quickstart' },
            { label: 'Live monitoring', to: '/guides/ingest-timeseries' },
          ]},
        ],
        copyright: `Copyright © ${new Date().getFullYear()} IntelliStream.`,
      },
      prism: {
        theme: prismThemes.github,
        darkTheme: prismThemes.dracula,
        additionalLanguages: ['java', 'rust', 'toml', 'bash', 'python', 'kotlin', 'groovy', 'json'],
      },
    }),
};

export default config;
