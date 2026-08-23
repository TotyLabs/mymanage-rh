import { apiFetch, showError, showSuccess, getApiBase } from './common.js';

const $ = (id) => document.getElementById(id);

function getValue(id) {
  return $(id)?.value?.trim() || '';
}

function getRawValue(id) {
  return $(id)?.value || '';
}

async function checkMe() {
  try {
    const me = await apiFetch('/api/auth/me');

    const meInfo = $('meInfo');
    if (meInfo) {
      meInfo.innerText = `Conectado como ${me.email} (${me.role})`;
    }

    if (['admin', 'employer', 'owner'].includes(me.role)) {
      window.location.href = 'admin.html';
    }
  } catch (error) {
    // Sin sesión activa, no hacemos nada.
  }
}

async function login() {
  const msg = $('loginMsg');
  if (msg) msg.innerHTML = '';

  const body = {
    username: getValue('loginEmail'),
    password: getRawValue('loginPassword'),
  };

  if (!body.email || !body.password) {
    showError(msg, 'Ingresá email y contraseña.');
    return;
  }

  try {
    await apiFetch('/api/auth/login', {
      method: 'POST',
      body,
    });

    showSuccess(msg, 'Inicio de sesión correcto. Redirigiendo...');
    window.setTimeout(() => {
      window.location.href = 'admin.html';
    }, 600);
  } catch (error) {
    showError(msg, error);
    console.error('Error de login:', error);
  }
}

async function registerOrg() {
  const msg = $('orgMsg');
  if (msg) msg.innerHTML = '';

  const body = {
    email: getValue('orgEmail'),
    password: getRawValue('orgPassword'),
    full_name: getValue('orgFullName'),
    organization_name: getValue('orgName'),
  };

  if (!body.email || !body.password || !body.full_name || !body.organization_name) {
    showError(msg, 'Completá todos los campos de la organización.');
    return;
  }

  try {
    const response = await apiFetch('/api/auth/register', {
      method: 'POST',
      body,
    });

    showSuccess(msg, 'Organización registrada correctamente.');
    console.log('Registro de organización:', response);
  } catch (error) {
    showError(msg, error);
    console.error('Error al registrar organización:', error);
  }
}

async function registerEmployeePublic() {
  const msg = $('empMsgPublic');
  if (msg) msg.innerHTML = '';

  const body = {
    full_name: getValue('empFullNamePublic'),
    cuil: getValue('empCuilPublic'),
    email: getValue('empEmailPublic'),
    password: getRawValue('empPasswordPublic'),
  };

  if (!body.full_name || !body.cuil || !body.email || !body.password) {
    showError(msg, 'Completá nombre, CUIL, email y contraseña.');
    return;
  }



  try {
    const response = await apiFetch('/api/auth/register-employee', {
      method: 'POST',
      body,
    });

    showSuccess(msg, 'Empleado registrado correctamente.');
    console.log('Registro de empleado:', response);
  } catch (error) {
    showError(msg, error);
    console.error('Error al registrar empleado:', error);

    if (error?.body?.detail === 'organization_not_found') {
      const hint = document.createElement('div');
      hint.className = 'small-muted';
      hint.innerText = 'No se encontró la organización. Registrala primero.';
      msg?.appendChild(hint);
    }
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const apiInput = $('apiBase');

  if (apiInput) {
    apiInput.value = getApiBase();
    apiInput.addEventListener('change', () => {
      window.__API_BASE__ = apiInput.value.trim();
      console.log('API base actualizada en memoria:', window.__API_BASE__);
    });
  }

  $('btnLogin')?.addEventListener('click', login);
  $('btnRegisterOrg')?.addEventListener('click', registerOrg);
  $('btnRegisterEmpPublic')?.addEventListener('click', registerEmployeePublic);

  checkMe();
});