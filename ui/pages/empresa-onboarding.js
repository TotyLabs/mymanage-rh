import { apiFetch, showError, showSuccess, withLoader } from '../common.js';

function el(id, ctx = document) {
  return (ctx || document).querySelector(id.startsWith('#') ? id : `#${id}`);
}

export async function render(container) {
  // Get current user to pre-fill
  const meRes = await apiFetch('/api/auth/me');
  const user = meRes?.user;

  if (!user || user.role !== 'admin') {
    location.hash = '#/select-role';
    return;
  }

  container.innerHTML = `
    <section class="auth-shell">
      <div class="card auth-card auth-card-main max-w-600">
        <div class="auth-header">
          <div class="auth-icon" aria-hidden="true">
            <svg width="24" height="24" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4"></path>
            </svg>
          </div>

          <h1 class="auth-title">Completar Registro de Empresa</h1>
          <p class="auth-subtitle">
            Para comenzar a usar MyManageRH, por favor completá los datos de tu organización y aceptá los términos de servicio.
          </p>
        </div>

        <div id="onboardingMsg" class="mb-16"></div>

        <form id="onboardingForm" class="auth-form" novalidate>
          <div class="form-group">
            <label for="orgName">Nombre de la Empresa</label>
            <input
              id="orgName"
              type="text"
              class="input"
              placeholder="Ej: Mi Empresa S.A."
              value="${user.organization_name || ''}"
            />
          </div>

          <div class="form-group">
            <label for="orgCuit">CUIT de la Empresa</label>
            <input
              id="orgCuit"
              type="text"
              class="input"
              placeholder="30-XXXXXXXX-X"
              value="${user.organization_cuit || ''}"
            />
            <div class="form-hint mt-4">Formato sugerido: 11 dígitos sin guiones.</div>
          </div>

          <div class="form-group">
            <label for="orgEmail">Email de contacto</label>
            <input
              id="orgEmail"
              type="email"
              class="input"
              placeholder="empresa@mail.com"
              value="${user.organization_email || user.email || ''}"
            />
          </div>

          <div class="tos-container bg-gray-50 p-16 rounded border text-xs text-muted mb-24 max-h-200 overflow-y-auto">
            <h4 class="font-bold text-dark mb-8">Términos y Condiciones de Uso</h4>
            <p>Al acceder y utilizar el sistema MyManageRH, usted acepta cumplir con los siguientes términos...</p>
            <p>1. <strong>Confidencialidad:</strong> Usted es responsable de mantener la confidencialidad de su clave de acceso corporativa.</p>
            <p>2. <strong>Uso Autorizado:</strong> El sistema debe utilizarse exclusivamente para la gestión de recibos de sueldo y firmas digitales de su personal.</p>
            <p>3. <strong>Protección de Datos:</strong> MyManageRH cumple con la Ley de Protección de Datos Personales...</p>
            <p class="mt-12"><em>Para leer los términos completos, haga clic en el enlace de ayuda en el pie de página.</em></p>
          </div>

          <div class="form-group">
            <label class="checkbox-label">
              <input id="acceptTos" type="checkbox" ${user.tos_accepted ? 'checked' : ''} />
              <span class="text-sm font-semibold">He leído y acepto los Términos y Condiciones de Servicio</span>
            </label>
          </div>

          <button id="btnFinish" type="submit" class="btn btn-primary btn-lg w-full">
            Finalizar y entrar al Dashboard
          </button>
        </form>
      </div>
    </section>
  `;

  const msgEl = el('onboardingMsg', container);
  const formEl = el('onboardingForm', container);

  formEl.addEventListener(
    'submit',
    withLoader(async (event) => {
      event.preventDefault();
      msgEl.innerHTML = '';

      const name = el('orgName', formEl).value.trim();
      const cuit = el('orgCuit', formEl).value.trim().replace(/\D/g, '');
      const email = el('orgEmail', formEl).value.trim();
      const acceptTos = el('acceptTos', formEl).checked;

      if (!name || !cuit || !email) {
        showError(msgEl, 'Por favor completá todos los datos obligatorios.');
        return;
      }

      if (cuit.length !== 11) {
        showError(msgEl, 'El CUIT debe tener 11 dígitos.');
        return;
      }

      if (!acceptTos) {
        showError(msgEl, 'Debes aceptar los Términos y Condiciones para continuar.');
        return;
      }

      try {
        await apiFetch('/api/organizations/me', {
          method: 'PATCH',
          body: { name, cuit, email, accept_tos: true },
        });

        // Invalidate user cache to force re-fetch in router
        delete window.__USER_CACHE__;

        showSuccess(msgEl, '¡Configuración completada con éxito!');
        
        setTimeout(() => {
          location.hash = '#/empresa/dashboard';
        }, 1500);
      } catch (error) {
        showError(msgEl, error);
      }
    })
  );
}
