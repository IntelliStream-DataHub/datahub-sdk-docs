// @ts-check
import {themes as prismThemes} from 'prism-react-renderer';

/** @type {import('@docusaurus/types').Config} */
const config = {
  title: 'DataHub SDK',
  tagline: 'Java, Python & Rust client for the DataHub Platform',
  favicon: 'img/favicon.ico',

  // Served by the intellistream-web Spring Boot app alongside the user docs at
  // /data-platform-documentation. baseUrl is baked into every asset URL, the
  // router basename and the search-index fetch, so it must match the mount path.
  url: 'https://intellistream.ai',
  baseUrl: '/sdk-documentation/',
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
          // Adds "Edit this page" to every doc. Docusaurus appends the file's
          // path relative to this site directory. Note the branch here is
          // master, unlike datahub-docs which is main.
          editUrl: 'https://github.com/IntelliStream-DataHub/datahub-sdk-docs/edit/master/',
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
        // '/' is the main site root, not this site's baseUrl. That only works
        // because src/theme/Logo is ejected to pass href through verbatim —
        // stock Docusaurus would rewrite this to /sdk-documentation/.
        logo: {
          alt: 'IntelliStream',
          src: 'img/logo.svg',
          srcDark: 'img/logo-dark.svg',
          href: '/',
          target: '_self',
        },
        items: [
          { type: 'docSidebar', sidebarId: 'tutorialSidebar', position: 'left', label: 'Docs' },
          // Reciprocal of the "Developer & SDK docs" item in datahub-docs.
          // Same-domain links stay root-relative so they work on whatever host
          // serves the build. Docusaurus would otherwise prefix a leading slash
          // with this site's baseUrl (shouldAddBaseUrlAutomatically in Link.js),
          // hence autoAddBaseUrl: false. data-noBrokenLinkCheck stops the link
          // checker flagging a route that lives outside this site.
          { href: '/data-platform-documentation/', autoAddBaseUrl: false, 'data-noBrokenLinkCheck': true, label: 'Platform documentation', position: 'right' },
          { href: '/documentation', autoAddBaseUrl: false, 'data-noBrokenLinkCheck': true, label: 'All documentation', position: 'right' },
          // Simple version indicator. When the docs start tracking multiple releases,
          // replace this with a docsVersionDropdown via `npm run docusaurus docs:version`.
          { type: 'html', position: 'right', value: '<span class="badge badge--secondary navbar__version-badge">v1.0</span>' },
          // This site's own repo, so "GitHub" is unambiguous. The old link went
          // to the SDK code on Gitea; if a code link is wanted too it needs its
          // own item, since the SDK spans three language repos.
          { href: 'https://github.com/IntelliStream-DataHub/datahub-sdk-docs', label: 'GitHub', position: 'right' },
        ],
      },
      footer: {
        style: 'light',
        links: [
          { title: 'Docs', items: [
            { label: 'Quick start', to: '/quickstart' },
            { label: 'Live monitoring', to: '/guides/ingest-timeseries' },
          ]},
          { title: 'Elsewhere', items: [
            { label: 'Platform documentation', href: '/data-platform-documentation/', autoAddBaseUrl: false, 'data-noBrokenLinkCheck': true },
            { label: 'All documentation', href: '/documentation', autoAddBaseUrl: false, 'data-noBrokenLinkCheck': true },
            { label: 'intellistream.ai', href: '/', autoAddBaseUrl: false, 'data-noBrokenLinkCheck': true },
            { label: 'Contact us', href: '/contact-us', autoAddBaseUrl: false, 'data-noBrokenLinkCheck': true },
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
