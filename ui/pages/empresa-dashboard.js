import {
  apiFetch,
  apiUrl,
  showError,
  showToast,
  getMe,
  confirmAction,
  getApiBase,
} from '../common.js';
const RECEIPT_PREVIEW_LIMIT = 10;

function el(id, ctx = document) {
  return (ctx || document).querySelector(`#${id}`);
}

function createStatusBadge(status, rejectionReason) {
  const badge = document.createElement('span');
  badge.className = 'badge';

  if (!status) {
    badge.classList.add('neutral');
    badge.textContent = 'Sin estado';
    return badge;
  }

  if (status === 'pending_employee_signature') {
    badge.classList.add('warning');
    badge.textContent = 'Pendiente firma empleado';
    return badge;
  }

  if (status === 'pending_employer_signature') {
    badge.classList.add('warning');
    badge.textContent = 'Pendiente firma empresa';
    return badge;
  }

  if (status === 'signed') {
    badge.classList.add('success');
    badge.textContent = 'Completado';
    return badge;
  }

  badge.classList.add('neutral');
  badge.textContent = status.replace(/_/g, ' ');
  return badge;
}

function renderKpiCard(label, value, filterValue, isActive = false) {
  return `
    <div class="kpi-card empresa-kpi-card ${isActive ? 'active' : ''}" 
         data-filter="${filterValue || ''}" 
         style="cursor: pointer; transition: all 0.2s ease;">
      <div class="kpi-label">${label}</div>
      <div class="kpi-value tabular-nums">${value}</div>
    </div>
  `;
}

function renderEmptyReceipts() {
  return `
    <div class="empty-state">
      <div class="empty-title">Todavía no hay recibos para mostrar</div>
      <div class="empty-desc">
        No hay registros disponibles con los filtros actuales. Podés cargar un lote nuevo para comenzar.
      </div>
      <button id="btnEmptyUpload" class="btn btn-primary mt-16">Subir lote de nómina</button>
    </div>
  `;
}

function buildShell() {
  return `
    <section class="empresa-dashboard-shell">
      <!-- Top Action Bar -->
      <div class="flex items-center justify-between mb-32 pb-20 border-b border-slate-100">
        <div class="flex items-center gap-12">
          <div id="orgLogo" class="empresa-logo-container" style="width: 36px; height: 36px; border-radius: 10px; background: var(--brand-50); border-color: var(--brand-100);"></div>
          <h1 class="text-2xl font-black text-slate-900 tracking-tight" style="margin:0">Panel de Control</h1>
        </div>
        
        <div class="flex items-center gap-24">
          <div id="orgInfo" class="text-[11px] text-slate-400 font-bold uppercase tracking-widest"></div>
          <div class="flex items-center gap-12 bg-slate-50/50 p-6 rounded-xl border border-slate-100">
            <input id="searchInput" class="input text-xs px-16 py-8 bg-white border-slate-200 shadow-sm" placeholder="Buscar por DNI..." style="width: 160px; min-height: 36px;" />
            <button id="btnNewBatch" class="btn btn-primary text-xs py-8 px-20 shadow-md font-bold" style="min-height: 36px;">Subir recibos</button>
          </div>
        </div>
      </div>

      <!-- Integrated Dashboard Hub -->
      <div class="flex flex-col lg:flex-row gap-32 items-stretch mb-32">
        
        <!-- KPIs Sub-grid -->
        <div class="grid grid-cols-2 gap-16 lg:w-auto">
          <div class="card p-20 bg-white border-slate-100 shadow-sm hover:shadow-md transition-all flex flex-col justify-center" style="min-width: 170px; min-height: 100px;">
              <div class="text-[11px] font-black text-slate-400 uppercase tracking-widest mb-6">Pendientes</div>
              <div class="text-3xl font-black text-slate-900 tabular-nums" id="stat-pending">0</div>
          </div>
          <div class="card p-20 bg-white border-slate-100 shadow-sm hover:shadow-md transition-all flex flex-col justify-center" style="min-width: 170px; min-height: 100px;">
              <div class="text-[11px] font-black text-slate-400 uppercase tracking-widest mb-6">Completados</div>
              <div class="text-3xl font-black text-slate-900 tabular-nums" id="stat-completed">0</div>
          </div>
          <div class="card p-20 bg-white border-slate-100 shadow-sm hover:shadow-md transition-all flex flex-col justify-center cursor-pointer group" onclick="location.hash='#/empresa/notificaciones'" style="min-width: 170px; min-height: 100px;">
              <div class="flex justify-between items-start">
                  <div class="text-[11px] font-black text-slate-400 uppercase tracking-widest mb-6 group-hover:text-blue-600 transition-colors">Mensajes</div>
                  <div id="notif-dot" class="unread-dot hidden" style="width: 8px; height: 8px; border: 2px solid white;"></div>
              </div>
              <div class="text-3xl font-black text-slate-900 tabular-nums" id="stat-notifications">0</div>
          </div>
          <div class="card p-20 bg-white border-slate-100 shadow-sm hover:shadow-md transition-all flex flex-col justify-center" style="min-width: 170px; min-height: 100px;">
              <div class="text-[11px] font-black text-slate-400 uppercase tracking-widest mb-6">Total Nómina</div>
              <div class="text-3xl font-black text-slate-900 tabular-nums" id="stat-total">0</div>
          </div>
        </div>

        <!-- Recent Messages Hub -->
        <div class="card p-0 bg-white border-slate-100 shadow-sm flex flex-col flex-1 lg:max-w-[400px] overflow-hidden" id="notif-widget-container">
          <div class="flex justify-between items-center px-20 py-12 bg-slate-50/80 border-b border-slate-100">
              <h3 class="text-[11px] font-black uppercase tracking-[0.2em] text-slate-500">Mensajes Recientes</h3>
              <a href="#/empresa/notificaciones" class="text-[11px] font-bold text-blue-600 hover:text-blue-700 transition-colors">VER TODO</a>
          </div>
          <div id="notif-widget-list" class="flex flex-col p-12 overflow-y-auto" style="max-height: 160px; flex: 1;">
              <div class="small-muted py-32 text-center text-xs italic text-slate-400">Cargando actualizaciones...</div>
          </div>
        </div>
      </div>


      <section class="card empresa-table-card">
        <div class="flex-between empresa-table-header">
          <h2 class="card-title">Recibos digitales</h2>

          <div class="flex-center gap-12 empresa-table-filters">
            <select id="filterStatus" class="input input-auto empresa-filter-select">
              <option value="">Todos los registros</option>
              <option value="pending_employee_signature">Pendiente firma empleado</option>
              <option value="pending_employer_signature">Pendiente firma empresa</option>
              <option value="signed">Completado</option>
            </select>

            <button id="btnRefresh" class="btn btn-ghost btn-sm">Actualizar</button>
          </div>
        </div>

        <div id="receiptsEmpty" class="hidden"></div>

        <div id="receiptsTableWrap" class="table-container empresa-table-wrap">
          <div id="bulkActions" class="empresa-bulk-bar hidden">
            <span id="selectedCount" class="small-muted empresa-bulk-count"></span>

            <div class="flex items-center gap-12">
              <button id="btnBulkSign" class="btn btn-sm btn-primary">Firmar lote</button>
              <button id="btnBulkDelete" class="btn btn-sm btn-danger">Eliminar lote</button>
            </div>
          </div>

          <table id="receiptsTable" class="table">
            <thead>
              <tr>
                <th class="empresa-check-col">
                  <input type="checkbox" id="selectAllReceipts" />
                </th>
                <th class="sortable" data-sort="full_name">Empleado ↕</th>
                <th class="sortable" data-sort="dni">DNI ↕</th>
                <th>Referencia</th>
                <th>Estado</th>
                <th>Enlace firma</th>
                <th>Acciones</th>
              </tr>
            </thead>
            <tbody></tbody>
          </table>
          <div class="text-center p-16">
            <button id="btnReceiptsMore" class="btn btn-ghost btn-sm hidden" type="button">Ver más</button>
          </div>
        </div>
      </section>

      <div id="uploadModal" class="modal hidden" aria-hidden="true">
        <div class="modal-content empresa-modal-md">
          <div class="modal-header">
            <h3 id="uploadModalTitle" class="modal-title">Carga de Documentación</h3>
          </div>

          <div class="modal-body">
            <div id="uploadMsg" class="mb-16"></div>

            <div class="form-group mb-16">
              <label for="uploadDocType">Tipo de Documento</label>
              <select id="uploadDocType" class="input">
                <option value="PAYROLL">Recibos de Nómina (.pdf)</option>
                <option value="TRANSFER">Transferencias Bancarias (Cualquier formato)</option>
                <option value="ART">Listados ART / Seguros (Cualquier formato)</option>
                <option value="UNEMPLOYMENT">Fondo de Desempleo (Cualquier formato)</option>
                <option value="MISC">Varios / Otros (Cualquier formato)</option>
              </select>
            </div>

            <div class="form-group">
              <label for="uploadPeriod">Período de liquidación / Referencia</label>
              <input id="uploadPeriod" type="text" class="input" placeholder="Ej: Marzo 2026" />
              <div class="small-muted mt-8">Identificador temporal del lote.</div>
            </div>

            <div class="form-group mt-16">
              <label for="uploadPdf">Archivo documental</label>

              <div id="uploadDropZone" class="empresa-upload-dropzone">
                <div class="empresa-upload-plus">+</div>
                <div id="uploadDropZoneTitle" class="empresa-upload-title">Seleccionar archivo</div>
                <div id="uploadDropZoneFormat" class="small-muted">Todos los formatos aceptados</div>
              </div>

              <input id="uploadPdf" type="file" class="hidden" />
            </div>
          </div>

          <div class="modal-footer">
            <button id="uploadClose" class="btn btn-ghost">Cancelar</button>
            <button id="uploadSubmit" class="btn btn-primary">Iniciar procesamiento</button>
          </div>
        </div>
      </div>

      <div id="signModal" class="modal hidden" aria-hidden="true">
        <div class="modal-content empresa-modal-sm">
          <div class="modal-header">
            <h3 id="signModalTitle" class="modal-title">
              Firmar como empresa
              <span id="modalReceiptId" class="small-muted"></span>
            </h3>
          </div>

          <div class="modal-body">
            <div id="modalMsg" class="mb-16"></div>

            <div class="form-group">
              <label for="companySignerSelect">Representante legal</label>
              <select id="companySignerSelect" class="input"></select>
              <div class="small-muted mt-8">
                Administrá firmantes desde
                <a href="#/empresa/configuracion" class="link empresa-config-link">Configuración</a>.
              </div>
            </div>
          </div>

          <div class="modal-footer">
            <button id="modalClose" class="btn btn-ghost">Cancelar</button>
            <button id="modalSubmit" class="btn btn-primary">Proceder a firmar</button>
          </div>

          <div id="modalResult" class="small-muted empresa-modal-result"></div>
        </div>
      </div>

      <div id="employeeProfileModal" class="modal hidden" aria-hidden="true">
        <div class="modal-content empresa-modal-md">
          <div class="modal-header">
            <h3 id="empProfileTitle" class="modal-title">Información del empleado</h3>
            <button id="empProfileClose" class="btn btn-ghost btn-sm">Cerrar</button>
          </div>

          <div class="modal-body">
            <div id="empProfileBody" class="empresa-profile-box"></div>
          </div>
        </div>
      </div>

      <div id="tokenModal" class="modal hidden" aria-hidden="true">
        <div class="modal-content empresa-modal-md">
          <div class="modal-body">
            <h3 class="card-title mb-8">Enlace de firma</h3>
            <p class="small-muted">
              Este enlace permite al empleado acceder directamente a revisar y firmar su recibo.
            </p>

            <div class="empresa-token-row mt-16">
              <input type="text" id="signTokenLink" readonly class="input empresa-token-input" />
              <button id="btnCopyToken" class="btn btn-secondary">Copiar enlace</button>
            </div>

            <p id="copyFeedback" class="small-muted text-success hidden mt-8">
              Enlace copiado al portapapeles.
            </p>
          </div>

          <div class="modal-footer">
            <button id="tokenClose" class="btn btn-ghost">Cerrar</button>
          </div>
        </div>
      </div>

      <div id="emailPreviewModal" class="modal hidden" aria-hidden="true">
        <div class="modal-content empresa-modal-md">
          <div class="modal-body">
            <h3 class="card-title mb-16">Correo enviado al empleado</h3>

            <div id="emailInfoBlock" class="empresa-email-box hidden">
              <ul class="empresa-email-list">
                <li><strong>Destinatario:</strong> <span id="employeeEmailDisplay"></span></li>
                <li><strong>Enviado el:</strong> <span id="emailSentAtDisplay"></span></li>
                <li class="text-success empresa-email-success">
                  La notificación fue enviada correctamente por el servidor.
                </li>
              </ul>
            </div>
          </div>

          <div class="modal-footer">
            <button id="emailPreviewClose" class="btn btn-ghost">Cerrar</button>
          </div>
        </div>
      </div>

      <div id="bulkProgressModal" class="modal hidden" aria-hidden="true">
        <div class="modal-content empresa-modal-sm">
          <div class="modal-body">
            <h3 class="card-title">Procesando firmas</h3>
            <div id="bulkProgressMsg" class="mt-12"></div>

            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-24 mb-48">
                <div class="card p-24">
                    <div class="text-slate-500 font-medium text-xs uppercase tracking-wider mb-8">Nómina de Empleados</div>
                    <div class="h2" id="stat-employees">0</div>
                </div>
            </div>

            <div id="bulkProgressSummary" class="hidden mt-12">
              <div class="success" id="bulkSuccessCount"></div>
              <div class="error mt-8" id="bulkErrorCount"></div>
            </div>
          </div>

          <div class="modal-footer">
            <button id="bulkProgressClose" class="btn btn-ghost">Cerrar</button>
          </div>
        </div>
      </div>

      <!-- NOTIFICATION DETAILS MODAL (SINGLETON) -->
      <div id="notifDetailsModal" class="modal hidden" aria-hidden="true">
        <div class="modal-content empresa-modal-md">
          <div class="modal-header">
            <h3 class="modal-title">Mensaje de Empleado</h3>
            <button id="notifDetailsClose" class="btn btn-ghost btn-sm">X</button>
          </div>
          <div class="modal-body">
            <div class="flex-between mb-16">
              <div id="notifModalSender" class="small-muted"></div>
              <div id="notifModalDate" class="small-muted" style="text-align: right;"></div>
            </div>
            <div id="notifModalBody" style="white-space: pre-wrap; background: rgba(0,0,0,0.03); padding: 16px; border-radius: 8px; max-height: 400px; overflow-y: auto; border: 1px solid rgba(0,0,0,0.05);" class="mb-24"></div>
            <div id="notifModalAttachmentContainer" class="hidden" style="border-top: 1px solid rgba(0,0,0,0.05); padding-top: 16px;">
              <span class="small-muted mb-8 block">Archivo adjunto:</span>
              <a id="notifModalDownload" href="#" target="_blank" class="btn btn-secondary btn-sm">
                Descargar Adjunto
              </a>
            </div>
          </div>
          <div class="modal-footer flex-between">
            <div id="notifModalStatusBadge"></div>
            <div class="flex gap-12">
               <button id="notifModalReadBtn" class="btn btn-info">Marcar como leído</button>
               <button id="notifDetailsCloseBtn" class="btn btn-ghost">Cerrar</button>
            </div>
          </div>
        </div>
      </div>
    </section>
  `;
}

// dashboardStore persists state between re-renders in the same session
const dashboardStore = {
  receipts: [],
  employees: [],
  me: null,
  search: '',
  filterStatus: '',
  sortField: 'full_name', // Default sort
  sortOrder: 'asc',
  selectedIds: new Set(),
  receiptsExpanded: false,
  summary: null
};

export async function render(container, params) {
  container.innerHTML = buildShell();

  // Local alias for store
  const state = dashboardStore;

  let currentReceipt = null;
  let bulkTargets = null;
  let companySignersList = [];

  function openModal(id) {
    const modal = el(id, container);
    modal.classList.remove('hidden');
    modal.setAttribute('aria-hidden', 'false');
  }

  function closeModal(id) {
    const modal = el(id, container);
    modal.classList.add('hidden');
    modal.setAttribute('aria-hidden', 'true');
  }

  async function loadMe() {
    try {
      const response = await getMe();
      state.me = response?.user || response || null;
      const orgIdHash = state.me?.organization_id ? ` [${state.me.organization_id.substring(0, 6)}]` : '';
      el('orgInfo', container).innerText = state.me?.organization_name
        ? `Organización: ${state.me.organization_name}${orgIdHash}`
        : '';

      if (state.me?.organization_id) {
        const logoUrl = apiUrl(`/api/organizations/${state.me.organization_id}/logo`);
        const orgLogoEl = el('orgLogo', container);
        const orgName = state.me.organization_name || 'Empresa';
        
        const logoImg = document.createElement('img');
        logoImg.src = `${logoUrl}?t=${Date.now()}`;
        logoImg.alt = 'Logo';
        logoImg.className = 'empresa-logo';
        
        logoImg.onerror = () => {
          // Fallback: Show initials in a colored circle
          const initials = orgName.substring(0, 2).toUpperCase();
          orgLogoEl.innerHTML = `<div class="logo-fallback">${initials}</div>`;
        };
        
        orgLogoEl.innerHTML = '';
        orgLogoEl.appendChild(logoImg);
      }
    } catch (error) {
      showError(el('orgInfo', container), error);
    }
  }

  async function loadEmployees() {
    try {
      const response = await apiFetch('/api/employees');
      state.employees = response?.employees || [];
    } catch {
      state.employees = [];
    }
  }

  async function loadReceipts() {
    try {
      // Partial refresh: we don't clear state.receipts unless needed
      const response = await apiFetch('/api/receipts/pending?include_signed=true');
      state.receipts = Array.isArray(response) ? response : (response?.receipts || []);
      
      // Update summary in parallel
      loadSummary();
      
      renderReceipts();
    } catch (error) {
      const emptyEl = el('receiptsEmpty', container);
      showError(emptyEl, error);
      emptyEl.classList.remove('hidden');
    }
  }

  async function loadSummary() {
    try {
      const summary = await apiFetch('/api/receipts/summary');
      state.summary = summary;
      updateKPIs(summary);
    } catch (error) {
      console.error('Error loading summary:', error);
    }
  }

  function updateKPIs(summary) {
    if (!summary) return;

    if (el('stat-pending', container)) el('stat-pending', container).textContent = summary.pending || 0;
    if (el('stat-completed', container)) el('stat-completed', container).textContent = summary.signed || 0;
    if (el('stat-total', container)) el('stat-total', container).textContent = summary.total_receipts || 0;
    if (el('stat-employees', container)) el('stat-employees', container).textContent = summary.total_employees || 0;
  }

  function setLoading(loading) {
    const refreshBtn = el('btnRefresh', container);
    if (loading) {
      if (refreshBtn) refreshBtn.disabled = true;
    } else {
      if (refreshBtn) refreshBtn.disabled = false;
    }
  }

  function getVisibleReceipts() {
    let visible = [...state.receipts];

    if (state.filterStatus) {
      visible = visible.filter((receipt) => receipt.status === state.filterStatus);
    }

    if (state.search.trim()) {
      const search = state.search.trim().toLowerCase();
      visible = visible.filter((receipt) => {
        const name = (receipt.full_name || receipt.employee_name || '').toLowerCase();
        const dni = String(receipt.dni || receipt.employee_dni || '').toLowerCase();
        return name.includes(search) || dni.includes(search);
      });
    }

    // Sorting (Requirement 2)
    visible.sort((a, b) => {
      const valA = (a[state.sortField] || a.full_name || a.employee_name || '').toLowerCase();
      const valB = (b[state.sortField] || b.full_name || b.employee_name || '').toLowerCase();
      if (valA < valB) return state.sortOrder === 'asc' ? -1 : 1;
      if (valA > valB) return state.sortOrder === 'asc' ? 1 : -1;
      return 0;
    });

    return visible;
  }

  function updateBulkUI() {
    const count = state.selectedIds.size;
    const bulkBar = el('bulkActions', container);

    if (count > 0) {
      bulkBar.classList.remove('hidden');
      el('selectedCount', container).innerText = `${count} seleccionado(s)`;
    } else {
      bulkBar.classList.add('hidden');
      el('selectAllReceipts', container).checked = false;
    }
  }

  function renderReceipts() {
    const tbody = container.querySelector('#receiptsTable tbody');
    const emptyEl = el('receiptsEmpty', container);
    const wrapEl = el('receiptsTableWrap', container);
    const moreButton = el('btnReceiptsMore', container);

    tbody.innerHTML = '';

    const visible = getVisibleReceipts();

    if (!visible.length) {
      emptyEl.innerHTML = renderEmptyReceipts();
      emptyEl.classList.remove('hidden');
      wrapEl.classList.add('hidden');
      moreButton?.classList.add('hidden');

      const emptyUploadBtn = el('btnEmptyUpload', container);
      if (emptyUploadBtn) {
        emptyUploadBtn.addEventListener('click', openUpload);
      }
      return;
    }

    emptyEl.classList.add('hidden');
    wrapEl.classList.remove('hidden');

    const rowsToRender = state.receiptsExpanded ? visible : visible.slice(0, RECEIPT_PREVIEW_LIMIT);
    if (moreButton) {
      moreButton.classList.toggle('hidden', visible.length <= RECEIPT_PREVIEW_LIMIT);
      moreButton.textContent = state.receiptsExpanded ? 'Ver menos' : 'Ver más';
    }

    rowsToRender.forEach((receipt) => {
      const tr = document.createElement('tr');

      const signUrl = receipt.signature_url || null;
      const fullSignUrl = signUrl ? `${window.location.origin}${signUrl}` : null;

      const tdCheck = document.createElement('td');
      const checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.className = 'receipt-select';
      checkbox.dataset.id = receipt.id;
      checkbox.checked = state.selectedIds.has(receipt.id);
      tdCheck.appendChild(checkbox);

      const tdEmp = document.createElement('td');
      const empButton = document.createElement('button');
      empButton.type = 'button';
      empButton.className = 'empresa-employee-link';
      empButton.dataset.empName = receipt.employee_name || '';
      empButton.textContent = receipt.employee_name || 'Sin nombre';
      tdEmp.appendChild(empButton);

      const tdDni = document.createElement('td');
      tdDni.textContent = receipt.employee_dni || '-';

      const tdReference = document.createElement('td');
      tdReference.textContent = receipt.period || 'N/D';

      const tdStatus = document.createElement('td');
      tdStatus.appendChild(createStatusBadge(receipt.status, receipt.rejection_reason));

      if (receipt.status === 'signed') {
        const lock = document.createElement('span');
        lock.className = 'empresa-lock-indicator';
        lock.title = 'Sellado criptográficamente';
        lock.innerHTML = `
          <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"></path>
          </svg>
        `;
        tdStatus.appendChild(lock);
      }

      const tdToken = document.createElement('td');
      if (fullSignUrl) {
        const code = document.createElement('code');
        code.className = 'empresa-token-preview';
        code.textContent = `${signUrl.slice(-16)}...`;
        tdToken.appendChild(code);
      } else if (receipt.has_pending_token) {
        const tokenBadge = document.createElement('span');
        tokenBadge.className = 'badge success';
        tokenBadge.textContent = 'Token generado';
        tdToken.appendChild(tokenBadge);
      } else {
        const muted = document.createElement('span');
        muted.className = 'small-muted';
        muted.textContent = '-';
        tdToken.appendChild(muted);
      }

      const tdActions = document.createElement('td');
      tdActions.className = 'table-actions';

      const actions = document.createElement('div');
      actions.className = 'form-row';
      tdActions.appendChild(actions);

      checkbox.addEventListener('change', () => {
        if (checkbox.checked) state.selectedIds.add(receipt.id);
        else state.selectedIds.delete(receipt.id);
        updateBulkUI();
      });

      if (receipt.status === 'pending_signature' || receipt.status === 'pending_employer_signature') {
        const signBtn = document.createElement('button');
        signBtn.className = 'btn btn-primary btn-sm';
        signBtn.textContent = 'Firmar';
        signBtn.addEventListener('click', () => openSignModal(receipt));
        actions.appendChild(signBtn);
      }

      if (receipt.status === 'pending_employee_signature') {
        const reminderBtn = document.createElement('button');
        reminderBtn.className = 'btn btn-secondary btn-sm';
        reminderBtn.textContent = 'Enviar recordatorio de firma';
        reminderBtn.addEventListener('click', async () => {
          reminderBtn.disabled = true;
          try {
            await apiFetch(`/api/receipts/${receipt.id}/remind-signature`, { method: 'POST' });
            showToast('Recordatorio de firma enviado al empleado', 'success');
          } catch (error) {
            const detail = error?.body?.detail ? String(error.body.detail) : 'No se pudo enviar el recordatorio.';
            showToast(detail, 'error');
          } finally {
            reminderBtn.disabled = false;
          }
        });
        actions.appendChild(reminderBtn);
      }

      if (receipt.status === 'signed') {
        const base = getApiBase();
        const url = `${base}/api/receipts/${receipt.id}/download`;

        const downloadBtn = document.createElement('button');
        downloadBtn.className = 'btn btn-ghost btn-sm';
        downloadBtn.textContent = 'Descargar PDF';
        downloadBtn.addEventListener('click', () => window.open(url, '_blank', 'noopener'));

        actions.appendChild(downloadBtn);
      }

      if (receipt.status !== 'signed') {
        const deleteBtn = document.createElement('button');
        deleteBtn.className = 'btn btn-danger btn-sm';
        deleteBtn.textContent = 'Eliminar';

        deleteBtn.addEventListener('click', async () => {
          const ok = await confirmAction('¿Querés eliminar este recibo? Esta acción no se puede deshacer.');
          if (!ok) return;

          try {
            await apiFetch(`/api/receipts/${receipt.id}`, { method: 'DELETE' });
            showToast('Recibo eliminado', 'success');
            await refreshAll();
          } catch (error) {
            const detail = error?.body?.detail ? String(error.body.detail) : 'No se pudo eliminar el recibo.';
            showToast(detail, 'error');
          }
        });

        actions.appendChild(deleteBtn);
      }

      empButton.addEventListener('click', () => {
        const employee = state.employees.find(
          (item) => item.full_name === receipt.employee_name || item.id === receipt.employee_id
        );

        if (employee) {
          openEmployeeProfile(employee.id);
        } else {
          showToast('Empleado no encontrado en la nómina cargada.', 'warning');
        }
      });

      tr.append(tdCheck, tdEmp, tdDni, tdReference, tdStatus, tdToken, tdActions);
      tbody.appendChild(tr);
    });

    const allChecked = visible.length > 0 && visible.every((receipt) => state.selectedIds.has(receipt.id));
    el('selectAllReceipts', container).checked = allChecked;
    updateBulkUI();
  }

  async function handleBulkDelete() {
    const ids = Array.from(state.selectedIds);
    if (!ids.length) return;

    const ok = await confirmAction(
      `¿Querés eliminar ${ids.length} recibos seleccionados? Esta acción no se puede deshacer.`
    );
    if (!ok) return;

    try {
      await apiFetch('/api/receipts/bulk-delete', {
        method: 'POST',
        body: { ids },
      });

      showToast(`${ids.length} recibos eliminados`, 'success');
      state.selectedIds.clear();
      await refreshAll();
    } catch (error) {
      const detail = error?.body?.detail ? String(error.body.detail) : 'No se pudo eliminar el lote.';
      showToast(detail, 'error');
    }
  }

  async function openEmployeeProfile(employeeId) {
    const profileBody = el('empProfileBody', container);
    profileBody.innerHTML = '<div class="small-muted">Cargando...</div>';
    openModal('employeeProfileModal');

    try {
      const response = await apiFetch(`/api/employees/${employeeId}`);
      const employee = response?.employee || response;

      el('empProfileTitle', container).innerText = employee.full_name || 'Empleado';

      const fields = [
        { label: 'Nombre completo', value: employee.full_name },
        { label: 'DNI', value: employee.dni },
        { label: 'CUIL', value: employee.cuil },
        { label: 'Email', value: employee.email },
        { label: 'Estado', value: employee.status },
        { label: 'Estado civil', value: employee.marital_status },
        { label: 'Fecha de nacimiento', value: employee.birth_date },
        { label: 'Dirección', value: employee.address },
        { label: 'Teléfono', value: employee.phone },
        { label: 'Cargo', value: employee.position },
        { label: 'Fecha de ingreso', value: employee.hire_date },
        { label: 'Perfil completo', value: employee.profile_completed ? 'Sí' : 'No' },
        { label: 'Activo', value: employee.is_active ? 'Sí' : 'No' },
        { label: 'Creado', value: employee.created_at },
      ];

      const grid = document.createElement('div');
      grid.className = 'empresa-profile-grid';

      fields.forEach((field) => {
        const item = document.createElement('div');
        item.className = 'dl-item';

        const label = document.createElement('div');
        label.className = 'dl-label';
        label.textContent = field.label;

        const value = document.createElement('div');
        value.className = 'dl-value';
        value.textContent = field.value || '—';

        item.append(label, value);
        grid.appendChild(item);
      });

      profileBody.innerHTML = '';
      profileBody.appendChild(grid);
    } catch {
      profileBody.innerHTML = '<div class="error">No se pudieron cargar los datos del empleado.</div>';
    }
  }

  async function handleGetToken(receipt) {
    try {
      const response = await apiFetch(`/api/receipts/${receipt.id}/token`, { method: 'POST' });
      const fullUrl = `${window.location.origin}${response.sign_url || ''}`;
      el('signTokenLink', container).value = fullUrl;
      openModal('tokenModal');
    } catch (error) {
      const detail = error?.body?.detail ? String(error.body.detail) : 'No se pudo generar el token.';
      showToast(detail, 'error');
    }
  }

  function closeSignModal() {
    closeModal('signModal');
    currentReceipt = null;
    bulkTargets = null;
  }

  async function openSignModal(receipt, bulkList = null) {
    currentReceipt = receipt;
    bulkTargets = bulkList;

    const titleEl = el('signModalTitle', container);
    const idEl = el('modalReceiptId', container);
    const msgEl = el('modalMsg', container);
    const resultEl = el('modalResult', container);
    const submitBtn = el('modalSubmit', container);

    msgEl.innerHTML = '';
    resultEl.innerHTML = '';

    if (bulkTargets) {
      titleEl.innerText = `Firma masiva de ${bulkTargets.length} recibos`;
      idEl.innerText = '';
    } else {
      titleEl.innerText = 'Firmar como empresa';
      idEl.innerText = receipt?.id ? ` ${receipt.id.slice(0, 8)}...` : '';
    }

    openModal('signModal');

    try {
      const response = await apiFetch('/api/company-signers');
      companySignersList = (response?.signers || []).filter((signer) => signer.is_active && signer.has_signature);

      const select = el('companySignerSelect', container);
      select.innerHTML = '';

      if (!companySignersList.length) {
        const option = document.createElement('option');
        option.value = '';
        option.textContent = 'No hay firmantes activos con firma configurada';
        select.appendChild(option);
        submitBtn.disabled = true;
        return;
      }

      companySignersList.forEach((signer) => {
        const option = document.createElement('option');
        option.value = signer.id;
        let text = `${signer.name} (${signer.position})`;
        if (signer.needs_reupload) {
          text += ' - [IMAGEN EXTRAVIADA]';
        }
        option.textContent = text;
        select.appendChild(option);
      });

      select.addEventListener('change', () => {
        const selected = companySignersList.find(s => s.id === select.value);
        if (selected && selected.needs_reupload) {
          msgEl.innerHTML = '<div class="warning small"><strong>Modo Contingencia:</strong> La imagen de firma no se encuentra. Se utilizará un sello formal de validación sin la firma manuscrita.</div>';
        } else {
          msgEl.innerHTML = '';
        }
      });
      
      // Trigger change for initial selection
      select.dispatchEvent(new Event('change'));

      submitBtn.disabled = false;
    } catch {
      msgEl.innerHTML = '<div class="error">No se pudieron cargar los firmantes.</div>';
    }
  }

  function openEmailPreview(email, name) {
    el('emailInfoBlock', container).classList.remove('hidden');
    el('employeeEmailDisplay', container).textContent = `${name || 'Empleado'} <${email}>`;
    el('emailSentAtDisplay', container).textContent = new Date().toLocaleString('es-AR');
    openModal('emailPreviewModal');
  }

  async function submitBulkSignature(signerId) {
    el('modalMsg', container).innerText = 'Iniciando firma masiva...';
    el('modalSubmit', container).disabled = true;

    try {
      const response = await apiFetch('/api/receipts/bulk-sign-employer', {
        method: 'POST',
        body: {
          receipt_ids: bulkTargets,
          company_signer_id: signerId,
        },
      });

      closeSignModal();
      openModal('bulkProgressModal');

      el('bulkProgressMsg', container).innerText = 'Operación completada.';
      el('bulkProgressSummary', container).classList.remove('hidden');
      el('bulkSuccessCount', container).innerText = `${response.signed_count} documentos rubricados correctamente.`;
      el('bulkErrorCount', container).innerText =
        response.error_count > 0
          ? `${response.error_count} errores durante la operación.`
          : '';

      state.selectedIds.clear();
      await refreshAll();
    } catch (error) {
      const detail = error?.body?.detail ? String(error.body.detail) : 'No se pudo completar la firma masiva.';
      el('modalMsg', container).innerHTML = `<div class="error">${detail}</div>`;
      showToast('Error en el proceso de firma masiva', 'error');
    } finally {
      el('modalSubmit', container).disabled = false;
    }
  }

  async function submitEmployerSignature() {
    if (!currentReceipt && !bulkTargets) return;

    const signerId = el('companySignerSelect', container).value;
    if (!signerId) return;

    if (bulkTargets) {
      await submitBulkSignature(signerId);
      return;
    }

    el('modalMsg', container).innerText = 'Enviando...';
    el('modalSubmit', container).disabled = true;

    try {
      const response = await apiFetch(`/api/receipts/${currentReceipt.id}/sign-employer`, {
        method: 'POST',
        body: { company_signer_id: signerId },
      });

      el('modalResult', container).innerText = 'Firma registrada.';
      
      if (response?.signature_mode === 'seal_only') {
        showToast('Firma de empresa registrada (Modo Contingencia)', 'warning');
      } else {
        showToast('Firma de empresa registrada', 'success');
      }

      closeSignModal();
      await refreshAll();

      if (response?.token && response?.employee_email) {
        openEmailPreview(response.employee_email, response.employee_name);
      } else if (response?.token) {
        el('signTokenLink', container).value = `${window.location.origin}/ui/#/sign/${response.token}`;
        openModal('tokenModal');
      }
    } catch {
      el('modalMsg', container).innerHTML = '<div class="error">No se pudo completar la firma.</div>';
      showToast('Error al registrar la firma', 'error');
    } finally {
      el('modalSubmit', container).disabled = false;
    }
  }

  function openUpload() {
    el('uploadMsg', container).innerHTML = '';
    el('uploadPdf', container).value = '';

    const dropZone = el('uploadDropZone', container);
    dropZone.classList.remove('has-file');
    el('uploadDropZoneTitle', container).textContent = 'Seleccionar archivo';
    el('uploadDropZoneFormat', container).textContent = 'Todos los formatos aceptados';

    // Reset doc type to PAYROLL by default
    const typeSelect = el('uploadDocType', container);
    if (typeSelect) typeSelect.value = 'PAYROLL';

    const now = new Date();
    const defaultPeriod = now.toLocaleString('es-AR', { month: 'long', year: 'numeric' });
    el('uploadPeriod', container).value = defaultPeriod.charAt(0).toUpperCase() + defaultPeriod.slice(1);

    openModal('uploadModal');
  }

  function closeUpload() {
    closeModal('uploadModal');
  }

  async function submitUpload() {
    const file = el('uploadPdf', container).files?.[0];
    const docType = el('uploadDocType', container).value;
    const msgEl = el('uploadMsg', container);
    const submitBtn = el('uploadSubmit', container);

    if (!file) {
      msgEl.innerHTML = '<div class="error">Seleccioná un archivo para subir.</div>';
      return;
    }

    if (docType === 'PAYROLL' && !file.name.toLowerCase().endsWith('.pdf')) {
      msgEl.innerHTML = '<div class="error">El lote de nómina debe ser un archivo PDF.</div>';
      return;
    }

    const periodLabel = el('uploadPeriod', container).value.trim();
    if (!periodLabel) {
      msgEl.innerHTML = '<div class="error">Ingresá el período o referencia del lote.</div>';
      return;
    }

    submitBtn.disabled = true;
    msgEl.innerHTML = '<div class="small-muted">Subiendo y procesando... Esto puede demorar algunos segundos.</div>';

    try {
      const formData = new FormData();
      const orgId = state.me?.organization_id;

      if (!orgId) {
        msgEl.innerHTML = '<div class="error">No hay organización asociada a tu cuenta.</div>';
        submitBtn.disabled = false;
        return;
      }

      formData.append('organization_id', orgId);
      formData.append('period_label', periodLabel);
      formData.append('document_type', docType);
      formData.append('pdf', file);

      const response = await fetch(`${getApiBase()}/api/batches/upload`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
        body: formData,
      });

      if (!response.ok) {
        throw new Error(await response.text());
      }

      const data = await response.json();
      const stats = data.stats || data;
      const matched = stats.matched || stats.matched_receipts || 0;
      const pendingMatch = stats.pending_match || 0;
      const totalPages = stats.total_pages || 0;
      const errors = stats.errors || 0;

      msgEl.innerHTML = `
        <div class="success">
          Batch subido: ${matched} matcheados, ${pendingMatch} en revisión, ${totalPages} páginas procesadas${errors ? `, ${errors} con error` : ''}.
        </div>
      `;

      if (matched > 0) {
        const button = document.createElement('button');
        button.className = 'btn btn-primary btn-sm mt-12';
        button.textContent = `Firmar lote de ${matched} recibos`;

        button.addEventListener('click', async () => {
          closeUpload();
          await refreshAll();

          const toSign = state.receipts
            .filter((receipt) => receipt.status === 'pending_signature' || receipt.status === 'pending_employer_signature')
            .map((receipt) => receipt.id);

          if (toSign.length > 0) {
            openSignModal(null, toSign);
          }
        });

        msgEl.appendChild(button);
      }

      if (data.alerts?.length) {
        const list = document.createElement('ul');
        list.className = 'list mt-8';

        data.alerts.forEach((alert) => {
          const li = document.createElement('li');
          li.className = 'small-muted';
          li.textContent = alert;
          list.appendChild(li);
        });

        msgEl.appendChild(list);
      }

      showToast('Batch subido correctamente', 'success');
      await refreshAll();
    } catch (error) {
      msgEl.innerHTML = `<div class="error">${error.message || 'No se pudo subir el batch.'}</div>`;
      showToast('Error al subir batch', 'error');
    } finally {
      submitBtn.disabled = false;
    }
  }

  async function refreshAll() {
    setLoading(true);
    try {
      await Promise.allSettled([
        loadEmployees(),
        loadReceipts(),
        loadNotifications()
      ]);
      if (state.summary) updateKPIs(state.summary);
    } finally {
      setLoading(false);
    }
  }

  el('btnNewBatch', container).addEventListener('click', openUpload);
  el('uploadClose', container).addEventListener('click', closeUpload);
  el('uploadSubmit', container).addEventListener('click', submitUpload);

  el('btnRefresh', container).addEventListener('click', async () => {
    state.selectedIds.clear();
    await refreshAll();
  });


  el('filterStatus', container).addEventListener('change', () => {
    state.filterStatus = el('filterStatus', container).value;
    state.receiptsExpanded = false;
    state.selectedIds.clear();
    renderReceipts();
  });

  el('btnReceiptsMore', container).addEventListener('click', () => {
    state.receiptsExpanded = !state.receiptsExpanded;
    renderReceipts();
  });

  el('selectAllReceipts', container).addEventListener('change', (event) => {
    const checked = event.target.checked;
    const visible = getVisibleReceipts();

    if (checked) visible.forEach((receipt) => state.selectedIds.add(receipt.id));
    else visible.forEach((receipt) => state.selectedIds.delete(receipt.id));

    renderReceipts();
  });

  el('btnBulkDelete', container).addEventListener('click', handleBulkDelete);
  el('btnBulkSign', container).addEventListener('click', () => {
    const ids = Array.from(state.selectedIds);
    if (ids.length > 0) {
      openSignModal(null, ids);
    }
  });

  el('bulkProgressClose', container).addEventListener('click', () => closeModal('bulkProgressModal'));

  el('modalClose', container).addEventListener('click', closeSignModal);
  el('modalSubmit', container).addEventListener('click', submitEmployerSignature);
  el('empProfileClose', container).addEventListener('click', () => closeModal('employeeProfileModal'));
  el('tokenClose', container).addEventListener('click', () => closeModal('tokenModal'));
  el('emailPreviewClose', container).addEventListener('click', () => closeModal('emailPreviewModal'));
  el('notifDetailsClose', container).addEventListener('click', () => closeModal('notifDetailsModal'));
  el('notifDetailsCloseBtn', container).addEventListener('click', () => closeModal('notifDetailsModal'));

  el('btnCopyToken', container).addEventListener('click', async () => {
    const input = el('signTokenLink', container);

    try {
      await navigator.clipboard.writeText(input.value);
      el('copyFeedback', container).classList.remove('hidden');

      const button = el('btnCopyToken', container);
      button.textContent = 'Copiado ✓';

      setTimeout(() => {
        button.textContent = 'Copiar enlace';
        el('copyFeedback', container).classList.add('hidden');
      }, 2000);
    } catch {
      showToast('No se pudo copiar el enlace', 'warning');
    }
  });

  const tableWrap = el('receiptsTableWrap', container);
  tableWrap.addEventListener('click', (event) => {
    const target = event.target;
    if (!target || !target.classList.contains('btn-print')) return;

    const url = target.getAttribute('data-url');
    const iframe = document.createElement('iframe');
    iframe.className = 'hidden';
    iframe.src = url;

    document.body.appendChild(iframe);

    iframe.onload = () => {
      setTimeout(() => {
        iframe.focus();
        iframe.contentWindow?.print();
        setTimeout(() => {
          if (iframe.parentNode) iframe.parentNode.removeChild(iframe);
        }, 10000);
      }, 500);
    };
  });

  el('searchInput', container).addEventListener('input', () => {
    state.search = el('searchInput', container).value || '';
    state.receiptsExpanded = false;
    renderReceipts();
  });

  const uploadDropZone = el('uploadDropZone', container);
  const uploadPdf = el('uploadPdf', container);

  uploadPdf.addEventListener('change', (event) => {
    const file = event.target.files?.[0];
    if (!file) return;

    uploadDropZone.classList.add('has-file');
    uploadDropZone.querySelector('.empresa-upload-title').textContent = file.name;
    uploadDropZone.querySelector('.small-muted').textContent = `${(file.size / 1024 / 1024).toFixed(1)} MB`;
  });

  uploadDropZone.addEventListener('click', () => uploadPdf.click());

  const searchInp = el('searchInput', container);
  const filterSel = el('filterStatus', container);

  if (searchInp) {
    searchInp.value = state.search;
    searchInp.addEventListener('input', (e) => {
      state.search = e.target.value;
      renderReceipts();
    });
  }

  if (filterSel) {
    filterSel.value = state.filterStatus;
    filterSel.addEventListener('change', (e) => {
      state.filterStatus = e.target.value;
      renderReceipts();
    });
  }

  // btnRefresh is already handled above

  container.querySelectorAll('th.sortable').forEach(th => {
    th.addEventListener('click', () => {
      const field = th.dataset.sort;
      if (state.sortField === field) {
        state.sortOrder = state.sortOrder === 'asc' ? 'desc' : 'asc';
      } else {
        state.sortField = field;
        state.sortOrder = 'asc';
      }
      renderReceipts();
    });
  });

  await loadNotifications();

  // V4.1 Auto-Modal Trigger (RequestAnimationFrame for DOM Sync)
  if (params && params.get('action') === 'upload') {
    requestAnimationFrame(() => {
      const btn = el('btnNewBatch', container);
      if (btn) {
        // Pre-select document type if provided
        const targetType = params.get('type');
        if (targetType) {
          const select = el('uploadDocType', container);
          if (select) select.value = targetType.toUpperCase();
        }
        btn.click();
      }
    });
  }

  async function loadNotifications() {
    try {
      const response = await apiFetch('/api/notifications');
      const notifs = response?.notifications || [];
      const unreadCount = notifs.filter(n => !n.is_read).length;
      if (el('stat-notifications', container)) el('stat-notifications', container).textContent = unreadCount;
      if (el('notif-dot', container)) {
        if (unreadCount > 0) el('notif-dot', container).classList.remove('hidden');
        else el('notif-dot', container).classList.add('hidden');
      }

      // Populate Widget
      const widgetList = el('notif-widget-list', container);
      if (widgetList) {
        if (notifs.length === 0) {
          widgetList.innerHTML = '<div class="small-muted p-8 text-center text-xs">No hay mensajes</div>';
        } else {
          widgetList.innerHTML = notifs.slice(0, 5).map(n => `
            <div class="p-8 rounded hover:bg-slate-50 border-bottom last:border-0 cursor-pointer" onclick="location.hash='#/empresa/notificaciones'">
                <div class="flex justify-between items-center mb-4">
                    <span class="font-bold text-xs">${n.sender_name || 'Empleado'}</span>
                    <span class="text-[10px] text-slate-400">${n.created_at ? new Date(n.created_at).toLocaleDateString() : ''}</span>
                </div>
                <div class="text-xs text-slate-600 truncate">${n.message}</div>
            </div>
          `).join('');
        }
      }
    } catch (err) {
      console.error(err);
      showToast('No se pudieron cargar las notificaciones', 'error');
    }
  }

  async function openNotifModal(n, badgeElement) {
    const modal = el('notifDetailsModal', container);
    const body = el('notifModalBody', modal);
    const sender = el('notifModalSender', modal);
    const dateE = el('notifModalDate', modal);
    const download = el('notifModalDownload', modal);
    const attachContainer = el('notifModalAttachmentContainer', modal);
    const readBtn = el('notifModalReadBtn', modal);
    const statusDiv = el('notifModalStatusBadge', modal);

    // Reset & Populate
    sender.textContent = `De: ${n.sender_name || 'Empleado'} (${n.sender_email})`;
    dateE.textContent = n.created_at ? new Date(n.created_at).toLocaleString('es-AR') : '';
    body.textContent = n.message;
    
    // Status Badge inside modal
    statusDiv.innerHTML = '';
    const modalBadge = badgeElement.cloneNode(true);
    modalBadge.id = ''; // remove id for clone
    statusDiv.appendChild(modalBadge);

    // Handle Attachment
    if (n.has_file) {
      attachContainer.classList.remove('hidden');
      download.href = `${getApiBase()}/api/notifications/${n.id}/file`;
    } else {
      attachContainer.classList.add('hidden');
    }

    // Handle Read Button
    if (n.is_read) {
      readBtn.classList.add('hidden');
    } else {
      readBtn.classList.remove('hidden');
      readBtn.onclick = async () => {
        try {
          await apiFetch(`/api/notifications/${n.id}/read`, { method: 'POST' });
          n.is_read = true;
          // UI Sync: update table row
          badgeElement.className = 'badge neutral';
          badgeElement.textContent = 'Visto';
          // Update modal
          readBtn.classList.add('hidden');
          modalBadge.className = 'badge neutral';
          modalBadge.textContent = 'Visto';
        } catch (err) {
          showToast('Error al marcar como leído', 'error');
        }
      };
    }

    openModal('notifDetailsModal');
  }

  // Industrial Startup Sequence (V4.4)
  const start = async () => {
    setLoading(true);
    try {
      await loadMe(); // Sequential for Org Context
      await Promise.allSettled([
        loadEmployees(),
        loadReceipts(),
        loadNotifications()
      ]);
    } catch (err) {
       console.error("Critical dashboard load error:", err);
    } finally {
      setLoading(false);
    }
  };

  start();
}