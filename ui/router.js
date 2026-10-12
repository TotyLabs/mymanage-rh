/**
 * Router con separación de roles y protección de rutas.
 */
import { getMe, logoutSession } from './common.js?v=118';
import { tosAcceptance } from './tos-acceptance.js?v=118';
import { ROUTES } from './constants.js?v=118';

const VERSION = '118'; // Refresh the updated employee legajo editor

const loadPage = (page) => import(`./pages/${page}.js?v=${VERSION}`);

const routes = {
  '': () => loadPage('landing'),
  '#/': () => loadPage('landing'),
  '#/select-role': () => loadPage('select-role'),
  '#/soporte': () => loadPage('soporte'),
  '#/login': () => loadPage('login'),
  '#/auth': () => loadPage('auth'),
  '#/forgot-password': () => loadPage('forgot-password'),
  '#/reset-password': () => loadPage('reset-password'),
  '#/documentacion': () => loadPage('documentation'),
  '#/tos-gate': () => loadPage('tos-gate'),
  '#/dashboard': async () => {
    const user = await getCurrentUser();
    if (user?.role === 'admin') location.hash = ROUTES.dashboard;
    else if (user?.role === 'employee') location.hash = ROUTES.myReceipts;
    else location.hash = ROUTES.root;
  },

  '#/empresa/dashboard': () => loadPage('empresa-dashboard'),
  '#/empresa/recibos': () => loadPage('empresa-dashboard'),
  '#/empresa/batches': () => loadPage('empresa-dashboard'),
  '#/empresa/empleados': () => loadPage('empresa-empleados'),
  '#/empresa/modelos-laborales': () => loadPage('empresa-modelos-laborales'),
  '#/empresa/configuracion': () => loadPage('empresa-configuracion'),
  '#/empresa/historial': () => loadPage('empresa-historial'),
  '#/empresa/notificaciones': () => loadPage('empresa-notificaciones'),

  '#/empleado/recibos': () => loadPage('empleado-recibos'),
  '#/empleado/perfil': () => loadPage('empleado-home'),
  '#/empleado/notificaciones': () => loadPage('empleado-notificaciones'),
  '#/empleado/inicio': () => { location.hash = '#/empleado/recibos'; },
  '#/empleado/dashboard': () => { location.hash = '#/empleado/recibos'; },
  '#/empleado-dashboard': () => { location.hash = '#/empleado/recibos'; },

  '#/sign': () => loadPage('sign'),
  '#/verify': () => loadPage('verify'),
  '#/verify-account': () => loadPage('verify-account'),
  '#/empresa/onboarding': () => loadPage('empresa-onboarding'),
};

function renderNavbar(user, currentPath) {
  if (!user) return '';

  const active = (p) => (currentPath === p ? 'active' : '');

  if (user.role === 'admin') {
    return `
      <a href="#/empresa/dashboard" class="nav-link ${active('#/empresa/dashboard')}">Panel de Control</a>
      <a href="#/empresa/historial" class="nav-link ${active('#/empresa/historial')}">Historial</a>
      <a href="#/empresa/empleados" class="nav-link ${active('#/empresa/empleados')}">Empleados</a>
      <a href="#/empresa/modelos-laborales" class="nav-link ${active('#/empresa/modelos-laborales')}">Modelos Laborales</a>
      <a href="#/empresa/notificaciones" class="nav-link ${active('#/empresa/notificaciones')}" id="nav-notif">Notificaciones</a>
      <a href="#/empresa/configuracion" class="nav-link ${active('#/empresa/configuracion')}">Configuración</a>
      <a href="javascript:void(0)" onclick="logout()" class="nav-link">Cerrar sesión</a>
    `;
  }

  if (user.role === 'employee') {
    return `
      <a href="#/empleado/recibos" class="nav-link ${active('#/empleado/recibos')}">Mis Recibos</a>
      <a href="#/empleado/notificaciones" class="nav-link ${active('#/empleado/notificaciones')}" id="nav-notif">Notificaciones</a>
      <a href="#/empleado/perfil" class="nav-link ${active('#/empleado/perfil')}">Mi Perfil</a>
      <a href="javascript:void(0)" onclick="logout()" class="nav-link">Cerrar sesión</a>
    `;
  }

  return '';
}

async function updateNotificationBadges() {
    try {
        const token = localStorage.getItem('token');
        if (!token) return;

        const res = await fetch('/api/notifications/unread-count', {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (res.status === 401) return;
        
        const data = await res.json();
        const navNotif = document.getElementById('nav-notif');
        if (navNotif && data.count > 0) {
            // Remove old badge if exists
            const oldBadge = navNotif.querySelector('.notification-badge');
            if (oldBadge) oldBadge.remove();
            
            const badge = document.createElement('span');
            badge.className = 'notification-badge';
            badge.textContent = data.count > 9 ? '9+' : data.count;
            navNotif.appendChild(badge);
        }
    } catch (e) {
        console.error('Error updating badges:', e);
    }
}

// Polling every 60 seconds
setInterval(updateNotificationBadges, 60000);

window.logout = async () => {
    try {
    await logoutSession();
    location.hash = '#/select-role';
  } catch (error) {
    console.error('Error al cerrar sesión:', error);
    window.alert('No se pudo cerrar la sesión. Verificá la conexión e intentá nuevamente.');
  }
};

function parseHash() {
  const hash = location.hash || '#/';
  const [path, queryString] = hash.split('?');
  return {
    path: path || '#/',
    params: new URLSearchParams(queryString || ''),
  };
}

function isSignRoute(path) {
  return path.startsWith('#/sign/');
}

function isVerifyRoute(path) {
  return path.startsWith('#/verify/');
}

function isVerifyAccountRoute(path) {
  return path === '#/verify-account';
}

function getFallbackRoute() {
  return routes['#/'] || (() => loadPage('select-role'));
}

async function getCurrentUser() {
  try {
    // We check session cache first
    if (window.__USER_CACHE__) return window.__USER_CACHE__;
    const me = await getMe();
    const user = me?.user || me || null;
    window.__USER_CACHE__ = user;
    return user;
  } catch (error) {
    return null;
  }
}

function redirectToLogin(role, path) {
  const redirect = encodeURIComponent(location.hash || path || '#/');
  location.hash = `#/login?role=${role}&redirect=${redirect}`;
}

function redirectToHome() {
  location.hash = '#/select-role';
}

function redirectToVerify(email) {
  location.hash = `#/verify-account?email=${encodeURIComponent(email)}`;
}

async function resolveRoute(path) {
  if (isSignRoute(path)) return () => loadPage('sign');
  if (isVerifyRoute(path)) return () => loadPage('verify');
  if (isVerifyAccountRoute(path)) return () => loadPage('verify-account');
  return routes[path] || getFallbackRoute();
}

function renderRouteError(error, path = '') {
  const pageEl = document.getElementById('page');
  if (!pageEl) return;

  pageEl.innerHTML = `
    <div class="error">
      <h3>No se pudo cargar la página solicitada</h3>
      <div class="small-muted mt-8 mb-12">Ruta: ${path || location.hash}</div>
      <div class="error-hint mt-8 p-16 bg-error-light rounded shadow-sm">
        <strong>Detalle del error:</strong> ${error?.message || error || 'Error desconocido'}
      </div>
      <button class="btn btn-secondary mt-16" onclick="location.reload()">Reintentar carga</button>
    </div>
  `;

  console.error('Error al cargar ruta:', error, 'Path:', path);
}

export function initRouter() {
  async function guardAndRender() {
    const { path, params } = parseHash();
    
    // 1. Fetch User (Unified check)
    const user = await getCurrentUser();

    // 2. Global Status Guard (Hardened)
    if (user && user.user_status !== 'active') {
      if (!isVerifyAccountRoute(path) && path !== '#/login' && path !== '#/') {
        redirectToVerify(user.email || user.username);
        return;
      }
    }
    
    // 2.1 Reverse Guard: If active but on verify-account, go to dashboard
    if (user && user.user_status === 'active' && isVerifyAccountRoute(path)) {
      if (user.role === 'admin') location.hash = '#/empresa/dashboard';
      else if (user.role === 'employee') location.hash = '#/empleado/recibos';
      else location.hash = '#/';
      return;
    }

    // 2.2 Navigation guardrail for employees (Safety check)
    if (user && user.role === 'employee') {
      const isEmployeeRoute = path.startsWith('#/empleado/') || path === ROUTES.tosGate || isSignRoute(path) || isVerifyRoute(path) || isVerifyAccountRoute(path) || path === '#/empleado/notificaciones' || path.startsWith('#/documentacion') || path === '#/logout';
      if (!isEmployeeRoute || path === '#/empleado/' || path === '#/empleado') {
        location.hash = '#/empleado/recibos';
        return;
      }
    }

    // 2.3 Navigation guardrail for admins
    if (user && user.role === 'admin') {
      const isAdminRoute = path.startsWith('#/empresa/') || path === '#/dashboard' || path === '#/empresa/notificaciones' || isVerifyAccountRoute(path) || isSignRoute(path) || isVerifyRoute(path) || path.startsWith('#/documentacion') || path === '#/logout';
      if (!isAdminRoute) {
        location.hash = '#/empresa/dashboard';
        return;
      }
    }

    // 3. Resolve and Render
    const renderFn = await resolveRoute(path);
    const navEl = document.getElementById('navbar-nav');
    if (navEl) {
      navEl.innerHTML = renderNavbar(user, path);
      // GAP-010: Only update unread count if user is logged in
      if (user) {
        updateNotificationBadges();
      }
    }

    // 2.3 TOS & Onboarding Gate Guard
    if (user && user.user_status === 'active') {
      const needsOnboarding = user.role === 'admin' && (!user.tos_accepted || !user.organization_cuit);
      const needsTos = user.role === 'employee' && !tosAcceptance.check(user);

      if (needsOnboarding) {
        if (path !== ROUTES.onboarding && path !== ROUTES.logout && !path.startsWith('#/documentacion')) {
          localStorage.setItem('tos_target_route', path);
          location.hash = ROUTES.onboarding;
          return;
        }
      } else if (needsTos) {
        if (path !== ROUTES.tosGate && path !== ROUTES.logout && !path.startsWith('#/documentacion')) {
          localStorage.setItem('tos_target_route', path);
          location.hash = ROUTES.tosGate;
          return;
        }
      }
    }

    // 3. Role-based Guards
    if (path.startsWith('#/empresa/')) {
      if (!user) {
        redirectToLogin('empresa', path);
        return;
      }
      if (user.role !== 'admin') {
        redirectToHome();
        return;
      }
    }

    if (path.startsWith('#/empleado/') || path.startsWith('#/empleado-dashboard')) {
      if (!user) {
        redirectToLogin('empleado', path);
        return;
      }
      if (!['employee', 'admin'].includes(user.role)) {
        redirectToHome();
        return;
      }
    }

    try {
      const loader = await resolveRoute(path);
      const module = await loader();

      const pageEl = document.getElementById('page');
      if (!pageEl) return;

      pageEl.innerHTML = '';

      if (module?.render) {
        await module.render(pageEl, params);
      }
    } catch (error) {
      renderRouteError(error, path);
    }
  }

  window.addEventListener('hashchange', guardAndRender);
  guardAndRender();
}