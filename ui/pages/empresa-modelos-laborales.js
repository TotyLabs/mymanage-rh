import { apiFetch, apiUrl, esc, getAuthToken, getMe, showError, showToast } from '../common.js';

function el(id, ctx = document) {
  return (ctx || document).querySelector(`#${id}`);
}

function getEmployeeName(employee) {
  if (!employee) return 'Sin asociar';
  return employee.full_name || `${employee.last_name || ''} ${employee.first_name || ''}`.trim() || 'Empleado';
}

function getEmployeeById(state, employeeId) {
  if (!employeeId) return null;
  return (state.employees || []).find((employee) => String(employee.id) === String(employeeId)) || null;
}

function formatStatus(status) {
  const map = {
    BORRADOR: 'Borrador',
    LISTO_PARA_FIRMAR: 'Listo para firmar',
    FIRMADO: 'Firmado',
    ENVIADO: 'Enviado',
    ELIMINADO: 'Eliminado',
  };
  return map[status] || status || 'Sin estado';
}

function canEditDocument(status) {
  return !status || ['BORRADOR', 'LISTO_PARA_FIRMAR'].includes(status);
}

function formatModelValue(value) {
  if (value === null || value === undefined || value === '') return '';
  if (typeof value === 'string') return value;
  if (typeof value === 'number') return String(value);
  return '';
}

export async function render(container) {
  const state = {
    models: [], documents: [], employees: [], organizationName: '', user: null, selectedModel: null,
  };

  container.innerHTML = `
    <style>
      .labor-models-page { color: #1e293b; }
      .labor-models-hero { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 24px; }
      .labor-models-header { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
      .development-badge { display: inline-flex; align-items: center; gap: 6px; padding: 6px 10px; border-radius: 999px; background: #fef3c7; color: #92400e; border: 1px solid #facc15; font-size: 11px; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; }
      .labor-model-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 18px; }
      .labor-model-card { display: flex; flex-direction: column; justify-content: space-between; gap: 18px; padding: 20px; border: 1px solid #e2e8f0; border-radius: 16px; background: #fff; }
      .labor-model-card-actions { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
      .labor-model-form-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; }
      .labor-model-form-grid label { display: block; font-size: 12px; color: #334155; }
      .labor-model-form-grid .input { width: 100%; margin-top: 6px; }
      .labor-tab-row { display: flex; gap: 8px; margin-bottom: 20px; }
      .tab-item.active { background: #e0f2fe; color: #075985; border-color: #7dd3fc; }
      .labor-panel-toggle { position: relative; }
      .labor-panel-toggle .btn-create-labor { width: auto; }
      .labor-panel-toggle-panel { position: relative; width: min(980px, calc(100vw - 40px)); z-index: 20; }
      .labor-form-anchor { position: relative; }
      .context-menu-wrap { position: relative; display: inline-block; }
      .context-menu { position: absolute; right: 0; top: calc(100% + 6px); background: white; border: 1px solid #e2e8f0; border-radius: 12px; box-shadow: 0 12px 30px rgba(15, 23, 42, 0.12); min-width: 184px; padding: 8px; z-index: 5; display: flex; flex-direction: column; gap: 2px; }
      .context-menu.hidden { display: none; }
      .context-menu button { width: 100%; text-align: left; border: none; background: transparent; padding: 8px 10px; border-radius: 8px; cursor: pointer; color: #1e293b; display: block; }
      .context-menu button:hover { background: #f8fafc; }
      .mini-link { display: inline-flex; align-items: center; justify-content: center; border: 1px solid #dbeafe; background: #eff6ff; color: #1d4ed8; border-radius: 999px; padding: 6px 10px; font-size: 12px; font-weight: 600; cursor: pointer; }
      .mini-link.secondary { border-color: #e2e8f0; background: #fff; color: #334155; }
      .mini-link.danger { border-color: #fecaca; background: #fff1f2; color: #be123c; }
      .mini-link:hover { opacity: 0.96; }
      .editor-modal-backdrop { position: fixed; inset: 0; background: rgba(15, 23, 42, 0.5); display: flex; align-items: center; justify-content: center; z-index: 30; }
      .editor-modal-card { width: min(1100px, 94vw); max-height: 86vh; display: flex; flex-direction: column; background: white; border-radius: 18px; overflow: hidden; box-shadow: 0 30px 80px rgba(15, 23, 42, 0.28); }
      .editor-modal-header { display: flex; justify-content: space-between; align-items: center; gap: 12px; padding: 16px 20px; border-bottom: 1px solid #e2e8f0; }
      .editor-modal-body { padding: 18px; background: #f8fafc; min-height: 420px; }
      .editor-modal-body iframe { width: 100%; height: 70vh; border: 1px solid #dfe7f3; border-radius: 12px; background: white; }
      .editor-note { margin-top: 12px; color: #475569; font-size: 13px; }
      .pdf-actions { display: flex; gap: 8px; }
      .table-actions { display: inline-flex; flex-direction: column; gap: 8px; align-items: stretch; }
      .context-menu-wrap { position: relative; display: block; }
      .menu-trigger { border: 1px solid #e2e8f0; border-radius: 10px; background: white; width: 100%; min-width: 30px; height: 30px; display: inline-flex; align-items: center; justify-content: center; cursor: pointer; }
      .menu-trigger:hover { background: #f8fafc; }
      .variable-editor-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; }
      .variable-field { display: flex; flex-direction: column; gap: 6px; }
      .variable-field input, .variable-field textarea { width: 100%; }
      .labor-expand-panel { overflow: hidden; transition: max-height 0.25s ease, opacity 0.2s ease; max-height: 0; opacity: 0; }
      .labor-expand-panel.is-open { max-height: 1200px; opacity: 1; }
      .labor-inline-editor { margin-top: 18px; background: #f8fafc; border: 1px solid #dfe7f3; border-radius: 14px; padding: 18px; }
      .labor-inline-editor .pdf-actions { margin-top: 18px; }
      .labor-inline-editor .variable-editor-grid { margin-top: 0; }
      .labor-email-backdrop { position: fixed; inset: 0; z-index: 40; display: flex; align-items: center; justify-content: center; padding: 16px; background: rgba(15, 23, 42, 0.52); }
      .labor-email-card { width: min(480px, 100%); background: #fff; border-radius: 12px; box-shadow: 0 24px 64px rgba(15, 23, 42, 0.25); }
      .labor-email-header, .labor-email-footer { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 16px 20px; border-bottom: 1px solid #e2e8f0; }
      .labor-email-body { display: grid; gap: 16px; padding: 20px; }
      .labor-email-footer { justify-content: flex-end; border-top: 1px solid #e2e8f0; border-bottom: 0; }
      .labor-sign-confirm-backdrop { position: fixed; inset: 0; z-index: 45; display: flex; align-items: center; justify-content: center; padding: 16px; background: rgba(15, 23, 42, 0.52); }
      .labor-sign-confirm-card { width: min(480px, 100%); background: #fff; border-radius: 12px; box-shadow: 0 24px 64px rgba(15, 23, 42, 0.25); }
      .labor-sign-confirm-body { padding: 20px; color: #475569; line-height: 1.6; }
    </style>

    <section class="labor-models-page">
      <div class="labor-models-hero">
        <div class="labor-models-header">
          <h1 class="card-title empresa-page-title mb-8">Modelos Laborales</h1>
        </div>
        <button id="btnLaborRefresh" class="btn btn-ghost btn-sm">Actualizar</button>
      </div>

      <div class="labor-tab-row tabs">
        <button class="tab-item active" data-labor-tab="library">Biblioteca</button>
        <button class="tab-item" data-labor-tab="history">Historial</button>
      </div>

      <div id="laborLibraryView"></div>
      <div id="laborHistoryView" class="hidden"></div>
    </section>
  `;

  async function load() {
    try {
      const me = await getMe();
      state.user = me?.user || me;
      state.organizationName = state.user?.organization_name || '';
      await Promise.all([
        loadModels(),
        loadDocuments(),
        loadEmployees(),
      ]);
      renderLibrary();
      renderHistory();
    } catch (error) {
      showError(el('laborLibraryView', container), error);
    }
  }

  async function loadModels() {
    const response = await apiFetch('/api/labor-models/catalog');
    state.models = response.models || [];
  }

  async function loadDocuments() {
    const response = await apiFetch('/api/labor-models/documents');
    state.documents = response.documents || [];
  }

  async function loadEmployees() {
    const response = await apiFetch('/api/employees?limit=200');
    state.employees = response.employees || [];
  }

  function renderLibrary() {
    const view = el('laborLibraryView', container);
    const groupedModels = (state.models.length ? state.models : []).reduce((groups, model) => {
      const category = (model.category || 'General').trim() || 'General';
      if (!groups[category]) groups[category] = [];
      groups[category].push(model);
      return groups;
    }, {});

    const cardsHtmlByCategory = Object.entries(groupedModels).map(([category, models]) => `
      <section class="mb-24">
        <div class="section-label mb-12">${esc(category)}</div>
        <div class="labor-model-grid">
          ${models.map((model) => `
            <article class="labor-model-card">
              <div>
                <div class="small-muted font-mono mb-8">${esc(model.code)}</div>
                <h2 class="card-title mb-8">${esc(model.title)}</h2>
                <div class="small-muted mb-8">${esc(model.model_label || 'Modelo estándar')}</div>
                <p class="small-muted">${esc(model.description || 'Modelo legal disponible para generar el PDF')}</p>
              </div>
              <div class="labor-model-card-actions">
                <button class="btn btn-ghost btn-sm btn-download-template" data-code="${esc(model.code)}">Descargar plantilla</button>
                <button class="btn btn-primary btn-sm btn-create-labor" data-code="${esc(model.code)}">Nuevo documento</button>
              </div>
            </article>
          `).join('')}
        </div>
      </section>
    `).join('');

    const formHtml = state.models.length ? `
      <div class="labor-form-anchor">
        <section id="laborGenerateFormSection" class="card mb-24 p-24 labor-expand-panel hidden labor-panel-toggle-panel">
          <div class="section-label mb-12">Nuevo documento</div>
          <h2 id="laborCreateTitle" class="card-title mb-8"></h2>
          <p id="laborCreateDescription" class="small-muted mb-20"></p>
          <div class="labor-model-form-grid mb-20">
            <label>
              Empleado (opcional para completar desde legajo)
              <select id="laborCreateEmployee" class="input">
                <option value="">Completar datos manualmente</option>
                ${state.employees.map((employee) => `<option value="${esc(employee.id)}">${esc(getEmployeeName(employee))} · ${esc(employee.dni || employee.cuil || '')}</option>`).join('')}
              </select>
            </label>
          </div>
          <div id="laborCreateFields" class="labor-model-form-grid"></div>
          <div class="mt-20" style="display:flex; gap:12px; flex-wrap:wrap;">
            <button id="btnGenerateLaborDocument" class="btn btn-primary">Generar documento</button>
          </div>
        </section>
      </div>
    ` : '<div class="empty-state">No hay modelos disponibles.</div>';

    view.innerHTML = `
      ${state.models.length ? `
        <section class="card mb-24 p-24">
          <div class="section-label mb-12">Biblioteca</div>
          ${cardsHtmlByCategory}
        </section>
      ` : ''}
      ${formHtml}
    `;

    const toggleForm = () => {
      const section = el('laborGenerateFormSection', container);
      const isHidden = section.classList.contains('hidden');
      section.classList.toggle('hidden', !isHidden);
      section.classList.toggle('is-open', isHidden);
      if (isHidden) section.scrollIntoView({ behavior: 'smooth', block: 'start' });
    };

    const openModelForm = (model) => {
      state.selectedModel = model;
      el('laborCreateTitle', container).textContent = model.title;
      el('laborCreateDescription', container).textContent = `${model.model_label || ''} · ${model.code} · Los campos con * son obligatorios.`;
      el('laborCreateFields', container).innerHTML = model.fields.map((field) => {
        const sourceValue = getInitialFieldValue(field);
        const control = field.options?.length
          ? `<select class="input" data-model-field="${esc(field.key)}" ${field.required ? 'required' : ''}>${field.options.map((option) => `<option value="${esc(option)}">${esc(option)}</option>`).join('')}</select>`
          : `<input class="input" data-model-field="${esc(field.key)}" type="${field.input_type || 'text'}" value="${esc(sourceValue)}" ${field.required ? 'required' : ''}>`;
        return `<label class="variable-field"><span>${esc(field.label)}${field.required ? ' *' : ''}</span>${control}</label>`;
      }).join('');
      el('laborGenerateFormSection', container).classList.remove('hidden');
      el('laborGenerateFormSection', container).classList.add('is-open');
      el('laborGenerateFormSection', container).scrollIntoView({ behavior: 'smooth', block: 'start' });
    };

    view.querySelectorAll('.btn-download-template').forEach((button) => {
      button.onclick = () => downloadBaseTemplate(button.dataset.code);
    });
    view.querySelectorAll('.btn-create-labor').forEach((button) => {
      button.onclick = () => {
        const model = state.models.find((item) => item.code === button.dataset.code);
        if (model) openModelForm(model);
      };
    });

    el('laborCreateEmployee', container).onchange = (event) => prefillFromEmployee(event.target.value);
    el('btnGenerateLaborDocument', container).onclick = () => {
      if (state.selectedModel) generateFromCode(state.selectedModel.code);
    };
  }

  function renderHistory() {
    const view = el('laborHistoryView', container);
    const docs = state.documents.filter((doc) => doc.status !== 'ELIMINADO');
    const historyHeader = `
      <div class="labor-models-header mb-16">
        <h2 class="card-title">Historial</h2>
        <span class="development-badge">Sección en desarrollo</span>
      </div>
    `;

    if (!docs.length) {
      view.innerHTML = `${historyHeader}<div class="empty-state">Todavía no hay documentos laborales en historial.</div>`;
      return;
    }

    view.innerHTML = `
      ${historyHeader}
      <div class="table-container">
        <table class="table">
          <thead>
            <tr>
              <th>Documento</th>
              <th>Empleado</th>
              <th>Estado</th>
              <th>Modificado</th>
              <th>Acciones</th>
            </tr>
          </thead>
          <tbody>
            ${docs.map((doc) => {
              const employee = getEmployeeById(state, doc.employee_id);
              const canEdit = canEditDocument(doc.status);
              return `
                <tr>
                  <td>
                    <strong>${esc(doc.title || 'Documento laboral')}</strong>
                    <div class="small-muted">${esc(doc.template_code || 'TLG-INT-001')}</div>
                  </td>
                  <td>${esc(getEmployeeName(employee))}</td>
                  <td>${esc(formatStatus(doc.status))}</td>
                  <td>${esc(doc.updated_at || doc.created_at || '')}</td>
                  <td>
                    <div class="table-actions">
                      <button class="mini-link danger btn-history-delete" data-id="${esc(doc.id)}">Eliminar</button>
                      <div class="context-menu-wrap">
                        <button class="menu-trigger" data-menu-trigger="${esc(doc.id)}" aria-label="Más acciones">⋯</button>
                        <div class="context-menu hidden" data-menu-panel="${esc(doc.id)}">
                          <button data-doc-action="view" data-id="${esc(doc.id)}">Ver PDF</button>
                          <button data-doc-action="download" data-id="${esc(doc.id)}">Descargar PDF</button>
                          ${doc.status === 'LISTO_PARA_FIRMAR' && doc.rendered_pdf_path ? `<button data-doc-action="sign" data-id="${esc(doc.id)}">Firmar Documento</button>` : ''}
                          <button data-doc-action="email" data-id="${esc(doc.id)}">Enviar por correo</button>
                          <button data-doc-action="info" data-id="${esc(doc.id)}">Información del documento</button>
                        </div>
                      </div>
                    </div>
                  </td>
                </tr>
              `;
            }).join('')}
          </tbody>
        </table>
      </div>
    `;

    bindHistoryActions(view);
  }

  function bindHistoryActions(view) {
    view.querySelectorAll('.btn-history-delete').forEach((button) => {
      button.onclick = () => deleteDocument(button.dataset.id);
    });

    view.querySelectorAll('.btn-history-view').forEach((button) => {
      button.onclick = () => openPdf(button.dataset.id);
    });

    view.querySelectorAll('[data-menu-trigger]').forEach((button) => {
      button.onclick = (event) => {
        event.stopPropagation();
        const panel = view.querySelector(`[data-menu-panel="${button.dataset.menuTrigger}"]`);
        if (!panel) return;
        const isHidden = panel.classList.contains('hidden');
        view.querySelectorAll('[data-menu-panel]').forEach((item) => item.classList.add('hidden'));
        if (isHidden) panel.classList.remove('hidden');
      };
    });

    document.addEventListener('click', (event) => {
      if (!event.target.closest('[data-menu-trigger]') && !event.target.closest('[data-menu-panel]')) {
        view.querySelectorAll('[data-menu-panel]').forEach((item) => item.classList.add('hidden'));
      }
    });

    view.querySelectorAll('[data-doc-action]').forEach((button) => {
      button.onclick = () => {
        const id = button.dataset.id;
        const action = button.dataset.docAction;
        if (action === 'view') openPdf(id, false);
        if (action === 'download') openPdf(id, true);
        if (action === 'info') showDocumentInfo(id);
        if (action === 'delete') deleteDocument(id);
        if (action === 'sign') showSignConfirmation(id);
        if (action === 'email') showEmailRecipientDialog(id);
      };
    });
  }

  function showSignConfirmation(documentId) {
    const doc = state.documents.find((item) => item.id === documentId);
    if (!doc || doc.status !== 'LISTO_PARA_FIRMAR' || !doc.rendered_pdf_path) {
      showToast('El documento no está listo para firmar.', 'error');
      return;
    }

    const modal = document.createElement('div');
    modal.className = 'labor-sign-confirm-backdrop';
    modal.innerHTML = `
      <section class="labor-sign-confirm-card" role="dialog" aria-modal="true" aria-labelledby="laborSignConfirmTitle">
        <form>
          <header class="labor-email-header">
            <h2 id="laborSignConfirmTitle" class="card-title">Confirmar firma</h2>
          </header>
          <div class="labor-sign-confirm-body">
            <p>¿Estás seguro de que querés firmar este documento?</p>
            <p>Se aplicarán la firma digital y el sello al PDF actual. No se volverá a generar.</p>
            <strong>${esc(doc.title || 'Documento laboral')}</strong>
          </div>
          <footer class="labor-email-footer">
            <button type="button" class="btn btn-ghost" data-sign-cancel>Volver</button>
            <button type="submit" class="btn btn-primary">Firmar Documento</button>
          </footer>
        </form>
      </section>
    `;
    document.body.appendChild(modal);

    const form = modal.querySelector('form');
    const close = () => modal.remove();
    modal.querySelector('[data-sign-cancel]').addEventListener('click', close);
    modal.addEventListener('click', (event) => {
      if (event.target === modal) close();
    });
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const submit = form.querySelector('[type="submit"]');
      submit.disabled = true;
      try {
        const result = await apiFetch(`/api/labor-models/documents/${documentId}/sign`, { method: 'POST' });
        state.documents = state.documents.map((item) => item.id === documentId ? result.document : item);
        close();
        renderHistory();
        showToast('Documento firmado y sellado correctamente.', 'success');
      } catch (error) {
        showToast(error?.detail || 'No se pudo firmar el documento.', 'error');
      } finally {
        if (submit.isConnected) submit.disabled = false;
      }
    });
  }

  function showEmailRecipientDialog(documentId) {
    const modal = document.createElement('div');
    modal.className = 'labor-email-backdrop';
    modal.innerHTML = `
      <section class="labor-email-card" role="dialog" aria-modal="true" aria-labelledby="laborEmailTitle">
        <form>
          <header class="labor-email-header">
            <h2 id="laborEmailTitle" class="card-title">Seleccionar Destinatario</h2>
            <button type="button" class="btn btn-ghost btn-sm" data-email-close aria-label="Cerrar">Cerrar</button>
          </header>
          <div class="labor-email-body">
            <label class="variable-field">
              <span>Destinatario</span>
              <select class="input" name="recipient_type">
                <option value="employee">Elegir Empleado</option>
                <option value="other">Seleccionar Otro Destinatario</option>
              </select>
            </label>
            <label class="variable-field" data-employee-recipient>
              <span>Empleado de la empresa</span>
              <select class="input" name="employee_id">
                <option value="">Seleccionar empleado</option>
                ${state.employees.map((employee) => `<option value="${esc(employee.id)}" ${employee.email ? '' : 'disabled'}>${esc(getEmployeeName(employee))}${employee.email ? ` · ${esc(employee.email)}` : ' · Sin correo'}</option>`).join('')}
              </select>
            </label>
            <label class="variable-field hidden" data-other-recipient>
              <span>Correo electrónico</span>
              <input class="input" name="recipient_email" type="email" autocomplete="email" placeholder="nombre@empresa.com">
            </label>
          </div>
          <footer class="labor-email-footer">
            <button type="button" class="btn btn-ghost" data-email-close>Cancelar</button>
            <button type="submit" class="btn btn-primary">Enviar Correo</button>
          </footer>
        </form>
      </section>
    `;
    document.body.appendChild(modal);

    const form = modal.querySelector('form');
    const recipientType = form.elements.recipient_type;
    const employeeField = modal.querySelector('[data-employee-recipient]');
    const otherField = modal.querySelector('[data-other-recipient]');
    const close = () => modal.remove();
    const syncRecipientFields = () => {
      const isEmployee = recipientType.value === 'employee';
      employeeField.classList.toggle('hidden', !isEmployee);
      otherField.classList.toggle('hidden', isEmployee);
      form.elements.employee_id.required = isEmployee;
      form.elements.recipient_email.required = !isEmployee;
    };
    recipientType.addEventListener('change', syncRecipientFields);
    syncRecipientFields();
    modal.querySelectorAll('[data-email-close]').forEach((button) => button.addEventListener('click', close));
    modal.addEventListener('click', (event) => {
      if (event.target === modal) close();
    });

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const submit = form.querySelector('[type="submit"]');
      submit.disabled = true;
      try {
        await ensureDocumentRendered(documentId);
        const payload = recipientType.value === 'employee'
          ? { employee_id: form.elements.employee_id.value }
          : { recipient_email: form.elements.recipient_email.value.trim() };
        const result = await apiFetch(`/api/labor-models/documents/${documentId}/email`, {
          method: 'POST',
          body: payload,
        });
        close();
        showToast(`Correo enviado a ${result.recipient_email}`, 'success');
      } catch (error) {
        showToast(error?.detail || 'No se pudo enviar el correo.', 'error');
      } finally {
        if (submit.isConnected) submit.disabled = false;
      }
    });
  }

  function showDocumentInfo(id) {
    const document = state.documents.find((item) => item.id === id);
    if (!document) {
      showToast('Documento no encontrado', 'error');
      return;
    }
    showToast(`Documento: ${document.title || 'Modelo legal'} · Estado: ${formatStatus(document.status)}`, 'success');
  }

  async function ensureDocumentRendered(id) {
    const doc = state.documents.find((item) => item.id === id);
    if (!doc) return null;
    if (doc.rendered_pdf_path || doc.final_pdf_path) return doc;
    const rendered = await apiFetch(`/api/labor-models/documents/${id}/render`, { method: 'POST' });
    const refreshed = await apiFetch(`/api/labor-models/documents/${id}`);
    state.documents = state.documents.map((item) => item.id === id ? refreshed : item);
    return refreshed;
  }

  async function openPdf(id, download = false) {
    try {
      await ensureDocumentRendered(id);
      const url = `/api/labor-models/documents/${id}/download`;
      if (download) {
        window.location.href = url;
        return;
      }
      window.open(url, '_blank');
    } catch (error) {
      showToast(error?.detail || 'No se pudo abrir el PDF generado.', 'error');
    }
  }

  async function deleteDocument(id) {
    const doc = state.documents.find((item) => item.id === id);
    const label = doc?.title || 'este documento';
    const confirmed = window.confirm(`¿Eliminar ${label}? Esta operación marca el documento como eliminado y no lo vuelve a mostrar en el historial.`);
    if (!confirmed) return;

    try {
      await apiFetch(`/api/labor-models/documents/${id}`, { method: 'DELETE' });
      state.documents = state.documents.filter((item) => item.id !== id);
      renderHistory();
      showToast('Documento eliminado', 'success');
    } catch (error) {
      showToast(error.detail || 'No se pudo eliminar el documento', 'error');
    }
  }

  function renderInlineVariableEditor(doc, focusMissing = []) {
    const model = state.models.find((item) => item.code === doc.template_code) || state.models[0];
    const availableFields = (model?.fields || []).map((field) => ({
      ...field,
      value: doc.fields?.[field.key] ?? '',
      required: Boolean(field.required),
    }));

    const inline = container.querySelector('#laborInlineVariableEditor');
    if (!inline) return;

    inline.classList.remove('hidden');
    inline.innerHTML = `
      <div class="section-label mb-12">Completar variables</div>
      <div class="variable-editor-grid mb-20">
        ${availableFields.map((field) => `
          <label class="variable-field">
            <span>${esc(field.label || field.key)}${field.required ? ' *' : ''}</span>
            <input class="input" name="${esc(field.key)}" value="${esc(field.value || '')}" placeholder="${esc(field.label || field.key)}" ${focusMissing.includes(field.key) ? 'style="border-color:#f59e0b;"' : ''}>
          </label>
        `).join('')}
      </div>
      <div class="pdf-actions">
        <button type="button" class="btn btn-primary btn-sm" data-inline-save="${esc(doc.id)}">Guardar variables</button>
        <button type="button" class="btn btn-ghost btn-sm" data-inline-cancel="${esc(doc.id)}">Cancelar</button>
      </div>
    `;

    inline.querySelector('[data-inline-save]').addEventListener('click', async () => {
      const payload = {};
      inline.querySelectorAll('input[name]').forEach((input) => {
        payload[input.name] = input.value;
      });

      try {
        await apiFetch(`/api/labor-models/documents/${doc.id}`, {
          method: 'PATCH',
          body: { fields: payload },
        });
        const refreshed = await apiFetch(`/api/labor-models/documents/${doc.id}`);
        state.documents = state.documents.map((item) => item.id === doc.id ? refreshed : item);
        renderHistory();
        inline.classList.add('hidden');
        showToast('Variables actualizadas', 'success');
      } catch (error) {
        showToast(error?.detail || 'No se pudieron guardar las variables', 'error');
      }
    });

    inline.querySelector('[data-inline-cancel]').addEventListener('click', () => {
      inline.classList.add('hidden');
    });
  }

  async function openVariableEditor(id, focusMissing = []) {
    const doc = state.documents.find((item) => item.id === id);
    if (!doc) return;

    const model = state.models.find((item) => item.code === doc.template_code) || state.models[0];
    const availableFields = (model?.fields || []).map((field) => ({
      ...field,
      value: doc.fields?.[field.key] ?? '',
      required: Boolean(field.required),
    }));

    const inline = container.querySelector('#laborInlineVariableEditor');
    if (inline) {
      renderInlineVariableEditor(doc, focusMissing);
      return;
    }

    const modal = document.createElement('div');
    modal.className = 'editor-modal-backdrop';
    modal.innerHTML = `
      <div class="editor-modal-card">
        <div class="editor-modal-header">
          <div>
            <strong>Completar variables</strong>
            <div class="small-muted">${esc(doc.title || 'Documento laboral')}</div>
          </div>
          <button class="btn btn-ghost btn-sm" type="button" data-editor-close="close">Cerrar</button>
        </div>
        <div class="editor-modal-body">
          <form id="laborVariableEditorForm">
            <div class="variable-editor-grid mb-20">
              ${availableFields.map((field) => `
                <label class="variable-field">
                  <span>${esc(field.label || field.key)}${field.required ? ' *' : ''}</span>
                  <input class="input" name="${esc(field.key)}" value="${esc(field.value || '')}" placeholder="${esc(field.label || field.key)}" ${focusMissing.includes(field.key) ? 'style="border-color:#f59e0b;"' : ''}>
                </label>
              `).join('')}
            </div>
            <div class="pdf-actions">
              <button type="submit" class="btn btn-primary btn-sm">Guardar variables</button>
              <button type="button" class="btn btn-ghost btn-sm" data-editor-close="close">Cancelar</button>
            </div>
          </form>
        </div>
      </div>
    `;

    document.body.appendChild(modal);
    const form = modal.querySelector('#laborVariableEditorForm');
    const closeModal = () => modal.remove();

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const payload = {};
      const formData = new FormData(form);
      for (const [key, value] of formData.entries()) {
        payload[key] = value;
      }

      try {
        await apiFetch(`/api/labor-models/documents/${id}`, {
          method: 'PATCH',
          body: { fields: payload },
        });
        const refreshed = await apiFetch(`/api/labor-models/documents/${id}`);
        state.documents = state.documents.map((item) => item.id === id ? refreshed : item);
        renderHistory();
        showToast('Variables actualizadas', 'success');
        closeModal();
      } catch (error) {
        showToast(error?.detail || 'No se pudieron guardar las variables', 'error');
      }
    });

    modal.querySelectorAll('[data-editor-close]').forEach((button) => {
      button.addEventListener('click', closeModal);
    });
  }

  function getInitialFieldValue(field) {
    const today = new Date();
    const sourceValues = {
      'organization.name': state.organizationName,
      'organization.cuit': state.user?.organization_cuit || state.user?.cuit || '',
      'organization.city': state.user?.organization_city || state.user?.city || '',
      'organization.province': state.user?.organization_province || state.user?.province || '',
      'system.today': today.toISOString().slice(0, 10),
      'system.day': String(today.getDate()).padStart(2, '0'),
      'system.month_name': today.toLocaleDateString('es-AR', { month: 'long' }),
      'system.year': String(today.getFullYear()),
    };
    return formatModelValue(sourceValues[field.source] ?? field.default ?? '');
  }

  async function downloadBaseTemplate(code) {
    const model = state.models.find((item) => item.code === code);
    if (!model) return;
    try {
      const token = getAuthToken();
      const response = await fetch(apiUrl(`/api/labor-models/catalog/${encodeURIComponent(code)}/download`), {
        credentials: 'include',
        headers: {
          'X-Requested-With': 'XMLHttpRequest',
          ...(token ? { Authorization: `Bearer ${token}`, 'X-Session-Token': token } : {}),
        },
      });
      if (!response.ok) throw new Error('No se pudo descargar la plantilla base.');
      const blob = await response.blob();
      const objectUrl = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = objectUrl;
      link.download = model.template_filename || `${code}.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(objectUrl);
    } catch (error) {
      showToast(error?.detail || error.message || 'No se pudo descargar la plantilla base.', 'error');
    }
  }

  async function prefillFromEmployee(employeeId) {
    if (!employeeId || !state.selectedModel) return;
    try {
      const response = await apiFetch(`/api/employees/${employeeId}`);
      const employee = response.employee || response;
      const address = [
        employee.address,
        employee.address_number,
        [employee.city, employee.province].filter(Boolean).join(', '),
        employee.postal_code ? `CP ${employee.postal_code}` : '',
      ].filter(Boolean).join(', ');
      const sourceValues = {
        'employee.full_name': employee.full_name || getEmployeeName(employee),
        'employee.dni': employee.dni,
        'employee.cuil': employee.cuil,
        'employee.cuil_or_dni': employee.cuil || employee.dni,
        'employee.address': address,
        'employee.city': employee.city,
        'employee.province': employee.province,
        'employee.nationality': employee.nationality,
        'employee.age': employee.birth_date ? String(new Date().getFullYear() - new Date(employee.birth_date).getFullYear()) : '',
        'employee.file_number': employee.file_number,
        'employee.job_title': employee.job_title,
        'employee.category': employee.category,
        'employee.task': employee.task,
        'employee.union_agreement': employee.union_agreement,
        'employee.marital_status': employee.marital_status,
      };
      state.selectedModel.fields.forEach((field) => {
        if (!field.source || !(field.source in sourceValues)) return;
        const input = container.querySelector(`[data-model-field="${CSS.escape(field.key)}"]`);
        if (input && sourceValues[field.source]) input.value = sourceValues[field.source];
      });
    } catch (error) {
      showToast(error?.detail || 'No se pudieron cargar los datos del empleado.', 'error');
    }
  }

  async function generateFromCode(templateCode) {
    const model = state.models.find((item) => item.code === templateCode);
    if (!model) return;
    const fieldsContainer = el('laborCreateFields', container);
    const requiredFields = Array.from(fieldsContainer.querySelectorAll('[required]'));
    const invalid = requiredFields.find((input) => !input.value.trim());
    if (invalid) {
      invalid.reportValidity();
      invalid.focus();
      return;
    }

    const employeeId = el('laborCreateEmployee', container).value || null;
    const fieldValues = {};
    fieldsContainer.querySelectorAll('[data-model-field]').forEach((input) => {
      fieldValues[input.dataset.modelField] = input.value.trim();
    });
    const button = el('btnGenerateLaborDocument', container);
    button.disabled = true;
    try {
      const created = await apiFetch('/api/labor-models/documents', {
        method: 'POST',
        body: { template_code: model.code, employee_id: employeeId },
      });
      const patched = await apiFetch(`/api/labor-models/documents/${created.id}`, {
        method: 'PATCH',
        body: { fields: fieldValues },
      });
      try {
        await apiFetch(`/api/labor-models/documents/${patched.id}/render`, { method: 'POST' });
      } catch (error) {
        const details = error?.detail;
        const missingFields = Array.isArray(details?.fields) ? details.fields : [];
        if (missingFields.length) {
          const refreshed = await apiFetch(`/api/labor-models/documents/${patched.id}`);
          state.documents = [refreshed, ...state.documents.filter((doc) => doc.id !== refreshed.id)];
          renderHistory();
          openVariableEditor(refreshed.id, missingFields);
          showToast('Completá los campos obligatorios para generar el documento.', 'warning');
          return;
        }
        throw error;
      }

      const refreshed = await apiFetch(`/api/labor-models/documents/${created.id}`);
      state.documents = [refreshed, ...state.documents.filter((doc) => doc.id !== refreshed.id)];
      renderHistory();
      container.querySelector('[data-labor-tab="history"]')?.click();
      showToast('Documento generado y guardado en Historial.', 'success');
      window.open(`/api/labor-models/documents/${refreshed.id}/download`, '_blank', 'noopener');
    } catch (error) {
      showToast(error?.detail || 'No se pudo generar el documento.', 'error');
    } finally {
      button.disabled = false;
    }
  }

  container.querySelectorAll('[data-labor-tab]').forEach((tab) => {
    tab.onclick = () => {
      container.querySelectorAll('[data-labor-tab]').forEach((item) => item.classList.toggle('active', item === tab));
      const isLibrary = tab.dataset.laborTab === 'library';
      el('laborLibraryView', container).classList.toggle('hidden', !isLibrary);
      el('laborHistoryView', container).classList.toggle('hidden', isLibrary);
    };
  });

  el('btnLaborRefresh', container)?.addEventListener('click', () => load());

  try {
    await load();
  } catch (error) {
    showError(container, error);
  }
}
