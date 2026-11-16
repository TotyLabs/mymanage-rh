import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const source = await readFile(new URL('../../ui/seo.js', import.meta.url), 'utf8');
const seo = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');

function pageElement(selectors) {
  return {
    querySelector(selector) {
      return selectors[selector] ? { textContent: selectors[selector] } : null;
    },
  };
}

function installDocument() {
  const elements = [];
  globalThis.document = {
    title: '',
    head: {
      querySelector(selector) {
        return elements.find((element) => {
          if (selector.startsWith('meta[')) {
            if (selector.startsWith('meta[name="')) {
              return element.tagName === 'meta' && selector === `meta[name="${element.name}"]`;
            }
            if (selector.startsWith('meta[property="')) {
              return element.tagName === 'meta'
                && selector === `meta[property="${element.property}"]`;
            }
          }
          if (selector === 'link[rel="canonical"]') {
            return element.tagName === 'link' && element.rel === 'canonical';
          }
          return false;
        }) || null;
      },
      querySelectorAll(selector) {
        if (selector === 'meta[property^="og:"]') {
          return elements.filter((element) => element.tagName === 'meta' && element.property?.startsWith('og:'));
        }
        return [];
      },
      appendChild(element) {
        elements.push(element);
        return element;
      },
    },
    getElementById(id) {
      return elements.find((element) => element.id === id) || null;
    },
    createElement(tagName) {
      return {
        tagName,
        setAttribute(name, value) {
          this[name] = value;
        },
        remove() {
          const index = elements.indexOf(this);
          if (index >= 0) elements.splice(index, 1);
        },
      };
    },
    _elements: elements,
  };
}

test('homepage graph uses consistent organization, product, website, and webpage IDs', () => {
  const page = seo.getPublicPageDefinition(
    '#/',
    new URLSearchParams(),
    pageElement({
      '.hero-copy h1': 'Gestión laboral',
      '.hero-lead': 'Legajos y recibos.',
    }),
  );
  const graph = seo.buildSchemaGraph(page);
  const [organization, application, website, webpage] = graph['@graph'];

  assert.equal(graph['@context'], 'https://schema.org');
  assert.equal(organization['@type'], 'Organization');
  assert.equal(organization.name, 'MyManageRH');
  assert.equal(application['@type'], 'SoftwareApplication');
  assert.equal(application.applicationCategory, 'BusinessApplication');
  assert.equal(application.provider['@id'], organization['@id']);
  assert.equal(website.publisher['@id'], organization['@id']);
  assert.equal(webpage.mainEntity['@id'], application['@id']);
  assert.equal(webpage.isPartOf['@id'], website['@id']);
  assert.equal('offers' in application, false);
  assert.equal('sameAs' in organization, false);
  assert.equal('aggregateRating' in application, false);
});

test('legal documents map to stable canonical URLs and visible text', () => {
  const params = new URLSearchParams('docId=privacy');
  const page = seo.getPublicPageDefinition(
    '#/documentacion',
    params,
    pageElement({
      '.docs-header h1': 'Política de Privacidad',
      '.docs-content p': 'Texto visible de la política.',
    }),
  );

  assert.equal(page.url, 'https://mymanagerh.com/ui/?page=privacy');
  assert.equal(page.name, 'Política de Privacidad');
  assert.equal(page.description, 'Texto visible de la política.');
  assert.equal(seo.getPublicPageDefinition('#/soporte', params, pageElement({})), null);

  const terms = seo.getPublicPageDefinition(
    '#/documentacion',
    new URLSearchParams('docId=tos'),
    pageElement({
      '.docs-header h1': 'Términos y Condiciones',
      '.docs-content p': 'Texto visible de los términos.',
    }),
  );
  assert.equal(terms.url, 'https://mymanagerh.com/ui/?page=terms');
});

test('stable legal URLs resolve to the matching documentation route', () => {
  const terms = seo.getLegalDocumentRoute('?page=terms');
  const privacy = seo.getLegalDocumentRoute('?page=privacy');

  assert.equal(terms.path, '#/documentacion');
  assert.equal(terms.params.get('docId'), 'tos');
  assert.equal(privacy.path, '#/documentacion');
  assert.equal(privacy.params.get('docId'), 'privacy');
  assert.equal(seo.getLegalDocumentRoute('?page=other'), null);
});

test('JSON-LD serialization escapes markup-significant less-than characters', () => {
  const serialized = seo.serializeSchemaGraph({
    '@context': 'https://schema.org',
    name: '</script><script>alert(1)</script>',
  });

  assert.equal(serialized.includes('<'), false);
  assert.equal(JSON.parse(serialized).name, '</script><script>alert(1)</script>');
});

test('authenticated routes remove public structured data and become noindex', () => {
  installDocument();
  const home = pageElement({
    '.hero-copy h1': 'Gestión laboral',
    '.hero-lead': 'Legajos y recibos.',
  });
  const params = new URLSearchParams();

  seo.updatePageSeo({ path: '#/', params, user: null, pageElement: home });
  const firstSchema = document.getElementById('mymanage-schema');
  assert.ok(firstSchema);
  assert.equal(document.head.querySelector('meta[property="og:url"]').content, 'https://mymanagerh.com/ui/');
  assert.equal(document.head.querySelector('meta[property="og:title"]').content, 'Gestión laboral | MyManageRH');
  assert.equal(document.head.querySelector('meta[property="og:image"]').content, 'https://mymanagerh.com/ui/assets/social/mymanagerh-social-card.png');
  assert.equal(document.head.querySelector('meta[name="twitter:card"]').content, 'summary_large_image');
  assert.equal(document.head.querySelector('meta[name="twitter:image"]').content, 'https://mymanagerh.com/ui/assets/social/mymanagerh-social-card.png');

  seo.updatePageSeo({ path: '#/', params, user: null, pageElement: home });
  assert.equal(document._elements.filter((element) => element.id === 'mymanage-schema').length, 1);
  assert.equal(document.getElementById('mymanage-schema'), firstSchema);

  seo.updatePageSeo({ path: '#/empleado/recibos', params, user: { role: 'employee' }, pageElement: null });
  assert.equal(document.getElementById('mymanage-schema'), null);
  assert.equal(document.head.querySelector('meta[name="robots"]').content, 'noindex,follow');
  assert.equal(document.head.querySelector('link[rel="canonical"]'), null);
  assert.equal(document.head.querySelector('meta[property="og:url"]'), null);

  seo.updatePageSeo({ path: '#/login', params, user: null, pageElement: null });
  assert.equal(document.head.querySelector('meta[name="robots"]').content, 'noindex,follow');
  assert.equal(document.head.querySelector('link[rel="canonical"]'), null);
  assert.equal(document.getElementById('mymanage-schema'), null);
});

test('checked-in prerendered pages match their source modules', () => {
  execFileSync(process.execPath, ['scripts/prerender_public.mjs', '--check'], {
    cwd: repoRoot,
    stdio: 'pipe',
  });
});
