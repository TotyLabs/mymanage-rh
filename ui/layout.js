import { logoutSession, showToast } from './common.js?v=118';

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

function createNavLink(href, text, isActive) {
  const link = document.createElement('a');
  link.className = `link ${isActive ? 'active' : ''}`;
  link.href = href;
  link.textContent = text;
  return link;
}

function createRoleBadge(text) {
  const badge = document.createElement('span');
  badge.className = 'nav-role';
  badge.textContent = text;
  return badge;
}

function createSeparator() {
  const sep = document.createElement('div');
  sep.className = 'nav-separator';
  sep.style.width = '1px';
  sep.style.height = '20px';
  sep.style.background = 'var(--slate-200)';
  sep.style.margin = '0 8px';
  return sep;
}

function createLogoutButton() {
  const button = document.createElement('button');
  button.className = 'btn btn-logout';
  button.innerHTML = `
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path>
      <polyline points="16 17 21 12 16 7"></polyline>
      <line x1="21" y1="12" x2="9" y2="12"></line>
    </svg>
    Salir
  `;
  button.addEventListener('click', logoutAndReturnHome);
  return button;
}

export function renderLayout(root) {
  if (!root) return;

  root.innerHTML = `
    <div class="layout">
      <header class="site-header" id="siteHeader">
        <div class="brand">
          <a href="#/" class="brand-link">
            <span class="brand-title">MyManageRH</span>
          </a>
        </div>

        <nav class="header-actions" id="headerNav"></nav>
      </header>

      <main id="page" class="page container"></main>

      <div id="toasts" class="toasts" aria-live="polite"></div>

      <div id="confirmModal" class="modal hidden" aria-hidden="true">
        <div class="modal-content modal-content-sm">
          <h3>Confirmar acción</h3>
          <div id="confirmMsg" class="small-muted mt-8">¿Estás seguro?</div>

          <div class="modal-actions mt-12">
            <button id="confirmCancel" class="btn btn-ghost">Cancelar</button>
            <button id="confirmOk" class="btn btn-primary">Confirmar</button>
          </div>
        </div>
      </div>

      <footer class="footer">
        <div class="footer-content">
          <div class="footer-legal">
            <a href="#/documentacion?docId=tos">Términos y Condiciones</a>
            <span class="separator">|</span>
            <a href="#/documentacion?docId=privacy">Política de Privacidad</a>
          </div>
          <div class="footer-copyright">
            © 2026 MyManageRH
          </div>
        </div>
      </footer>
    </div>
  `;
}

export function bindHeader() {
  const nav = document.getElementById('headerNav');
  if (!nav) return;

  function updateNav() {
    const path = location.hash || '#/';
    const type = getLayoutType(path);

    nav.innerHTML = '';

    if (type === 'public') {
      if (path.startsWith('#/login')) {
        nav.appendChild(createNavLink('#/select-role', 'Volver', false));
      }

      if (path.startsWith('#/sign/')) {
        nav.appendChild(createNavLink('#/select-role', 'Volver', false));
      }

      return;
    }

    if (type === 'empresa') {
      nav.appendChild(createRoleBadge('Empresa'));
      nav.appendChild(createSeparator());

      const links = [
        { href: '#/empresa/dashboard', text: 'Panel de Control' },
        { href: '#/empresa/historial', text: 'Historial' },
        { href: '#/empresa/empleados', text: 'Empleados' },
        { href: '#/empresa/modelos-laborales', text: 'Modelos Laborales' },
        { href: '#/empresa/notificaciones', text: 'Notificaciones', id: 'nav-notif' },
        { href: '#/empresa/configuracion', text: 'Configuración' },
      ];

      links.forEach(({ href, text, id }) => {
        const isActive = path.startsWith(href);
        const link = createNavLink(href, text, isActive);
        if (id) link.id = id;
        nav.appendChild(link);
      });

      nav.appendChild(createSeparator());
      nav.appendChild(createLogoutButton());
      return;
    }

    if (type === 'empleado') {
      nav.appendChild(createRoleBadge('Empleado'));
      nav.appendChild(createSeparator());

      const links = [
        { href: '#/empleado/recibos', text: 'Mis recibos' },
        { href: '#/empleado/notificaciones', text: 'Notificaciones', id: 'nav-notif' },
        { href: '#/empleado/perfil', text: 'Mi Perfil' },
      ];

      links.forEach(({ href, text, id }) => {
        const isActive = path.startsWith(href);
        const link = createNavLink(href, text, isActive);
        if (id) link.id = id;
        nav.appendChild(link);
      });

      nav.appendChild(createSeparator());
      nav.appendChild(createLogoutButton());
    }
  }

  updateNav();
  window.addEventListener('hashchange', updateNav);
}