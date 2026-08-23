import { apiFetch, el, esc, openModal, closeModal, showToast } from '../../common.js';
import { LABELS } from '../../constants.js';

export async function initSignModal(container, { onSignComplete }) {
  const submitBtn = el('modalSubmit', container);
  const select = el('companySignerSelect', container);
  
  submitBtn.onclick = async () => {
    const signerId = select.value;
    if (!signerId) return;
    
    submitBtn.disabled = true;
    try {
      // Logic would be passed from orchestrator or handled here
      await onSignComplete(signerId);
      closeModal('signModal', container);
    } catch (err) {
      showToast('Error al firmar', 'error');
    } finally {
      submitBtn.disabled = false;
    }
  };
}

export async function openUploadModal(container, { organization_id, onUploadComplete }) {
  const msgEl = el('uploadMsg', container);
  const submitBtn = el('uploadSubmit', container);
  const fileInput = el('uploadPdf', container);
  const periodInput = el('uploadPeriod', container);

  msgEl.innerHTML = '';
  fileInput.value = '';
  
  const now = new Date();
  const defaultPeriod = now.toLocaleString('es-AR', { month: 'long', year: 'numeric' });
  periodInput.value = defaultPeriod.charAt(0).toUpperCase() + defaultPeriod.slice(1);

  submitBtn.onclick = async () => {
    const file = fileInput.files?.[0];
    if (!file) {
      msgEl.innerHTML = '<div class="error">Seleccioná un archivo PDF.</div>';
      return;
    }

    const periodLabel = periodInput.value.trim();
    submitBtn.disabled = true;
    msgEl.innerHTML = '<div class="small-muted">Subiendo y procesando...</div>';

    try {
      const formData = new FormData();
      formData.append('organization_id', organization_id);
      formData.append('period_label', periodLabel);
      formData.append('pdf', file);

      const res = await apiFetch(`/api/batches/upload`, {
        method: 'POST',
        body: formData,
      });

      showToast('Batch subido correctamente', 'success');
      onUploadComplete(res);
      closeModal('uploadModal', container);
    } catch (err) {
      msgEl.innerHTML = `<div class="error">${esc(err.message || 'Error al subir batch')}</div>`;
    } finally {
      submitBtn.disabled = false;
    }
  };

  openModal('uploadModal', container);
}
