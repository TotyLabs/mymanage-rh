export function createStatusBadge(status) {
  const badge = document.createElement('span');
  badge.className = 'badge badge-dot';

  if (!status) {
    badge.classList.add('neutral');
    badge.textContent = 'Sin estado';
    return badge;
  }

  if (status === 'signed') {
    badge.classList.add('success');
    badge.textContent = 'Firmado';
    return badge;
  }

  if (status === 'pending' || status === 'pending_employee_signature' || status === 'pending_signature') {
    badge.classList.add('warning');
    badge.textContent = 'Pendiente';
    return badge;
  }

  if (status === 'rejected') {
    badge.classList.add('error');
    badge.textContent = 'Rechazado';
    return badge;
  }

  badge.classList.add('neutral');
  badge.textContent = status.replace(/_/g, ' ');
  return badge;
}

export function renderEmptyState(messageTitle, messageText) {
  return `
    <div class="empty-state">
      <div class="empty-title">${messageTitle}</div>
      <div class="empty-desc">${messageText}</div>
    </div>
  `;
}
