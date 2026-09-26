function getApiBase() {
  return window.__API_BASE__ || '';
}

function getAuthToken() {
  return window.localStorage.getItem('token') || '';
}

function getSessionToken() {
  const storageToken = getAuthToken();
  if (storageToken) return storageToken;

  if (typeof document === 'undefined') return '';
  const match = document.cookie.match(/(?:^|;\s*)session=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : '';
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

  const sessionToken = getSessionToken();
  const config = {
    credentials: 'include',
    headers: {
      'X-Requested-With': 'XMLHttpRequest',
      'ngrok-skip-browser-warning': 'true',
      ...(sessionToken ? { Authorization: `Bearer ${sessionToken}`, 'X-Session-Token': sessionToken } : {}),
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
  const sessionToken = getSessionToken();
  const response = await fetch(apiUrl('/api/auth/logout'), {
    method: 'POST',
    credentials: 'include',
    headers: {
      'X-Requested-With': 'XMLHttpRequest',
      ...(sessionToken ? { Authorization: `Bearer ${sessionToken}`, 'X-Session-Token': sessionToken } : {}),
    },
  });

  if (!response.ok) {
    throw new Error(`logout_failed_${response.status}`);
  }

  window.localStorage.removeItem('token');
  window.__USER_CACHE__ = null;
}

function showToast(message, type = 'info', timeout = 4000) {
  try {
    const container = document.getElementById('toasts');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerText = message;

    container.appendChild(toast);

    setTimeout(() => {
      toast.classList.add('fade-out');
      setTimeout(() => toast.remove(), 300);
    }, timeout);
  } catch (error) {
    console.error('Error al mostrar toast:', error);
  }
}

function confirmAction(message) {
  return new Promise((resolve) => {
    const modal = document.getElementById('confirmModal');

    if (!modal) {
      resolve(window.confirm(message));
      return;
    }

    const msgEl = modal.querySelector('#confirmMsg');
    const okBtn = modal.querySelector('#confirmOk');
    const cancelBtn = modal.querySelector('#confirmCancel');

    msgEl.innerText = message || '¿Confirmar?';
    modal.classList.remove('hidden');

    function cleanup(result) {
      modal.classList.add('hidden');
      okBtn.removeEventListener('click', onOk);
      cancelBtn.removeEventListener('click', onCancel);
      resolve(result);
    }

    function onOk() {
      cleanup(true);
    }

    function onCancel() {
      cleanup(false);
    }

    okBtn.addEventListener('click', onOk);
    cancelBtn.addEventListener('click', onCancel);
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
  getAuthToken,
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