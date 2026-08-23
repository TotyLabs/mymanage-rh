/**
 * LandingPage Component
 * Executive-level one-page entry point for MyManagerRH.
 * Focused on B2B conversion, legal integrity, and system infrastructure.
 */

const ICONS = {
  check: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>`,
  lock: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect><path d="M7 11V7a5 5 0 0 1 10 0v4"></path></svg>`,
  shield: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path></svg>`,
  file: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>`,
  users: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M23 21v-2a4 4 0 0 0-3-3.87"></path><path d="M16 3.13a4 4 0 0 1 0 7.75"></path></svg>`,
  upload: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="17 8 12 3 7 8"></polyline><line x1="12" y1="3" x2="12" y2="15"></line></svg>`,
  pen: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 19l7-7 3 3-7 7-3-3z"></path><path d="M18 13l-1.5-7.5L2 2l3.5 14.5L13 18l5-5z"></path><path d="M2 2l7.586 7.586"></path><circle cx="11" cy="11" r="2"></circle></svg>`,
  eye: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>`,
  grid: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"></rect><rect x="14" y="3" width="7" height="7"></rect><rect x="14" y="14" width="7" height="7"></rect><rect x="3" y="14" width="7" height="7"></rect></svg>`,
};

export async function render(container) {
  container.innerHTML = `
    <div class="landing-page">
      <section class="hero-section reveal-on-scroll">
        <div class="hero-copy">
          <span class="eyebrow">MyManageRH</span>
          <h1>MyManageRH</h1>
          <p class="hero-lead">Gestión laboral con firma digital y auditoría inalterable para tu empresa. Centraliza legajos, recibos y cumplimiento legal en un solo sistema seguro.</p>
          <div class="hero-actions">
            <a href="#/select-role" class="btn btn-primary btn-xl">Ingresar al sistema</a>
            <a href="#/soporte" class="btn btn-secondary btn-xl">Contactar Soporte</a>
          </div>
          <div class="hero-highlights">
            <article>
              <strong>Seguridad Jurídica</strong>
              <p>Respaldo legal inalterable en cada firma.</p>
            </article>
            <article>
              <strong>Eficiencia Operativa</strong>
              <p>Reducción de costos y tiempos de procesamiento.</p>
            </article>
            <article>
              <strong>Visibilidad Total</strong>
              <p>Control claro sobre todos los procesos documentales.</p>
            </article>
          </div>
        </div>
        <div class="hero-media">
          <img src="./IVMMRH/resource_8MPyrSyYQQ37qJAhRh3_JT.png" alt="Panel de control de empresa MyManageRH" loading="eager" />
        </div>
      </section>

      <section class="landing-section reveal-on-scroll intro-section">
        <span class="section-label">Módulos del Sistema</span>
        <h2>Ingeniería aplicada a los recursos humanos</h2>
        <p class="section-subtitle">Nuestra plataforma está estructurada para optimizar el flujo de trabajo corporativo, minimizando errores y garantizando el cumplimiento normativo.</p>
      </section>

      <section class="landing-section feature-grid reveal-on-scroll">
        <div class="feature-card delay-1">
          <div class="feature-icon-wrapper">${ICONS.file}</div>
          <h3>Legajos Digitales Centralizados</h3>
          <p>Reemplace el archivo físico con un entorno estructurado. Control y visibilidad completa del expediente de cada empleado.</p>
        </div>
        <div class="feature-card delay-2">
          <div class="feature-icon-wrapper">${ICONS.upload}</div>
          <h3>Importación Masiva desde Excel</h3>
          <p>Carga ágil de empleados y liquidaciones. Procesamiento automático de grandes volúmenes de datos mediante validación por CUIL.</p>
        </div>
        <div class="feature-card delay-3">
          <div class="feature-icon-wrapper">${ICONS.pen}</div>
          <h3>Firma Electrónica Inalterable</h3>
          <p>Firma digital vinculada a la identidad del empleado, operando sobre protocolos criptográficos de grado industrial.</p>
        </div>
        <div class="feature-card delay-4">
          <div class="feature-icon-wrapper">${ICONS.shield}</div>
          <h3>Auditoría y Trazabilidad</h3>
          <p>Historial inmutable de eventos del sistema. Base probatoria sólida para auditorías internas y forenses.</p>
        </div>
      </section>

      <section class="landing-section security-section reveal-on-scroll">
        <div class="security-columns">
          <div class="security-copy">
            <span class="section-label">Infraestructura Corporativa</span>
            <h2>Cumplimiento Legal y Respaldo Técnico</h2>
            <p>MyManagerRH es una solución de infraestructura que resuelve la brecha entre la gestión de personal y la exigencia legal, protegiendo los datos sensibles bajo estrictos estándares de ciberseguridad.</p>
          </div>
          <div class="security-grid">
            <div class="security-item delay-1">
              <div class="security-icon">${ICONS.shield}</div>
              <h4>Integridad Legal</h4>
              <p>Evidencia criptográfica en cada transacción.</p>
            </div>
            <div class="security-item delay-2">
              <div class="security-icon">${ICONS.upload}</div>
              <h4>Implementación Directa</h4>
              <p>Transición fluida desde sistemas heredados (Legacy).</p>
            </div>
            <div class="security-item delay-3">
              <div class="security-icon">${ICONS.grid}</div>
              <h4>Escalabilidad</h4>
              <p>Arquitectura preparada para soportar el crecimiento de nómina.</p>
            </div>
            <div class="security-item delay-4">
              <div class="security-icon">${ICONS.lock}</div>
              <h4>Protección de Datos</h4>
              <p>Aislamiento y cifrado de información confidencial.</p>
            </div>
          </div>
        </div>
      </section>

      <section class="landing-section campaigns-section reveal-on-scroll">
        <div class="campaign-block">
          <div class="campaign-copy">
            <h2>Prueba inmutable para cada firma</h2>
            <p>Nos centramos en la excelencia técnica de nuestra infraestructura digital. Mediante un diseño minimalista de nuestra interfaz segura y la verificación criptográfica, posicionamos a MyManageRH como la opción de referencia para la trazabilidad legal de nóminas.</p>
          </div>
          <div class="campaign-grid single">
            <article class="campaign-card">
              <img src="./IVMMRH/resource_aFFXnvDIdP02Z9Rc60f4Q8.png" alt="Evidencia inmutable" loading="lazy" />
              <h4>Evidencia inmutable para cada firma</h4>
            </article>
          </div>
        </div>
      </section>

      <section class="landing-section cta-section reveal-on-scroll">
        <div class="cta-panel">
          <div>
            <span class="section-label">Implementación</span>
            <h2>Plataforma unificada para documentos, firmas y auditoría.</h2>
            <p>Transforme la gestión de su nómina con un sistema centrado en la seguridad jurídica y el alto rendimiento operativo.</p>
          </div>
          <a href="#/soporte" class="btn btn-primary btn-xl">Comenzar Integración</a>
        </div>
      </section>
    </div>
  `;

  const observerOptions = {
    root: null,
    rootMargin: '0px',
    threshold: 0.15
  };

  const observer = new IntersectionObserver((entries, observer) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('visible');
        observer.unobserve(entry.target);
      }
    });
  }, observerOptions);

  const revealElements = container.querySelectorAll('.reveal-on-scroll');
  revealElements.forEach(el => observer.observe(el));
}