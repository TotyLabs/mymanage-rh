import { apiFetch, showToast, apiUrl } from '../../common.js';

export async function handleLegajoExport(format, { debug = false } = {}) {
  try {
    const url = apiUrl(`/api/legajo/export?format=${format}${debug ? '&debug=true' : ''}`);
    window.open(url, '_blank');
    showToast('Exportación iniciada', 'success');
  } catch (err) {
    showToast('Error al exportar', 'error');
  }
}

export async function handleLegajoImport(file, mode) {
  const fd = new FormData();
  fd.append('file', file);
  fd.append('mode', mode);
  
  return await apiFetch('/api/legajo/preview', {
    method: 'POST',
    body: fd
  });
}
