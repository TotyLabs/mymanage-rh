import { el, formatCuil, navigate, Store } from '../../common.js';
import { createStatusBadge } from '../../utils-ui.js';
import { LABELS } from '../../constants.js';

export function renderEmployeesTable(container, state, callbacks) {
  const tbody = container.querySelector('#employeesTable tbody');
  const emptyEl = el('employeesEmpty', container);
  const wrapEl = el('employeesTableWrap', container);

  if (!tbody) return;
  tbody.innerHTML = '';

  let visible = [...state.employees];
  
  if (state.search.trim()) {
    const search = state.search.toLowerCase();
    visible = visible.filter(e => 
      (e.full_name || '').toLowerCase().includes(search) || 
      (e.dni || '').includes(search)
    );
  }

  // Sorting
  const { sort } = Store.getState();
  visible.sort((a, b) => {
    let vA, vB;
    if (sort.column === 'name') { vA = (a.full_name || '').toLowerCase(); vB = (b.full_name || '').toLowerCase(); }
    else if (sort.column === 'dni') { vA = a.dni || ''; vB = b.dni || ''; }
    else if (sort.column === 'status') { vA = a.status || ''; vB = b.status || ''; }
    else { vA = a[sort.column] || ''; vB = b[sort.column] || ''; }

    if (vA < vB) return sort.direction === 'asc' ? -1 : 1;
    if (vA > vB) return sort.direction === 'asc' ? 1 : -1;
    return 0;
  });

  if (!visible.length) {
    emptyEl.classList.remove('hidden');
    wrapEl.classList.add('hidden');
    return;
  }
  emptyEl.classList.add('hidden');
  wrapEl.classList.remove('hidden');

  visible.forEach(emp => {
    const tr = document.createElement('tr');
    
    tr.innerHTML = `
      <td class="empresa-check-col"><input type="checkbox" class="emp-select" data-id="${emp.id}" ${state.selectedIds.has(emp.id) ? 'checked' : ''} /></td>
      <td><button class="empresa-employee-link">${emp.full_name || 'Sin nombre'}</button></td>
      <td>${emp.file_number || '-'}</td>
      <td>${emp.dni || '-'}</td>
      <td>${formatCuil(emp.cuil)}</td>
      <td class="status-cell"></td>
      <td class="text-center">${emp.receipts_count || 0}</td>
      <td class="table-actions">
        <div class="form-row">
          <button class="btn btn-ghost btn-sm btn-edit">Editar</button>
          <button class="btn btn-ghost btn-sm btn-dni">DNI OCR</button>
        </div>
      </td>
    `;

    tr.querySelector('.status-cell').appendChild(createStatusBadge(emp.status));
    
    tr.querySelector('.empresa-employee-link').onclick = () => callbacks.onView(emp.id);
    tr.querySelector('.btn-edit').onclick = () => callbacks.onEdit(emp.id);
    tr.querySelector('.btn-dni').onclick = () => callbacks.onDniOcr(emp.id);
    
    const checkbox = tr.querySelector('.emp-select');
    checkbox.onchange = () => {
      if (checkbox.checked) state.selectedIds.add(emp.id);
      else state.selectedIds.delete(emp.id);
      callbacks.onSelectionChange();
    };

    tbody.appendChild(tr);
  });
}
