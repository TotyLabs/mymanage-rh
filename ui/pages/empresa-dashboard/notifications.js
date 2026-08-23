import { apiFetch, el, esc, getApiBase, openModal, showToast } from '../../common.js';

export function renderNotifications(container, notifs) {
  const tbody = container.querySelector('#notifsTable tbody');
  const empty = el('notifsEmpty', container);
  
  if (!tbody) return;
  tbody.innerHTML = '';
  
  if (!notifs || !notifs.length) {
    if (empty) empty.classList.remove('hidden');
    return;
  }
  if (empty) empty.classList.add('hidden');

  notifs.forEach(n => {
    const tr = document.createElement('tr');
    tr.id = `notif-row-${n.id}`;

    const stTd = document.createElement('td');
    const badge = document.createElement('span');
    badge.id = `notif-badge-${n.id}`;
    badge.className = 'badge';
    if (n.is_read) {
      badge.classList.add('neutral');
      badge.textContent = 'Visto';
    } else {
      badge.classList.add('info');
      badge.textContent = 'Nuevo';
    }
    stTd.appendChild(badge);

    const empTd = document.createElement('td');
    empTd.innerHTML = `<strong>${esc(n.sender_name || 'Empleado')}</strong><br><small class="small-muted">${esc(n.sender_email)}</small>`;

    const dateTd = document.createElement('td');
    const d = n.created_at ? new Date(n.created_at) : null;
    dateTd.textContent = d ? d.toLocaleString('es-AR') : '-';

    const msgTd = document.createElement('td');
    const limit = 50;
    const cleanMsg = n.message || '';
    if (cleanMsg.length > limit) {
      msgTd.innerHTML = `
        <span class="text-muted">${esc(cleanMsg).substring(0, limit)}...</span>
        <button class="btn-link btn-sm p-0 ml-4" style="text-decoration: underline; color: var(--brand-700); border: none; cursor: pointer; font-weight: 500;">Ver más</button>
      `;
      msgTd.querySelector('button').onclick = () => openNotifModal(container, n, badge);
    } else {
      msgTd.textContent = cleanMsg;
    }

    const actTd = document.createElement('td');
    if (n.has_file) {
      const url = `${getApiBase()}/api/notifications/${n.id}/file`;
      const fl = document.createElement('a');
      fl.href = url;
      fl.target = '_blank';
      fl.className = 'btn btn-secondary btn-sm';
      fl.textContent = 'Ver Adjunto';
      actTd.appendChild(fl);
    } else {
      actTd.innerHTML = '<span class="small-muted">Sin adjuntos</span>';
    }
    
    tr.append(stTd, empTd, dateTd, msgTd, actTd);
    tbody.appendChild(tr);
  });
}

export async function openNotifModal(container, n, badgeElement) {
  const modal = el('notifDetailsModal', container);
  if (!modal) return;

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

  openModal('notifDetailsModal', container);
}
