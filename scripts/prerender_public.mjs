import { mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const uiDir = path.join(root, 'ui');
const outputDir = path.join(uiDir, 'prerender');
const checkOnly = process.argv.includes('--check');

function dataModule(source) {
  return `data:text/javascript;base64,${Buffer.from(source).toString('base64')}`;
}

function textContent(markup) {
  return markup
    .replace(/<br\s*\/?>/gi, ' ')
    .replace(/<[^>]*>/g, '')
    .replace(/&nbsp;/gi, ' ')
    .replace(/&amp;/gi, '&')
    .replace(/&quot;/gi, '"')
    .replace(/&#39;|&apos;/gi, "'")
    .replace(/&lt;/gi, '<')
    .replace(/&gt;/gi, '>')
    .replace(/&#x([0-9a-f]+);/gi, (_match, code) => String.fromCodePoint(parseInt(code, 16)))
    .replace(/&#(\d+);/g, (_match, code) => String.fromCodePoint(Number(code)))
    .replace(/\s+/g, ' ')
    .trim();
}

function escapeAttribute(value) {
  return value
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function dataUrl(source) {
  return `data:text/javascript;base64,${Buffer.from(source).toString('base64')}`;
}

const layoutSource = (await readFile(path.join(uiDir, 'layout.js'), 'utf8'))
  .replace(/^import .*?;\s*/m, '');
const { renderLayout } = await import(dataModule(layoutSource));
const shellRoot = {
  html: '',
  set innerHTML(value) { this.html = value; },
  querySelector() { return null; },
};
renderLayout(shellRoot);

const seo = await import(dataModule(await readFile(path.join(uiDir, 'seo.js'), 'utf8')));
const indexHtml = await readFile(path.join(uiDir, 'index.html'), 'utf8');
const landingSource = await readFile(path.join(uiDir, 'pages/landing.js'), 'utf8');
const landing = await import(dataModule(landingSource));
const docsContentSource = await readFile(path.join(uiDir, 'docs-content.js'), 'utf8');
const docsPageSource = (await readFile(path.join(uiDir, 'pages/documentation.js'), 'utf8'))
  .replace(
    /^import \{ docsContent \} from .*?;\s*/m,
    `const { docsContent } = await import(${JSON.stringify(dataUrl(docsContentSource))});`,
  );
const documentation = await import(dataModule(docsPageSource));

globalThis.window = {};

async function renderPage(kind) {
  const container = {
    innerHTML: '',
    querySelector() { return null; },
    querySelectorAll() { return []; },
  };
  const params = new URLSearchParams(kind === 'home' ? '' : `docId=${kind === 'terms' ? 'tos' : 'privacy'}`);

  if (kind === 'home') {
    await landing.render(container);
  } else {
    await documentation.render(container, params);
  }

  const mainElement = '<main id="page" class="page container" tabindex="-1"></main>';
  if (!shellRoot.html.includes(mainElement)) {
    throw new Error('Public layout no longer contains the expected main content element.');
  }

  const documentHtml = shellRoot.html.replace(
    mainElement,
    `<main id="page" class="page container" tabindex="-1">${container.innerHTML}</main>`,
  );
  const heading = documentHtml.match(/<h1\b[^>]*>([\s\S]*?)<\/h1>/i)?.[1];
  const descriptionMarkup = kind === 'home'
    ? documentHtml.match(/<p class="hero-lead">([\s\S]*?)<\/p>/i)?.[1]
    : documentHtml.match(/<article class="docs-content[^"]*">([\s\S]*?)<\/article>/i)?.[1]
      ?.match(/<p\b[^>]*>([\s\S]*?)<\/p>/i)?.[1];
  const name = textContent(heading || '');
  const description = textContent(descriptionMarkup || '');
  if (!name || !description) {
    throw new Error(`Could not extract visible SEO text for public page: ${kind}`);
  }

  const pageElement = {
    querySelector(selector) {
      const text = selector === '.hero-copy h1' || selector === '.docs-header h1'
        ? name
        : selector === '.hero-lead' || selector === '.docs-content p'
          ? description
          : '';
      return text ? { textContent: text } : null;
    },
  };
  const pagePath = kind === 'home' ? '#/' : '#/documentacion';
  const pageParams = new URLSearchParams(kind === 'home' ? '' : `docId=${kind === 'terms' ? 'tos' : 'privacy'}`);
  const page = seo.getPublicPageDefinition(pagePath, pageParams, pageElement);
  if (!page) throw new Error(`Could not create SEO metadata for public page: ${kind}`);

  const schema = seo.serializeSchemaGraph(seo.buildSchemaGraph(page));
  const title = `${page.name} | MyManageRH`;
  const metadata = [
    `<meta name="description" content="${escapeAttribute(page.description)}" />`,
    '<meta name="robots" content="index,follow" />',
    '<meta property="og:type" content="website" />',
    '<meta property="og:site_name" content="MyManageRH" />',
    '<meta property="og:locale" content="es_AR" />',
    `<meta property="og:title" content="${escapeAttribute(title)}" />`,
    `<meta property="og:description" content="${escapeAttribute(page.description)}" />`,
    `<meta property="og:url" content="${escapeAttribute(page.url)}" />`,
    '<meta property="og:image" content="https://mymanagerh.com/ui/assets/social/mymanagerh-social-card.png" />',
    '<meta property="og:image:width" content="1200" />',
    '<meta property="og:image:height" content="630" />',
    '<meta property="og:image:alt" content="MyManageRH - Gestión laboral con firma digital y auditoría inalterable" />',
    '<meta name="twitter:card" content="summary_large_image" />',
    `<meta name="twitter:title" content="${escapeAttribute(title)}" />`,
    `<meta name="twitter:description" content="${escapeAttribute(page.description)}" />`,
    '<meta name="twitter:image" content="https://mymanagerh.com/ui/assets/social/mymanagerh-social-card.png" />',
    '<meta name="twitter:image:alt" content="MyManageRH - Gestión laboral con firma digital y auditoría inalterable" />',
    `<link rel="canonical" href="${escapeAttribute(page.url)}" />`,
    `<script id="mymanage-schema" type="application/ld+json">${schema}</script>`,
  ].join('\n  ');
  const appMarkup = `<div id="app">${documentHtml}</div>`;
  const output = indexHtml
    .replace(/<title>[\s\S]*?<\/title>/i, `<title>${escapeAttribute(title)}</title>`)
    .replace('</head>', `  ${metadata}\n</head>`)
    .replace('<div id="app"></div>', appMarkup);
  return output;
}

const pages = [
  ['home', 'home.html'],
  ['terms', 'terms.html'],
  ['privacy', 'privacy.html'],
];

if (!checkOnly) await mkdir(outputDir, { recursive: true });

let stale = false;
for (const [kind, filename] of pages) {
  const expected = await renderPage(kind);
  const outputPath = path.join(outputDir, filename);
  if (checkOnly) {
    let actual = '';
    try {
      actual = await readFile(outputPath, 'utf8');
    } catch (error) {
      if (error.code !== 'ENOENT') throw error;
    }
    if (actual !== expected) {
      console.error(`Prerendered page is missing or stale: ui/prerender/${filename}`);
      stale = true;
    }
  } else {
    await writeFile(outputPath, expected);
    console.log(`Generated ui/prerender/${filename}`);
  }
}

if (stale) process.exitCode = 1;
