/**
 * TOS Gate Page
 * Full-screen blocker forcing acceptance.
 */
import { docsContent } from '../docs-content.js';
import { tosAcceptance } from '../tos-acceptance.js';
import { ROUTES } from '../constants.js';

export const render = async (container, params = {}) => {
  const user = window.__USER_CACHE__;
  if (!user) {
    window.location.hash = ROUTES.login;
    return;
  }

  const doc = docsContent['tos'];

  container.innerHTML = `
    <div class="tos-gate-overlay">
      <div class="tos-gate-card">
        <header class="tos-gate-header">
          <img src="/static/logo.png" alt="Logo" class="tos-logo" onerror="this.src='https://placehold.co/120x40?text=MyManageRH'"/>
          <h2>Actualización de Términos y Condiciones</h2>
          <p>Para continuar utilizando la plataforma, debés leer y aceptar los nuevos términos legales.</p>
        </header>
        
        <div class="tos-gate-body">
          <div class="tos-viewer markdown-body">
            ${doc.html}
          </div>
        </div>
        
        <footer class="tos-gate-footer">
          <div class="tos-checkbox-wrapper">
            <label class="checkbox-container">
              <input type="checkbox" id="tos-confirm-checkbox">
              <span class="checkmark"></span>
              Confirmo que he leído y acepto los <a href="#/documentacion?docId=tos" target="_blank">Términos y Condiciones</a> y la <a href="#/documentacion?docId=privacy" target="_blank">Política de Privacidad</a>.
            </label>
          </div>
          
          <div class="tos-actions">
            <button id="tos-accept-btn" class="btn btn-primary btn-block" disabled>
              Aceptar y Continuar
            </button>
            <button id="tos-logout-btn" class="btn btn-link btn-sm">
              Cerrar sesión
            </button>
          </div>
        </footer>
      </div>
    </div>
  `;

  // Interaction logic
  const checkbox = document.getElementById('tos-confirm-checkbox');
  const acceptBtn = document.getElementById('tos-accept-btn');
  const logoutBtn = document.getElementById('tos-logout-btn');

  checkbox.addEventListener('change', () => {
    acceptBtn.disabled = !checkbox.checked;
  });

  acceptBtn.addEventListener('click', async () => {
    acceptBtn.disabled = true;
    acceptBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Procesando...';
    
    const success = await tosAcceptance.accept(user);
    if (success) {
      // Redirect back to original target if stored, or dashboard
      const target = localStorage.getItem('tos_target_route') || ROUTES.dashboard;
      localStorage.removeItem('tos_target_route');
      window.location.hash = target;
    } else {
      acceptBtn.disabled = false;
      acceptBtn.innerHTML = 'Aceptar y Continuar';
    }
  });

  logoutBtn.addEventListener('click', () => {
    window.location.hash = ROUTES.logout;
  });
};
