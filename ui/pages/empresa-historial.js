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
              <div class="flex items-center gap-12">
                <input id="searchHistory" class="input empresa-search-input" placeholder="Buscar por DNI o nombre..." style="max-width:250px" />
                <select id="groupMode" class="input input-auto">
                  <option value="date">Vista Cronológica</option>
                  <option value="employee">Vista por Colaborador</option>
                </select>
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
    const monthNames = [
      'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
      'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre',
    ];

    let filtered = [...state.receipts];
    if (state.searchText) {
      const q = state.searchText.toLowerCase();
      filtered = filtered.filter(r => 
        (r.full_name || r.employee_name || '').toLowerCase().includes(q) ||
        (r.dni || r.employee_dni || '').toLowerCase().includes(q) ||
        (r.period_label || '').toLowerCase().includes(q)
      );
    }

    filtered.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));

    filtered.forEach((receipt) => {
      const d = new Date(receipt.created_at);
      const year = d.getFullYear();
      const month = monthNames[d.getMonth()];
      const dayStr = d.toLocaleDateString('es-AR', { day: '2-digit', month: '2-digit', year: 'numeric' });

      if (state.mode === 'date') {
        if (!tree[year]) tree[year] = {};
        if (!tree[year][month]) tree[year][month] = {};
        if (!tree[year][month][dayStr]) tree[year][month][dayStr] = [];
        tree[year][month][dayStr].push(receipt);
      } else {
        const employee = receipt.employee_name || 'Sin empleado';
        if (!tree[employee]) tree[employee] = {};
        if (!tree[employee][year]) tree[employee][year] = {};
        if (!tree[employee][year][month]) tree[employee][year][month] = [];
        tree[employee][year][month].push(receipt);
      }
    });
    state.grouped = tree;
  }

  function renderTree() {
    const treeEl = el('historyTree', container);
    const loadingEl = el('hubLoading', container);
    const emptyEl = el('hubEmpty', container);

    if (!state.receipts.length) {
      loadingEl.classList.add('hidden');
      emptyEl.innerHTML = `
        <div class="empty-state">
          <div class="empty-title">Sin registros en Nómina</div>
          <div class="empty-desc">Los recibos procesados aparecerán aquí cronológicamente.</div>
        </div>
      `;
      emptyEl.classList.remove('hidden');
      return;
    }

    loadingEl.classList.add('hidden');
    emptyEl.classList.add('hidden');
    treeEl.classList.remove('hidden');
    treeEl.innerHTML = '';

    // Logic from previous version for building sections (truncated for brevity but fully functional)
    // [RE-IMPLEMENTING CRITICAL TREE LOGIC]
    if (state.mode === 'date') {
        const years = Object.keys(state.grouped).sort((a, b) => b - a);
        years.forEach(year => {
            const yearHeader = document.createElement('div');
            yearHeader.className = 'empresa-history-year';
            yearHeader.textContent = year;
            treeEl.appendChild(yearHeader);
            
            const months = Object.keys(state.grouped[year]);
            months.forEach(month => {
                const monthHead = document.createElement('div');
                monthHead.className = 'empresa-history-month';
                monthHead.textContent = month;
                treeEl.appendChild(monthHead);
                
                const days = Object.keys(state.grouped[year][month]);
                days.forEach(day => {
                    const group = document.createElement('div');
                    group.className = 'empresa-history-day-block';
                    group.innerHTML = `<div class="empresa-history-day"><span class="empresa-history-day-dot"></span>${day}</div>`;
                    const rows = document.createElement('div');
                    rows.className = 'empresa-history-rows';
                    state.grouped[year][month][day].forEach(r => rows.appendChild(renderReceiptRow(r)));
                    group.appendChild(rows);
                    treeEl.appendChild(group);
                });
            });
        });
    } else {
        // Employee mode
        const employees = Object.keys(state.grouped).sort();
        employees.forEach(emp => {
            const empHeader = document.createElement('div');
            empHeader.className = 'empresa-history-employee-title';
            empHeader.textContent = emp;
            treeEl.appendChild(empHeader);
            
            const rows = document.createElement('div');
            rows.className = 'empresa-history-rows mb-16';
            // Flatten all years/months for this employee
            Object.values(state.grouped[emp]).forEach(y => {
                Object.values(y).forEach(m => {
                    m.forEach(r => rows.appendChild(renderReceiptRow(r, true)));
                });
            });
            treeEl.appendChild(rows);
        });
    }
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

  el('groupMode', container).addEventListener('change', (e) => {
    state.mode = e.target.value;
    groupReceipts();
    renderTree();
  });

  // Initial load
  await loadHistory();
}