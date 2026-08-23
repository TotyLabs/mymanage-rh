import { el } from '../../common.js';

export function renderKPIs(container, state) {
  const counts = {
    pending: 0,
    signed: 0,
    pending_match: 0,
    rejected: 0,
    total: state.receipts.length
  };

  state.receipts.forEach(r => {
    if (r.status === 'signed') counts.signed++;
    else if (r.status === 'pending_match') counts.pending_match++;
    else if (r.status === 'rejected') counts.rejected++;
    else counts.pending++;
  });

  const kpiBox = el('kpis', container);
  if (!kpiBox) return;

  kpiBox.innerHTML = `
    <div class="kpi-card">
      <div class="kpi-label">Pendientes</div>
      <div class="kpi-value tabular-nums">${counts.pending}</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">Firmados</div>
      <div class="kpi-value tabular-nums">${counts.signed}</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">Observados</div>
      <div class="kpi-value tabular-nums">${counts.rejected}</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">Total Gral.</div>
      <div class="kpi-value tabular-nums">${counts.total}</div>
    </div>
  `;
}
