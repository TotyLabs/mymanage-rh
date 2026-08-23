import {
  apiFetch,
  showError,
  showToast,
  confirmAction,
  apiUrl,
} from '../common.js';

function el(id, ctx = document) {
  return (ctx || document).querySelector(`#${id}`);
}

export async function render(container) {
  container.innerHTML = `
    <section>
      <div class="action-bar">
        <div>
          <h1 class="card-title mb-8">Configuración de empresa</h1>
          <div class="small-muted">
            Administrá datos legales, firmantes autorizados y logo institucional.
          </div>
        </div>
      </div>

      <section class="card mb-24">
        <div class="card-header">
          <h2 class="card-title">Datos de la empresa</h2>
        </div>

        <div id="orgDataError" class="hidden mb-16"></div>

        <div class="empresa-config-grid">
          <div class="form-group empresa-config-full">
            <label for="orgNameInput">Razón social / Nombre legal</label>
            <input type="text" id="orgNameInput" class="input" placeholder="Ej: Mi Empresa S.A." />
          </div>

          <div class="form-group">
            <label for="orgCuitInput">CUIT (sin guiones)</label>
            <input type="text" id="orgCuitInput" class="input" placeholder="Ej: 30123456789" />
          </div>

          <div class="form-group">
            <label for="orgEmailInput">Email de contacto / Respuesta</label>
            <input type="email" id="orgEmailInput" class="input" placeholder="Ej: rrhh@miempresa.com" />
          </div>

          <div class="form-group">
            <label for="orgPhoneInput">Teléfono de contacto</label>
            <input type="text" id="orgPhoneInput" class="input" placeholder="Ej: +54 11 1234-5678" />
          </div>

          <div class="form-group">
            <label for="orgWebsiteInput">Sitio Web</label>
            <input type="url" id="orgWebsiteInput" class="input" placeholder="https://www.miempresa.com" />
          </div>

          <div class="form-group empresa-config-full">
            <label for="orgActivityInput">Actividad principal</label>
            <input type="text" id="orgActivityInput" class="input" placeholder="Ej: Servicios de Software" />
          </div>

          <div class="form-group empresa-config-full">
            <label for="orgAddressInput">Dirección (Calle y Número)</label>
            <input type="text" id="orgAddressInput" class="input" placeholder="Ej: Av. Corrientes 1234" />
          </div>

          <div class="form-group">
            <label for="orgCityInput">Ciudad / Localidad</label>
            <input type="text" id="orgCityInput" class="input" placeholder="Ej: CABA" />
          </div>

          <div class="form-group">
            <label for="orgProvinceInput">Provincia / Estado</label>
            <input type="text" id="orgProvinceInput" class="input" placeholder="Ej: Buenos Aires" />
          </div>

          <div class="form-group">
            <label for="orgZipInput">Código Postal</label>
            <input type="text" id="orgZipInput" class="input" placeholder="Ej: 1425" />
          </div>
        </div>

        <div class="flex justify-end mt-16">
          <button id="btnSaveOrgData" class="btn btn-primary">Guardar cambios</button>
        </div>
      </section>

      <section class="card mb-24">
        <div class="flex-between mb-16 empresa-config-header-wrap">
          <div>
            <h2 class="card-title mb-8">Firmantes autorizados</h2>
            <div class="small-muted">
              Estas personas podrán firmar digitalmente recibos en representación de la empresa.
            </div>
          </div>

          <button id="btnNewSigner" class="btn btn-primary btn-sm">Subir firma</button>
        </div>

        <div class="notice-panel mb-16">
          <span class="small-muted">
            Podés registrar la firma dibujándola o subiendo una imagen escaneada.
          </span>
        </div>

        <div id="signersEmpty" class="hidden"></div>
        <div id="signersList" class="empresa-signers-grid"></div>
      </section>

      <section class="card">
        <div class="card-header">
          <h2 class="card-title">Logo de la empresa</h2>
        </div>

        <div class="notice-panel mb-16">
          <span class="small-muted">
            Este logo se incluirá en el membrete y sello visual de los recibos emitidos.
          </span>
        </div>

        <div class="empresa-logo-layout">
          <div id="logoPreviewBox" class="logo-preview-box">
            <img id="logoPreviewImg" src="" alt="Logo de la empresa" class="logo-preview-img hidden" />
            <span id="logoPreviewEmpty" class="small-muted text-center">Sin logo</span>
          </div>

          <div class="empresa-logo-actions">
            <input type="file" id="logoUploadInput" accept="image/png, image/jpeg" class="hidden" />
            <button id="btnSelectLogo" class="btn btn-secondary">Seleccionar archivo</button>
            <div id="logoUploadError" class="hidden mt-8"></div>
            <div id="logoUploadSuccess" class="success hidden mt-8">Logo actualizado correctamente.</div>
          </div>
        </div>
      </section>

      <section class="card">
        <div class="card-header">
          <h2 class="card-title" style="color: var(--danger);">Zona de peligro</h2>
        </div>

        <div class="notice-panel warning mb-16">
          <strong>Eliminación de cuenta</strong>
          <p class="mt-8 small-muted">
            Una vez eliminada, la cuenta y todos los datos asociados no podrán ser recuperados. Esta acción es irreversible.
          </p>
        </div>

        <button id="btnDeleteAccount" class="btn btn-danger">Eliminar cuenta y datos</button>
      </section>

      <div id="signerModal" class="modal hidden" aria-hidden="true">
        <div class="modal-content">
          <div class="modal-header">
            <h3 id="signerModalTitle" class="modal-title">Subir firma</h3>
          </div>

          <div class="modal-body">
            <div id="signerModalError" class="hidden mb-16"></div>

            <form id="signerForm" class="auth-form" novalidate>
              <div class="form-group">
                <label for="signerName">Nombre y apellido</label>
                <input type="text" id="signerName" class="input" placeholder="Ej: Juan Pérez" />
              </div>

              <div class="form-group">
                <label for="signerPosition">Cargo / rol</label>
                <input type="text" id="signerPosition" class="input" placeholder="Ej: Apoderado, Gerente RRHH" />
              </div>

              <div class="form-group">
                <label>Modo de firma</label>
                <div class="mode-switch">
                  <button type="button" id="btnModeCanvas" class="btn btn-secondary btn-sm mode-btn active">
                    Dibujar firma
                  </button>
                  <button type="button" id="btnModeFile" class="btn btn-ghost btn-sm mode-btn">
                    Subir archivo
                  </button>
                </div>
              </div>

              <div id="signerCanvasMode" class="mt-12">
                <label class="auth-section-label">Dibujá la firma</label>
                <div class="canvas-wrap">
                  <canvas id="signerCanvas" width="440" height="140" class="empresa-signer-canvas"></canvas>
                </div>

                <div class="mt-8">
                  <button type="button" id="btnClearSignerCanvas" class="btn btn-ghost btn-sm">
                    Limpiar firma
                  </button>
                </div>
              </div>

              <div id="signerFileMode" class="hidden mt-12">
                <label class="auth-section-label" for="signerImage">Firma escaneada (PNG/JPG)</label>
                <input type="file" id="signerImage" class="input" accept="image/png, image/jpeg" />
                <div class="small-muted mt-8">
                  La imagen se utilizará como firma visible en los recibos emitidos.
                </div>
              </div>
            </form>
          </div>

          <div class="modal-footer">
            <button type="button" id="btnCancelSigner" class="btn btn-ghost">Cancelar</button>
            <button type="button" id="btnSaveSigner" class="btn btn-primary">Guardar firmante</button>
          </div>
        </div>
      </div>
    </section>
  `;

  const state = {
    signers: [],
    mode: 'canvas',
    hasDrawn: false,
    org: null,
  };

  let canvas = null;
  let ctx = null;
  let drawing = false;
  let lastPos = { x: 0, y: 0 };

  function showInlineError(target, message) {
    if (!target) return;
    target.className = 'error';
    target.textContent = message;
  }

  function hideInlineMessage(target) {
    if (!target) return;
    target.className = 'hidden';
    target.textContent = '';
  }

  function openSignerModal() {
    el('signerForm', container).reset();
    hideInlineMessage(el('signerModalError', container));
    clearCanvas();
    state.mode = 'canvas';
    setMode('canvas');

    const modal = el('signerModal', container);
    modal.classList.remove('hidden');
    modal.setAttribute('aria-hidden', 'false');
  }

  function closeSignerModal() {
    const modal = el('signerModal', container);
    modal.classList.add('hidden');
    modal.setAttribute('aria-hidden', 'true');
  }

  function setMode(mode) {
    state.mode = mode;

    const btnCanvas = el('btnModeCanvas', container);
    const btnFile = el('btnModeFile', container);
    const canvasMode = el('signerCanvasMode', container);
    const fileMode = el('signerFileMode', container);

    const isCanvas = mode === 'canvas';

    btnCanvas.classList.toggle('btn-secondary', isCanvas);
    btnCanvas.classList.toggle('btn-ghost', !isCanvas);
    btnCanvas.classList.toggle('active', isCanvas);

    btnFile.classList.toggle('btn-secondary', !isCanvas);
    btnFile.classList.toggle('btn-ghost', isCanvas);
    btnFile.classList.toggle('active', !isCanvas);

    canvasMode.classList.toggle('hidden', !isCanvas);
    fileMode.classList.toggle('hidden', isCanvas);
  }

  function initCanvas() {
    canvas = el('signerCanvas', container);
    if (!canvas) return;

    ctx = canvas.getContext('2d');
    ctx.strokeStyle = '#0f172a';
    ctx.lineWidth = 2;
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';

    const getPos = (event) => {
      const rect = canvas.getBoundingClientRect();
      const clientX = event.touches ? event.touches[0].clientX : event.clientX;
      const clientY = event.touches ? event.touches[0].clientY : event.clientY;

      return {
        x: (clientX - rect.left) * (canvas.width / rect.width),
        y: (clientY - rect.top) * (canvas.height / rect.height),
      };
    };

    const start = (event) => {
      drawing = true;
      lastPos = getPos(event);
      state.hasDrawn = true;
    };

    const move = (event) => {
      if (!drawing) return;
      if (event.cancelable) event.preventDefault();

      const pos = getPos(event);
      ctx.beginPath();
      ctx.moveTo(lastPos.x, lastPos.y);
      ctx.lineTo(pos.x, pos.y);
      ctx.stroke();
      lastPos = pos;
    };

    const stop = () => {
      drawing = false;
    };

    canvas.addEventListener('mousedown', start);
    canvas.addEventListener('mousemove', move);
    window.addEventListener('mouseup', stop);

    canvas.addEventListener('touchstart', start, { passive: false });
    canvas.addEventListener('touchmove', move, { passive: false });
    window.addEventListener('touchend', stop);
  }

  function clearCanvas() {
    if (!ctx || !canvas) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    state.hasDrawn = false;
  }

  async function loadOrgData() {
    try {
      const response = await apiFetch('/api/admin/organization');
      state.org = response;

      el('orgNameInput', container).value = response?.name || '';
      el('orgCuitInput', container).value = response?.cuit || '';
      el('orgEmailInput', container).value = response?.email || '';
      el('orgPhoneInput', container).value = response?.phone || '';
      el('orgWebsiteInput', container).value = response?.website || '';
      el('orgActivityInput', container).value = response?.activity || '';
      el('orgAddressInput', container).value = response?.address || '';
      el('orgCityInput', container).value = response?.city || '';
      el('orgProvinceInput', container).value = response?.province || '';
      el('orgZipInput', container).value = response?.zip_code || '';
    } catch (error) {
      console.error('Error al cargar datos de organización:', error);
    }
  }

  async function saveOrgData() {
    const errorEl = el('orgDataError', container);
    hideInlineMessage(errorEl);

    const name = el('orgNameInput', container).value.trim();
    const cuit = el('orgCuitInput', container).value.trim();
    const email = el('orgEmailInput', container).value.trim();
    const phone = el('orgPhoneInput', container).value.trim();
    const website = el('orgWebsiteInput', container).value.trim();
    const activity = el('orgActivityInput', container).value.trim();
    const address = el('orgAddressInput', container).value.trim();
    const city = el('orgCityInput', container).value.trim();
    const province = el('orgProvinceInput', container).value.trim();
    const zip_code = el('orgZipInput', container).value.trim();

    if (!name || !cuit) {
      showInlineError(errorEl, 'El nombre y el CUIT son obligatorios.');
      return;
    }

    if (!/^\d{11}$/.test(cuit)) {
      showInlineError(errorEl, 'El CUIT debe tener 11 dígitos numéricos.');
      return;
    }

    const button = el('btnSaveOrgData', container);
    button.disabled = true;
    button.textContent = 'Guardando...';

    try {
      await apiFetch('/api/admin/organization', {
        method: 'PATCH',
        body: { name, cuit, email, phone, website, activity, address, city, province, zip_code },
      });

      showToast('Datos de empresa actualizados', 'success');
      await loadOrgData();
    } catch (error) {
      showInlineError(errorEl, error?.message || 'No se pudieron guardar los cambios.');
    } finally {
      button.disabled = false;
      button.textContent = 'Guardar cambios';
    }
  }

  async function loadLogo() {
    try {
      if (!state.org?.id) return;

      const url = apiUrl(`/api/organizations/${state.org.id}/logo`);
      const response = await fetch(url, { credentials: 'include' });

      if (!response.ok) return;

      const logoImg = el('logoPreviewImg', container);
      const logoEmpty = el('logoPreviewEmpty', container);

      logoImg.src = `${url}?t=${Date.now()}`;
      logoImg.classList.remove('hidden');
      logoEmpty.classList.add('hidden');
    } catch (error) {
      console.error('Error al cargar logo:', error);
    }
  }

  async function uploadLogo(event) {
    const file = event.target.files?.[0];
    if (!file) return;

    const errorEl = el('logoUploadError', container);
    const successEl = el('logoUploadSuccess', container);
    const button = el('btnSelectLogo', container);

    hideInlineMessage(errorEl);
    successEl.classList.add('hidden');

    const formData = new FormData();
    formData.append('file', file);

    button.disabled = true;
    button.textContent = 'Subiendo...';

    try {
      if (!state.org?.id) {
        throw new Error('Todavía no se pudo cargar la organización. Intentá nuevamente.');
      }

      const response = await fetch(apiUrl(`/api/organizations/${state.org.id}/logo`), {
        method: 'POST',
        credentials: 'include',
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
        body: formData,
      });

      if (!response.ok) {
        throw new Error(await response.text());
      }

      successEl.classList.remove('hidden');
      await loadLogo();

      setTimeout(() => {
        successEl.classList.add('hidden');
      }, 3000);
    } catch (error) {
      showInlineError(errorEl, error.message || 'No se pudo subir el logo.');
    } finally {
      button.disabled = false;
      button.textContent = 'Seleccionar archivo';
      event.target.value = '';
    }
  }

  async function loadSigners() {
    try {
      const response = await apiFetch('/api/company-signers');
      state.signers = response?.signers || [];
      renderSigners();
    } catch (error) {
      showToast('No se pudieron cargar los firmantes', 'error');
    }
  }

  function renderSigners() {
    const listEl = el('signersList', container);
    const emptyEl = el('signersEmpty', container);

    listEl.innerHTML = '';

    if (!state.signers.length) {
      emptyEl.innerHTML = `
        <div class="empty-state">
          <div class="empty-title">Todavía no hay firmantes cargados</div>
          <div class="empty-desc">
            Agregá al menos un responsable autorizado para firmar recibos en nombre de la empresa.
          </div>
        </div>
      `;
      emptyEl.classList.remove('hidden');
      return;
    }

    emptyEl.classList.add('hidden');

    state.signers.forEach((signer) => {
      const card = document.createElement('article');
      card.className = 'card empresa-signer-card';

      const statusClass = signer.is_active ? 'success' : 'neutral';
      const statusText = signer.is_active ? 'Activo' : 'Inactivo';

      card.innerHTML = `
        <div class="empresa-signer-card-head">
          <div>
            <div class="empresa-signer-name">${signer.name}</div>
            <div class="small-muted">${signer.position}</div>
          </div>

          <span class="badge ${statusClass}">
            ${statusText}
          </span>
        </div>

        <div class="empresa-signer-preview">
          ${
            signer.has_signature
              ? `<img src="${apiUrl(`/api/company-signers/${signer.id}/image`)}" alt="Firma de ${signer.name}" class="empresa-signer-image" />`
              : `<span class="small-muted">Sin firma guardada</span>`
          }
        </div>

        <div class="empresa-signer-actions">
          <button class="btn btn-ghost btn-sm btnToggle" data-id="${signer.id}">
            ${signer.is_active ? 'Desactivar' : 'Activar'}
          </button>

          <button class="btn btn-danger btn-sm btnDelete" data-id="${signer.id}">
            Borrar
          </button>
        </div>
      `;

      listEl.appendChild(card);
    });

    listEl.querySelectorAll('.btnToggle').forEach((button) => {
      button.addEventListener('click', async (event) => {
        const id = event.currentTarget.getAttribute('data-id');

        try {
          await apiFetch(`/api/company-signers/${id}/toggle`, { method: 'POST' });
          await loadSigners();
        } catch (error) {
          showToast('No se pudo cambiar el estado del firmante', 'error');
        }
      });
    });

    listEl.querySelectorAll('.btnDelete').forEach((button) => {
      button.addEventListener('click', async (event) => {
        const id = event.currentTarget.getAttribute('data-id');

        const ok = await confirmAction(
          '¿Querés eliminar este firmante? Los recibos ya firmados no se verán afectados.'
        );
        if (!ok) return;

        try {
          await apiFetch(`/api/company-signers/${id}`, { method: 'DELETE' });
          showToast('Firmante eliminado', 'success');
          await loadSigners();
        } catch (error) {
          showToast('No se pudo eliminar el firmante', 'error');
        }
      });
    });
  }

  async function saveSigner() {
    const errorEl = el('signerModalError', container);
    hideInlineMessage(errorEl);

    const name = el('signerName', container).value.trim();
    const position = el('signerPosition', container).value.trim();

    if (!name || !position) {
      showInlineError(errorEl, 'El nombre y el cargo son obligatorios.');
      return;
    }

    const formData = new FormData();
    formData.append('name', name);
    formData.append('position', position);

    if (state.mode === 'canvas') {
      if (!state.hasDrawn) {
        showInlineError(errorEl, 'Debés dibujar la firma.');
        return;
      }

      formData.append('signature_base64', canvas.toDataURL('image/png'));
    } else {
      const file = el('signerImage', container).files?.[0];
      if (!file) {
        showInlineError(errorEl, 'Debés seleccionar un archivo de firma.');
        return;
      }

      formData.append('signature_image', file);
    }

    const button = el('btnSaveSigner', container);
    button.disabled = true;
    button.textContent = 'Guardando...';

    try {
      const response = await fetch(apiUrl('/api/company-signers'), {
        method: 'POST',
        credentials: 'include',
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
        body: formData,
      });

      if (!response.ok) {
        throw new Error(await response.text());
      }

      showToast('Firmante creado correctamente', 'success');
      closeSignerModal();
      await loadSigners();
    } catch (error) {
      showInlineError(errorEl, `Error: ${error.message}`);
    } finally {
      button.disabled = false;
      button.textContent = 'Guardar firmante';
    }
  }

  el('btnModeCanvas', container).addEventListener('click', () => setMode('canvas'));
  el('btnModeFile', container).addEventListener('click', () => setMode('file'));
  el('btnClearSignerCanvas', container).addEventListener('click', clearCanvas);

  el('btnNewSigner', container).addEventListener('click', openSignerModal);
  el('btnCancelSigner', container).addEventListener('click', closeSignerModal);
  el('btnSaveSigner', container).addEventListener('click', saveSigner);

  el('btnSaveOrgData', container).addEventListener('click', saveOrgData);

  el('btnSelectLogo', container).addEventListener('click', () => {
    el('logoUploadInput', container).click();
  });

  el('logoUploadInput', container).addEventListener('change', uploadLogo);

  el('btnDeleteAccount', container).addEventListener('click', async () => {
    const ok = await confirmAction(
      '¿Estás seguro/a que querés eliminar tu cuenta? Esta acción es irreversible y se perderán todos los datos.'
    );
    if (!ok) return;

    try {
      await apiFetch('/api/organizations/me', { method: 'DELETE' });
      showToast('Cuenta eliminada correctamente', 'success');
      setTimeout(() => {
        window.location.href = '#/login';
      }, 1000);
    } catch (error) {
      showToast('Error al eliminar la cuenta: ' + error.message, 'error');
    }
  });

  initCanvas();
  await loadOrgData();
  await loadSigners();
  await loadLogo();
}