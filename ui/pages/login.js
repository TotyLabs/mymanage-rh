/**
 * Login: endpoint /api/auth/login, sesión por cookie, redirección por rol.
 * UX: pantalla de acceso con jerarquía clara y foco operativo.
 *
 * Features:
 * - "Recordar mis datos" checkbox → saves email to localStorage
 * - "¿Olvidaste tu contraseña?" link → forgot-password flow
 */
import { apiFetch, showError, showToast, withLoader } from '../common.js';
import { saveUserData, loadUserData, clearUserData, isRememberEnabled } from '../remember-user.js';
import { ROUTES } from '../constants.js';


function el(id, ctx = document) {
  return (ctx || document).querySelector(id.startsWith('#') ? id : `#${id}`);
}

export async function render(container, params) {
  const roleHint = params?.get ? params.get('role') : '';
  const redirect = params?.get ? params.get('redirect') : '';

  if (roleHint === 'empresa') {
    // ==========================================
    // EMPRESA LOGIN (TOKEN-ONLY)
    // ==========================================
    container.innerHTML = `
      <section class="auth-shell">
        <div class="card auth-card auth-card-main">
          <div class="auth-header">
            <div class="auth-icon" aria-hidden="true">
              <svg width="24" height="24" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4"></path>
              </svg>
            </div>

            <h1 class="auth-title">Acceso Corporativo</h1>
            <p class="auth-subtitle">
              Ingresá tu clave única de empresa para acceder al sistema.
            </p>
          </div>

          <div id="loginMsg" class="mb-16"></div>

          <form id="loginForm" class="auth-form" novalidate>
            <div class="form-group">
              <label for="loginClave">Clave de Acceso</label>
              <input
                id="loginClave"
                type="password"
                class="input font-mono text-center text-lg tracking-widest"
                placeholder="YCP-..."
                autocomplete="current-password"
              />
              <div class="form-hint mt-4 text-center">
                <a class="link text-sm" href="#/forgot-password?role=empresa">¿Olvidaste tu clave?</a>
              </div>
            </div>

            <button id="btnLogin" type="submit" class="btn btn-primary btn-lg w-full">
              Ingresar al sistema
            </button>
          </form>

          <div class="auth-backlink mt-8">
            <a class="link" href="#/select-role">← Volver al portal</a>
          </div>
        </div>
      </section>
    `;

    const msgEl = el('loginMsg', container);
    const formEl = el('loginForm', container);
    const claveInput = el('loginClave', container);

    formEl.addEventListener(
      'submit',
      withLoader(async (event) => {
        event.preventDefault();
        msgEl.innerHTML = '';

        const clave = claveInput.value.trim();
        if (!clave) {
          showError(msgEl, 'Ingresá tu clave corporativa.');
          return;
        }

        try {
          const res = await apiFetch('/api/auth/login-empresa', {
            method: 'POST',
            body: { clave },
          });

          if (res?.status === 'success' && res.user) {
            if (res.session_token) {
              localStorage.setItem('token', res.session_token);
            }
            // Guardar rol para enrutamiento (NO la clave)
            localStorage.setItem('userRole', res.user.role);
            localStorage.setItem('userId', res.user.id);

            // Onboarding check happens via an endpoint or by going directly to dashboard and intercepting
            // Here we just redirect to dashboard.
            location.hash = redirect || ROUTES.dashboard;
          } else {
            showError(msgEl, 'Clave inválida. Verificá los datos e intentá nuevamente.');
          }
        } catch (error) {
          showError(msgEl, error);
        }
      })
    );

    claveInput.focus();

  } else {
    // ==========================================
    // EMPLEADO LOGIN (EMAIL/DNI + PASSWORD)
    // ==========================================
    const roleLabel = roleHint === 'empleado' ? 'Acceso empleado' : 'Acceso al sistema';
    const remembered = loadUserData();
    const rememberChecked = isRememberEnabled();

    container.innerHTML = `
      <section class="auth-shell">
        <div class="card auth-card auth-card-main">
          <div class="auth-header">
            <div class="auth-icon" aria-hidden="true">
              <svg width="24" height="24" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" d="M12 11c0 3.517-1.009 6.799-2.753 9.571m-3.44-2.04l.054-.09A13.916 13.916 0 008 11a4 4 0 118 0c0 1.017-.07 2.019-.203 3m-2.118 6.844A21.88 21.88 0 0015.171 17m3.839 1.132c.645-2.266.99-4.659.99-7.132A8 8 0 008 4.07M3 15.364c.64-1.319 1-2.8 1-4.364 0-1.457.39-2.823 1.07-4"></path>
              </svg>
            </div>

            <h1 class="auth-title">${roleLabel}</h1>
            <p class="auth-subtitle">
              Ingresá con tus credenciales para continuar en MyManageRH.
            </p>
          </div>

          <div id="loginMsg" class="mb-16"></div>

          <form id="loginForm" class="auth-form" novalidate>
            <div class="form-group">
              <label for="loginEmail">Email</label>
              <input
                id="loginEmail"
                type="text"
                class="input"
                placeholder="ej: usuario@email.com"
                autocomplete="username"
                value="${remembered?.email || ''}"
              />
            </div>

            <div class="form-group">
              <label for="loginPassword">Contraseña</label>
              <input
                id="loginPassword"
                type="password"
                class="input"
                placeholder="Tu contraseña"
                autocomplete="current-password"
              />
              <div class="form-hint mt-4">
                <a class="link text-sm" href="#/forgot-password?role=empleado">¿Olvidaste tu contraseña?</a>
              </div>
            </div>

            <div class="form-group">
              <label class="checkbox-label">
                <input id="rememberCheck" type="checkbox" ${rememberChecked ? 'checked' : ''} />
                <span>Recordar mis datos</span>
              </label>
            </div>

            <button id="btnLogin" type="submit" class="btn btn-primary btn-lg w-full">
              Ingresar al sistema
            </button>
          </form>

          <div class="auth-backlink">
            <a class="link" href="#/select-role">← Volver al portal</a>
          </div>
        </div>

        <div class="card auth-card auth-card-secondary">
          <p class="text-muted auth-secondary-text">
            ¿No tenés cuenta de empleado?
          </p>

          <div class="flex-center gap-12 auth-secondary-actions">
            <a class="btn btn-ghost btn-sm" href="#/auth?role=empleado">Registrarme</a>
          </div>
        </div>
      </section>
    `;

    const msgEl = el('loginMsg', container);
    const formEl = el('loginForm', container);
    const emailInput = el('loginEmail', container);
    const passwordInput = el('loginPassword', container);
    const rememberCheck = el('rememberCheck', container);

    async function doLogin() {
      const email = emailInput.value.trim();
      const password = passwordInput.value;

      if (!email || !password) {
        showError(msgEl, 'Completá usuario y contraseña.');
        return;
      }

      msgEl.innerHTML = '';

      if (rememberCheck.checked) {
        saveUserData({ email });
      } else {
        clearUserData();
      }

      try {
        const response = await apiFetch('/api/auth/login', {
          method: 'POST',
          body: { username: email, password },
        });

        if (response?.session_token) {
          localStorage.setItem('token', response.session_token);
        }

        const user = response?.user || response;

        if (!user?.role) {
          showError(msgEl, 'La respuesta del servidor no incluye un rol válido.');
          return;
        }

        if (redirect && redirect.startsWith('#/')) {
          location.hash = redirect;
          return;
        }

        if (user.role === 'admin') {
          location.hash = '#/empresa/dashboard';
        } else if (user.role === 'employee') {
          location.hash = '#/empleado/dashboard';
        } else {
          location.hash = '#/select-role';
        }
      } catch (error) {
        if (error?.detail === 'cuenta_no_verificada' || error?.body?.detail === 'cuenta_no_verificada') {
          showToast('Debes verificar tu cuenta antes de ingresar.', 'warning');
          location.hash = `#/verify-account?email=${encodeURIComponent(email)}`;
          return;
        }
        showError(msgEl, error);
      }
    }

    formEl.addEventListener(
      'submit',
      withLoader(async (event) => {
        event.preventDefault();
        await doLogin();
      })
    );

    emailInput.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') {
        event.preventDefault();
        passwordInput.focus();
      }
    });

    if (!emailInput.value) emailInput.focus();
    else passwordInput.focus();
  }
}