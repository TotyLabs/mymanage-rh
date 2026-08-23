import { apiFetch, showError, getMe, getApiBase, showToast, el } from '../common.js';
import { createStatusBadge, renderEmptyState } from '../utils-ui.js';

export async function render(container) {
  const state = {
    me: null,
    receipts: [],
    activeSection: 'PAYROLL',
  };

  container.innerHTML = `
    <div class="action-bar">
      <div>
        <h1 class="card-title mb-8">Mis Documentos</h1>
        <div id="userInfo" class="small-muted">Cargando perfil...</div>
      </div>
    </div>

    <div class="tabs mb-24">
      <button class="tab-item active" data-section="PAYROLL">Recibos</button>
      <button class="tab-item" data-section="UNEMPLOYMENT">Fondo de Desempleo</button>
      <button class="tab-item" data-section="MISC">Varios</button>
    </div>

    <div id="notif-alert-box" class="hidden mb-24">
        <div class="card p-16 border-left-brand bg-brand-50 flex justify-between items-center cursor-pointer" onclick="location.hash='#/empleado/notificaciones'">
            <div class="flex items-center">
                <span class="notification-badge mr-12" style="position: static; padding: 4px 8px;">NUEVO</span>
                <div>
                    <div class="font-bold text-brand-900">Tenés mensajes nuevos de la empresa</div>
                    <div class="text-sm text-brand-700">Hacé click acá para leer las notificaciones pendientes.</div>
                </div>
            </div>
            <div class="text-brand-400">
                <svg width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M9 5l7 7-7 7"></path></svg>
            </div>
        </div>
    </div>

    <section class="card">
      <div class="card-header">
        <h2 class="card-title">Listado de Recibos</h2>
      </div>

      <div id="receiptsEmpty" class="hidden"></div>

      <div id="receiptsTableWrap" class="table-container hidden">
        <table id="receiptsTable" class="table">
          <thead>
            <tr>
              <th>Fecha</th>
              <th>Período</th>
              <th>Empresa</th>
              <th>Estado</th>
              <th>Tipo</th>
              <th>Acciones</th>
            </tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>
    </section>
  `;

  const userInfoEl = el('userInfo', container);
  const emptyEl = el('receiptsEmpty', container);
  const tableWrapEl = el('receiptsTableWrap', container);
  const tbodyEl = container.querySelector('#receiptsTable tbody');

  function showEmpty(html) {
    emptyEl.innerHTML = html;
    emptyEl.classList.remove('hidden');
    tableWrapEl.classList.add('hidden');
  }

  function getSectionLabel(type) {
    switch ((type || 'PAYROLL').toUpperCase()) {
      case 'UNEMPLOYMENT':
        return 'Fondo de Desempleo';
      case 'MISC':
        return 'Varios';
      default:
        return 'Recibos';
    }
  }

  function getVisibleReceipts() {
    return state.receipts.filter((receipt) => {
      const type = (receipt.doc_type || receipt.document_type || 'PAYROLL').toUpperCase();
      return type === state.activeSection;
    });
  }

  function showTable() {
    emptyEl.classList.add('hidden');
    tableWrapEl.classList.remove('hidden');
  }

  function renderSectionEmpty() {
    showEmpty(renderEmptyState(`No hay documentos en la sección ${getSectionLabel(state.activeSection)}.`, 'Si tenés documentos firmados en esta categoría, deberían aparecer aquí.'));
  }

  async function loadData() {
    try {
      const response = await getMe();
      state.me = response?.user || response || null;
      if (state.me) {
        userInfoEl.textContent = `${state.me.full_name || ''} — ${state.me.email || ''}`;
      }
      await loadReceipts();
      await checkUnreadNotifs();
    } catch (error) {
      showError(userInfoEl, error);
    }
  }

  async function checkUnreadNotifs() {
    try {
      const res = await apiFetch('/api/notifications/unread-count');
      if (res.count > 0) {
        const box = el('notif-alert-box', container);
        if (box) box.classList.remove('hidden');
      }
    } catch (e) {}
  }

  function renderReceiptsTable(receipts) {
    tbodyEl.innerHTML = '';
    if (!receipts.length) {
      renderSectionEmpty();
      return;
    }
    receipts.forEach((receipt) => {
      const tr = document.createElement('tr');

      const dateTd = document.createElement('td');
      dateTd.textContent = receipt.date ? new Date(receipt.date).toLocaleString('es-AR') : '—';

      const periodTd = document.createElement('td');
      periodTd.textContent = receipt.period || 'N/D';

      const companyTd = document.createElement('td');
      companyTd.textContent = receipt.company_name;

      const statusTd = document.createElement('td');
      statusTd.appendChild(createStatusBadge(receipt.status));
      const typeTd = document.createElement('td');
      typeTd.textContent = getSectionLabel(receipt.doc_type || receipt.document_type);

      const actionsTd = document.createElement('td');
      actionsTd.className = 'table-actions';
      const actionsRow = document.createElement('div');
      actionsRow.className = 'form-row';
      actionsTd.appendChild(actionsRow);

      const base = getApiBase();
      // Use documents endpoints for company_document entries. For Fondo de Desempleo
      // (UNEMPLOYMENT) use the preview endpoint to open inline instead of forcing download.
      const url = (receipt.source === 'company_document')
        ? ((receipt.doc_type || '').toUpperCase() === 'UNEMPLOYMENT'
            ? `${base}/api/documents/${receipt.id}/preview`
            : `${base}/api/documents/${receipt.id}/download`)
        : `${base}/api/receipts/${receipt.id}/download`;

      if (receipt.can_sign) {
        const signBtn = document.createElement('button');
        signBtn.type = 'button';
        signBtn.className = 'btn btn-primary btn-sm btn-simple-sign';
        signBtn.dataset.id = receipt.id;
        signBtn.textContent = 'Firmar ahora';
        
        const viewBtn = document.createElement('button');
        viewBtn.className = 'btn btn-ghost btn-sm';
        viewBtn.textContent = 'Ver PDF';
        viewBtn.onclick = () => window.open(url, '_blank', 'noopener');
        
        actionsRow.append(viewBtn, signBtn);
      } else if (receipt.status === 'signed') {
        const downloadBtn = document.createElement('button');
        downloadBtn.className = 'btn btn-secondary btn-sm';
        downloadBtn.textContent = 'Descargar';
        downloadBtn.onclick = () => window.open(url, '_blank', 'noopener');

        const printBtn = document.createElement('button');
        printBtn.type = 'button';
        printBtn.className = 'btn btn-ghost btn-sm btn-print';
        printBtn.dataset.url = url;
        printBtn.textContent = 'Imprimir';

        actionsRow.append(downloadBtn, printBtn);
      } else {
        // Non-signable, non-signed (e.g. pending_employer_signature, pending_match)
        const viewBtn = document.createElement('button');
        viewBtn.className = 'btn btn-ghost btn-sm';
        viewBtn.textContent = 'Ver PDF';
        viewBtn.onclick = () => window.open(url, '_blank', 'noopener');
        actionsRow.append(viewBtn);
      }

      tr.append(dateTd, periodTd, companyTd, statusTd, typeTd, actionsTd);
      tbodyEl.appendChild(tr);
    });
  }

  function setActiveSection(section) {
    state.activeSection = section;
    const tabs = container.querySelectorAll('.tab-item');
    tabs.forEach((tab) => {
      tab.classList.toggle('active', tab.dataset.section === section);
    });
    const visibleReceipts = getVisibleReceipts();
    if (!visibleReceipts.length) {
      renderSectionEmpty();
    } else {
      renderReceiptsTable(visibleReceipts);
      showTable();
    }
  }

  async function loadReceipts() {
    if (!state.me) return;

    try {
      const response = await apiFetch(`/api/receipts/my-history`);
      state.receipts = response?.receipts || [];

      if (!state.receipts.length) {
        showEmpty(renderEmptyState('Todavía no tenés documentos disponibles', 'Cuando tu empresa cargue o firme documentos asociados a tu usuario, vas a poder revisarlos desde esta sección.'));
        return;
      }

      setActiveSection(state.activeSection);
    } catch (error) {
      showError(emptyEl, error);
      emptyEl.classList.remove('hidden');
      tableWrapEl.classList.add('hidden');
    }
  }

  const tabItems = container.querySelectorAll('.tab-item');
  tabItems.forEach((tab) => {
    tab.addEventListener('click', () => setActiveSection(tab.dataset.section));
  });

  tableWrapEl.addEventListener('click', async (event) => {
    const target = event.target;
    if (!target) return;

    if (target.classList.contains('btn-print')) {
      const url = target.getAttribute('data-url');
      if (!url) return;
      const iframe = document.createElement('iframe');
      iframe.className = 'hidden';
      iframe.src = url;
      document.body.appendChild(iframe);
      iframe.onload = () => {
        setTimeout(() => {
          iframe.focus();
          iframe.contentWindow?.print();
          setTimeout(() => { if (iframe.parentNode) iframe.parentNode.removeChild(iframe); }, 10000);
        }, 500);
      };
      return;
    }

    if (target.classList.contains('btn-simple-sign')) {
      const receiptId = target.getAttribute('data-id');
      if (!receiptId) return;

      target.disabled = true;
      target.textContent = 'Firmando...';

      try {
        const response = await apiFetch(`/api/receipts/${receiptId}/token/me`, { method: 'POST' });
        if (response.token) {
          // Redirect the user to the frictionless flow for this token
          window.location.hash = `#/sign/${response.token}`;
        }
      } catch (error) {
        target.disabled = false;
        target.textContent = 'Firmar ahora';
        const message = error?.body?.detail ? String(error.body.detail) : 'Error al procesar la firma.';
        if (message === 'signature_required') {
          alert('Primero debés registrar tu firma en la sección Mi Perfil para poder firmar recibos.');
          location.hash = '#/empleado/perfil';
        } else {
          alert('Hubo un problema al preparar tu firma: ' + message);
        }
      }
    }
  });

  await loadData();
}
