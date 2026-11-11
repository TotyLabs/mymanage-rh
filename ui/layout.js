import { logoutSession, showToast } from './common.js?v=123';

/* ==========================================================================
   Shell de la aplicación
   - Rutas públicas: encabezado simple.
   - #/empresa/* y #/empleado/*: barra lateral (escritorio) o barra inferior
     con hoja "Más" (móvil/tablet). Una sola navegación para ambos tamaños.
   Contratos que se conservan:
   - exports renderLayout / bindHeader
   - #headerNav, #page, #toasts, #confirmModal (+ #confirmMsg/#confirmOk/#confirmCancel)
   - #nav-notif: router.js le agrega la insignia .notification-badge
   ========================================================================== */

const ICON_ATTRS = 'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"';

const ICONS = {
  dashboard: `<svg ${ICON_ATTRS}><rect x="3" y="3" width="7" height="9" rx="1.5"></rect><rect x="14" y="3" width="7" height="5" rx="1.5"></rect><rect x="14" y="12" width="7" height="9" rx="1.5"></rect><rect x="3" y="16" width="7" height="5" rx="1.5"></rect></svg>`,
  users: `<svg ${ICON_ATTRS}><path d="M16 20v-1.5a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4V20"></path><circle cx="9.5" cy="8" r="3.5"></circle><path d="M21 20v-1.5a4 4 0 0 0-3-3.87"></path><path d="M15.5 4.3a3.5 3.5 0 0 1 0 6.4"></path></svg>`,
  history: `<svg ${ICON_ATTRS}><path d="M3 12a9 9 0 1 0 3-6.7"></path><path d="M3 4v4.5h4.5"></path><path d="M12 7.5V12l3 2"></path></svg>`,
  bell: `<svg ${ICON_ATTRS}><path d="M6 9a6 6 0 0 1 12 0c0 6 2.5 7.5 2.5 7.5h-17S6 15 6 9z"></path><path d="M10 20a2 2 0 0 0 4 0"></path></svg>`,
  models: `<svg ${ICON_ATTRS}><path d="M12 3l9 4.5-9 4.5-9-4.5z"></path><path d="M3 12l9 4.5 9-4.5"></path><path d="M3 16.5L12 21l9-4.5"></path></svg>`,
  settings: `<svg ${ICON_ATTRS}><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"></path></svg>`,
  receipt: `<svg ${ICON_ATTRS}><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"></path><path d="M14 3v5h5"></path><path d="M9 13h6"></path><path d="M9 17h4"></path></svg>`,
  user: `<svg ${ICON_ATTRS}><circle cx="12" cy="8" r="4"></circle><path d="M4 21v-1a6 6 0 0 1 6-6h4a6 6 0 0 1 6 6v1"></path></svg>`,
  more: `<svg ${ICON_ATTRS}><circle cx="5" cy="12" r="1.2"></circle><circle cx="12" cy="12" r="1.2"></circle><circle cx="19" cy="12" r="1.2"></circle></svg>`,
  collapse: `<svg ${ICON_ATTRS}><path d="m15 18-6-6 6-6"></path></svg>`,
  logout: `<svg ${ICON_ATTRS}><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path><path d="M16 17l5-5-5-5"></path><path d="M21 12H9"></path></svg>`,
};

/*
  Navegación por rol. `primary` va en la barra inferior (móvil) y arriba en la
  barra lateral; `secondary` va en la hoja "Más" (móvil) y debajo de un
  separador en la barra lateral. `match` cubre rutas que comparten pantalla.
*/
const NAV = {
  empresa: {
    context: 'Empresa',
    primary: [
      { href: '#/empresa/dashboard', text: 'Panel', icon: 'dashboard', match: ['#/empresa/dashboard', '#/empresa/recibos', '#/empresa/batches'] },
      { href: '#/empresa/empleados', text: 'Empleados', icon: 'users' },
      { href: '#/empresa/historial', text: 'Historial', icon: 'history' },
      { href: '#/empresa/notificaciones', text: 'Notificaciones', icon: 'bell', id: 'nav-notif' },
    ],
    secondary: [
      { href: '#/empresa/modelos-laborales', text: 'Modelos laborales', icon: 'models' },
      { href: '#/empresa/configuracion', text: 'Configuración', icon: 'settings' },
    ],
  },
  empleado: {
    context: 'Empleado',
    primary: [
      { href: '#/empleado/recibos', text: 'Mis recibos', icon: 'receipt' },
      { href: '#/empleado/notificaciones', text: 'Notificaciones', icon: 'bell', id: 'nav-notif' },
      { href: '#/empleado/perfil', text: 'Mi perfil', icon: 'user' },
    ],
    secondary: [],
  },
};

function getLayoutType(path) {
  if (!path) return 'public';
  if (path.startsWith('#/empresa/')) return 'empresa';
  if (path.startsWith('#/empleado/')) return 'empleado';
  return 'public';
}

async function logoutAndReturnHome() {
  try {
    await logoutSession();
    location.hash = '#/select-role';
    location.reload();
  } catch (error) {
    console.error('Error al cerrar sesión:', error);
    showToast('No se pudo cerrar la sesión. Verificá la conexión e intentá nuevamente.', 'error');
  }
}

function isActive(path, item) {
  const targets = item.match || [item.href];
  return targets.some((target) => path === target || path.startsWith(`${target}?`) || path.startsWith(`${target}/`));
}

function createPublicLink(href, text) {
  const link = document.createElement('a');
  link.className = 'link';
  link.href = href;
  link.textContent = text;
  return link;
}

function createAppLink(item, path) {
  const link = document.createElement('a');
  link.className = 'app-link';
  link.href = item.href;
  if (item.id) link.id = item.id;
  if (isActive(path, item)) link.setAttribute('aria-current', 'page');
  link.innerHTML = `${ICONS[item.icon]}<span class="link-label">${item.text}</span>`;
  return link;
}

function createLogoutButton() {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'app-link app-link--logout';
  button.innerHTML = `${ICONS.logout}<span class="link-label">Cerrar sesión</span>`;
  button.addEventListener('click', logoutAndReturnHome);
  return button;
}

export function renderLayout(root) {
  if (!root) return;

  root.innerHTML = `
    <div class="layout" data-shell="public">
      <a class="skip-link" href="#page" id="skipLink">Saltar al contenido</a>

      <header class="site-header" id="siteHeader">
        <div class="brand">
          <a href="#/" class="brand-link">
            <span class="brand-title">MyManageRH</span>
          </a>
        </div>

        <nav class="header-actions" id="headerActions" aria-label="Acciones"></nav>
      </header>

      <nav class="app-nav" id="headerNav" aria-label="Navegación principal"></nav>

      <main id="page" class="page container" tabindex="-1"></main>

      <div id="toasts" class="toasts" aria-live="polite"></div>

      <div id="confirmModal" class="modal hidden" aria-hidden="true">
        <div class="modal-content modal-content-sm" role="alertdialog" aria-modal="true" aria-labelledby="confirmTitle" aria-describedby="confirmMsg">
          <div class="modal-body">
            <h3 id="confirmTitle" class="modal-title">Confirmar acción</h3>
            <div id="confirmMsg" class="small-muted mt-8">¿Estás seguro?</div>

            <div class="modal-actions mt-16">
              <button id="confirmCancel" type="button" class="btn btn-ghost">Cancelar</button>
              <button id="confirmOk" type="button" class="btn btn-primary">Confirmar</button>
            </div>
          </div>
        </div>
      </div>

      <footer class="footer">
        <div class="footer-content">
          <div class="footer-legal">
            <a href="#/documentacion?docId=tos">Términos y Condiciones</a>
            <span class="separator" aria-hidden="true">|</span>
            <a href="#/documentacion?docId=privacy">Política de Privacidad</a>
          </div>
          <div class="footer-copyright">
            © 2026 MyManageRH
          </div>
        </div>
      </footer>
    </div>
  `;

  // "Saltar al contenido" no puede usar el ancla nativa: el hash pertenece al router.
  const skip = root.querySelector('#skipLink');
  const page = root.querySelector('#page');
  skip?.addEventListener('click', (event) => {
    event.preventDefault();
    page?.focus({ preventScroll: false });
  });
}

export function bindHeader() {
  const nav = document.getElementById('headerNav');
  const actions = document.getElementById('headerActions');
  const layout = document.querySelector('.layout');
  if (!nav || !actions || !layout) return;
  let sidebarCollapsed = false;

  function setMore(open) {
    nav.dataset.more = open ? 'open' : 'closed';
    const trigger = nav.querySelector('.nav-more-btn');
    if (trigger) trigger.setAttribute('aria-expanded', String(open));
  }

  function setSidebarCollapsed(collapsed) {
    sidebarCollapsed = collapsed;
    layout.dataset.sidebarCollapsed = String(collapsed);
    const trigger = nav.querySelector('.nav-collapse-btn');
    if (!trigger) return;
    const label = collapsed ? 'Expandir menú' : 'Contraer menú';
    trigger.setAttribute('aria-expanded', String(!collapsed));
    trigger.setAttribute('aria-label', label);
    trigger.title = label;
  }

  function buildMoreSheet(config, path) {
    const sheet = document.createElement('div');
    sheet.className = 'nav-more-sheet';
    sheet.id = 'navMoreSheet';

    if (config.secondary.length) {
      const divider = document.createElement('div');
      divider.className = 'nav-divider';
      divider.setAttribute('role', 'separator');
      sheet.appendChild(divider);
      config.secondary.forEach((item) => sheet.appendChild(createAppLink(item, path)));
    }
    sheet.appendChild(createLogoutButton());
    return sheet;
  }

  function updateNav() {
    const path = location.hash || '#/';
    const type = getLayoutType(path);

    nav.innerHTML = '';
    actions.innerHTML = '';
    layout.dataset.shell = type === 'public' ? 'public' : 'app';
    layout.dataset.sidebarCollapsed = String(sidebarCollapsed);
    nav.dataset.more = 'closed';

    if (type === 'public') {
      if (path.startsWith('#/login') || path.startsWith('#/sign/')) {
        actions.appendChild(createPublicLink('#/select-role', 'Volver'));
      }
      return;
    }

    const config = NAV[type];

    const context = document.createElement('div');
    context.className = 'nav-context';
    const contextLabel = document.createElement('span');
    contextLabel.className = 'nav-context-label';
    contextLabel.textContent = config.context;
    context.appendChild(contextLabel);

    const collapse = document.createElement('button');
    collapse.type = 'button';
    collapse.className = 'nav-collapse-btn';
    collapse.setAttribute('aria-controls', 'headerNav');
    collapse.innerHTML = ICONS.collapse;
    collapse.addEventListener('click', () => setSidebarCollapsed(!sidebarCollapsed));
    context.appendChild(collapse);
    nav.appendChild(context);
    setSidebarCollapsed(sidebarCollapsed);

    config.primary.forEach((item) => nav.appendChild(createAppLink(item, path)));

    // Botón "Más": solo visible en móvil/tablet (ver ds.css).
    const more = document.createElement('button');
    more.type = 'button';
    more.className = 'app-link nav-more-btn';
    more.setAttribute('aria-haspopup', 'true');
    more.setAttribute('aria-expanded', 'false');
    more.setAttribute('aria-controls', 'navMoreSheet');
    more.innerHTML = `${ICONS.more}<span class="link-label">Más</span>`;
    more.addEventListener('click', () => setMore(nav.dataset.more !== 'open'));
    nav.appendChild(more);

    nav.appendChild(buildMoreSheet(config, path));
  }

  // Cerrar la hoja "Más" con Escape o tocando fuera de la barra.
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && nav.dataset.more === 'open') {
      setMore(false);
      nav.querySelector('.nav-more-btn')?.focus();
    }
  });
  document.addEventListener('pointerdown', (event) => {
    if (nav.dataset.more === 'open' && !nav.contains(event.target)) setMore(false);
  });

  updateNav();
  window.addEventListener('hashchange', updateNav);
}
