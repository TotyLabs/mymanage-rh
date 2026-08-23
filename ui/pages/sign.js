/**
 * Vista de firma frictionless: /sign/:token
 * Flujo: Token → OTP (SMS/Email) → CUIL + Firma → Éxito
 * NO requiere registro ni login.
 */
import { apiFetch, apiUrl, showError, showToast, confirmAction } from '../common.js';

function el(id, ctx = document) {
  return (ctx || document).querySelector(`#${id}`);
}

function openModal(id, container) {
  const modal = el(id, container);
  if (!modal) return;
  modal.classList.remove('hidden');
  modal.setAttribute('aria-hidden', 'false');
}

function closeModal(id, container) {
  const modal = el(id, container);
  if (!modal) return;
  modal.classList.add('hidden');
  modal.setAttribute('aria-hidden', 'true');
}

export async function render(container, params) {
  const path = (location.hash || '').replace('#', '');
  const tokenMatch = path.match(/\/sign\/([a-z0-9\-_]+)/i);
  const token = tokenMatch ? tokenMatch[1] : (params && params.get && params.get('token')) || null;
  const redirectToSign = encodeURIComponent(`#${path}`);

  if (!token || token.length < 32) {
    container.innerHTML = `
      <section class="card sign-shell">
        <h1 class="card-title mb-8">Enlace inválido</h1>
        <div class="error mb-16">El enlace de firma no es válido o está incompleto.</div>
        <p class="small-muted mb-16">Usá el enlace que recibiste por correo o solicitá uno nuevo a tu empresa.</p>
        <a class="link" href="#/select-role">Volver al inicio</a>
      </section>
    `;
    return;
  }

  // GAP-AUTH: Enforce registration/login before signing
  const user = window.__USER_CACHE__; // We check the global cache from router.js
  
  if (!user) {
    container.innerHTML = `
      <section class="card sign-shell text-center p-48">
        <div class="text-4xl mb-24">🔐</div>
        <h1 class="card-title mb-16">Acceso Restringido</h1>
        <div class="notice-panel warning mb-24">
          Usted no está registrado en la plataforma.
        </div>
        <p class="mb-32 text-slate-600">Para firmar este recibo, primero creá tu cuenta. Luego volverás automáticamente aquí para continuar.</p>
        <div class="flex-center gap-16">
          <a href="#/auth?role=empleado&redirect=${redirectToSign}" class="btn btn-primary px-32">Crear cuenta</a>
          <a href="#/login?role=empleado&redirect=${redirectToSign}" class="btn btn-secondary px-32">Ya tengo cuenta</a>
        </div>
      </section>
    `;
    return;
  }

  // Load token data to verify identity
  let tokenData = null;
  try {
    tokenData = await apiFetch(`/api/signature-requests/${token}/info`);
    
    // Check if user is the correct recipient
    if (user.employee_id && tokenData.employee_id && user.employee_id !== tokenData.employee_id) {
       container.innerHTML = `
        <section class="card sign-shell text-center p-48">
          <div class="text-4xl mb-24">🚫</div>
          <h1 class="card-title mb-16">Identidad Incorrecta</h1>
          <div class="notice-panel error mb-24">
            Este enlace de firma pertenece a otro empleado. No puedes firmar documentos que no sean tuyos.
          </div>
          <p class="mb-32 text-slate-600">Estás logueado como <strong>${user.full_name}</strong>.</p>
          <div class="flex-center gap-16">
            <button class="btn btn-secondary" onclick="logout()">Cerrar sesión e ingresar con otra cuenta</button>
            <a href="#/empleado/recibos" class="btn btn-primary">Ir a mis recibos</a>
          </div>
        </section>
      `;
      return;
    }
  } catch (e) {
    console.error('Error fetching token info:', e);
    // Fallback: If we can't verify, we'll continue and the API will fail later if needed,
    // but the token info is public enough to check here.
  }

  // ─── Shell ───
  container.innerHTML = `
    <section class="sign-shell-unified" id="signCard">
      <div class="sign-header mb-32">
        <h1 class="card-title sign-title">Revisión y Firma Digital</h1>
        <div id="signTokenNotice" class="small-muted sign-token-notice mt-8"></div>
      </div>

      <div id="signError" class="hidden mt-16 mb-16"></div>

      <!-- STEP 0: OTP Verification (shown first) -->
      <div id="signOtpStep" class="hidden mb-32">
        <div class="card p-24" style="max-width: 480px; margin: 0 auto;">
          <div class="flex items-center gap-12 mb-16">
            <span class="text-2xl">🔐</span>
            <h3 class="font-bold" style="margin:0">Verificar tu identidad</h3>
          </div>

          <p class="small-muted mb-8" id="otpChannelHint">Enviamos un código de verificación</p>
          <p class="small-muted mb-16">al número <strong id="otpDestHint"></strong></p>

          <div class="flex gap-8 mb-16">
            <input id="signOtpCode" type="text" maxlength="6" inputmode="numeric" autocomplete="one-time-code"
                   class="input text-center text-xl font-mono tracking-widest"
                   placeholder="000000" style="letter-spacing: 0.5em; font-size: 24px; text-align: center;" />
            <button id="signVerifyOtp" class="btn btn-primary">Validar</button>
          </div>

          <div id="otpStatus" class="mb-12 hidden"></div>

          <div class="flex gap-16 items-center">
            <button id="signResendOtp" class="link small" disabled>Reenviar código (<span id="resendTimer">60</span>s)</button>
            <button id="signFallbackChannel" class="link small hidden">📧 Validar por Email</button>
          </div>

          <div id="otpNoContact" class="hidden mt-16">
            <div class="notice-panel warning">
              No hay teléfono ni email registrado en tu legajo. Contactá a RRHH para actualizar tus datos.
            </div>
          </div>
        </div>
      </div>

      <!-- MAIN CONTENT (unlocked after OTP) -->
      <div id="signContent" class="hidden">
        <div class="sign-grid">

          <!-- Column 1: Document View -->
          <div class="sign-pdf-column">
             <div class="sign-pdf-viewer">
                <div class="sign-pdf-header flex-between">
                  <span>Documento a firmar</span>
                  <div id="signStatus" class="sign-otp-status-badge sign-otp-success">Identidad Verificada ✓</div>
                </div>
                <div id="pdfViewerContainer" class="sign-pdf-iframe-unified" style="overflow-y: auto; background: #525659; display: flex; flex-direction: column; align-items: center; padding: 15px 0; gap: 15px;"></div>
                <iframe id="signPdfIframe" class="sign-pdf-iframe-unified hidden"></iframe>
             </div>
          </div>

          <!-- Column 2: Action Sidebar -->
          <aside class="sign-sidebar-sticky">

            <!-- Context Box -->
            <div id="signInfo" class="sign-info-box"></div>

            <!-- Signature Section (Unlocked) -->
            <div id="signatureSection" class="card sign-action-card sign-canvas-unlocked">
              <div class="flex items-center gap-12 mb-16">
                <span class="text-2xl">✍️</span>
                <h3 class="font-bold">Estampar Firma</h3>
              </div>

              <div class="form-group mb-16">
                <label>Confirmar CUIL / ID</label>
                <input id="signCuil" type="text" class="input" placeholder="Sin guiones" inputmode="numeric" />
              </div>

              <div id="storedSigWrap" class="hidden mb-16"></div>

              <div id="canvasSection" class="mb-24">
                <div class="sign-canvas-wrap">
                  <canvas id="signCanvas" width="620" height="200" class="sign-canvas"></canvas>
                </div>
                <div class="flex justify-between mt-8">
                  <span class="small-muted">Área de firma manual</span>
                  <button id="signClear" class="link small">Limpiar</button>
                </div>
              </div>

              <div class="flex flex-col gap-12">
                <button id="signSubmit" class="btn btn-primary btn-lg w-full">Finalizar y Firmar Recibo</button>
                <button id="signReject" class="btn btn-ghost text-danger small">Observar Recibo</button>
              </div>

              <textarea id="signRejectReason" class="input hidden mt-12" rows="2" placeholder="Motivo de la observación (mín. 10 carac.)"></textarea>
            </div>

          </aside>
        </div>
      </div>

      <!-- Finished States -->
      <div id="signAlreadySigned" class="hidden" style="max-width: 600px; margin: 0 auto;">
        <div class="card sign-state-card sign-state-card-success">
          <div class="sign-state-title">Firma registrada con éxito</div>
          <p class="small-muted mb-24">El documento ha sido firmado digitalmente y archivado en tu legajo.</p>
          <div class="flex gap-12 justify-center">
            <button id="signDownload" class="btn btn-primary px-32">Descargar PDF</button>
          </div>

          <a class="btn btn-ghost w-full mt-16" href="#/select-role">Salir del portal</a>
        </div>
      </div>

      <div id="signAlreadyRejected" class="hidden text-center" style="max-width: 400px; margin: 0 auto;">
        <div class="card p-32">
           <div class="sign-state-title">Recibo observado</div>
           <p class="small-muted">La observación fue comunicada a la empresa.</p>
           <a class="btn btn-secondary mt-24 w-full" href="#/select-role">Regresar al inicio</a>
        </div>
      </div>

      <div id="signExpired" class="hidden text-center" style="max-width: 400px; margin: 0 auto;">
        <div class="card p-32">
           <div class="sign-state-title">Enlace expirado</div>
           <p class="small-muted mb-24">Este enlace de firma ya no es válido.</p>
           <a class="btn btn-secondary w-full" href="#/select-role">Volver</a>
        </div>
      </div>
    </section>

    <!-- Signature Required Modal -->
    <div id="sigRequiredModal" class="modal hidden">
      <div class="modal-content modal-sig-required">
        <div class="modal-body p-32 text-center">
          <span class="sig-required-icon">✍️</span>
          <h2 class="text-h2 mb-12">Firma Requerida</h2>
          <p class="small-muted mb-24">Para firmar este recibo, primero tenés que configurar tu firma digital en tu panel de control.</p>
          <button id="btnGoToDashboard" class="btn btn-primary w-full">Configurar mi firma ahora</button>
          <button id="btnCancelSigModal" class="btn btn-ghost w-full mt-8">Cerrar</button>
        </div>
      </div>
    </div>
  `;

  // ─── State ───
  let tokenInfo = null;
  let hasDrawn = false;
  let otpVerified = false;
  let resendCountdown = null;
  let otpChannel = 'sms';

  // ─── 1. Fetch Token Info ───
  try {
    tokenInfo = await apiFetch(`/api/signature-requests/${token}/info`);
    if (tokenInfo.status === 'signed') { el('signAlreadySigned', container).classList.remove('hidden'); bindFinalActions(); return; }
    if (tokenInfo.status === 'rejected') { el('signAlreadyRejected', container).classList.remove('hidden'); return; }

    el('signTokenNotice', container).textContent = `Recibo ${tokenInfo.period} — ${tokenInfo.employee}`;
  } catch (err) {
    if (err.status === 404 || err.status === 410) {
      el('signExpired', container).classList.remove('hidden');
    } else {
      showError(el('signError', container), err);
      el('signError', container).classList.remove('hidden');
    }
    return;
  }

  // ─── 2. Soft-Match / Pre-validation Skip (Requirement 11) ───
  if (tokenInfo.requires_verification === false) {
    otpVerified = true;
    el('signOtpStep', container).classList.add('hidden');
    if (tokenInfo.soft_match) {
        showToast('Identidad reconocida ✓ (Conexión segura)', 'success');
    }
    await renderSigningContent("NONE", "SOFT_MATCH");
    return;
  }

  // ─── 3. Show OTP Step ───
  if (!tokenInfo.has_phone && !tokenInfo.has_email) {
    el('signOtpStep', container).classList.remove('hidden');
    el('otpNoContact', container).classList.remove('hidden');
    // Hide the input fields
    el('signOtpCode', container).parentElement.classList.add('hidden');
    el('signResendOtp', container).classList.add('hidden');
    return;
  }

  el('signOtpStep', container).classList.remove('hidden');
  otpChannel = tokenInfo.has_phone ? 'sms' : 'email';

  // Auto-send OTP on page load
  await sendOtp(otpChannel);

  // Show email fallback if phone is primary
  if (tokenInfo.has_phone && tokenInfo.has_email) {
    el('signFallbackChannel', container).classList.remove('hidden');
    el('signFallbackChannel', container).textContent = '📧 ¿Ya no tenés este número? Validar por Email';
  }

  // ─── OTP Handlers ───

  async function sendOtp(channel) {
    otpChannel = channel;
    updateChannelHints(channel);
    startResendCooldown();

    try {
      const res = await apiFetch(`/api/signature-requests/${token}/send-otp`, {
        method: 'POST',
        body: { channel }
      });

      // Update hints with actual destination
      if (res.destination) {
        el('otpDestHint', container).textContent = res.destination;
      }
      if (res.channel !== channel) {
        // Server fell back to a different channel
        updateChannelHints(res.channel);
        otpChannel = res.channel;
      }

      showToast(res.channel === 'sms' ? 'Código enviado por SMS' : 'Código enviado por Email', 'success');
    } catch (err) {
      showError(el('otpStatus', container), err);
      el('otpStatus', container).classList.remove('hidden');
    }
  }

  function updateChannelHints(channel) {
    const hint = el('otpChannelHint', container);
    const dest = el('otpDestHint', container);

    if (channel === 'sms') {
      hint.textContent = '📱 Código enviado por SMS';
      dest.textContent = tokenInfo.employee_phone || '...';
      if (tokenInfo.has_email) {
        el('signFallbackChannel', container).classList.remove('hidden');
        el('signFallbackChannel', container).textContent = '📧 ¿Ya no tenés este número? Validar por Email';
      }
    } else {
      hint.textContent = '📧 Código enviado por Email';
      dest.textContent = 'tu correo registrado';
      el('signFallbackChannel', container).classList.add('hidden');
    }
  }

  function startResendCooldown() {
    const btn = el('signResendOtp', container);
    const timer = el('resendTimer', container);
    btn.disabled = true;
    let seconds = 60;
    timer.textContent = seconds;
    btn.innerHTML = `Reenviar código (<span id="resendTimer">${seconds}</span>s)`;

    if (resendCountdown) clearInterval(resendCountdown);
    resendCountdown = setInterval(() => {
      seconds--;
      const t = el('resendTimer', container) || btn.querySelector('span');
      if (t) t.textContent = seconds;
      if (seconds <= 0) {
        clearInterval(resendCountdown);
        btn.disabled = false;
        btn.textContent = 'Reenviar código';
      }
    }, 1000);
  }

  el('signResendOtp', container).onclick = () => sendOtp(otpChannel);
  el('signFallbackChannel', container).onclick = () => sendOtp('email');

  el('signVerifyOtp', container).onclick = async () => {
    const code = el('signOtpCode', container).value.trim();
    if (!code || code.length < 6) return showToast('Ingresá el código de 6 dígitos', 'warning');

    const btn = el('signVerifyOtp', container);
    btn.disabled = true;
    btn.textContent = 'Verificando...';

    try {
      const res = await apiFetch(`/api/signature-requests/${token}/verify-otp`, {
        method: 'POST',
        body: { code }
      });

      // Set the session cookie for subsequent authenticated requests
      if (res.session_token) {
        document.cookie = `session=${res.session_token}; path=/; max-age=900; SameSite=Lax`;
      }

      otpVerified = true;
      showToast('Identidad verificada correctamente ✓', 'success');

      // Transition: hide OTP step, show signing content
      el('signOtpStep', container).classList.add('hidden');
      await renderSigningContent(res.otp_channel, res.otp_destination_hash);

    } catch (err) {
      showError(el('otpStatus', container), err);
      el('otpStatus', container).classList.remove('hidden');
    } finally {
      btn.disabled = false;
      btn.textContent = 'Validar';
    }
  };

  // Allow Enter key on OTP input
  el('signOtpCode', container).addEventListener('keydown', (e) => {
    if (e.key === 'Enter') el('signVerifyOtp', container).click();
  });

  // ─── Signing Content (after OTP verified) ───

  async function renderSigningContent(otpChannelUsed, otpDestHash) {
    el('signContent', container).classList.remove('hidden');
    const pdfUrl = apiUrl(`/api/signature-requests/${token}/view`);
    const viewerContainer = el('pdfViewerContainer', container);
    const iframe = el('signPdfIframe', container);

    const totalPages = tokenInfo.page_count || 1;
    viewerContainer.classList.remove('hidden');
    iframe.classList.add('hidden');
    viewerContainer.innerHTML = '';

    for (let pageNum = 0; pageNum < totalPages; pageNum++) {
      const pageDiv = document.createElement('div');
      pageDiv.style.marginBottom = '15px';
      pageDiv.style.boxShadow = '0 4px 12px rgba(0,0,0,0.3)';
      pageDiv.style.backgroundColor = '#fff';
      pageDiv.style.display = 'flex';
      pageDiv.style.justifyContent = 'center';
      pageDiv.style.borderRadius = '4px';
      pageDiv.style.overflow = 'hidden';
      pageDiv.style.width = '90%';
      pageDiv.style.maxWidth = '800px';

      const img = document.createElement('img');
      img.src = apiUrl(`/api/signature-requests/${token}/page/${pageNum}`);
      img.alt = `Página ${pageNum + 1}`;
      img.style.width = '100%';
      img.style.height = 'auto';
      img.style.display = 'block';

      img.onerror = () => {
        console.error(`Error loading page image ${pageNum}`);
        pageDiv.innerHTML = `<div style="padding: 20px; color: red; text-align: center; font-weight: 500;">Error al cargar la página ${pageNum + 1}.</div>`;
      };

      pageDiv.appendChild(img);
      viewerContainer.appendChild(pageDiv);
    }

    const softMatchBadge = (otpDestHash === 'SOFT_MATCH') 
        ? '<div class="sign-otp-status-badge sign-otp-success">Seguridad de Red: Verificada ✓</div>'
        : '<div id="signStatus" class="sign-otp-status-badge sign-otp-success">Identidad Verificada ✓</div>';

    el('signStatus', container).outerHTML = softMatchBadge;

    el('signInfo', container).innerHTML = `
      <div class="dl-grid">
        <div class="dl-item"><div class="dl-label">Empleado</div><div class="dl-value">${tokenInfo.employee}</div></div>
        <div class="dl-item"><div class="dl-label">Período</div><div class="dl-value">${tokenInfo.period}</div></div>
        <div class="dl-item"><div class="dl-label">Organización</div><div class="dl-value">${tokenInfo.organization_name}</div></div>
      </div>
    `;

    // ─── Signature options: stored signature or manual canvas ───
const storedSigWrap = el('storedSigWrap', container);
const canvasSection = el('canvasSection', container);

async function configureSignatureOptions() {
  // Estado seguro por defecto:
  // si algo falla, el usuario siempre podrá dibujar una firma nueva.
  storedSigWrap.classList.add('hidden');
  storedSigWrap.innerHTML = '';
  canvasSection.classList.remove('hidden');

  try {
    const sigStatus = await apiFetch('/api/signatures/user/me');

    if (!sigStatus?.has_signature) {
      return;
    }

    /*
     * Se agrega un parámetro para evitar que el navegador reutilice
     * una imagen anterior cuando el empleado actualizó su firma.
     */
    const signatureImageUrl = apiUrl(
      `/api/signatures/user/image?v=${Date.now()}`
    );

    storedSigWrap.innerHTML = `
      <div class="card p-16 bg-slate-50">
        <label
          for="useStored"
          class="flex items-center gap-12 cursor-pointer"
        >
          <input
            type="checkbox"
            id="useStored"
            checked
            class="w-20 h-20"
          />

          <div class="flex-1">
            <strong>Usar mi firma guardada</strong>
            <div class="small-muted mt-4">
              Esta es la firma que se estampará en el documento.
            </div>
          </div>
        </label>

        <div
          id="storedSignaturePreviewWrap"
          class="mt-12 p-12 bg-white rounded border"
          style="
            min-height: 100px;
            display: flex;
            align-items: center;
            justify-content: center;
          "
        >
          <div
            id="storedSignatureLoading"
            class="small-muted"
          >
            Cargando firma guardada...
          </div>

          <img
            id="storedSignaturePreview"
            class="hidden"
            alt="Vista previa de tu firma guardada"
            draggable="false"
            style="
              display: block;
              width: auto;
              max-width: 100%;
              max-height: 120px;
              object-fit: contain;
            "
          />
        </div>

        <div
          id="storedSignatureError"
          class="hidden notice-panel warning mt-12"
        >
          No se pudo cargar la imagen de tu firma guardada.
          Podés dibujar una firma nueva para continuar.
        </div>
      </div>
    `;

    storedSigWrap.classList.remove('hidden');

    const useStoredCheckbox = el('useStored', container);
    const signaturePreview = el('storedSignaturePreview', container);
    const signatureLoading = el('storedSignatureLoading', container);
    const signaturePreviewWrap = el(
      'storedSignaturePreviewWrap',
      container
    );
    const signatureError = el('storedSignatureError', container);

    const enableStoredSignature = () => {
      useStoredCheckbox.checked = true;
      useStoredCheckbox.disabled = false;
      canvasSection.classList.add('hidden');
    };

    const disableStoredSignature = () => {
      useStoredCheckbox.checked = false;
      useStoredCheckbox.disabled = true;

      signatureLoading?.classList.add('hidden');
      signaturePreview?.classList.add('hidden');
      signaturePreviewWrap?.classList.add('hidden');
      signatureError?.classList.remove('hidden');

      canvasSection.classList.remove('hidden');
    };

    useStoredCheckbox.addEventListener('change', (event) => {
      canvasSection.classList.toggle(
        'hidden',
        event.target.checked
      );
    });

    /*
     * Se carga manualmente después de registrar onload/onerror,
     * para no perder eventos si la respuesta llega muy rápido.
     */
    signaturePreview.onload = () => {
      signatureLoading?.classList.add('hidden');
      signaturePreview.classList.remove('hidden');
      signatureError?.classList.add('hidden');

      enableStoredSignature();
    };

    signaturePreview.onerror = () => {
      console.error(
        'No se pudo cargar la firma guardada desde:',
        signatureImageUrl
      );

      disableStoredSignature();

      showToast(
        'No se pudo mostrar tu firma guardada. Podés dibujar una nueva.',
        'warning'
      );
    };

    signaturePreview.src = signatureImageUrl;

  } catch (err) {
    console.error('Error al consultar la firma guardada:', err);

    /*
     * /user/me normalmente no debería devolver 404:
     * devuelve has_signature=false.
     * Por eso cualquier error debe registrarse y no ocultarse.
     */
    storedSigWrap.classList.add('hidden');
    storedSigWrap.innerHTML = '';
    canvasSection.classList.remove('hidden');

    showToast(
      'No se pudo consultar tu firma guardada. Podés dibujar una nueva.',
      'warning'
    );
  }
}

await configureSignatureOptions();

initCanvas();

    // Scroll to signing section
    el('signatureSection', container).scrollIntoView({ behavior: 'smooth', block: 'center' });

    // ─── Submit Signature ───
    el('signSubmit', container).onclick = async () => {
      const useStored = el('useStored', container)?.checked || false;
      if (!useStored && !hasDrawn) return showToast('Por favor, dibujá tu firma en el recuadro', 'warning');

      if (!await confirmAction('¿Estás seguro de que deseas firmar este recibo con validez legal?')) return;

      const btn = el('signSubmit', container);
      btn.disabled = true;
      btn.textContent = 'Firmando...';

      try {
        await apiFetch(`/api/signature-requests/${token}/accept`, {
          method: 'POST',
          body: {
            signature_image: useStored ? 'STORED_SIGNATURE' : el('signCanvas', container).toDataURL(),
            cuil: el('signCuil', container).value
          }
        });
        el('signContent', container).classList.add('hidden');
        el('signAlreadySigned', container).classList.remove('hidden');
        bindFinalActions();
        showToast('Recibo firmado y archivado ✓', 'success');
      } catch (err) {
        if (err.body?.detail === 'signature_required') {
          openModal('sigRequiredModal', container);
        } else {
          showToast(err.body?.detail || 'Error al firmar', 'error');
        }
      } finally {
        btn.disabled = false;
        btn.textContent = 'Finalizar y Firmar Recibo';
      }
    };

    // ─── Reject ───
    el('signReject', container).onclick = () => {
      const reasonEl = el('signRejectReason', container);
      if (reasonEl.classList.contains('hidden')) {
        reasonEl.classList.remove('hidden');
        reasonEl.focus();
        return;
      }
      if (reasonEl.value.length < 10) return showToast('Por favor, detallá el motivo del rechazo (mín. 10 caracteres)', 'warning');

      (async () => {
        try {
          await apiFetch(`/api/signature-requests/${token}/reject`, { method: 'POST', body: { reason: reasonEl.value } });
          el('signContent', container).classList.add('hidden');
          el('signAlreadyRejected', container).classList.remove('hidden');
        } catch (err) {
          showToast('Error al registrar rechazo', 'error');
        }
      })();
    };
  }

  // ─── Canvas Drawing ───
  function initCanvas() {
    const canvas = el('signCanvas', container);
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    ctx.strokeStyle = '#0f172a'; ctx.lineWidth = 3; ctx.lineJoin = 'round'; ctx.lineCap = 'round';
    let drawing = false; let last = { x: 0, y: 0 };
    const getP = (e) => {
      const r = canvas.getBoundingClientRect();
      const x = (e.touches ? e.touches[0].clientX : e.clientX) - r.left;
      const y = (e.touches ? e.touches[0].clientY : e.clientY) - r.top;
      return { x: x * (canvas.width / r.width), y: y * (canvas.height / r.height) };
    };
    canvas.onmousedown = (e) => { drawing = true; last = getP(e); hasDrawn = true; };
    canvas.onmousemove = (e) => { if(!drawing) return; e.preventDefault(); const p = getP(e); ctx.beginPath(); ctx.moveTo(last.x, last.y); ctx.lineTo(p.x, p.y); ctx.stroke(); last = p; };
    window.onmouseup = () => drawing = false;
    canvas.addEventListener('touchstart', (e) => { drawing = true; last = getP(e); hasDrawn = true; }, {passive:false});
    canvas.addEventListener('touchmove', (e) => { if(!drawing) return; e.preventDefault(); const p = getP(e); ctx.beginPath(); ctx.moveTo(last.x, last.y); ctx.lineTo(p.x, p.y); ctx.stroke(); last = p; }, {passive:false});
    el('signClear', container).onclick = () => { ctx.clearRect(0,0, canvas.width, canvas.height); hasDrawn = false; };
  }

  // ─── Final Actions (for already-signed state) ───
  function bindFinalActions() {
    const dl = el('signDownload', container);
    if (dl) dl.onclick = () => {
      const url = apiUrl(`/api/signature-requests/${token}/view`);
      const link = document.createElement('a');
      link.href = url;
      // Provide a nice fallback filename
      const filename = tokenInfo && tokenInfo.period 
          ? `Recibo_${tokenInfo.period.replace(/ /g, '_')}_firmado.pdf` 
          : 'Recibo_Firmado.pdf';
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    };
  }

  bindFinalActions();

  // Modal handlers
  const goToDash = el('btnGoToDashboard', container);
  if (goToDash) goToDash.onclick = () => { location.hash = '#/empleado/dashboard'; };
  const cancelModal = el('btnCancelSigModal', container);
  if (cancelModal) cancelModal.onclick = () => closeModal('sigRequiredModal', container);
}