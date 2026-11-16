const SITE_URL = 'https://mymanagerh.com';
const ORGANIZATION_ID = `${SITE_URL}/#organization`;
const SOFTWARE_ID = `${SITE_URL}/#software`;
const WEBSITE_ID = `${SITE_URL}/#website`;
const LOGO_URL = `${SITE_URL}/ui/assets/logo/logo-horizontal.svg`;
const SOCIAL_IMAGE_URL = `${SITE_URL}/ui/assets/social/mymanagerh-social-card.png`;
const SOCIAL_IMAGE_WIDTH = 1200;
const SOCIAL_IMAGE_HEIGHT = 630;
const SOCIAL_IMAGE_ALT = 'MyManageRH - Gestión laboral con firma digital y auditoría inalterable';

const ORGANIZATION = {
  '@type': 'Organization',
  '@id': ORGANIZATION_ID,
  name: 'MyManageRH',
  url: `${SITE_URL}/ui/`,
  logo: LOGO_URL,
  description: 'Gestión laboral con firma electrónica de recibos, legajos y documentación laboral.',
  contactPoint: {
    '@type': 'ContactPoint',
    contactType: 'customer support',
    email: 'mymanagerh.ar@gmail.com',
    availableLanguage: 'Spanish',
  },
};

const SOFTWARE_APPLICATION = {
  '@type': 'SoftwareApplication',
  '@id': SOFTWARE_ID,
  name: 'MyManageRH',
  url: `${SITE_URL}/ui/`,
  description: 'Plataforma web para centralizar legajos, recibos y documentación laboral.',
  applicationCategory: 'BusinessApplication',
  operatingSystem: 'Web',
  provider: { '@id': ORGANIZATION_ID },
  featureList: [
    'Gestión centralizada de legajos digitales',
    'Importación masiva desde Excel',
    'Firma electrónica de documentación laboral',
    'Auditoría y trazabilidad de documentos',
  ],
};

const WEBSITE = {
  '@type': 'WebSite',
  '@id': WEBSITE_ID,
  url: `${SITE_URL}/ui/`,
  name: 'MyManageRH',
  publisher: { '@id': ORGANIZATION_ID },
  inLanguage: 'es-AR',
};

function visibleText(element) {
  return element?.textContent?.replace(/\s+/g, ' ').trim() || '';
}

function getDescription(pageElement, selector) {
  return visibleText(pageElement?.querySelector(selector));
}

export function getLegalDocumentRoute(search) {
  const page = new URLSearchParams(search).get('page');
  if (page !== 'terms' && page !== 'privacy') return null;
  return {
    path: '#/documentacion',
    params: new URLSearchParams(`docId=${page === 'privacy' ? 'privacy' : 'tos'}`),
  };
}

export function getPublicPageDefinition(path, params, pageElement) {
  if (path === '' || path === '#/' || path === '#') {
    const name = visibleText(pageElement?.querySelector('.hero-copy h1'));
    const description = getDescription(pageElement, '.hero-lead');
    if (!name || !description) return null;
    return {
      url: `${SITE_URL}/ui/`,
      name,
      description,
      about: { '@id': ORGANIZATION_ID },
      mainEntity: { '@id': SOFTWARE_ID },
    };
  }

  if (path === '#/documentacion') {
    const docId = params?.get('docId') === 'privacy' ? 'privacy' : 'tos';
    const pageSlug = docId === 'privacy' ? 'privacy' : 'terms';
    const name = visibleText(pageElement?.querySelector('.docs-header h1'));
    const description = getDescription(pageElement, '.docs-content p');
    if (!name || !description) return null;
    return {
      url: `${SITE_URL}/ui/?page=${pageSlug}`,
      name,
      description,
      about: { '@id': ORGANIZATION_ID },
    };
  }

  return null;
}

export function buildSchemaGraph(page) {
  const graph = [ORGANIZATION, SOFTWARE_APPLICATION, WEBSITE];
  if (page) {
    graph.push({
      '@type': 'WebPage',
      '@id': `${page.url}#webpage`,
      url: page.url,
      name: page.name,
      description: page.description,
      isPartOf: { '@id': WEBSITE_ID },
      inLanguage: 'es-AR',
      ...(page.about ? { about: page.about } : {}),
      ...(page.mainEntity ? { mainEntity: page.mainEntity } : {}),
    });
  }
  return { '@context': 'https://schema.org', '@graph': graph };
}

export function serializeSchemaGraph(graph) {
  return JSON.stringify(graph).replace(/</g, '\\u003c');
}

function getOrCreateMeta(name) {
  let meta = document.head.querySelector(`meta[name="${name}"]`);
  if (!meta) {
    meta = document.createElement('meta');
    meta.name = name;
    document.head.appendChild(meta);
  }
  return meta;
}

function getOrCreatePropertyMeta(property) {
  let meta = document.head.querySelector(`meta[property="${property}"]`);
  if (!meta) {
    meta = document.createElement('meta');
    meta.setAttribute('property', property);
    document.head.appendChild(meta);
  }
  return meta;
}

function getOrCreateNameMeta(name) {
  let meta = document.head.querySelector(`meta[name="${name}"]`);
  if (!meta) {
    meta = document.createElement('meta');
    meta.setAttribute('name', name);
    document.head.appendChild(meta);
  }
  return meta;
}

function getOrCreateCanonical() {
  let canonical = document.head.querySelector('link[rel="canonical"]');
  if (!canonical) {
    canonical = document.createElement('link');
    canonical.rel = 'canonical';
    document.head.appendChild(canonical);
  }
  return canonical;
}

export function clearPageSchema() {
  document.getElementById('mymanage-schema')?.remove();
  document.head.querySelector('link[rel="canonical"]')?.remove();
}

function clearPublicPageMetadata() {
  clearPageSchema();
  document.head.querySelector('meta[name="description"]')?.remove();
  document.head.querySelectorAll('meta[property^="og:"]').forEach((meta) => meta.remove());
  document.head.querySelectorAll('meta[name^="twitter:"]').forEach((meta) => meta.remove());
}

export function updatePageSeo({ path, params, user, pageElement }) {
  const existingSchema = document.getElementById('mymanage-schema');
  const page = user ? null : getPublicPageDefinition(path, params, pageElement);
  const robots = getOrCreateMeta('robots');

  if (!page) {
    robots.content = 'noindex,follow';
    clearPublicPageMetadata();
    return;
  }

  const title = `${page.name} | MyManageRH`;
  document.title = title;
  getOrCreateMeta('description').content = page.description;
  robots.content = 'index,follow';
  getOrCreateCanonical().href = page.url;
  getOrCreatePropertyMeta('og:type').content = 'website';
  getOrCreatePropertyMeta('og:site_name').content = 'MyManageRH';
  getOrCreatePropertyMeta('og:locale').content = 'es_AR';
  getOrCreatePropertyMeta('og:title').content = title;
  getOrCreatePropertyMeta('og:description').content = page.description;
  getOrCreatePropertyMeta('og:url').content = page.url;
  getOrCreatePropertyMeta('og:image').content = SOCIAL_IMAGE_URL;
  getOrCreatePropertyMeta('og:image:width').content = String(SOCIAL_IMAGE_WIDTH);
  getOrCreatePropertyMeta('og:image:height').content = String(SOCIAL_IMAGE_HEIGHT);
  getOrCreatePropertyMeta('og:image:alt').content = SOCIAL_IMAGE_ALT;

  getOrCreateNameMeta('twitter:card').content = 'summary_large_image';
  getOrCreateNameMeta('twitter:title').content = title;
  getOrCreateNameMeta('twitter:description').content = page.description;
  getOrCreateNameMeta('twitter:image').content = SOCIAL_IMAGE_URL;
  getOrCreateNameMeta('twitter:image:alt').content = SOCIAL_IMAGE_ALT;

  const schema = existingSchema || document.createElement('script');
  schema.id = 'mymanage-schema';
  schema.type = 'application/ld+json';
  schema.textContent = serializeSchemaGraph(buildSchemaGraph(page));
  if (!existingSchema) document.head.appendChild(schema);
}
