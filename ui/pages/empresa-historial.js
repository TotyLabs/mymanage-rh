import { apiFetch, showError, getApiBase } from '../common.js';

function el(id, ctx = document) {
  return (ctx || document).querySelector(`#${id}`);
}

function badgeForStatus(status) {
  const span = document.createElement('span');
  span.className = 'badge badge-dot';

  if (!status) {
    span.classList.add('neutral');
    span.textContent = 'N/D';
  } else if (status === 'pending_employee_signature') {
    span.classList.add('warning');
    span.textContent = 'Pendiente firma empleado';
  } else if (status === 'pending_employer_signature') {
    span.classList.add('warning');
    span.textContent = 'Pendiente firma empresa';
  } else if (status === 'signed') {
    span.classList.add('success');
    span.textContent = 'Completado';
  } else if (status === 'rejected') {
    span.classList.add('error');
    span.textContent = 'Observado';
  } else if (status === 'pending_match') {
    span.classList.add('neutral');
    span.textContent = 'En revisión';
  } else {
    span.classList.add('neutral');
    span.textContent = status;
  }

  return span;
}

export async function render(container) {
  const state = {
    activeTab: 'PAYROLL',
    receipts: [],
    documents: [],
    grouped: {},
    mode: 'date',
    selectedEmployeeKey: null,
    searchText: '',
    loading: false
  };

  container.innerHTML = `
    <section class="empresa-historial-hub">
      <div class="action-bar empresa-historial-bar mb-32">
        <div>
          <h1 class="card-title empresa-page-title mb-8">Hub de Historial y Documentos</h1>
          <div class="small-muted">Repositorio centralizado de toda la documentación organizacional.</div>
        </div>

        <div class="flex items-center gap-12 empresa-historial-actions">
           <button id="btnHubUpload" class="btn btn-primary">Subir Documentos</button>
           <button id="btnRefreshHub" class="btn btn-ghost btn-sm">Actualizar</button>
        </div>
      </div>

      <div class="tabs empresa-tabs mb-24">
        <button class="tab-item active" data-tab="PAYROLL">Recibos de Nómina</button>
        <button class="tab-item" data-tab="TRANSFER">Transferencias Bancarias</button>
        <button class="tab-item" data-tab="ART">Listados ART</button>
        <button class="tab-item" data-tab="UNEMPLOYMENT">Fondo de Desempleo</button>
        <button class="tab-item" data-tab="MISC">Varios</button>
      </div>

      <div id="hubContent" class="hub-tab-content">
         <!-- Sections will be injected here -->
         <div id="hubLoading" class="empresa-history-loading">Cargando repositorio...</div>
         <div id="hubEmpty" class="hidden"></div>
         
         <div id="payrollView" class="empresa-hub-view">
            <div class="flex-between mb-16">
              <div class="flex items-center gap-12 empresa-history-controls">
                <input id="searchHistory" class="input empresa-search-input" placeholder="Buscar por DNI o nombre..." style="max-width:250px" />
                <div class="empresa-history-mode-toggle" role="group" aria-label="Modo de vista">
                  <button type="button" class="empresa-history-mode active" data-mode="date" aria-pressed="true">Cronológica</button>
                  <button type="button" class="empresa-history-mode" data-mode="employee" aria-pressed="false">Por colaborador</button>
                </div>
              </div>
            </div>
            <div id="historyTree" class="empresa-history-tree"></div>
         </div>

         <div id="genericView" class="empresa-hub-view hidden">
            <div class="table-container">
              <table class="table" id="docsTable">
                <thead>
                  <tr>
                    <th>Fecha de Carga</th>
                    <th>Referencia / Período</th>
                    <th>Nombre de Archivo</th>
                    <th>Acciones</th>
                  </tr>
                </thead>
                <tbody id="docsTableBody"></tbody>
              </table>
            </div>
         </div>
      </div>
    </section>

    <!-- Hidden file input for payment certificates (legacy) -->
    <input type="file" id="paymentUploadInput" class="hidden" accept="image/*,application/pdf" />
  `;

  // --- TAB SWITCH LOGIC ---
  const tabs = container.querySelectorAll('.tab-item');
  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      tabs.forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      state.activeTab = tab.dataset.tab;
      switchTab();
    });
  });

  function switchTab() {
    const isPayroll = state.activeTab === 'PAYROLL';
    el('payrollView', container).classList.toggle('hidden', !isPayroll);
    el('genericView', container).classList.toggle('hidden', isPayroll);
    
    // Auto-refresh when switching
    if (isPayroll) loadHistory();
    else loadGenericDocuments();
  }

  // --- UPLOAD BRIDGE ---
  el('btnHubUpload', container).onclick = () => {
    // Redirect to dashboard with pre-filled type
    location.hash = `#/empresa/dashboard?action=upload&type=${state.activeTab}`;
  };

  // --- DATA FETCHING (PAYROLL) ---
  async function loadHistory() {
    const hubLoading = el('hubLoading', container);
    const tree = el('historyTree', container);
    const empty = el('hubEmpty', container);
    
    hubLoading.classList.remove('hidden');
    tree.classList.add('hidden');
    empty.classList.add('hidden');

    try {
      const res = await apiFetch('/api/receipts/history');
      state.receipts = res.receipts || [];
      groupReceipts();
      renderTree();
    } catch (e) {
      showError(hubLoading, e);
    }
  }

  function groupReceipts() {
    const tree = {};
    let filtered = [...state.receipts];
    if (state.searchText) {
      const q = state.searchText.toLowerCase();
      filtered = filtered.filter(r => 
        `${r.full_name || r.employee_name || ''} ${r.dni || r.employee_dni || ''} ${r.period_label || r.period || ''}`.toLowerCase().includes(q)
      );
    }

    filtered.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));

    if (state.mode === 'date') {
      Object.assign(tree, groupChronologically(filtered));
    } else {
      filtered.forEach((receipt) => {
        const name = receipt.employee_name || receipt.full_name || 'Sin empleado';
        const key = receipt.employee_id ? `id:${receipt.employee_id}` : `name:${name.trim().toLowerCase()}`;
        if (!tree[key]) tree[key] = { name, receipts: [] };
        tree[key].receipts.push(receipt);
      });
    }
    state.grouped = tree;
  }

  function groupChronologically(receipts) {
    const grouped = {};
    const monthNames = [
      'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
      'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre',
    ];

    receipts.forEach((receipt) => {
      const date = new Date(receipt.created_at);
      const year = date.getFullYear();
      const month = monthNames[date.getMonth()];
      const day = date.toLocaleDateString('es-AR', { day: '2-digit', month: '2-digit', year: 'numeric' });
      if (!grouped[year]) grouped[year] = {};
      if (!grouped[year][month]) grouped[year][month] = {};
      if (!grouped[year][month][day]) grouped[year][month][day] = [];
      grouped[year][month][day].push(receipt);
    });

    return grouped;
  }

  function renderTree() {
    const treeEl = el('historyTree', container);
    const loadingEl = el('hubLoading', container);
    const emptyEl = el('hubEmpty', container);

    if (!state.receipts.length || !Object.keys(state.grouped).length) {
      loadingEl.classList.add('hidden');
      emptyEl.innerHTML = `
        <div class="empty-state">
          <div class="empty-title">${state.receipts.length ? 'Sin resultados' : 'Sin registros en Nómina'}</div>
          <div class="empty-desc">${state.receipts.length ? 'Probá con otro nombre, DNI o período.' : 'Los recibos procesados aparecerán aquí cronológicamente.'}</div>
        </div>
      `;
      emptyEl.classList.remove('hidden');
      return;
    }

    loadingEl.classList.add('hidden');
    emptyEl.classList.add('hidden');
    treeEl.classList.remove('hidden');
    treeEl.innerHTML = '';

    if (state.mode === 'date') {
      renderChronologicalTree(treeEl, Object.values(state.grouped).flatMap(year =>
        Object.values(year).flatMap(month => Object.values(month).flat())
      ));
    } else {
      if (state.selectedEmployeeKey && state.grouped[state.selectedEmployeeKey]) {
        renderSelectedEmployee(treeEl, state.selectedEmployeeKey, state.grouped[state.selectedEmployeeKey]);
      } else {
        renderEmployeeSelector(treeEl);
      }
    }
  }

  function renderChronologicalTree(target, receipts) {
    const grouped = groupChronologically(receipts);
    Object.keys(grouped).sort((a, b) => b - a).forEach(year => {
      const yearHeader = document.createElement('div');
      yearHeader.className = 'empresa-history-year';
      yearHeader.textContent = year;
      target.appendChild(yearHeader);

      Object.keys(grouped[year]).forEach(month => {
        const monthHeader = document.createElement('div');
        monthHeader.className = 'empresa-history-month';
        monthHeader.textContent = month;
        target.appendChild(monthHeader);

        Object.keys(grouped[year][month]).forEach(day => {
          const group = document.createElement('div');
          group.className = 'empresa-history-day-block';
          const dayHeader = document.createElement('div');
          dayHeader.className = 'empresa-history-day';
          dayHeader.innerHTML = '<span class="empresa-history-day-dot"></span>';
          dayHeader.append(document.createTextNode(day));
          group.appendChild(dayHeader);

          const rows = document.createElement('div');
          rows.className = 'empresa-history-rows';
          grouped[year][month][day].forEach(receipt => rows.appendChild(renderReceiptRow(receipt)));
          group.appendChild(rows);
          target.appendChild(group);
        });
      });
    });
  }

  function renderEmployeeSelector(target) {
    const selector = document.createElement('div');
    selector.className = 'empresa-history-employee-grid';
    Object.entries(state.grouped)
      .sort(([, first], [, second]) => first.name.localeCompare(second.name, 'es'))
      .forEach(([key, employee]) => {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'empresa-history-employee-button';
        button.textContent = employee.name;
        button.setAttribute('aria-label', `Ver historial cronológico de ${employee.name}`);
        button.onclick = () => {
          state.selectedEmployeeKey = key;
          renderTree();
        };
        selector.appendChild(button);
      });
    target.appendChild(selector);
  }

  function renderSelectedEmployee(target, employeeKey, employee) {
    const header = document.createElement('div');
    header.className = 'empresa-history-selected-header';

    const backButton = document.createElement('button');
    backButton.type = 'button';
    backButton.className = 'btn btn-ghost btn-sm';
    backButton.textContent = '← Colaboradores';
    backButton.onclick = () => {
      state.selectedEmployeeKey = null;
      renderTree();
    };

    const title = document.createElement('h2');
    title.className = 'empresa-history-selected-name';
    title.textContent = employee.name;
    header.append(backButton, title);
    target.appendChild(header);

    const completed = employee.receipts.filter(receipt => receipt.status === 'signed').length;
    const pending = employee.receipts.filter(receipt => ['pending', 'pending_employee_signature', 'pending_employer_signature', 'pending_signature'].includes(receipt.status)).length;
    const stats = document.createElement('div');
    stats.className = 'empresa-history-stats';
    stats.innerHTML = `
      <div class="empresa-history-stat empresa-history-stat-complete"><span>Recibos completados</span><strong>${completed}</strong></div>
      <div class="empresa-history-stat empresa-history-stat-pending"><span>Recibos pendientes de firma</span><strong>${pending}</strong></div>
    `;
    target.appendChild(stats);

    renderChronologicalTree(target, employee.receipts);
  }

  function renderReceiptRow(receipt, hideEmployee = false) {
    const row = document.createElement('div');
    row.className = 'empresa-history-row';
    const dateStr = new Date(receipt.created_at).toLocaleDateString('es-AR');

    row.innerHTML = `
      <div class="empresa-history-row-left">
        <span class="small-muted empresa-history-time">${dateStr}</span>
        ${!hideEmployee ? `<span class="empresa-history-employee">${receipt.employee_name || 'N/D'}</span>` : ''}
        <span class="small-muted">Ref: ${receipt.period || 'N/D'}</span>
      </div>
      <div class="empresa-history-row-right" style="display:flex; gap:8px; align-items:center;">
      </div>
    `;
    
    const right = row.querySelector('.empresa-history-row-right');
    right.appendChild(badgeForStatus(receipt.status));

    const viewBtn = document.createElement('button');
    viewBtn.className = 'btn btn-ghost btn-sm';
    viewBtn.textContent = 'Ver PDF';
    viewBtn.onclick = () => window.open(`/api/receipts/${receipt.id}/download`, '_blank');
    right.appendChild(viewBtn);

    return row;
  }

  // --- DATA FETCHING (GENERIC DOCUMENTS) ---
  async function loadGenericDocuments() {
    const hubLoading = el('hubLoading', container);
    const table = el('genericView', container);
    const empty = el('hubEmpty', container);
    const tbody = el('docsTableBody', container);
    
    hubLoading.classList.remove('hidden');
    table.classList.add('hidden');
    empty.classList.add('hidden');
    tbody.innerHTML = '';

    try {
      const res = await apiFetch(`/api/documents/list?doc_type=${state.activeTab}`);
      state.documents = res.documents || [];
      
      if (!state.documents.length) {
        hubLoading.classList.add('hidden');
        empty.innerHTML = `
           <div class="empty-state">
             <div class="empty-title">Sin documentos disponibles</div>
             <div class="empty-desc">No se encontraron archivos en la categoría ${state.activeTab}.</div>
           </div>
        `;
        empty.classList.remove('hidden');
        return;
      }

      state.documents.forEach(doc => {
        const tr = document.createElement('tr');
        const d = new Date(doc.created_at).toLocaleString('es-AR');
        
        tr.innerHTML = `
          <td class="small-muted">${d}</td>
          <td><strong>${doc.period_label || 'Puntual'}</strong></td>
          <td class="small-muted">${doc.file_name}</td>
          <td>
            <button class="btn btn-ghost btn-sm btn-doc-view" data-id="${doc.id}">Ver / Descargar</button>
          </td>
        `;

        tr.querySelector('.btn-doc-view').onclick = () => {
            window.open(`/api/documents/${doc.id}/download`, '_blank');
        };

        tbody.appendChild(tr);
      });

      hubLoading.classList.add('hidden');
      table.classList.remove('hidden');

    } catch (e) {
      showError(hubLoading, e);
    }
  }

  // --- UTILS ---
  el('btnRefreshHub', container).onclick = () => {
    if (state.activeTab === 'PAYROLL') loadHistory();
    else loadGenericDocuments();
  };

  el('searchHistory', container).addEventListener('input', (e) => {
    state.searchText = e.target.value;
    groupReceipts();
    renderTree();
  });

  container.querySelectorAll('.empresa-history-mode').forEach((button) => {
    button.addEventListener('click', () => {
      state.mode = button.dataset.mode;
      state.selectedEmployeeKey = null;
      container.querySelectorAll('.empresa-history-mode').forEach((modeButton) => {
        const active = modeButton === button;
        modeButton.classList.toggle('active', active);
        modeButton.setAttribute('aria-pressed', String(active));
      });
      groupReceipts();
      renderTree();
    });
  });

  // Initial load
  await loadHistory();
}