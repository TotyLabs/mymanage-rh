import { apiFetch, confirmAction, getApiBase, showError, showToast } from '../common.js';

function getIdentifier(params) {
  const routePart = decodeURIComponent((location.hash.split('?')[0].split('/').pop() || '').trim());
  return params?.get?.('id') || routePart;
}

export async function render(container, params) {
  const identifier = getIdentifier(params);
  container.innerHTML = `
    <section class="card" style="max-width:1000px;margin:24px auto;padding:24px">
      <h1 class="card-title mb-8">Firma electrónica de legajo</h1>
      <p id="legajoSignInfo" class="small-muted mb-16">Cargando solicitud...</p>
      <div id="legajoSignError" class="hidden mb-16"></div>
      <div id="legajoSignNoSignature" class="hidden mb-16">
        <p>Para firmar, primero registrá tu firma en Mi Perfil.</p>
        <button id="goToSignatureProfile" class="btn btn-secondary" type="button">Ir a Mi Perfil</button>
      </div>
      <div id="legajoSignContent" class="hidden">
        <p class="mb-12">Revisá el legajo completo. Al confirmar, se aplicará una sola firma electrónica a todas sus páginas.</p>
        <iframe id="legajoSignPdf" title="Legajo pendiente de firma" style="width:100%;height:65vh;border:1px solid #cbd5e1;border-radius:8px"></iframe>
        <div class="form-group mt-16">
          <label for="legajoSignCuil">Confirmá tu CUIL antes de firmar</label>
          <input id="legajoSignCuil" class="input" type="text" inputmode="numeric" autocomplete="off" maxlength="16" />
        </div>
        <div class="flex items-center gap-12 mt-16">
          <button id="legajoSignSubmit" class="btn btn-primary" type="button">Confirmar CUIL y firmar legajo</button>
          <button id="legajoSignBack" class="btn btn-ghost" type="button">Volver a Mis Documentos</button>
        </div>
      </div>
    </section>
  `;

  const info = container.querySelector('#legajoSignInfo');
  const errorEl = container.querySelector('#legajoSignError');
  const content = container.querySelector('#legajoSignContent');
  const noSignature = container.querySelector('#legajoSignNoSignature');
  const submit = container.querySelector('#legajoSignSubmit');

  container.querySelector('#goToSignatureProfile').onclick = () => {
    location.hash = '#/empleado/perfil';
  };
  container.querySelector('#legajoSignBack').onclick = () => {
    location.hash = '#/empleado/recibos';
  };

  if (!identifier) {
    showError(errorEl, 'No se encontró el identificador de la solicitud.');
    errorEl.classList.remove('hidden');
    info.textContent = '';
    return;
  }

  let legajo;
  try {
    legajo = await apiFetch(`/api/employee-legajos/pending/${encodeURIComponent(identifier)}`);
  } catch (error) {
    const detail = error?.body?.detail;
    const messages = {
      cuil_incorrecto: 'El CUIL ingresado no coincide con el registrado para este legajo.',
      signature_required: 'No encontramos una firma guardada. Registrala desde Mi Perfil antes de continuar.',
      solicitud_de_firma_vencida_o_completada: 'La solicitud venció o ya fue firmada.',
      solicitud_de_firma_ya_en_proceso: 'La firma ya está siendo procesada. Esperá un momento y revisá Mis Documentos.',
    };
    showError(errorEl, messages[detail] || error);
    errorEl.classList.remove('hidden');
    info.textContent = '';
    return;
  }

  info.textContent = `${legajo.organization_name} · ${legajo.employee_name} · Solicitud del ${new Date(legajo.created_at).toLocaleString('es-AR')}`;
  if (!legajo.has_signature) {
    noSignature.classList.remove('hidden');
    return;
  }
  container.querySelector('#legajoSignPdf').src =
    `${getApiBase()}/api/employee-legajos/pending/${encodeURIComponent(identifier)}/pdf`;
  content.classList.remove('hidden');

  submit.onclick = async () => {
    const cuil = container.querySelector('#legajoSignCuil').value.trim();
    if (!cuil) {
      showToast('Ingresá tu CUIL para continuar.', 'warning');
      return;
    }
    if (!await confirmAction('¿Confirmás tu CUIL y la firma electrónica de todas las páginas de este legajo?')) return;
    submit.disabled = true;
    submit.textContent = 'Firmando...';
    try {
      await apiFetch(`/api/employee-legajos/pending/${encodeURIComponent(identifier)}/sign`, {
        method: 'POST',
        body: { cuil },
      });
      showToast('Legajo firmado correctamente.', 'success');
      location.hash = '#/empleado/recibos';
    } catch (error) {
      const detail = error?.body?.detail;
      const messages = {
        cuil_incorrecto: 'El CUIL ingresado no coincide con el registrado para este legajo.',
        signature_required: 'No encontramos una firma guardada. Registrala desde Mi Perfil antes de continuar.',
        solicitud_de_firma_vencida_o_completada: 'La solicitud venció o ya fue firmada.',
        solicitud_de_firma_ya_en_proceso: 'La firma ya está siendo procesada. Esperá un momento y revisá Mis Documentos.',
      };
      showError(errorEl, messages[detail] || error);
      errorEl.classList.remove('hidden');
    } finally {
      submit.disabled = false;
      submit.textContent = 'Confirmar CUIL y firmar legajo';
    }
  };
}
