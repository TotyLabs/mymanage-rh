/**
 * Pantalla inicial: elegir rol (Empresa o Empleado).
 * Estética sobria, clara y orientada a confianza operativa.
 */
import { navigateTo } from '../utils.js';

export async function render(container) {

  container.innerHTML = `
    <section class="role-select-shell">
      <div class="role-select-intro">
        <div class="mb-16">
          <span class="badge neutral">Plataforma de firma electrónica</span>
        </div>

        <h1 class="role-select-title">MyManageRH</h1>

        <p class="role-select-desc">
          Gestión centralizada y segura de recibos de sueldo, firmas digitales y documentación laboral.
        </p>
      </div>

      <div class="role-grid">
        <article class="role-card role-card-company" data-role="empresa" tabindex="0">
          <div class="role-card-head">
            <div class="role-card-icon role-card-icon-company" aria-hidden="true">
              <svg width="32" height="32" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4"></path>
              </svg>
            </div>

            <div>
              <h2 class="role-card-title">Empresa</h2>
              <span class="text-subtle">Panel administrativo</span>
            </div>
          </div>

          <p class="role-card-desc">
            Subí recibos en lote, gestioná empleados y supervisá el estado de firma de cada documento.
          </p>

          <button class="btn role-btn" type="button" tabindex="-1">
            Ingreso corporativo
            <svg class="role-btn-arrow" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"></line><polyline points="12 5 19 12 12 19"></polyline></svg>
          </button>
        </article>

        <article class="role-card role-card-employee" data-role="empleado" tabindex="0">
          <div class="role-card-head">
            <div class="role-card-icon role-card-icon-employee" aria-hidden="true">
              <svg width="32" height="32" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"></path>
              </svg>
            </div>

            <div>
              <h2 class="role-card-title">Empleado</h2>
              <span class="text-subtle">Portal personal</span>
            </div>
          </div>

          <p class="role-card-desc">
            Accedé a tu legajo, descargá recibos de haberes y firmá documentación electrónicamente.
          </p>

          <button class="btn role-btn" type="button" tabindex="-1">
            Ingreso empleados
            <svg class="role-btn-arrow" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"></line><polyline points="12 5 19 12 12 19"></polyline></svg>
          </button>
        </article>
      </div>

      <div class="role-select-trust">
        <span class="role-trust-item">
          <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"></path>
          </svg>
          Infraestructura segura
        </span>

        <span class="role-trust-item">
          <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path>
          </svg>
          Cumplimiento documental
        </span>
      </div>

      <a href="#/soporte" class="role-support-banner">
        <div class="role-support-banner-content">
          <div class="role-support-banner-icon" aria-hidden="true">
            <svg width="24" height="24" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" d="M18.364 5.636a9 9 0 11-12.728 0M12 21v-3m-4-4a4 4 0 018 0v1a2 2 0 01-2 2H10a2 2 0 01-2-2v-1z"></path>
            </svg>
          </div>
          <div>
            <h3 class="role-support-banner-title">¿Necesitás ayuda o soporte técnico?</h3>
            <p class="role-support-banner-desc">Contactá directamente con nuestro equipo de atención</p>
          </div>
        </div>
        <span class="btn role-support-banner-btn">
          Ir a Soporte
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="5" y1="12" x2="19" y2="12"></line><polyline points="12 5 19 12 12 19"></polyline></svg>
        </span>
      </a>
    </section>
  `;

  const goToRole = (role) => {
    navigateTo(`#/login?role=${role}`);
  };

  container.querySelectorAll('.role-card').forEach((card) => {
    card.addEventListener('click', () => {
      const role = card.getAttribute('data-role');
      goToRole(role);
    });

    card.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        const role = card.getAttribute('data-role');
        goToRole(role);
      }
    });
  });
}