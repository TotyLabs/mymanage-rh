import { apiFetch, esc } from '../common.js';

function el(id, ctx = document) {
  return (ctx || document).querySelector(`#${id}`);
}

function getVerifyId() {
  const hash = window.location.hash || '';
  const match = hash.match(/^#\/verify\/([^?]+)/);
  return match ? match[1] : null;
}

function renderInvalid(container, message) {
  container.innerHTML = `
    <section class="card verify-card verify-card-invalid">
      <div class="verify-card-header">
        <div class="verify-icon verify-icon-error" aria-hidden="true">
          <svg width="28" height="28" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"></path>
          </svg>
        </div>

        <h1 class="verify-title">Documento no válido</h1>
        <p class="verify-subtitle">
          El código de verificación no corresponde a un documento firmado válido.
        </p>
      </div>

      <div class="verify-card-body">
        <div class="notice-panel warning verify-notice-center">
          ${esc(message)}
        </div>

        <p class="small-muted verify-footer-note">
          Ante cualquier inconsistencia, contactá al área de RRHH.
        </p>
      </div>
    </section>
  `;
}

export async function render(container) {
  const vid = getVerifyId();

  if (!vid) {
    container.innerHTML = `
      <section class="card verify-shell">
        <div class="error">ID de verificación no proporcionado.</div>
      </section>
    `;
    return;
  }

  container.innerHTML = `
    <section class="verify-shell">
      <div id="verifyLoading" class="verify-loading">
        Verificando firma criptográfica...
      </div>
      <div id="verifyResult" class="hidden"></div>
    </section>
  `;

  const resultEl = el('verifyResult', container);
  const loadingEl = el('verifyLoading', container);

  try {
    const res = await apiFetch(`/api/verify/${vid}`);

    loadingEl.classList.add('hidden');
    resultEl.classList.remove('hidden');

    if (res.status !== 'valid') {
      renderInvalid(resultEl, 'El documento no pudo ser validado.');
      return;
    }

    const tsaLabel = res.tsa_timestamp
      ? esc(new Date(res.tsa_timestamp).toLocaleString('es-AR'))
      : 'Marca de tiempo local';

    resultEl.innerHTML = `
      <section class="card verify-card verify-card-valid">
        <div class="verify-card-header">
          <div class="verify-icon verify-icon-success" aria-hidden="true">
            <svg width="28" height="28" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7"></path>
            </svg>
          </div>

          <h1 class="verify-title">Documento íntegro</h1>
          <p class="verify-subtitle">
            La firma electrónica y el certificado fueron validados correctamente.
          </p>
        </div>

        <div class="verify-card-body">
          <div class="dl-grid mb-24">
            <div class="dl-item">
              <span class="dl-label">Estado</span>
              <span class="badge success verify-badge-fit">Validación exitosa</span>
            </div>

            <div class="dl-item">
              <span class="dl-label">Sello de tiempo (TSA)</span>
              <span class="dl-value">${tsaLabel}</span>
            </div>
          </div>

          <div class="dl-grid mb-24">
            <div class="dl-item">
              <span class="dl-label">Firmante (empleado)</span>
              <span class="dl-value">${esc(res.employee?.name || 'N/D')}</span>
              <span class="text-subtle">CUIL: ${esc(res.employee?.cuil || 'N/D')}</span>
            </div>

            <div class="dl-item">
              <span class="dl-label">Organización</span>
              <span class="dl-value">${esc(res.organization || 'N/D')}</span>
              <span class="text-subtle">Período: ${esc(res.period || 'N/D')}</span>
            </div>
          </div>

          <div class="dl-grid mb-24">
            <div class="dl-item">
              <span class="dl-label">Certificado criptográfico</span>
              <div class="notice-panel info verify-certificate-box">
                <strong>Emisor:</strong> ${esc(res.certificate?.issuer || 'N/D')}<br />
                <strong>Estado:</strong> ${esc((res.certificate?.validation || 'N/D').toUpperCase())}
              </div>
            </div>
          </div>

          <div class="dl-item mb-24">
            <span class="dl-label">Integridad SHA-256</span>
            <div class="verify-hash-box">
              ${esc(res.document_hash || 'N/D')}
            </div>
          </div>

          <div class="verify-actions">
            <button class="btn btn-secondary" id="btnDownloadAudit">
              Descargar informe PDF
            </button>
          </div>
        </div>
      </section>
    `;

    el('btnDownloadAudit', resultEl).addEventListener('click', () => {
      window.open(`/api/audit/${vid}/pdf`, '_blank', 'noopener');
    });
  } catch {
    loadingEl.classList.add('hidden');
    resultEl.classList.remove('hidden');
    renderInvalid(resultEl, 'ID de verificación inválido o inexistente.');
  }
}