import { apiFetch, esc } from '../common.js';

function el(id, ctx = document) {
  return (ctx || document).querySelector(`#${id}`);
}

function getVerifyId() {
  const hash = window.location.hash || '';
  const match = hash.match(/^#\/verify\/([^?]+)/);
  return match ? match[1] : null;
}

function renderLoading(container) {
  container.innerHTML = `
    <div class="verify-shell flex-center flex-col py-64">
      <div class="spinner mb-16"></div>
      <p class="text-muted">Validando integridad del documento...</p>
    </div>
  `;
}

function renderError(container, title, message) {
  container.innerHTML = `
    <section class="card verify-card verify-card-invalid animate-fade-in mx-auto" style="max-width: 500px; margin-top: 40px;">
      <div class="verify-card-header text-center pb-24">
        <div class="verify-icon verify-icon-error mb-16 mx-auto" style="background: var(--error-bg); color: var(--error-text); width: 64px; height: 64px; border-radius: 50%; display: flex; align-items: center; justify-content: center;">
          <svg width="32" height="32" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"></path>
          </svg>
        </div>
        <h1 class="text-h2">${esc(title)}</h1>
        <p class="text-muted mt-8">${esc(message)}</p>
      </div>
      <div class="verify-card-body pt-24 border-top">
        <button class="btn btn-secondary w-full" onclick="location.hash='#/'">Volver al inicio</button>
      </div>
    </section>
  `;
}

async function handleDownload(vid, container) {
  const btn = el('btnDownload');
  const otpSection = el('otpDownloadSection');
  const identifierInput = el('downloadIdentifier');
  const otpInput = el('downloadOtp');
  const statusEl = el('downloadStatus');

  btn.disabled = true;
  statusEl.innerText = 'Preparando descarga...';
  statusEl.className = 'text-center small-muted mt-8';

  try {
    // Attempt download directly (for authenticated/admins)
    window.location.href = `/api/receipts/${vid}/download`;
    // We can't easily catch 401/403 with window.location.href, so we use a probe
    const probe = await fetch(`/api/receipts/${vid}/download`, { method: 'HEAD' });
    
    if (probe.status === 401 || probe.status === 403) {
      // Show OTP flow
      otpSection.classList.remove('hidden');
      statusEl.innerText = 'Este documento requiere verificación de identidad para su descarga.';
      statusEl.className = 'text-center text-warning small-muted mt-8';
    }
  } catch (err) {
    console.error('Download probe failed', err);
  } finally {
    btn.disabled = false;
  }
}

async function sendOtp(vid, identifier) {
  const statusEl = el('downloadStatus');
  try {
    const res = await apiFetch('/api/verification/send', {
      method: 'POST',
      body: JSON.stringify({
        email: identifier.includes('@') ? identifier : null,
        phone: identifier.includes('@') ? null : identifier,
        receipt_id: vid,
        channel: identifier.includes('@') ? 'email' : 'sms',
        context: 'download'
      })
    });
    if (res.status === 'ok') {
      statusEl.innerText = `Código enviado a ${identifier}. Por favor, ingréselo para descargar.`;
      statusEl.className = 'text-center text-success small-muted mt-8';
      el('otpInputArea').classList.remove('hidden');
    }
  } catch (err) {
    statusEl.innerText = 'Error al enviar OTP. Verifique el identificador.';
    statusEl.className = 'text-center text-danger small-muted mt-8';
  }
}

async function verifyAndDownload(vid, identifier, code) {
  const statusEl = el('downloadStatus');
  try {
    // We just trigger the download with the code as query param
    // The backend will verify it
    window.location.href = `/api/receipts/${vid}/download?otp_code=${encodeURIComponent(code)}&identifier=${encodeURIComponent(identifier)}`;
    statusEl.innerText = 'Iniciando descarga...';
    statusEl.className = 'text-center text-success small-muted mt-8';
  } catch (err) {
    statusEl.innerText = 'Código incorrecto o expirado.';
    statusEl.className = 'text-center text-danger small-muted mt-8';
  }
}

export async function render(container) {
  const vid = getVerifyId();
  if (!vid) {
    renderError(container, 'Falta ID', 'No se proporcionó un identificador de verificación válido.');
    return;
  }

  renderLoading(container);

  try {
    const res = await apiFetch(`/api/verification/receipt/${vid}`);

    if (!res.valid) {
      renderError(container, 'Documento no encontrado', 'El código escaneado no corresponde a un documento vigente o válido en el sistema.');
      return;
    }

    const globalStatus = res.global_status || 'VALID';
    const statusColor = globalStatus === 'VALID' ? 'var(--success-solid)' : (globalStatus.includes('BREACH') ? 'var(--error-solid)' : 'var(--warning-solid)');
    const statusBg = globalStatus === 'VALID' ? 'var(--success-bg)' : (globalStatus.includes('BREACH') ? 'var(--error-bg)' : 'var(--warning-bg)');

    container.innerHTML = `
      <div class="container animate-fade-in" style="max-width: 850px; padding-top: 40px; padding-bottom: 80px;">
        <header class="text-center mb-32">
          <div class="verify-badge mb-16 mx-auto" style="background: ${statusBg}; color: ${statusColor}; padding: 8px 18px; border-radius: 999px; display: inline-flex; align-items: center; font-weight: 600; font-size: 14px; gap: 8px; border: 1px solid ${statusColor}40;">
            <svg width="20" height="20" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"></path>
            </svg>
            Validación de Integridad: ${esc(globalStatus)}
          </div>
          <h1 class="text-h1 mb-8" style="font-size: 32px; letter-spacing: -0.02em;">Documento Certificado</h1>
          <p class="text-muted" style="max-width: 500px; margin: 0 auto;">Este documento posee plena validez jurídica según la Ley 25.506 de Firma Digital y ha sido verificado contra nuestro nodo de auditoría central.</p>
        </header>

        <section class="card mb-32 shadow-lg" style="border-radius: 16px; overflow: hidden; border: 1px solid var(--slate-200);">
          <div class="card-header bg-slate-50 border-bottom px-24 py-16 flex-between">
            <h3 class="font-bold text-slate-800" style="margin:0; font-size: 16px;">METADATOS DEL DOCUMENTO</h3>
            <span class="text-caption font-mono text-slate-400">ID: ${esc(res.verification_id || vid)}</span>
          </div>
          <div class="p-0">
            <table class="w-full" style="border-collapse: collapse;">
              <tbody>
                <tr class="border-bottom">
                  <td class="px-24 py-16 bg-slate-50 font-semibold text-slate-500" style="width: 200px; font-size: 12px; text-transform: uppercase;">Organización</td>
                  <td class="px-24 py-16 text-slate-800 font-medium">${esc(res.organization.name)}</td>
                </tr>
                <tr class="border-bottom">
                  <td class="px-24 py-16 bg-slate-50 font-semibold text-slate-500" style="font-size: 12px; text-transform: uppercase;">Titular / Empleado</td>
                  <td class="px-24 py-16 text-slate-800 font-medium">${esc(res.employee_name || 'No especificado')}</td>
                </tr>
                <tr class="border-bottom">
                  <td class="px-24 py-16 bg-slate-50 font-semibold text-slate-500" style="font-size: 12px; text-transform: uppercase;">CUIL / CUIT</td>
                  <td class="px-24 py-16 text-slate-800 font-mono">${esc(res.employee_cuil || 'N/A')}</td>
                </tr>
                <tr class="border-bottom">
                  <td class="px-24 py-16 bg-slate-50 font-semibold text-slate-500" style="font-size: 12px; text-transform: uppercase;">Finalizado el</td>
                  <td class="px-24 py-16 text-slate-800 font-medium">${res.signed_at ? new Date(res.signed_at).toLocaleString('es-AR') : 'Procesando...'}</td>
                </tr>
                <tr>
                  <td class="px-24 py-16 bg-slate-50 font-semibold text-slate-500" style="font-size: 12px; text-transform: uppercase;">PDF Fingerprint</td>
                  <td class="px-24 py-16 text-slate-400 font-mono" style="font-size: 11px; word-break: break-all;">SHA256: ${esc(res.document_hash)}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <h3 class="mb-16 mt-40 text-slate-800 font-bold flex items-center gap-12" style="font-size: 20px;">
          <div style="background: var(--brand-600); width: 8px; height: 24px; border-radius: 4px;"></div>
          Sellos de Firma Digital (PAdES-LTV)
        </h3>
        
        <div class="grid" style="grid-template-columns: 1fr; gap: 20px;">
          ${res.signatures.map(sig => `
            <div class="card signature-seal-card p-0 shadow-md hover-glow transition-all" style="border-radius: 16px; border: 1px solid var(--slate-200); background: white;">
              <div class="flex flex-col md:flex-row">
                <div class="p-24 flex-1">
                  <div class="flex items-center gap-12 mb-16">
                    <div style="background: ${sig.role === 'employer' ? 'var(--brand-600)' : 'var(--success-solid)'}; color: white; padding: 4px 12px; border-radius: 6px; font-weight: 800; font-size: 11px; letter-spacing: 0.05em;">
                      ${esc(sig.role === 'employer' ? 'EMPLEADOR' : 'EMPLEADO')}
                    </div>
                    <span class="text-h3 font-bold text-slate-800">${esc(sig.signer)}</span>
                  </div>
                  
                  <div class="grid grid-cols-1 sm:grid-cols-2 gap-y-12 gap-x-24 text-caption">
                    <div class="flex flex-col">
                      <span class="text-slate-400 uppercase font-bold" style="font-size: 10px;">ID de Sello</span>
                      <span class="text-slate-700 font-mono">${esc(sig.id)}</span>
                    </div>
                    <div class="flex flex-col">
                      <span class="text-slate-400 uppercase font-bold" style="font-size: 10px;">Identidad Fiscal</span>
                      <span class="text-slate-700">${esc(sig.cuil || res.employee_cuil || 'Verificado')}</span>
                    </div>
                    <div class="flex flex-col">
                      <span class="text-slate-400 uppercase font-bold" style="font-size: 10px;">Nivel de Garantía</span>
                      <span class="text-brand-600 font-bold">${esc(sig.level)}</span>
                    </div>
                    <div class="flex flex-col">
                      <span class="text-slate-400 uppercase font-bold" style="font-size: 10px;">Fecha/Hora</span>
                      <span class="text-slate-700">${sig.signed_at ? new Date(sig.signed_at).toLocaleString('es-AR') : 'Timestamp TSA'}</span>
                    </div>
                  </div>
                </div>
                
                <div class="bg-slate-50 p-24 flex-center flex-col border-left" style="width: 220px; border-radius: 0 16px 16px 0; min-height: 140px;">
                   <div class="sig-preview-container mb-12 shadow-inner" style="background: white; border: 1px solid var(--slate-200); border-radius: 8px; width: 100%; height: 80px; display: flex; align-items: center; justify-content: center; overflow: hidden; position: relative;">
                      <img src="/api/signatures/${sig.id}/image" alt="Visual" style="max-height: 50px; mix-blend-mode: multiply;" />
                      <div style="position: absolute; bottom: 0; width: 100%; background: rgba(241, 245, 249, 0.9); font-size: 9px; font-weight: 700; text-align: center; color: var(--slate-400); padding: 2px;">AUDIT VIEW</div>
                   </div>
                   <a href="/api/signatures/${sig.id}/image" target="_blank" class="btn btn-ghost w-full py-6 text-brand-600 font-bold" style="font-size: 12px; gap: 6px;">
                      <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"></path>
                      </svg>
                      Ver Versión Original
                   </a>
                </div>
              </div>
            </div>
          `).join('')}
        </div>

        <section class="mt-56 p-40 text-center animate-slide-up" style="background: linear-gradient(135deg, var(--slate-900), var(--brand-900)); border-radius: 20px; color: white; box-shadow: 0 20px 40px rgba(0,0,0,0.15);">
          <div class="mb-24 flex-center">
            <div style="background: rgba(255,255,255,0.1); padding: 16px; border-radius: 50%;">
              <svg width="32" height="32" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"></path>
              </svg>
            </div>
          </div>
          <h2 class="text-h2 mb-12" style="color: white; font-size: 24px;">Acceso al Documento Completo</h2>
          <p class="mb-32 mx-auto" style="color: rgba(255,255,255,0.7); max-width: 500px;">Por políticas de seguridad y privacidad, la descarga del archivo PDF requiere una validación adicional de identidad.</p>
          
          <div id="downloadMainAction">
            <button id="btnDownload" class="btn bg-white text-brand-900 hover-scale px-48 py-16 font-bold" style="border-radius: 12px; font-size: 16px; border: none; box-shadow: 0 4px 12px rgba(0,0,0,0.2);">
              <svg width="20" height="20" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24" style="margin-right: 12px;">
                <path stroke-linecap="round" stroke-linejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path>
              </svg>
              Descargar Recibo en PDF
            </button>
            <div id="downloadStatus" class="mt-16 text-center" style="font-size: 14px; color: var(--brand-100);"></div>
          </div>

          <div id="otpDownloadSection" class="mt-32 p-32 bg-white rounded-2xl hidden text-left shadow-2xl animate-fade-in" style="border: 1px solid rgba(255,255,255,0.1);">
            <p class="text-h3 mb-20 text-slate-800 font-bold">Verificación de Identidad para Descarga</p>
            <div class="form-group mb-20">
              <label class="text-slate-500 font-semibold mb-8 block" style="font-size: 12px;">EMAIL O CUIL REGISTRADO</label>
              <div class="flex gap-12">
                <input type="text" id="downloadIdentifier" class="input flex-1 py-12 px-16 text-slate-800 border-slate-200" placeholder="ej: 20-12345678-9 o email@corp.com" style="border-radius: 10px;">
                <button id="btnSendOtp" class="btn btn-primary px-24 font-bold" style="border-radius: 10px;">Enviar Código</button>
              </div>
            </div>
            
            <div id="otpInputArea" class="form-group hidden animate-slide-down">
              <label class="text-slate-500 font-semibold mb-8 block" style="font-size: 12px;">CÓDIGO DE VERIFICACIÓN (6 DÍGITOS)</label>
              <div class="flex gap-12">
                <input type="text" id="downloadOtp" class="input flex-1 text-center font-bold text-slate-900 py-12" maxlength="6" style="letter-spacing: 0.8em; font-size: 20px; border-radius: 10px;">
                <button id="btnVerifyDownload" class="btn bg-brand-600 text-white font-bold px-24" style="border-radius: 10px;">Validar y Abrir</button>
              </div>
              <p class="mt-12 text-slate-400" style="font-size: 11px;">Busque el código en su bandeja de entrada o mensaje de texto.</p>
            </div>
          </div>
        </section>

        <footer class="mt-80 pt-40 border-top text-center text-caption text-muted">
          <div class="flex flex-col items-center gap-16">
            <div style="opacity: 0.5;">Audit Fingerprint: ${esc(res.document_hash.substring(0, 32))}...</div>
            <div class="flex gap-24 font-semibold uppercase tracking-widest" style="font-size: 10px;">
               <span style="color: var(--success-solid);">• INTEGRIDAD VERIFICADA</span>
               <span style="color: var(--brand-600);">• FIRMA PADeS-LTV</span>
               <span style="color: var(--slate-500);">• ARCHIVO AUDITADO</span>
            </div>
            <p style="font-style: italic; margin-top: 24px;">Powered by MyManageRH Compliance Engine v2.4.0-hardened</p>
          </div>
        </footer>
      </div>
    `;

    // Event Listeners
    el('btnDownload').addEventListener('click', () => handleDownload(vid, container));
    el('btnSendOtp').addEventListener('click', () => {
      const iden = el('downloadIdentifier').value.trim();
      if (iden) sendOtp(vid, iden);
    });
    el('btnVerifyDownload').addEventListener('click', () => {
      const iden = el('downloadIdentifier').value.trim();
      const code = el('downloadOtp').value.trim();
      if (iden && code) verifyAndDownload(vid, iden, code);
    });

  } catch (err) {
    console.error('Unified load failed', err);
    renderError(container, 'Error de conexión', 'No se pudo establecer comunicación con el servidor de validación.');
  }
}
