/**
 * LandingPage Component
 * Presentación pública de los servicios laborales y la plataforma MyManageRH.
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
          <span class="eyebrow">Asesoramiento, liquidación y tecnología propia</span>
          <h1>Soluciones integrales para la gestión de tu personal: 40 años de trayectoria y tecnología propia.</h1>
          <p class="hero-lead">En MyManageRH acompañamos a empresas, pymes y organizaciones de cualquier tamaño o rubro combinando el respaldo profesional de cuatro décadas en materia laboral y contable con una plataforma digital diseñada para ordenar, agilizar y asegurar toda la administración interna de Recursos Humanos. Sabemos que gestionar personas requiere tanto criterio legal y precisión numérica como herramientas modernas que eliminen las demoras administrativas. Por eso, integramos tres soluciones equitativas y complementarias para resolver tus necesidades laborales de punta a punta.</p>
          <div class="hero-actions">
            <a href="#/soporte" class="btn btn-primary btn-xl">Contactanos</a>
            <a href="#/soporte" class="btn btn-secondary btn-xl">Solicitar una demostración</a>
          </div>
        </div>
        <div class="hero-media">
          <img
            src="./assets/landing/equipo-asesoramiento-768.webp"
            srcset="./assets/landing/equipo-asesoramiento-480.webp 480w, ./assets/landing/equipo-asesoramiento-768.webp 768w"
            sizes="(min-width: 1024px) 48vw, 100vw"
            width="768"
            height="1024"
            alt="Profesionales revisando información de gestión laboral en una computadora portátil"
            loading="eager"
            fetchpriority="high"
            decoding="async"
          />
        </div>
      </section>

      <section class="landing-section reveal-on-scroll intro-section">
        <span class="section-label">Servicios integrales</span>
        <h2>Tres soluciones equitativas y complementarias</h2>
        <p class="section-subtitle">Asesoramiento Laboral Especializado, Liquidación Integral de Sueldos y Plataforma Digital MyManageRH para resolver tus necesidades laborales de punta a punta.</p>
      </section>

      <section class="landing-section service-grid reveal-on-scroll" aria-label="Servicios de MyManageRH">
        <article class="service-card delay-1">
          <div class="feature-icon-wrapper">${ICONS.file}</div>
          <h3>Asesoramiento Laboral Especializado</h3>
          <p>Brindamos acompañamiento permanente y estratégico en la toma de decisiones laborales diarias de tu empresa. Nuestro equipo te asesora en el encuadre y la correcta aplicación de convenios colectivos de trabajo, gestión de altas y bajas, elección de modalidades de contratación, redacción de comunicaciones fehacientes y cumplimiento estricto de la normativa vigente. Trabajamos de forma preventiva para evitar contingencias legales, ordenar las relaciones internas y permitir que tu negocio opere con total previsibilidad y tranquilidad.</p>
        </article>
        <article class="service-card delay-2">
          <div class="feature-icon-wrapper">${ICONS.grid}</div>
          <h3>Liquidación Integral de Sueldos</h3>
          <p>Respaldados por <strong>40 años de trayectoria</strong>, gestionamos de principio a fin todo el proceso de liquidación de haberes de tu nómina. Nos encargamos con rigor técnico del cálculo de sueldos, liquidaciones finales, cargas sociales, libros legales, certificaciones y obligaciones previsionales y sindicales. A diferencia de los servicios impersonales, nuestra liquidación integral se administra de manera dedicada y absolutamente confidencial mediante contacto directo con nuestra dirección (CEO), asegurando exactitud en los números, respuestas ágiles ante cada consulta y cumplimiento puntual en cada cierre mensual.</p>
        </article>
        <article class="service-card delay-3">
          <div class="feature-icon-wrapper">${ICONS.pen}</div>
          <h3>Plataforma Digital MyManageRH</h3>
          <p>Complementamos nuestros servicios profesionales con un ecosistema web propio, desarrollado para centralizar y digitalizar todo el ciclo documental de tus colaboradores en milisegundos, dejando atrás el papel, los archivos físicos y las planillas dispersas. Desde un panel de control claro y ejecutivo, podés visualizar métricas al instante y gestionar toda tu operación:</p>
        </article>
      </section>

      <section class="landing-section platform-section reveal-on-scroll">
        <h2>Una plataforma para centralizar y digitalizar todo el ciclo documental</h2>
        <figure class="platform-showcase">
          <img
            src="./assets/landing/hub-historial-documentos.webp"
            width="1539"
            height="688"
            alt="Vista del hub MyManageRH para buscar y consultar recibos, legajos y otros documentos"
            loading="lazy"
            decoding="async"
          />
        </figure>
        <ul class="platform-features">
          <li class="platform-feature">
            <h3>Hub Centralizado de Historial y Documentos</h3>
            <p>Repositorio inteligente organizado por categorías clave como recibos de nómina, legajos, transferencias bancarias, listados de ART, fondo de desempleo y documentación varia, con un motor de indexación ultrarrápido que permite localizar cualquier archivo por DNI, nombre o vista cronológica.</p>
          </li>
          <li class="platform-feature">
            <h3>Legajos Digitales Completos con Versionado</h3>
            <p>Creación de fichas de ingreso detalladas con datos personales, laborales, CBU, obra social, cargas de familia, declaración jurada de domicilio y afiliación sindical. Cada actualización conserva su historial de versiones para mantener una trazabilidad impecable.</p>
          </li>
          <li class="platform-feature">
            <h3>Firma Electrónica Integrada</h3>
            <p>Posibilidad de gestionar la firma de recibos de haberes, legajos y documentación laboral de forma totalmente digital y ágil tanto para la empresa como para los colaboradores, dejando atrás los circuitos en papel.</p>
          </li>
          <li class="platform-feature">
            <h3>Biblioteca de Modelos Laborales e Identidad Propia</h3>
            <p>Acceso inmediato a plantillas legales listas para usar, incluyendo contratos a plazo fijo, eventual, de temporada o período de prueba, intimaciones, sanciones disciplinarias y constancias de entrega de indumentaria. Al cargar el logotipo de tu empresa en la configuración, el sistema lo estampa automáticamente tanto en los legajos generados como en los recibos firmados.</p>
          </li>
        </ul>
      </section>

      <section class="landing-section advantages-section reveal-on-scroll">
        <span class="section-label">Nuestra propuesta</span>
        <h2>¿Qué ventajas tenemos frente a otros sistemas?</h2>
        <p class="section-subtitle">A diferencia de las plataformas tradicionales que solo ofrecen un repositorio estático o un soporte impersonal, <strong>MyManageRH</strong> marca una diferencia real en cuatro aspectos clave:</p>
        <ol class="benefits-list">
          <li><strong>Auditoría de firma verificable públicamente:</strong> Cada documento firmado genera un sello con un identificador único que puede validarse directamente en la web contra nuestra base de datos original, asegurando que el archivo no fue alterado y evitando cualquier validez sobre copias simples.</li>
          <li><strong>Seguridad de nivel empresarial:</strong> Protegemos la información sensible mediante cifrado individual de archivos, registros criptográficos y sellado de tiempo en cada operación.</li>
          <li><strong>Soporte técnico directo con el creador del sistema:</strong> Quienes usan nuestra plataforma no pierden tiempo con respuestas automáticas ni intermediarios; cuentan con el respaldo directo de quien diseñó y conoce el sistema a fondo.</li>
          <li><strong>Tecnología respaldada por 40 años de experiencia real:</strong> No somos únicamente un proveedor de software; entendemos la realidad laboral y contable de las empresas porque llevamos cuatro décadas liquidando sueldos.</li>
        </ol>
        <p class="platform-roadmap">Además, seguimos evolucionando de forma continua para sumar nuevas herramientas a la plataforma.</p>
      </section>

      <section class="landing-section cta-section reveal-on-scroll">
        <div class="cta-panel">
          <div>
            <span class="section-label">Hablemos</span>
            <h2>Ordená y simplificá la gestión de tu personal con un equipo que te acompaña en cada paso.</h2>
            <p>Contactanos por correo electrónico para coordinar una reunión personalizada por nuestros servicios de Asesoramiento Laboral y Liquidación Integral de Sueldos, o para solicitar una demostración y acceso a la plataforma digital <strong>MyManageRH</strong>.</p>
          </div>
          <a href="#/soporte" class="btn btn-primary btn-xl">Contactanos por correo</a>
        </div>
      </section>

      <p class="landing-copyright">© 2026 MyManageRH — Asesoramiento Laboral, Liquidación Integral de Sueldos y Gestión Documental Digital.</p>
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
