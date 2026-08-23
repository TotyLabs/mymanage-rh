import {
  apiFetch,
  showError,
  getMe,
  getApiBase,
  showToast,
  el,
} from '../common.js';

export async function render(container) {
  const state = {
    me: null,
    pendingCount: 0,
    hasSignature: false,
    signatureObjectUrl: null,
  };

  container.innerHTML = `
    <div class="action-bar">
      <div>
        <h1 class="card-title mb-8">Mi Perfil</h1>
        <div id="userInfo" class="small-muted">Cargando perfil...</div>
      </div>
    </div>

    <div id="summarySection" class="mb-24"></div>

    <div class="card mb-16">
      <div class="card-header flex-between">
        <h2 class="card-title">Mi Firma Digital</h2>
        <div id="sigBadgeContainer"></div>
      </div>

      <div class="p-16">
        <div class="signature-mgmt-grid">
          <div>
            <p class="small-muted mb-12">
              Dibujá tu firma en el recuadro gris. Esta firma se usará para
              autorizar tus recibos de sueldo.
            </p>

            <div
              class="signature-canvas-container"
              id="sigCanvasContainer"
            >
              <canvas
                id="employeeSigCanvas"
                width="600"
                height="200"
              ></canvas>
            </div>

            <div class="signature-actions">
              <button
                type="button"
                class="btn btn-secondary"
                id="btnClearSig"
              >
                Limpiar
              </button>

              <button
                type="button"
                class="btn btn-primary"
                id="btnSaveSig"
              >
                Guardar Firma
              </button>

              <label
                class="btn btn-ghost"
                style="
                  position: relative;
                  overflow: hidden;
                  cursor: pointer;
                "
              >
                Subir Imagen

                <input
                  type="file"
                  id="uploadSigFile"
                  accept="image/png,image/jpeg"
                  style="
                    position: absolute;
                    inset: 0;
                    opacity: 0;
                    width: 100%;
                    height: 100%;
                    cursor: pointer;
                  "
                >
              </label>
            </div>
          </div>

          <div>
            <h3
              class="
                text-label
                font-bold
                mb-8
                uppercase
                letter-spacing-05
              "
            >
              Firma Actual
            </h3>

            <div
              id="sigPreviewContainer"
              class="signature-preview-card"
            >
              <p class="small-muted">Cargando...</p>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="card mb-16">
      <div class="card-header flex-between">
        <h2 class="card-title">Documentos para firmar</h2>
      </div>

      <div class="p-16">
        <p class="small-muted mb-16">
          Subí un archivo PDF y elegí la sección donde querés guardarlo antes de firmarlo.
        </p>

        <div class="grid gap-16">
          <div>
            <label class="label" for="uploadEmployeeDocument">Archivo PDF</label>
            <input id="uploadEmployeeDocument" type="file" accept="application/pdf" class="input-block" />
          </div>

          <div>
            <label class="label" for="selectDocumentSection">Sección</label>
            <select id="selectDocumentSection" class="input-block">
              <option value="PAYROLL">Recibos</option>
              <option value="UNEMPLOYMENT">Fondo de Desempleo</option>
              <option value="MISC">Varios</option>
            </select>
          </div>

          <div class="col-span-2">
            <button id="btnUploadAndSign" type="button" class="btn btn-primary">
              Firmar como empleado
            </button>
          </div>

          <div id="uploadSignStatus" class="small-muted col-span-2"></div>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="p-16">
        <div class="notice-panel warning mb-16">
          <strong>Eliminación de cuenta</strong>

          <p class="mt-8 small-muted">
            Una vez eliminada, tu cuenta y todos los datos asociados no podrán
            recuperarse. Esta acción es irreversible.
          </p>
        </div>

        <button
          type="button"
          id="btnDeleteEmpAccount"
          class="btn btn-danger"
        >
          Eliminar mi cuenta y datos
        </button>
      </div>
    </div>
  `;

  const userInfoEl = el('userInfo', container);
  const summaryEl = el('summarySection', container);
  const sigCanvas = el('employeeSigCanvas', container);
  const sigPreview = el('sigPreviewContainer', container);
  const sigBadge = el('sigBadgeContainer', container);
  const btnSaveSig = el('btnSaveSig', container);
  const btnClearSig = el('btnClearSig', container);
  const uploadInput = el('uploadSigFile', container);
  const uploadDocumentInput = el('uploadEmployeeDocument', container);
  const selectDocumentSection = el('selectDocumentSection', container);
  const btnUploadAndSign = el('btnUploadAndSign', container);
  const uploadSignStatus = el('uploadSignStatus', container);
  const deleteAccountBtn = el('btnDeleteEmpAccount', container);

  let sigHasDrawn = false;

  function releaseSignatureObjectUrl() {
    if (!state.signatureObjectUrl) return;

    URL.revokeObjectURL(state.signatureObjectUrl);
    state.signatureObjectUrl = null;
  }

  function renderSummary() {
    if (state.pendingCount > 0) {
      summaryEl.innerHTML = `
        <div class="notice-panel warning">
          <strong>
            Tenés ${state.pendingCount} recibo(s) pendiente(s) de firma.
          </strong>

          <p class="mt-8">
            <a href="#/empleado/recibos" class="link">
              Ir a mis recibos para firmar ahora
            </a>
          </p>
        </div>
      `;

      return;
    }

    summaryEl.innerHTML = `
      <div class="notice-panel success">
        <strong>No tenés recibos pendientes de firma.</strong>

        <p class="mt-8 small-muted">
          Todo está al día.
        </p>
      </div>
    `;
  }

  async function loadSignatureImage() {
    releaseSignatureObjectUrl();

    sigPreview.innerHTML = `
      <p class="small-muted">
        Cargando firma...
      </p>
    `;

    try {
      const response = await fetch(
        `${getApiBase()}/api/signatures/user/image?v=${Date.now()}`,
        {
          method: 'GET',
          credentials: 'include',
          cache: 'no-store',
          headers: {
            'X-Requested-With': 'XMLHttpRequest',
          },
        }
      );

      if (!response.ok) {
        throw new Error(
          `No se pudo cargar la firma. Código HTTP: ${response.status}`
        );
      }

      const contentType = response.headers.get('content-type') || '';

      if (!contentType.startsWith('image/')) {
        throw new Error(
          `El servidor devolvió un formato inválido: ${contentType || 'desconocido'}`
        );
      }

      const blob = await response.blob();

      if (!blob.size) {
        throw new Error('La imagen de la firma está vacía.');
      }

      state.signatureObjectUrl = URL.createObjectURL(blob);

      const image = document.createElement('img');
      image.src = state.signatureObjectUrl;
      image.className = 'signature-preview-img';
      image.alt = 'Tu firma guardada';

      image.addEventListener(
        'error',
        () => {
          releaseSignatureObjectUrl();

          sigPreview.innerHTML = `
            <p class="error">
              La firma está guardada, pero la imagen no pudo mostrarse.
            </p>
          `;
        },
        { once: true }
      );

      sigPreview.innerHTML = '';
      sigPreview.appendChild(image);
    } catch (error) {
      console.error('Error cargando la firma guardada:', error);

      sigPreview.innerHTML = `
        <div>
          <p class="error mb-8">
            Tenés una firma guardada, pero no se pudo cargar la imagen.
          </p>

          <p class="small-muted">
            ${error.message || 'Error desconocido'}
          </p>
        </div>
      `;
    }
  }

  async function updateSignatureUI(hasSignature) {
    state.hasSignature = Boolean(hasSignature);

    if (!state.hasSignature) {
      releaseSignatureObjectUrl();

      sigBadge.innerHTML = `
        <span class="signature-badge missing">
          ⚠️ Sin Firma
        </span>
      `;

      sigPreview.innerHTML = `
        <p class="small-muted italic">
          No tenés una firma guardada todavía.
        </p>
      `;

      return;
    }

    sigBadge.innerHTML = `
      <span class="signature-badge active">
        ✓ Firma Activa
      </span>
    `;

    await loadSignatureImage();
  }

  async function loadInitialData() {
    try {
      const [meRes, receiptsRes, sigRes] = await Promise.all([
        getMe(),
        apiFetch('/api/receipts/my-history'),
        apiFetch('/api/signatures/user/me'),
      ]);

      state.me = meRes?.user || meRes || null;

      if (state.me) {
        const fullName = state.me.full_name || '';
        const email = state.me.email || '';

        userInfoEl.textContent = [fullName, email]
          .filter(Boolean)
          .join(' — ');
      } else {
        userInfoEl.textContent = 'No se pudo obtener la información del perfil.';
      }

      const receipts = Array.isArray(receiptsRes)
        ? receiptsRes
        : receiptsRes?.receipts || [];

      state.pendingCount = receipts.filter(
        (receipt) => receipt.status !== 'signed'
      ).length;

      renderSummary();

      console.log('SIG RES:', sigRes);
      await updateSignatureUI(Boolean(sigRes?.has_signature));
    } catch (error) {
      console.error('Error cargando el perfil del empleado:', error);

      showError(userInfoEl, error);

      summaryEl.innerHTML = `
        <div class="notice-panel warning">
          No se pudo cargar el resumen de tu cuenta.
        </div>
      `;

      sigBadge.innerHTML = `
        <span class="signature-badge missing">
          Estado desconocido
        </span>
      `;

      sigPreview.innerHTML = `
        <p class="error">
          No se pudo comprobar si tenés una firma guardada.
        </p>
      `;
    }
  }

  function configureSignatureCanvas() {
    if (!sigCanvas) return;

    const ctx = sigCanvas.getContext('2d');

    if (!ctx) {
      console.error('No se pudo obtener el contexto 2D del canvas.');
      return;
    }

    ctx.strokeStyle = '#0f172a';
    ctx.lineWidth = 3;
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';

    let drawing = false;
    let activePointerId = null;
    let lastPosition = { x: 0, y: 0 };

    function getCanvasPosition(event) {
      const rect = sigCanvas.getBoundingClientRect();

      const scaleX = sigCanvas.width / rect.width;
      const scaleY = sigCanvas.height / rect.height;

      return {
        x: (event.clientX - rect.left) * scaleX,
        y: (event.clientY - rect.top) * scaleY,
      };
    }

    function startDrawing(event) {
      if (event.pointerType === 'mouse' && event.button !== 0) {
        return;
      }

      event.preventDefault();

      drawing = true;
      activePointerId = event.pointerId;
      lastPosition = getCanvasPosition(event);

      sigCanvas.setPointerCapture?.(event.pointerId);
    }

    function draw(event) {
      if (!drawing || event.pointerId !== activePointerId) {
        return;
      }

      event.preventDefault();

      const position = getCanvasPosition(event);

      ctx.beginPath();
      ctx.moveTo(lastPosition.x, lastPosition.y);
      ctx.lineTo(position.x, position.y);
      ctx.stroke();

      lastPosition = position;
      sigHasDrawn = true;
    }

    function stopDrawing(event) {
      if (
        activePointerId !== null &&
        event.pointerId !== activePointerId
      ) {
        return;
      }

      drawing = false;

      if (activePointerId !== null) {
        try {
          sigCanvas.releasePointerCapture?.(activePointerId);
        } catch {
          // El puntero puede haberse liberado automáticamente.
        }
      }

      activePointerId = null;
    }

    sigCanvas.style.touchAction = 'none';

    sigCanvas.addEventListener('pointerdown', startDrawing);
    sigCanvas.addEventListener('pointermove', draw);
    sigCanvas.addEventListener('pointerup', stopDrawing);
    sigCanvas.addEventListener('pointercancel', stopDrawing);
    sigCanvas.addEventListener('pointerleave', stopDrawing);

    btnClearSig?.addEventListener('click', () => {
      ctx.clearRect(
        0,
        0,
        sigCanvas.width,
        sigCanvas.height
      );

      sigHasDrawn = false;
    });
  }

  async function saveSignatureImage(signatureImage) {
    await apiFetch('/api/signatures/user/save', {
      method: 'POST',
      body: {
        signature_image: signatureImage,
      },
    });

    state.hasSignature = true;
    await updateSignatureUI(true);
  }

  btnSaveSig?.addEventListener('click', async () => {
    if (!sigCanvas) return;

    if (!sigHasDrawn) {
      showToast(
        'Dibujá tu firma antes de guardarla.',
        'warning'
      );

      return;
    }

    btnSaveSig.disabled = true;
    btnSaveSig.textContent = 'Guardando...';

    try {
      const dataUrl = sigCanvas.toDataURL('image/png');

      await saveSignatureImage(dataUrl);

      const ctx = sigCanvas.getContext('2d');

      ctx?.clearRect(
        0,
        0,
        sigCanvas.width,
        sigCanvas.height
      );

      sigHasDrawn = false;

      showToast(
        'Firma guardada correctamente.',
        'success'
      );
    } catch (error) {
      console.error('Error guardando la firma:', error);

      const detail =
        error?.body?.detail ||
        error?.message ||
        'No se pudo guardar la firma.';

      showToast(
        `Error al guardar la firma: ${detail}`,
        'error'
      );
    } finally {
      btnSaveSig.disabled = false;
      btnSaveSig.textContent = 'Guardar Firma';
    }
  });

  btnUploadAndSign?.addEventListener('click', async () => {
    if (!state.hasSignature) {
      showToast(
        'Primero registrá tu firma en Mi Perfil.',
        'warning'
      );
      return;
    }

    const file = uploadDocumentInput?.files?.[0];
    const section = selectDocumentSection?.value;

    if (!file) {
      showToast('Seleccioná un archivo PDF para subir.', 'warning');
      return;
    }

    if (file.type !== 'application/pdf' && !file.name.toLowerCase().endsWith('.pdf')) {
      showToast('El archivo debe ser un PDF.', 'warning');
      return;
    }

    btnUploadAndSign.disabled = true;
    btnUploadAndSign.textContent = 'Firmando...';
    uploadSignStatus.textContent = '';

    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('section', section || 'PAYROLL');

      const result = await apiFetch('/api/signatures/user/upload-sign', {
        method: 'POST',
        body: formData,
      });

      uploadSignStatus.textContent = 'Documento firmado y guardado en la sección seleccionada.';
      showToast('Documento firmado correctamente.', 'success');

      uploadDocumentInput.value = '';
    } catch (error) {
      console.error('Error firmando el documento:', error);
      const detail = error?.body?.detail || error?.message || 'No se pudo firmar el documento.';
      uploadSignStatus.textContent = `Error: ${detail}`;
      showToast(`Error al firmar: ${detail}`, 'error');
    } finally {
      btnUploadAndSign.disabled = false;
      btnUploadAndSign.textContent = 'Firmar como empleado';
    }
  });

  uploadInput?.addEventListener('change', async (event) => {
    const file = event.target.files?.[0];

    if (!file) return;

    const allowedTypes = [
      'image/png',
      'image/jpeg',
    ];

    if (!allowedTypes.includes(file.type)) {
      showToast(
        'La firma debe ser una imagen PNG o JPG.',
        'warning'
      );

      uploadInput.value = '';
      return;
    }

    const maxFileSize = 5 * 1024 * 1024;

    if (file.size > maxFileSize) {
      showToast(
        'La imagen no puede superar los 5 MB.',
        'warning'
      );

      uploadInput.value = '';
      return;
    }

    uploadInput.disabled = true;

    try {
      const base64 = await new Promise((resolve, reject) => {
        const reader = new FileReader();

        reader.onload = () => {
          if (typeof reader.result !== 'string') {
            reject(
              new Error('No se pudo leer la imagen seleccionada.')
            );

            return;
          }

          resolve(reader.result);
        };

        reader.onerror = () => {
          reject(
            reader.error ||
            new Error('No se pudo leer la imagen seleccionada.')
          );
        };

        reader.readAsDataURL(file);
      });

      await saveSignatureImage(base64);

      showToast(
        'Imagen de firma subida correctamente.',
        'success'
      );
    } catch (error) {
      console.error('Error subiendo la firma:', error);

      const detail =
        error?.body?.detail ||
        error?.message ||
        'No se pudo subir la imagen.';

      showToast(
        `Error al subir la imagen: ${detail}`,
        'error'
      );
    } finally {
      uploadInput.disabled = false;
      uploadInput.value = '';
    }
  });

  deleteAccountBtn?.addEventListener('click', async () => {
    const { confirmAction } = await import('../common.js');

    const confirmed = await confirmAction(
      '¿Estás seguro/a de que querés eliminar tu cuenta? ' +
      'Esta acción es irreversible y se perderán todos los datos.'
    );

    if (!confirmed) return;

    deleteAccountBtn.disabled = true;
    deleteAccountBtn.textContent = 'Eliminando...';

    try {
      await apiFetch('/api/employees/me', {
        method: 'DELETE',
      });

      showToast(
        'Cuenta eliminada correctamente.',
        'success'
      );

      setTimeout(() => {
        window.location.hash = '#/login';
      }, 1000);
    } catch (error) {
      console.error('Error eliminando la cuenta:', error);

      const detail =
        error?.body?.detail ||
        error?.message ||
        'No se pudo eliminar la cuenta.';

      showToast(
        `Error al eliminar la cuenta: ${detail}`,
        'error'
      );

      deleteAccountBtn.disabled = false;
      deleteAccountBtn.textContent =
        'Eliminar mi cuenta y datos';
    }
  });

  configureSignatureCanvas();
  await loadInitialData();
}
