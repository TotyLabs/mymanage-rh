function getApiBase() {
  return window.__API_BASE__ || '';
}

if (typeof window !== 'undefined') {
  try {
    window.localStorage.removeItem('token');
  } catch (error) {
    console.warn('Unable to clear legacy browser session token.', error);
  }
}

function apiUrl(path) {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  return `${getApiBase()}${normalizedPath}`;
}

function esc(value) {
  if (value === null || value === undefined) return '';
  const div = document.createElement('div');
  div.textContent = String(value);
  return div.innerHTML;
}

/**
 * Display-side null guard. Prevents undefined, null, [object Object], 
 * and empty values from showing in UI. Returns fallback text.
 */
function safePrint(value, fallback = 'No disponible') {
  if (value === null || value === undefined) return fallback;
  // Catch raw objects/arrays that would stringify to [object Object]
  if (typeof value === 'object') return fallback;
  const s = String(value).trim();
  if (!s || s === 'undefined' || s === 'null' || s === 'NaN' || s === 'None') return fallback;
  return esc(s);
}

/**
 * Formats a date string consistently for display.
 */
function formatDate(dateStr, fallback = 'Sin fecha') {
  if (!dateStr) return fallback;
  try {
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return fallback;
    return d.toLocaleDateString('es-AR', { year: 'numeric', month: '2-digit', day: '2-digit' });
  } catch {
    return fallback;
  }
}

/**
 * Global input sanitizer: trims, strips control chars, normalizes encoding.
 */
function sanitizeInput(value) {
  if (value === null || value === undefined) return '';
  return String(value)
    .replace(/[\u0000-\u001F\u007F]/g, '')  // Strip control chars
    .replace(/\uFEFF/g, '')                  // Strip BOM
    .trim();
}

function escAttr(value) {
  if (value === null || value === undefined) return '';
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

async function safeJson(response) {
  const contentType = response.headers.get('content-type') || '';

  try {
    if (contentType.includes('application/json')) {
      return await response.json();
    }
    return await response.text();
  } catch (error) {
    return await response.text();
  }
}

function normalizeError(error, url = '') {
  if (error instanceof TypeError && error.message === 'Failed to fetch') {
    return {
      type: 'network_error',
      message: `Error de conexión o CORS. Verificá que el servidor esté disponible en ${url}`,
      url,
    };
  }

  if (error && typeof error === 'object') {
    if (!error.url && url) error.url = url;
    return error;
  }

  return {
    type: 'unknown_error',
    message: typeof error === 'string' ? error : 'Ocurrió un error inesperado.',
    url,
  };
}

async function apiFetch(path, options = {}) {
  const url = apiUrl(path);

  const config = {
    credentials: 'include',
    headers: {
      'X-Requested-With': 'XMLHttpRequest',
      'ngrok-skip-browser-warning': 'true',
      ...(options.headers || {}),
    },
    ...options,
  };

  if (config.body && typeof config.body === 'object' && !(config.body instanceof FormData)) {
    config.headers['Content-Type'] = 'application/json';
    config.body = JSON.stringify(config.body);
  }

  try {
    const response = await fetch(url, config);

    if (!response.ok) {
      const body = await safeJson(response);
      throw {
        status: response.status,
        body,
        url,
        type: 'api_error',
        detail: body?.detail || body
      };
    }

    return await safeJson(response);
  } catch (error) {
    throw normalizeError(error, url);
  }
}

function buildMessageFromError(error) {
  if (error?.body) {
    if (typeof error.body === 'object') {
      return JSON.stringify(error.body.detail || error.body);
    }
    return error.body;
  }

  if (error?.detail) {
    return typeof error.detail === 'object'
      ? JSON.stringify(error.detail)
      : error.detail;
  }

  if (error?.message) return error.message;
  if (typeof error === 'string') return error;

  return 'Error inesperado.';
}

function showError(targetEl, error) {
  if (!targetEl) return;

  console.error('API Error:', error);

  const wrapper = document.createElement('div');
  wrapper.className = 'error';
  wrapper.setAttribute('role', 'alert');

  const message = document.createElement('div');
  message.textContent = buildMessageFromError(error);
  wrapper.appendChild(message);

  if (error?.url) {
    const hint = document.createElement('div');
    hint.className = 'error-hint';
    hint.textContent = `URL: ${error.url}`;
    wrapper.appendChild(hint);
  }

  targetEl.innerHTML = '';
  targetEl.appendChild(wrapper);
}

function showSuccess(targetEl, message) {
  if (!targetEl) return;

  const wrapper = document.createElement('div');
  wrapper.className = 'success';
  wrapper.setAttribute('role', 'status');
  wrapper.innerText = message;

  targetEl.innerHTML = '';
  targetEl.appendChild(wrapper);
}

function withLoader(fn) {
  return async function (event) {
    let button = event?.target?.tagName === 'BUTTON' ? event.target : null;
    
    // GAP-015: Robust button detection for form submissions
    if (!button && event?.target?.tagName === 'FORM') {
      button = event.target.querySelector('button[type="submit"]');
    }

    let loader = null;

    if (button) {
      button.disabled = true;
      loader = document.createElement('span');
      loader.className = 'loader-small';
      button.prepend(loader);
    }

    try {
      return await fn(event);
    } finally {
      if (button) {
        button.disabled = false;
        loader?.remove();
      }
    }
  };
}

async function getMe() {
  return apiFetch('/api/auth/me');
}

async function logoutSession() {
  const response = await fetch(apiUrl('/api/auth/logout'), {
    method: 'POST',
    credentials: 'include',
    headers: {
      'X-Requested-With': 'XMLHttpRequest',
    },
  });

  if (!response.ok) {
    throw new Error(`logout_failed_${response.status}`);
  }

  window.localStorage.removeItem('token');
  window.__USER_CACHE__ = null;
}

/* ==========================================================================
   Avisos (toasts)
   - Un solo contenedor (#toasts, aria-live) para todo el producto.
   - Los errores se anuncian como alerta, quedan más tiempo en pantalla y se
     pueden cerrar; el temporizador se pausa con el mouse o el foco encima.
   - Los errores de formulario NO dependen solo de este aviso: se muestran
     también junto al campo (ver .form-error-msg).
   ========================================================================== */

const TOAST_ICONS = {
  success: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"></circle><path d="M8 12.5l2.7 2.7L16 9.8"></path></svg>',
  error: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"></circle><path d="M12 7.5v5.5"></path><path d="M12 16.5h.01"></path></svg>',
  warning: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3.5l9.5 16.5h-19z"></path><path d="M12 10v4.5"></path><path d="M12 17.5h.01"></path></svg>',
  info: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"></circle><path d="M12 11v5.5"></path><path d="M12 7.5h.01"></path></svg>',
  close: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12"></path><path d="M18 6L6 18"></path></svg>',
};

const MAX_VISIBLE_TOASTS = 4;

function showToast(message, type = 'info', timeout = 4000) {
  try {
    const container = document.getElementById('toasts');
    if (!container) return;

    const kind = TOAST_ICONS[type] && type !== 'close' ? type : 'info';
    const isError = kind === 'error';
    // Los errores se quedan al menos 8 s: hay que poder leerlos.
    const duration = isError ? Math.max(timeout, 8000) : timeout;

    const toast = document.createElement('div');
    toast.className = `toast ${kind}`;
    toast.setAttribute('role', isError ? 'alert' : 'status');

    const icon = document.createElement('span');
    icon.className = 'toast-icon';
    icon.innerHTML = TOAST_ICONS[kind];

    const text = document.createElement('span');
    text.className = 'toast-msg';
    text.textContent = String(message ?? '');

    const close = document.createElement('button');
    close.type = 'button';
    close.className = 'toast-close';
    close.setAttribute('aria-label', 'Cerrar aviso');
    close.innerHTML = TOAST_ICONS.close;

    toast.append(icon, text, close);

    // Evita pilas interminables: se descartan los más viejos.
    while (container.children.length >= MAX_VISIBLE_TOASTS) {
      container.firstElementChild.remove();
    }
    container.appendChild(toast);

    let timer = null;
    let removed = false;

    const dismiss = () => {
      if (removed) return;
      removed = true;
      clearTimeout(timer);
      toast.classList.add('fade-out');
      setTimeout(() => toast.remove(), 200);
    };
    const start = () => {
      clearTimeout(timer);
      timer = setTimeout(dismiss, duration);
    };
    const pause = () => clearTimeout(timer);

    close.addEventListener('click', dismiss);
    toast.addEventListener('mouseenter', pause);
    toast.addEventListener('mouseleave', start);
    toast.addEventListener('focusin', pause);
    toast.addEventListener('focusout', start);

    start();
  } catch (error) {
    console.error('Error al mostrar aviso:', error);
  }
}

/* ==========================================================================
   Diálogo de confirmación (#confirmModal, definido en layout.js)
   Compatible con la firma anterior: confirmAction(message).
   Opciones: { title, confirmLabel, cancelLabel, danger }
   Maneja foco (inicial en "Cancelar", atrapado dentro del diálogo y devuelto
   al disparador), Escape y clic sobre el fondo.
   ========================================================================== */

function confirmAction(message, options = {}) {
  return new Promise((resolve) => {
    const modal = document.getElementById('confirmModal');

    if (!modal) {
      resolve(window.confirm(message));
      return;
    }

    const titleEl = modal.querySelector('#confirmTitle');
    const msgEl = modal.querySelector('#confirmMsg');
    const okBtn = modal.querySelector('#confirmOk');
    const cancelBtn = modal.querySelector('#confirmCancel');
    const previouslyFocused = document.activeElement;

    if (titleEl) titleEl.textContent = options.title || 'Confirmar acción';
    msgEl.textContent = message || '¿Confirmar?';
    okBtn.textContent = options.confirmLabel || 'Confirmar';
    cancelBtn.textContent = options.cancelLabel || 'Cancelar';
    okBtn.classList.toggle('btn-danger', Boolean(options.danger));
    okBtn.classList.toggle('btn-primary', !options.danger);

    modal.classList.remove('hidden');
    modal.setAttribute('aria-hidden', 'false');
    document.body.classList.add('modal-open');
    cancelBtn.focus();

    function cleanup(result) {
      modal.classList.add('hidden');
      modal.setAttribute('aria-hidden', 'true');
      document.body.classList.remove('modal-open');
      okBtn.removeEventListener('click', onOk);
      cancelBtn.removeEventListener('click', onCancel);
      modal.removeEventListener('keydown', onKey);
      modal.removeEventListener('mousedown', onBackdrop);
      if (previouslyFocused && typeof previouslyFocused.focus === 'function') {
        previouslyFocused.focus({ preventScroll: true });
      }
      resolve(result);
    }

    function onOk() {
      cleanup(true);
    }

    function onCancel() {
      cleanup(false);
    }

    function onKey(event) {
      if (event.key === 'Escape') {
        event.preventDefault();
        cleanup(false);
        return;
      }
      if (event.key !== 'Tab') return;
      // Foco atrapado entre los dos botones del diálogo.
      const first = cancelBtn;
      const last = okBtn;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    function onBackdrop(event) {
      if (event.target === modal) cleanup(false);
    }

    okBtn.addEventListener('click', onOk);
    cancelBtn.addEventListener('click', onCancel);
    modal.addEventListener('keydown', onKey);
    modal.addEventListener('mousedown', onBackdrop);
  });
}

function el(id, ctx = document) {
  return (ctx || document).querySelector(`#${id}`);
}

export {
  apiFetch,
  apiUrl,
  showError,
  getApiBase,
  showSuccess,
  withLoader,
  getMe,
  logoutSession,
  showToast,
  confirmAction,
  esc,
  escAttr,
  safePrint,
  formatDate,
  sanitizeInput,
  el,
};
