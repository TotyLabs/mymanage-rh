import {
  apiFetch,
  showError,
  showToast,
  getMe,
  confirmAction,
  getApiBase,
  reloadApp,
  Store,
  el,
  openModal,
  closeModal,
  navigate,
  sanitizeInput
} from '../../common.js';
import { LABELS, ROUTES, DOMAINS } from '../../constants.js';
import { renderKPIs } from './kpis.js';
import { renderNotifications } from './notifications.js';
import { renderReceipts } from './receipts.js';
import { openUploadModal } from './modals.js';

export async function render(container) {
  const state = {
    receipts: [],
    employees: [],
    notifications: [],
    me: null,
    search: '',
    filterStatus: '',
    selectedIds: new Set(),
  };

  container.innerHTML = `
    <section class="empresa-dashboard-shell">
      <div class="flex-between mb-24 empresa-dashboard-topbar">
        <div class="flex items-center gap-16">
          <div class="empresa-brand-logo small">
             <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
               <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
             </svg>
          </div>
          <div>
            <h1 class="card-title empresa-page-title mb-8">${LABELS.dashboard}</h1>
            <div id="orgInfo" class="small-muted">Cargando organización...</div>
          </div>
        </div>

        <div class="flex items-center gap-12 empresa-dashboard-actions">
          <input id="searchInput" class="input empresa-search-input" placeholder="Buscar por DNI o nombre..." />
          <button id="btnNewBatch" class="btn btn-primary">${LABELS.uploadReceipts}</button>
          <button id="btnManageEmployees" class="btn btn-ghost">${LABELS.nomina}</button>
        </div>
      </div>

      <div id="kpis" class="kpi-grid mb-32"></div>

      <!-- Notifications -->
      <section class="card mb-32 empresa-table-card">
        <div class="flex-between empresa-table-header">
          <h2 class="card-title">Notificaciones de Empleados</h2>
          <button id="btnRefreshNotifs" class="btn btn-ghost btn-sm">${LABELS.refresh}</button>
        </div>
        <div id="notifsTableWrap" class="table-container empresa-table-wrap">
          <table id="notifsTable" class="table">
            <thead>
              <tr><th>Estado</th><th>Empleado</th><th>Fecha</th><th>Mensaje</th><th>Adjunto</th></tr>
            </thead>
            <tbody></tbody>
          </table>
          <div id="notifsEmpty" class="hidden text-center p-16 small-muted">No hay notificaciones pendientes.</div>
        </div>
      </section>

      <!-- Receipts -->
      <section class="card empresa-table-card">
        <div class="flex-between empresa-table-header">
          <h2 class="card-title">${LABELS.receipts}</h2>
          <div class="flex-center gap-12 empresa-table-filters">
            <select id="filterStatus" class="input input-auto empresa-filter-select">
              <option value="">No archivados</option>
              <option value="pending_match">En revisión</option>
              <option value="pending_signature">Pendiente firma</option>
              <option value="signed">${LABELS.signed}</option>
            </select>
            <button id="btnRefresh" class="btn btn-ghost btn-sm">${LABELS.refresh}</button>
          </div>
        </div>

        <div id="receiptsEmpty" class="hidden"></div>

        <div id="receiptsTableWrap" class="table-container empresa-table-wrap">
          <div id="bulkActions" class="empresa-bulk-bar hidden">
            <span id="selectedCount" class="small-muted empresa-bulk-count"></span>
            <div class="flex items-center gap-12">
              <button id="btnBulkDelete" class="btn btn-sm btn-danger">${LABELS.deleteSelection}</button>
            </div>
          </div>
          <table id="receiptsTable" class="table">
            <thead>
              <tr>
                <th class="empresa-check-col"><input type="checkbox" id="selectAllReceipts" /></th>
                <th class="sortable" data-sort="name">Empleado</th>
                <th class="sortable" data-sort="dni">DNI</th>
                <th class="sortable" data-sort="status">Estado</th>
                <th>Firmas</th>
                <th>Acciones</th>
              </tr>
            </thead>
            <tbody></tbody>
          </table>
        </div>
      </section>

      <!-- Modals -->
      <div id="notifDetailsModal" class="modal hidden" aria-hidden="true">
        <div class="modal-content empresa-modal-md">
           <div class="modal-header"><h3 class="modal-title">Mensaje</h3><button id="notifDetailsClose" class="btn btn-ghost btn-sm">X</button></div>
           <div class="modal-body">
             <div id="notifModalSender" class="small-muted mb-8"></div>
             <div id="notifModalBody" class="empresa-memo-body mb-16"></div>
             <div id="notifModalAttachmentContainer" class="hidden"><a id="notifModalDownload" class="btn btn-secondary btn-sm" target="_blank">Descargar adjunto</a></div>
           </div>
           <div class="modal-footer flex-between">
             <div id="notifModalStatusBadge"></div>
             <button id="notifModalReadBtn" class="btn btn-primary">Marcar leído</button>
           </div>
        </div>
      </div>

      <div id="uploadModal" class="modal hidden" aria-hidden="true">
        <div class="modal-content empresa-modal-md">
           <div class="modal-header"><h3 class="modal-title">${LABELS.receiptbatch}</h3></div>
           <div id="uploadMsg" class="p-16"></div>
           <div class="modal-body p-24">
             <div class="form-group"><label>Período</label><input id="uploadPeriod" class="input" placeholder="Enero 2026"></div>
             <div class="form-group mt-16"><label>PDF</label><input id="uploadPdf" type="file" accept=".pdf" class="input"></div>
           </div>
           <div class="modal-footer"><button onclick="closeModal('uploadModal')" class="btn btn-ghost">Cancelar</button><button id="uploadSubmit" class="btn btn-primary">Subir</button></div>
        </div>
      </div>
    </section>
  `;

  async function refreshAll() {
    try {
      if (!state.me) state.me = await getMe();
      
      const [receipts, notifs] = await Promise.all([
        apiFetch('/api/receipts/pending?include_signed=true'),
        apiFetch('/api/notifications')
      ]);
      
      state.receipts = Array.isArray(receipts) ? receipts : (receipts?.receipts || []);
      state.notifications = notifs?.notifications || [];
      
      const orgInfo = el('orgInfo', container);
      if (orgInfo && state.me) {
        orgInfo.innerText = `Organización: ${state.me.organization_name || 'N/D'} [${state.me.organization_id?.substring(0,8) || ''}]`;
      }

      renderKPIs(container, state);
      renderNotifications(container, state.notifications);
      renderReceipts(container, state, {
        onSign: (r) => navigate('empresa/historial'), // Standardizing sign path
        onGetToken: async (r) => {
          const res = await apiFetch(`/api/receipts/${r.id}/token`, { method: 'POST' });
          await navigator.clipboard.writeText(`${window.location.host}${res.sign_url}`);
          showToast('Enlace copiado', 'success');
        },
        onDelete: async (id) => {
          if (await confirmAction('¿Eliminar recibo?')) {
            await apiFetch(`/api/receipts/${id}`, { method: 'DELETE' });
            refreshAll();
          }
        },
        onSelectionChange: () => {
          const count = state.selectedIds.size;
          const bar = el('bulkActions', container);
          if (count > 0) {
            bar.classList.remove('hidden');
            el('selectedCount', container).innerText = `${count} seleccionados`;
          } else {
            bar.classList.add('hidden');
          }
        },
        onViewProfile: () => navigate('employees')
      });
    } catch (err) {
      showError(container, err);
    }
  }

  // Bindings
  el('btnRefresh', container).onclick = refreshAll;
  el('btnRefreshNotifs', container).onclick = refreshAll;
  el('btnNewBatch', container).onclick = () => openUploadModal(container, { 
    organization_id: state.me.organization_id, 
    onUploadComplete: refreshAll 
  });
  
  el('searchInput', container).oninput = (e) => {
    state.search = e.target.value;
    renderReceipts(container, state, {}); // Fast local filter
  };

  el('filterStatus', container).onchange = (e) => {
    state.filterStatus = e.target.value;
    renderReceipts(container, state, {});
  };

  await refreshAll();
}
