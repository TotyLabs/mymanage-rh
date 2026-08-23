import { apiFetch, apiUrl, showError, esc, escAttr } from './common.js';

const $ = (id) => document.getElementById(id);

const state = {
  modalCanvas: null,
  modalCtx: null,
  modalReceiptId: null,
  drawing: false,
  lastPoint: { x: 0, y: 0 },
};

const UI = {
  uploadMsg: () => $('uploadMsg'),
  organizationId: () => $('organization_id'),
  periodLabel: () => $('period_label'),
  pdfFile: () => $('pdffile'),
  batchStats: () => $('batchStats'),
  sampleUrls: () => $('sampleUrls'),

  receiptsMsg: () => $('receiptsMsg'),
  filterStatus: () => $('filterStatus'),
  receiptsTableBody: () => document.querySelector('#receiptsTable tbody'),

  signModal: () => $('signModal'),
  modalReceiptId: () => $('modalReceiptId'),
  modalMsg: () => $('modalMsg'),
  modalResult: () => $('modalResult'),
  modalCanvas: () => $('modalCanvas'),

  adminInfo: () => $('adminInfo'),
  btnUpload: () => $('btnUpload'),
  btnRefreshReceipts: () => $('btnRefreshReceipts'),
  btnLogout: () => $('btnLogout'),
  modalClose: () => $('modalClose'),
  modalSubmit: () => $('modalSubmit'),
};

function setHTML(element, html) {
  if (element) element.innerHTML = html;
}

function setText(element, text) {
  if (element) element.innerText = text;
}

function clearElement(element) {
  if (element) element.innerHTML = '';
}

function showSuccess(element, message) {
  setHTML(element, `<div class="success">${esc(message)}</div>`);
}

function getSelectedFile() {
  return UI.pdfFile()?.files?.[0] || null;
}

async function checkSession() {
  try {
    const me = await apiFetch('/api/auth/me');

    if (UI.adminInfo()) {
      setText(UI.adminInfo(), `Conectado como: ${me.email} (${me.role})`);
    }

    return me;
  } catch (error) {
    window.location.href = 'index.html';
    return null;
  }
}

async function uploadBatch() {
  const msg = UI.uploadMsg();
  clearElement(msg);

  const organizationId = UI.organizationId()?.value.trim();
  const periodLabel = UI.periodLabel()?.value.trim();
  const file = getSelectedFile();

  if (!organizationId || !periodLabel || !file) {
    showError(msg, 'Completá organización, período y archivo PDF.');
    return;
  }

  const formData = new FormData();
  formData.append('organization_id', organizationId);
  formData.append('period_label', periodLabel);
  formData.append('pdf', file);

  try {
    const response = await fetch(apiUrl('/api/batches/upload'), {
      method: 'POST',
      body: formData,
      credentials: 'include',
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
    });

    if (!response.ok) {
      throw { status: response.status, body: await response.text() };
    }

    const data = await response.json();

    showSuccess(msg, 'Archivo subido correctamente.');

    setText(
      UI.batchStats(),
      `Páginas: ${data.total_pages}, creados: ${data.created_receipts}, vinculados: ${data.matched_receipts}, pendientes: ${data.pending_signature}`
    );

    renderSampleUrls(data.sample_sign_urls || []);
  } catch (error) {
    showError(msg, error);
    console.error('Error al subir batch:', error);
  }
}

function renderSampleUrls(urls) {
  const list = UI.sampleUrls();
  clearElement(list);

  if (!list) return;

  if (!Array.isArray(urls) || urls.length === 0) {
    list.innerHTML = '<li class="small-muted">No hay enlaces de firma de ejemplo.</li>';
    return;
  }

  urls.forEach((urlValue) => {
    const li = document.createElement('li');
    li.className = 'sample-url-item';

    li.innerHTML = `
      <div class="sample-url-link-row">
        <span>${esc(urlValue)}</span>
        <a href="${escAttr(urlValue)}" target="_blank" rel="noopener noreferrer" class="link">
          Abrir enlace
        </a>
      </div>
      <div class="form-row mt-8">
        <input class="input sendEmail" placeholder="empleado@mail.com" />
        <button class="btn btn-secondary btn-send-email">Enviar por Mail</button>
      </div>
    `;

    const sendButton = li.querySelector('.btn-send-email');
    const emailInput = li.querySelector('.sendEmail');

    sendButton?.addEventListener('click', () => {
      const to = emailInput?.value.trim();

      if (!to) {
        alert('Ingresá un correo electrónico de destino.');
        return;
      }

      const mailUrl =
        `https://mail.google.com/mail/?view=cm&fs=1` +
        `&to=${encodeURIComponent(to)}` +
        `&su=${encodeURIComponent('Firma de recibo')}` +
        `&body=${encodeURIComponent(`Por favor, firmá el recibo desde este enlace: ${urlValue}`)}`;

      window.open(mailUrl, '_blank', 'noopener');
    });

    list.appendChild(li);
  });
}

async function getReceipts(status = '') {
  const data = await apiFetch('/api/receipts/pending');
  const items = Array.isArray(data) ? data : (data.receipts || []);

  if (!status) return items;
  return items.filter((item) => item.status === status);
}

function createActionLink(receipt) {
  if (!receipt.sign_url) return null;

  const link = document.createElement('a');
  link.href = receipt.sign_url;
  link.target = '_blank';
  link.rel = 'noopener noreferrer';
  link.className = 'link';
  link.innerText = 'Abrir enlace de firma';

  return link;
}

function createEmployerSignButton(receipt) {
  const button = document.createElement('button');
  button.className = 'btn btn-secondary ml-8';
  button.innerText = 'Firmar como empleador';
  button.addEventListener('click', () => openSignModal(receipt.id));
  return button;
}

function renderReceiptsTable(items) {
  const tbody = UI.receiptsTableBody();
  if (!tbody) return;

  clearElement(tbody);

  if (!Array.isArray(items) || items.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" class="small-muted">No hay recibos disponibles.</td></tr>';
    return;
  }

  items.forEach((item) => {
    const tr = document.createElement('tr');

    tr.innerHTML = `
      <td>${esc(item.employee || '')}</td>
      <td>${esc(item.period || '')}</td>
      <td>${esc(item.status || '')}</td>
      <td>${esc(item.employer_signed_at || '')}</td>
      <td>${esc(item.employee_signed_at || '')}</td>
      <td class="table-actions"></td>
    `;

    const actionsCell = tr.querySelector('.table-actions');

    const signLink = createActionLink(item);
    if (signLink) {
      actionsCell.appendChild(signLink);
    }

    // Mantengo tu lógica original, aunque conceptualmente convendría revisar este estado.
    if (item.status === 'pending_employee_signature') {
      const signButton = createEmployerSignButton(item);
      actionsCell.appendChild(signButton);
    }

    tbody.appendChild(tr);
  });
}

function initializeModalCanvas() {
  state.modalCanvas = UI.modalCanvas();
  if (!state.modalCanvas) return;

  state.modalCtx = state.modalCanvas.getContext('2d');
  state.modalCtx.strokeStyle = '#111827';
  state.modalCtx.lineWidth = 2;
  state.modalCtx.lineJoin = 'round';
  state.modalCtx.lineCap = 'round';
}

function clearModalCanvas() {
  if (!state.modalCanvas || !state.modalCtx) return;
  state.modalCtx.clearRect(0, 0, state.modalCanvas.width, state.modalCanvas.height);
}

function openSignModal(receiptId) {
  state.modalReceiptId = receiptId;

  setText(UI.modalReceiptId(), receiptId);
  clearElement(UI.modalMsg());
  clearElement(UI.modalResult());

  UI.signModal()?.classList.remove('hidden');
  UI.signModal()?.setAttribute('aria-hidden', 'false');

  initializeModalCanvas();
  clearModalCanvas();
}

function closeSignModal() {
  UI.signModal()?.classList.add('hidden');
  UI.signModal()?.setAttribute('aria-hidden', 'true');
  clearModalCanvas();

  state.modalReceiptId = null;
  state.drawing = false;
}

function getCanvasPoint(event) {
  const rect = state.modalCanvas.getBoundingClientRect();

  if (event.touches && event.touches[0]) {
    return {
      x: event.touches[0].clientX - rect.left,
      y: event.touches[0].clientY - rect.top,
    };
  }

  return {
    x: event.clientX - rect.left,
    y: event.clientY - rect.top,
  };
}

function startDrawing(event) {
  if (!state.modalCanvas) return;

  state.drawing = true;
  state.lastPoint = getCanvasPoint(event);
}

function stopDrawing() {
  state.drawing = false;
}

function draw(event) {
  if (!state.drawing || !state.modalCtx || !state.modalCanvas) return;

  const point = getCanvasPoint(event);

  state.modalCtx.beginPath();
  state.modalCtx.moveTo(state.lastPoint.x, state.lastPoint.y);
  state.modalCtx.lineTo(point.x, point.y);
  state.modalCtx.stroke();

  state.lastPoint = point;
}

function attachModalDrawing() {
  const canvas = UI.modalCanvas();
  if (!canvas) return;

  state.modalCanvas = canvas;
  initializeModalCanvas();

  canvas.addEventListener('mousedown', startDrawing);
  canvas.addEventListener('touchstart', (event) => {
    event.preventDefault();
    startDrawing(event);
  }, { passive: false });

  canvas.addEventListener('mousemove', draw);
  canvas.addEventListener('touchmove', (event) => {
    event.preventDefault();
    draw(event);
  }, { passive: false });

  window.addEventListener('mouseup', stopDrawing);
  window.addEventListener('touchend', stopDrawing);
}

async function submitEmployerSignature() {
  if (!state.modalCanvas || !state.modalReceiptId) {
    showError(UI.modalMsg(), 'No hay una firma lista para enviar.');
    return;
  }

  setText(UI.modalMsg(), 'Enviando firma...');

  try {
    const dataUrl = state.modalCanvas.toDataURL('image/png');

    const response = await apiFetch(`/api/receipts/${state.modalReceiptId}/sign-employer`, {
      method: 'POST',
      body: { signature: dataUrl },
    });

    setText(UI.modalResult(), `Respuesta: ${JSON.stringify(response)}`);

    if (
      response &&
      typeof response.token === 'string' &&
      /^[a-f0-9]{64}$/i.test(response.token)
    ) {
      const link = `${location.origin}/sign/${response.token}`;
      UI.modalResult().innerHTML += `
        <div class="mt-8">
          Link de firma del empleado:
          <a class="link" target="_blank" rel="noopener noreferrer" href="${escAttr(link)}">
            ${esc(link)}
          </a>
        </div>
      `;
    }

    showSuccess(UI.modalMsg(), 'Firma registrada correctamente.');
    await doRefreshReceipts();
  } catch (error) {
    setHTML(UI.modalMsg(), '<div class="error">No se pudo registrar la firma.</div>');
    console.error('Error al firmar como empleador:', error);
  }
}

async function doRefreshReceipts() {
  const msg = UI.receiptsMsg();
  clearElement(msg);

  try {
    const status = UI.filterStatus()?.value || '';
    const items = await getReceipts(status);
    renderReceiptsTable(items);
  } catch (error) {
    showError(msg, error);
  }
}

async function logout() {
  try {
    await apiFetch('/api/auth/logout', { method: 'POST' });
    window.location.href = 'index.html';
  } catch (error) {
    showError(UI.receiptsMsg(), error);
  }
}

document.addEventListener('DOMContentLoaded', async () => {
  await checkSession();

  UI.btnUpload()?.addEventListener('click', uploadBatch);
  UI.btnRefreshReceipts()?.addEventListener('click', doRefreshReceipts);
  UI.filterStatus()?.addEventListener('change', doRefreshReceipts);
  UI.modalClose()?.addEventListener('click', closeSignModal);
  UI.btnLogout()?.addEventListener('click', logout);

  if (UI.modalSubmit()) {
    UI.modalSubmit().addEventListener('click', submitEmployerSignature);
  }

  attachModalDrawing();
  await doRefreshReceipts();
});