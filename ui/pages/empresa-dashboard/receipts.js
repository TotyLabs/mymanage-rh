import { apiFetch, confirmAction, el, esc, getApiBase, navigate, showToast, Store } from '../../common.js';
import { createStatusBadge } from '../../utils-ui.js';
import { LABELS } from '../../constants.js';


export function getVisibleReceipts(state) {
  let visible = [...state.receipts];

  if (!state.filterStatus) {
    visible = visible.filter((receipt) => receipt.status !== 'signed');
  } else {
    visible = visible.filter((receipt) => receipt.status === state.filterStatus);
  }

  if (state.search.trim()) {
    const search = state.search.trim().toLowerCase();
    visible = visible.filter((receipt) => {
      const name = (receipt.employee_name || '').toLowerCase();
      const dni = String(receipt.employee_dni || '').toLowerCase();
      return name.includes(search) || dni.includes(search);
    });
  }

  const { sort } = Store.getState();
  visible.sort((a, b) => {
    let valA, valB;
    if (sort.column === 'name') {
      valA = (a.employee_name || '').toLowerCase();
      valB = (b.employee_name || '').toLowerCase();
    } else if (sort.column === 'dni') {
      valA = String(a.employee_dni || '');
      valB = String(b.employee_dni || '');
    } else if (sort.column === 'status') {
      valA = a.status || '';
      valB = b.status || '';
    }

    if (valA < valB) return sort.direction === 'asc' ? -1 : 1;
    if (valA > valB) return sort.direction === 'asc' ? 1 : -1;
    return 0;
  });

  return visible;
}

export function renderReceipts(container, state, callbacks) {
  const tbody = container.querySelector('#receiptsTable tbody');
  const emptyEl = el('receiptsEmpty', container);
  const wrapEl = el('receiptsTableWrap', container);

  if (!tbody) return;
  tbody.innerHTML = '';

  const visible = getVisibleReceipts(state);

  if (!visible.length) {
    emptyEl.classList.remove('hidden');
    wrapEl.classList.add('hidden');
    return;
  }

  emptyEl.classList.add('hidden');
  wrapEl.classList.remove('hidden');

  visible.forEach((receipt) => {
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
    empButton.textContent = receipt.employee_name || 'Sin nombre';
    tdEmp.appendChild(empButton);

    const tdDni = document.createElement('td');
    tdDni.textContent = receipt.employee_dni || '-';

    const tdStatus = document.createElement('td');
    tdStatus.appendChild(createStatusBadge(receipt.status, receipt.rejection_reason));

    const tdSignatures = document.createElement('td');
    const sigContainer = document.createElement('div');
    sigContainer.className = 'flex gap-4';
    const empSigned = receipt.employer_signed_at ? '✅' : '⏳';
    const usrSigned = receipt.employee_signed_at ? '✅' : '⏳';
    sigContainer.innerHTML = `<span title="Empresa">${empSigned}</span> <span title="Empleado">${usrSigned}</span>`;
    tdSignatures.appendChild(sigContainer);

    const tdActions = document.createElement('td');
    tdActions.className = 'table-actions';
    const actions = document.createElement('div');
    actions.className = 'form-row';

    // Action: Sign
    if (receipt.status === 'pending_signature' || receipt.status === 'pending_employer_signature') {
      const btn = document.createElement('button');
      btn.className = 'btn btn-primary btn-sm';
      btn.textContent = 'Firmar';
      btn.onclick = () => callbacks.onSign(receipt);
      actions.appendChild(btn);
    }

    // Action: Get Token
    if ((receipt.status || '').startsWith('pending_')) {
      const btn = document.createElement('button');
      btn.className = 'btn btn-ghost btn-sm';
      btn.textContent = 'Link';
      btn.onclick = () => callbacks.onGetToken(receipt);
      actions.appendChild(btn);
    }

    // Action: Download/Print
    if (receipt.status === 'signed') {
      const url = `${getApiBase()}/api/receipts/${receipt.id}/download`;
      const btnDown = document.createElement('button');
      btnDown.className = 'btn btn-ghost btn-sm';
      btnDown.textContent = 'Descargar';
      btnDown.onclick = () => window.open(url, '_blank', 'noopener');
      
      const btnPrint = document.createElement('button');
      btnPrint.className = 'btn btn-ghost btn-sm btn-print';
      btnPrint.dataset.url = url;
      btnPrint.textContent = 'Imprimir';
      
      actions.append(btnDown, btnPrint);
    }

    // Action: Delete
    if (receipt.status !== 'signed') {
      const btnDel = document.createElement('button');
      btnDel.className = 'btn btn-danger btn-sm';
      btnDel.textContent = 'Eliminar';
      btnDel.onclick = async () => {
        const ok = await confirmAction('¿Eliminar recibo?');
        if (ok) callbacks.onDelete(receipt.id);
      };
      actions.appendChild(btnDel);
    }

    tdActions.appendChild(actions);
    tr.append(tdCheck, tdEmp, tdDni, tdStatus, tdSignatures, tdActions);
    tbody.appendChild(tr);

    checkbox.addEventListener('change', () => {
      if (checkbox.checked) state.selectedIds.add(receipt.id);
      else state.selectedIds.delete(receipt.id);
      callbacks.onSelectionChange();
    });

    empButton.onclick = () => callbacks.onViewProfile(receipt.employee_id || receipt.employee_name);
  });
}
