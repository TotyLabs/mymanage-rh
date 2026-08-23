import { navigateTo } from '../utils.js';

export async function render(container) {
  container.innerHTML = `
    <section class="hero-section hero-section-sm">
      <div class="hero-copy">
        <h1 class="hero-title">MyManageRH</h1>
        <p class="hero-desc">
          Plataforma corporativa para gestión y firma electrónica de recibos.
        </p>
      </div>

      <div class="role-grid">
        <article class="card role-card-simple">
          <h2 class="role-card-title mb-8">Módulo corporativo</h2>
          <p class="text-muted mb-16 role-card-desc">
            Administrá recibos, validá documentación y seguí el estado de firmas.
          </p>
          <button class="btn btn-primary w-full" data-role="company">
            Acceso corporativo
          </button>
        </article>

        <article class="card role-card-simple">
          <h2 class="role-card-title mb-8">Portal empleado</h2>
          <p class="text-muted mb-16 role-card-desc">
            Firmá documentación, consultá recibos y accedé a tus copias digitales.
          </p>
          <button class="btn btn-secondary w-full" data-role="employee">
            Acceso empleados
          </button>
        </article>
      </div>
    </section>
  `;

  container.querySelectorAll('button[data-role]').forEach((button) => {
    button.addEventListener('click', () => {
      const role = button.getAttribute('data-role');
      navigateTo(`#/auth?role=${role}`);
    });
  });
}