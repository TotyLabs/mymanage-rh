import { apiFetch, esc } from '../common.js';

function getVerifyId() {
  const match = (window.location.hash || '').match(/^#\/verify\/([^?]+)/);
  return match ? match[1] : null;
}

function statusColor(status) {
  if (status === 'green' || status === 'valid') return 'var(--success-solid)';
  if (status === 'red' || status === 'failed' || status === 'invalid') return 'var(--error-solid)';
  if (status === 'not_applicable') return 'var(--slate-400, #94a3b8)';
  return 'var(--warning-solid)';
}

function renderError(container, message) {
  container.innerHTML = `
    <section class="card verify-card verify-card-invalid mx-auto" style="max-width: 700px; margin-top: 40px;">
      <div class="verify-card-header text-center">
        <h1 class="verify-title">No se pudo validar el documento</h1>
        <p class="verify-subtitle">${esc(message)}</p>
      </div>
    </section>
  `;
}

function renderResult(container, result) {
  const labels = {
    storage: '¿Está disponible el archivo?',
    database_hash: '¿Coincide el archivo con el registro?',
    seal_hash: '¿Está la firma vinculada al documento?',
    evidence_hash: '¿Coincide el registro de la firma?',
    database_evidence: '¿Coinciden los datos de la firma?',
    certificate_correlation: '¿Coincide la identidad de quien firmó?',
    pdf_signature: '¿Es válida la firma del documento?',
  };
  const stateLabel = {
    green: 'Documento íntegro',
    yellow: 'No se pudo confirmar todo',
    red: 'Se detectaron inconsistencias',
  };
  const friendlyMessage = (key, status, message) => {
    const messages = {
      storage: {
        valid: 'El archivo está guardado y disponible.',
        failed: 'No se encontró el archivo o no tiene un formato válido.',
        unknown: 'El archivo existe, pero no se pudo leer para comprobarlo.',
      },
      database_hash: {
        valid: 'El documento coincide con el registro del sistema.',
        failed: 'El documento no coincide con el registro del sistema.',
        unknown: 'No se pudo comparar el documento con el registro.',
      },
      seal_hash: {
        valid: 'La marca de firma coincide con el documento o con una versión registrada.',
        historical: 'La marca de firma corresponde a una versión anterior del documento.',
        failed: 'La marca de firma no coincide con el historial del documento.',
        unknown: 'No se pudo comparar la marca de firma con el documento.',
        not_applicable: 'El documento se identificó mediante su código de verificación.',
      },
      evidence_hash: {
        valid: 'El registro de firma corresponde a una versión del documento.',
        historical: 'El registro de firma corresponde a una versión anterior.',
        failed: 'El registro de firma no coincide con el documento.',
        unknown: 'No se pudo comparar el registro de firma.',
        not_applicable: 'No hay un registro adicional de firma para comparar.',
      },
      database_evidence: {
        valid: 'Los datos guardados al firmar coinciden entre sí.',
        warning: 'Faltan algunos datos para confirmar por completo la firma.',
        failed: 'Hay diferencias entre el documento y los datos guardados al firmar.',
      },
      certificate_correlation: {
        valid: 'Los datos de identidad de la firma coinciden con los guardados.',
        warning: 'No se pudo confirmar por completo la identidad de quien firmó.',
        failed: 'Los datos de identidad de la firma no coinciden.',
        not_applicable: 'Esta comprobación no corresponde a este documento.',
      },
      pdf_signature: {
        valid: 'Las firmas del documento son válidas.',
        untrusted: 'La firma está intacta, pero no se pudo confirmar su origen.',
        missing: 'No se encontró una firma electrónica dentro del documento.',
        invalid: 'La firma no es válida o el documento cambió después de firmarse.',
        unavailable: 'No se pudo comprobar la firma del documento.',
      },
    };
    return messages[key]?.[status] || message;
  };
  const color = statusColor(result.integrity_status);
  const checks = Object.entries(result.checks || {}).map(([key, check]) => {
    const checkColor = statusColor(check.status);
    const marker = check.status === 'valid'
      ? '✓'
      : check.status === 'failed' || check.status === 'invalid'
        ? '×'
        : check.status === 'not_applicable'
          ? '–'
          : '!';
    const details = Array.isArray(check.details) && check.details.length
      ? `<details style="margin-top: 8px;"><summary>Ver más información</summary><ul style="padding-left: 20px; margin: 8px 0 0;">${check.details.map(detail => `<li>${esc(detail)}</li>`).join('')}</ul></details>`
      : '';
    return `
      <li style="border-left: 4px solid ${checkColor}; padding: 12px 16px; margin: 0 0 12px; background: var(--slate-50, #f8fafc); list-style: none;">
        <strong style="color: ${checkColor};">${marker} ${esc(labels[key] || key)}</strong>
        <div class="text-muted mt-4">${esc(friendlyMessage(key, check.status, check.message))}</div>
        ${details}
      </li>
    `;
  }).join('');
  const pdfSignatures = (result.pdf_signatures || []).map((signature, index) => {
    const status = signature.valid === false || signature.intact === false
      || signature.docmdp_ok === false || signature.timestamp_status === 'invalid'
      ? 'failed'
      : signature.valid === true
        && signature.intact === true
        && signature.trusted === true
        && !['untrusted', 'unavailable'].includes(signature.timestamp_status)
        ? 'valid'
        : 'warning';
    const signatureColor = statusColor(status);
    const signatureState = status === 'valid'
      ? 'Válida'
      : status === 'failed'
        ? 'No válida o documento modificado'
        : 'No se pudo confirmar por completo';
    const timestamp = signature.timestamp_status === 'not_present'
      ? 'Sin sello de tiempo'
      : signature.timestamp_status === 'valid'
        ? 'Sello de tiempo válido'
        : signature.timestamp_status === 'untrusted'
          ? 'Sello de tiempo íntegro; emisor no confirmado'
          : signature.timestamp_status === 'invalid'
            ? 'Sello de tiempo inválido'
            : 'No se pudo comprobar el sello de tiempo';
    const resultLabel = (value, validLabel, invalidLabel) => value === true
      ? validLabel
      : value === false
        ? invalidLabel
        : 'No concluyente';
    return `
      <li style="border-left: 4px solid ${signatureColor}; padding: 12px 16px; margin: 0 0 12px; background: var(--slate-50, #f8fafc); list-style: none;">
        <strong style="color: ${signatureColor};">Firma ${index + 1}</strong>
        <div class="text-muted mt-4">${esc(signatureState)} · ${esc(timestamp)}</div>
        <div class="text-muted mt-4">${resultLabel(signature.intact, 'El documento no presenta cambios posteriores', 'Se detectaron cambios posteriores')} · ${resultLabel(signature.valid, 'Firma válida', 'Firma no válida')} · ${resultLabel(signature.trusted, 'Certificado confiable', 'Certificado no confiable')}</div>
        <details style="margin-top: 8px;">
          <summary>Ver detalles técnicos</summary>
          <div class="text-muted mt-4">Campo de firma: ${esc(signature.field_name || 'No disponible')}</div>
          <div class="text-muted mt-4">Huella del certificado: ${esc(signature.certificate_fingerprint || 'No disponible')}</div>
          <div class="text-muted mt-4">Número de serie: ${esc(signature.certificate_serial || 'No disponible')}</div>
        </details>
      </li>
    `;
  }).join('');
  const signedAt = result.signed_at
    ? new Date(result.signed_at).toLocaleString('es-AR')
    : 'No disponible';
  const documentType = result.document_type === 'legajo' ? 'Legajo' : 'Recibo';
  const downloadUrl = result.download_url ? esc(result.download_url) : '';
  const loginUrl = `#/login?redirect=${encodeURIComponent(window.location.hash || '#/')}`;
  const auditButton = result.audit_verification_id
    ? `<a class="btn btn-secondary" href="/api/audit/${encodeURIComponent(result.audit_verification_id)}/pdf">Descargar informe de auditoría</a>`
    : '';

  container.innerHTML = `
    <section class="card verify-card mx-auto" style="max-width: 760px; margin: 40px auto; overflow: hidden;">
      <header style="padding: 24px; border-bottom: 1px solid var(--slate-200);">
        <div style="display: inline-block; padding: 8px 14px; border-radius: 999px; color: ${color}; border: 1px solid ${color}; font-weight: 700;">
          ${esc(stateLabel[result.integrity_status] || stateLabel.yellow)}
        </div>
        <h1 class="verify-title mt-16">Verificación del ${esc(documentType.toLowerCase())}</h1>
        <p class="verify-subtitle">
          ${esc(result.organization || 'Organización no disponible')}
          ${signedAt ? ` · ${esc(signedAt)}` : ''}
        </p>
        <p class="text-caption text-muted">Código de verificación: ${esc(result.verification_id || '')}</p>
      </header>

      <div style="padding: 24px;">
        <h2 class="text-h3 mb-16">Qué se revisó</h2>
        <ul style="padding: 0; margin: 0;">${checks}</ul>
        ${pdfSignatures ? `
          <h2 class="text-h3 mb-16 mt-24">Firmas del documento</h2>
          <ul style="padding: 0; margin: 0;">${pdfSignatures}</ul>
        ` : ''}

        <details class="dl-item mt-24">
          <summary class="dl-label">Ver huella digital del documento</summary>
          <div class="verify-hash-box mt-8" style="overflow-wrap: anywhere;">${esc(result.document_hash || 'No disponible')}</div>
        </details>

        <p class="notice-panel warning mt-24">
          Los documentos del 20/11/2026 o anteriores pueden aparecer en amarillo por utilizar una versión anterior de la firma. Una discrepancia real del archivo o de su SHA-256 se muestra en rojo.
        </p>

        <div class="verify-actions mt-24" style="display: flex; flex-wrap: wrap; gap: 12px;">
          ${downloadUrl ? `<a class="btn btn-primary" href="${downloadUrl}">Descargar ${esc(documentType.toLowerCase())}</a>` : ''}
          ${auditButton}
        </div>
        <p class="small-muted mt-12">
          La descarga requiere sesión y permisos sobre el documento.
          <a href="${esc(loginUrl)}">Iniciar sesión</a>
        </p>
      </div>
    </section>
  `;
}

export async function render(container) {
  const publicId = getVerifyId();
  if (!publicId) {
    renderError(container, 'No se proporcionó un identificador de verificación.');
    return;
  }

  container.innerHTML = `
    <section class="verify-shell">
      <div class="verify-loading">Verificando el documento y sus firmas...</div>
    </section>
  `;

  try {
    const result = await apiFetch(`/api/receipts/v/${encodeURIComponent(publicId)}`);
    renderResult(container, result);
  } catch (error) {
    console.error('Public document verification failed', error);
    renderError(container, 'El identificador no existe o el servidor no pudo completar la verificación.');
  }
}
