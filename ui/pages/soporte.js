/**
 * Página individual de Soporte MyManageRH
 */
import { navigateTo } from '../utils.js';

export async function render(container) {
  container.innerHTML = `
    <section class="role-select-shell">
      <div class="role-select-intro" style="margin-bottom: 32px;">
        <div class="mb-16">
          <a href="#/select-role" class="badge neutral" style="text-decoration: none; cursor: pointer;">← Volver al inicio</a>
        </div>

        <h1 class="role-select-title" style="margin-top: 12px; margin-bottom: 12px;">Centro de Soporte</h1>

        <p class="role-select-desc">
          Completá tus datos y la descripción de tu consulta. Se abrirá tu aplicación de correo o Gmail con todos los datos precargados para enviar el mensaje directamente a nuestro equipo.
        </p>
      </div>

      <div class="role-support-section" style="margin-top: 0; max-width: 580px;">
        <div class="role-support-header">
          <div class="role-support-icon" aria-hidden="true">
            <svg width="28" height="28" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" d="M18.364 5.636a9 9 0 11-12.728 0M12 21v-3m-4-4a4 4 0 018 0v1a2 2 0 01-2 2H10a2 2 0 01-2-2v-1z"></path>
            </svg>
          </div>
          <div>
            <h3 class="role-support-title">Enviar consulta a soporte</h3>
            <p class="role-support-subtitle">Completá el formulario y te responderemos a la brevedad</p>
          </div>
        </div>

        <form id="supportForm" class="role-support-form" autocomplete="off">
          <div class="support-field">
            <label for="supportName" class="support-label">Nombre completo</label>
            <input type="text" id="supportName" class="support-input" placeholder="Ej: Juan Pérez" required />
          </div>

          <div class="support-field">
            <label for="supportEmail" class="support-label">Tu Email / Gmail</label>
            <input type="email" id="supportEmail" class="support-input" placeholder="Ej: juan@gmail.com" required />
          </div>

          <div class="support-field">
            <label for="supportSubject" class="support-label">Asunto</label>
            <input type="text" id="supportSubject" class="support-input" placeholder="Ej: Consulta sobre firma de recibo" required />
          </div>

          <div class="support-field">
            <label for="supportDesc" class="support-label">Descripción del inconveniente o consulta</label>
            <textarea id="supportDesc" class="support-input support-textarea" placeholder="Describí tu consulta con el mayor detalle posible..." rows="5" required></textarea>
          </div>

          <button class="btn role-support-btn" type="submit">
            <svg width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"></path>
            </svg>
            Enviar mensaje a soporte
          </button>
        </form>
      </div>

      <div style="margin-top: 24px;">
        <a href="#/select-role" style="color: var(--slate-500); font-weight: 600; text-decoration: none; font-size: 14px;">
          ← Volver a selección de rol
        </a>
      </div>
    </section>
  `;

  // Support form handler
  const supportForm = container.querySelector('#supportForm');
  if (supportForm) {
    supportForm.addEventListener('submit', (e) => {
      e.preventDefault();

      const name = container.querySelector('#supportName').value.trim();
      const email = container.querySelector('#supportEmail').value.trim();
      const subject = container.querySelector('#supportSubject').value.trim();
      const desc = container.querySelector('#supportDesc').value.trim();

      const body = `Nombre: ${name}\nEmail de contacto: ${email}\n\n${desc}`;
      const targetEmail = 'mymanagerh.ar@gmail.com';
      const subjectEncoded = encodeURIComponent(subject);
      const bodyEncoded = encodeURIComponent(body);

      const mailtoUrl = `mailto:${targetEmail}?subject=${subjectEncoded}&body=${bodyEncoded}`;
      const gmailWebUrl = `https://mail.google.com/mail/?view=cm&fs=1&to=${targetEmail}&su=${subjectEncoded}&body=${bodyEncoded}`;

      const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent) || (window.innerWidth <= 768);

      if (isMobile) {
        window.location.href = mailtoUrl;
      } else {
        const win = window.open(gmailWebUrl, '_blank');
        if (!win || win.closed || typeof win.closed === 'undefined') {
          window.location.href = mailtoUrl;
        }
      }
    });
  }
}
