/**
 * LandingPage Component
 * Entrada de una sola página para MyManageRH: conversión B2B, integridad legal
 * e infraestructura del sistema.
 */

const svg = (inner, size = 24, strokeWidth = 2) =>
  `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="${strokeWidth}" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${inner}</svg>`;

const ICONS = {
  lock: svg('<rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect><path d="M7 11V7a5 5 0 0 1 10 0v4"></path>'),
  shield: svg('<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path>'),
  file: svg('<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline>'),
  upload: svg('<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="17 8 12 3 7 8"></polyline><line x1="12" y1="3" x2="12" y2="15"></line>'),
  pen: svg('<path d="M12 19l7-7 3 3-7 7-3-3z"></path><path d="M18 13l-1.5-7.5L2 2l3.5 14.5L13 18l5-5z"></path><path d="M2 2l7.586 7.586"></path><circle cx="11" cy="11" r="2"></circle>'),
  grid: svg('<rect x="3" y="3" width="7" height="7"></rect><rect x="14" y="3" width="7" height="7"></rect><rect x="14" y="14" width="7" height="7"></rect><rect x="3" y="14" width="7" height="7"></rect>'),
};

export async function render(container) {
  container.innerHTML = `
    <div class="landing-page">
      <section class="hero-section reveal-on-scroll">
        <div class="hero-copy">
          <span class="eyebrow">Firma electrónica de recibos</span>
          <h1>Gestión laboral con firma digital y auditoría inalterable</h1>
          <p class="hero-lead">Centralizá los legajos, los recibos y el cumplimiento legal de tu empresa en un solo sistema seguro.</p>
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
          <img
            src="./assets/landing/hero-768.webp"
            srcset="./assets/landing/hero-480.webp 480w, ./assets/landing/hero-768.webp 768w, ./assets/landing/hero-1080.webp 1080w"
            sizes="(min-width: 1024px) 48vw, 100vw"
            width="1080"
            height="1920"
            alt="Panel de control de empresa MyManageRH"
            loading="eager"
            fetchpriority="high"
            decoding="async"
          />
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
            <p>MyManageRH es una solución de infraestructura que resuelve la brecha entre la gestión de personal y la exigencia legal, protegiendo los datos sensibles bajo estrictos estándares de ciberseguridad.</p>
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
              <img
                src="./assets/landing/evidence-768.webp"
                srcset="./assets/landing/evidence-480.webp 480w, ./assets/landing/evidence-768.webp 768w, ./assets/landing/evidence-1080.webp 1080w"
                sizes="(min-width: 1024px) 48vw, 100vw"
                width="1080"
                height="1920"
                alt="Evidencia inmutable"
                loading="lazy"
                decoding="async"
              />
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

  // El ocultamiento inicial lo activa JS: si el observador no existe o falla,
  // el contenido queda visible igual (ver landing.css, .reveal-ready).
  if (!('IntersectionObserver' in window)) return;

  const page = container.querySelector('.landing-page');
  page?.classList.add('reveal-ready');

  const observer = new IntersectionObserver(
    (entries, obs) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('visible');
          obs.unobserve(entry.target);
        }
      });
    },
    { root: null, rootMargin: '0px', threshold: 0.15 }
  );

  container.querySelectorAll('.reveal-on-scroll').forEach((el) => observer.observe(el));
}
