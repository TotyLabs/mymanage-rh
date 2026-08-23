/**
 * Forgot Password: solicita restablecimiento de contraseña.
 * UX: Siempre muestra mensaje de éxito (no revela si el email existe).
 */
import { apiFetch, showError, showSuccess, withLoader } from '../common.js';

function el(id, ctx = document) {
  return (ctx || document).querySelector(id.startsWith('#') ? id : `#${id}`);
}

export async function render(container, params) {
  const role = params?.get ? params.get('role') : 'empleado';
  const isEmpresa = role === 'empresa';

  const title = isEmpresa ? 'Recuperar Clave de Empresa' : 'Restablecer contraseña';
  const subtitle = isEmpresa 
    ? 'Ingresá el Mail de administración y te enviaremos un código para generar una nueva clave.'
    : 'Ingresá tu correo electrónico y te enviaremos un código de seguridad para restablecer tu contraseña.';

  container.innerHTML = `
    <section class="auth-shell">
      <div class="card auth-card auth-card-main">
        <div class="auth-header">
          <div class="auth-icon" aria-hidden="true">
            <svg width="24" height="24" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z"></path>
            </svg>
          </div>

          <h1 class="auth-title">${title}</h1>
          <p class="auth-subtitle">${subtitle}</p>
        </div>

        <div id="forgotMsg" class="mb-16"></div>

        <form id="forgotForm" class="auth-form" novalidate>
          <div class="form-group">
            <label for="forgotEmail">Correo electrónico</label>
            <input
              id="forgotEmail"
              type="email"
              class="input"
              placeholder="tu@email.com"
              autocomplete="email"
            />
          </div>

          <button id="btnForgot" type="submit" class="btn btn-primary btn-lg w-full">
            Enviar código de restablecimiento
          </button>
        </form>

        <div class="auth-backlink">
          <a class="link" href="#/login">← Volver al inicio de sesión</a>
        </div>
      </div>
    </section>
  `;

  const msgEl = el('forgotMsg', container);
  const formEl = el('forgotForm', container);
  const emailInput = el('forgotEmail', container);

  formEl.addEventListener(
    'submit',
    withLoader(async (event) => {
      event.preventDefault();
      msgEl.innerHTML = '';

      const email = emailInput.value.trim();
      if (!email) {
        showError(msgEl, 'Ingresá tu correo electrónico.');
        return;
      }

      try {
        const res = await apiFetch('/api/auth/forgot-password', {
          method: 'POST',
          body: { email },
        });

        showSuccess(
          msgEl,
          res?.message || 'Te enviamos un código de 6 dígitos a tu correo electrónico.'
        );

        // Redirect to OTP input screen only on success
        setTimeout(() => {
          location.hash = `#/reset-password?email=${encodeURIComponent(email)}&role=${role}`;
        }, 1500);

      } catch (error) {
        showError(msgEl, error);
      }
    })
  );

  // Focus email input on load
  emailInput.focus();
}
