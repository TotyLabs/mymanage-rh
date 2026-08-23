import { apiFetch, showError, showSuccess, showToast, withLoader } from '../common.js';
import { saveUserData, loadUserData, clearUserData, isRememberEnabled } from '../remember-user.js';

function el(selector, ctx = document) {
  return ctx.querySelector(selector);
}

function getRole(params) {
  const role = params?.get('role') || 'empresa';
  return role === 'company' ? 'empresa' : role;
}

function formatDni(value) {
  const normalized = value.replace(/\D/g, '');
  return normalized.replace(/\B(?=(\d{3})+(?!\d))/g, '.');
}

function formatCuil(value) {
  const normalized = value.replace(/\D/g, '');
  if (normalized.length !== 11) return normalized;
  return `${normalized.slice(0, 2)}-${normalized.slice(2, 10)}-${normalized.slice(10)}`;
}

function renderEmpresaForm() {
  return `
    <div class="notice-panel warning mb-24">
      <strong>Registro restringido:</strong> Las empresas ya no pueden auto-registrarse. 
      Utilizá tu Clave de Acceso directamente en el inicio de sesión corporativo.
    </div>
    <div class="text-center">
      <a href="#/login?role=empresa" class="btn btn-primary btn-lg w-full">Ir al Acceso Corporativo</a>
    </div>
  `;
}

function renderEmpleadoForm() {
  return `
    <div class="notice-panel info mb-24">
      <strong>Aviso:</strong> El DNI y CUIL deben coincidir con los datos informados por su empresa.
    </div>

    <form id="authForm" class="auth-form" novalidate>
      <div class="auth-section-label">Verificación de identidad</div>

      <div class="form-group">
        <label for="empFullName">Nombre completo registrado</label>
        <input id="empFullName" class="input" placeholder="Ej: Juan Pérez" />
      </div>

      <div class="auth-grid-2">
        <div class="form-group">
          <label for="empDni">DNI</label>
          <input id="empDni" class="input" placeholder="Sin puntos" />
          <div id="dniPreview" class="badge mt-8 hidden"></div>
        </div>

        <div class="form-group">
          <label for="empCuil">Nro. CUIL</label>
          <input id="empCuil" class="input" placeholder="11 dígitos" maxlength="11" />
          <div id="cuilPreview" class="badge mt-8 hidden"></div>
        </div>
      </div>

      <div class="form-group">
        <label for="empBirthDate">Fecha de nacimiento</label>
        <input id="empBirthDate" type="date" class="input" />
      </div>

      <div class="auth-section-label">Credenciales de acceso</div>

      <div class="form-group">
        <label for="empEmail">Correo electrónico <span class="text-muted text-sm">(Opcional)</span></label>
        <input id="empEmail" type="email" class="input" placeholder="email@ejemplo.com" />
      </div>

      <div class="form-group">
        <label for="empPhone">Número de teléfono <span class="text-muted text-sm">(Opcional)</span></label>
        <input id="empPhone" type="tel" class="input" placeholder="Ej: 1123456789" />
      </div>

      <div class="form-group">
        <label for="empPassword">Contraseña a asignar</label>
        <input id="empPassword" type="password" class="input" placeholder="Mínimo 8 caracteres" />
      </div>

      <div class="form-group">
        <label class="checkbox-label">
          <input id="rememberCheckEmp" type="checkbox" />
          <span>Recordar mis datos</span>
        </label>
      </div>

      <button id="btnRegisterEmp" type="submit" class="btn btn-secondary btn-lg w-full">
        Completar verificación y registro
      </button>
    </form>
  `;
}

function renderFooterCard(role, redirect) {
  const redirectParam = redirect ? `&redirect=${encodeURIComponent(redirect)}` : '';

  if (role === 'empresa') {
    return `
      <div class="card auth-card auth-card-secondary">
        <p class="text-muted auth-secondary-text">¿Ya tenés perfil de administrador?</p>
        <a href="#/login?role=empresa${redirectParam}" class="btn btn-ghost btn-sm">Iniciar sesión</a>
      </div>
    `;
  }

  return `
    <div class="card auth-card auth-card-secondary">
      <p class="text-muted auth-secondary-text">¿Ya tenés acceso asignado?</p>
      <a href="#/login?role=empleado${redirectParam}" class="btn btn-ghost btn-sm">Portal empleado</a>
    </div>
  `;
}

function renderShell(role, redirect = '') {
  const isEmpresa = role === 'empresa';

  return `
    <section class="auth-shell auth-shell-wide">
      <div class="card auth-card auth-card-main">
        <div class="auth-header">
          <div class="auth-icon ${isEmpresa ? 'auth-icon-company' : 'auth-icon-employee'}" aria-hidden="true">
            ${
              isEmpresa
                ? `<svg width="24" height="24" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4"></path>
                  </svg>`
                : `<svg width="24" height="24" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"></path>
                  </svg>`
            }
          </div>

          <h1 class="auth-title">
            ${isEmpresa ? 'Alta de organización' : 'Registro de empleado'}
          </h1>

          <p class="auth-subtitle">
            ${
              isEmpresa
                ? 'Creación del perfil corporativo y del administrador principal.'
                : 'Verificación de identidad y creación de credenciales de acceso.'
            }
          </p>
        </div>

        <div id="msgArea" class="mb-16"></div>
        <div id="formArea"></div>
      </div>

      ${renderFooterCard(role, redirect)}
    </section>
  `;
}

function attachIdentityPreview(container) {
  const empDni = el('#empDni', container);
  const dniPreview = el('#dniPreview', container);
  const empCuil = el('#empCuil', container);
  const cuilPreview = el('#cuilPreview', container);

  if (empDni && dniPreview) {
    empDni.addEventListener('input', (event) => {
      const normalized = event.target.value.replace(/\D/g, '');

      if (!normalized) {
        dniPreview.className = 'badge mt-8 hidden';
        dniPreview.textContent = '';
        return;
      }

      dniPreview.classList.remove('hidden');

      if (normalized.length < 7) {
        dniPreview.className = 'badge warning mt-8';
        dniPreview.textContent = 'DNI incompleto';
      } else {
        dniPreview.className = 'badge success mt-8';
        dniPreview.textContent = `Verificado: ${formatDni(normalized)}`;
      }
    });
  }

  if (empCuil && cuilPreview) {
    empCuil.addEventListener('input', (event) => {
      const normalized = event.target.value.replace(/\D/g, '');

      if (!normalized) {
        cuilPreview.className = 'badge mt-8 hidden';
        cuilPreview.textContent = '';
        return;
      }

      cuilPreview.classList.remove('hidden');

      if (normalized.length === 11) {
        cuilPreview.className = 'badge success mt-8';
        cuilPreview.textContent = `Validado: ${formatCuil(normalized)}`;
      } else {
        cuilPreview.className = 'badge warning mt-8';
        cuilPreview.textContent = 'Requiere 11 números';
      }
    });
  }
}

function validateEmployeeBody(body, msgEl) {
  const requiredLabels = {
    full_name: 'Nombre',
    dni: 'DNI',
    cuil: 'CUIL',
    birth_date: 'Fecha de nacimiento',
    password: 'Contraseña',
  };

  for (const [key, label] of Object.entries(requiredLabels)) {
    if (!body[key]) {
      showError(msgEl, `Falta completar: ${label}`);
      return false;
    }
  }

  return true;
}

async function handleEmpresaSubmit(container, msgEl) {
  msgEl.innerHTML = '';
  const email = el('#orgEmail', container).value.trim();
  const name = el('#orgFullName', container).value.trim();
  const rememberChecked = el('#rememberCheckOrg', container)?.checked;

  // Handle remember preference
  if (rememberChecked) {
    saveUserData({ email, name });
  } else {
    clearUserData();
  }

  try {
    const res = await apiFetch('/api/auth/register-with-key', {
      method: 'POST',
      body: {
        registration_key: el('#regKey', container).value.trim(),
        email: email,
        password: el('#orgPassword', container).value,
        full_name: name,
        organization_name: el('#orgName', container).value.trim(),
      },
    });

    // Clear router cache to ensure fresh state upon redirection
    window.__USER_CACHE__ = null;

    showToast('Registro exitoso. Verificá tu código OTP.', 'success');
    location.hash = `#/verify-account?email=${encodeURIComponent(email)}`;
  } catch (e) {
    showError(msgEl, e);
  }
}

async function handleEmpleadoSubmit(container, params, msgEl) {
  msgEl.innerHTML = '';
  const redirect = params?.get ? params.get('redirect') : '';

  const body = {
    full_name: el('#empFullName', container).value.trim(),
    dni: el('#empDni', container).value.replace(/\D/g, ''),
    cuil: el('#empCuil', container).value.replace(/\D/g, ''),
    birth_date: el('#empBirthDate', container).value,
    email: el('#empEmail', container).value.trim(),
    phone: el('#empPhone', container).value.trim(),
    password: el('#empPassword', container).value,
    invite_token: params?.get ? params.get('token') : '',
    organization_id: params?.get ? params.get('org') : ''
  };

  if (!validateEmployeeBody(body, msgEl)) return;

  // Handle remember preference (NEVER stores DNI/CUIL/password)
  const rememberChecked = el('#rememberCheckEmp', container)?.checked;
  if (rememberChecked) {
    saveUserData({ email: body.email, name: body.full_name });
  } else {
    clearUserData();
  }

  try {
    await apiFetch('/api/auth/register-employee', {
      method: 'POST',
      body,
    });

    // Clear router cache to ensure fresh state upon redirection
    window.__USER_CACHE__ = null;

    showToast('Registro exitoso. Verificá tu identidad con el código enviado.', 'success');
    
    const identifier = body.email || body.phone || body.dni;
    const redirectParam = redirect ? `&redirect=${encodeURIComponent(redirect)}` : '';
    location.hash = `#/verify-account?email=${encodeURIComponent(identifier)}${redirectParam}`;
  } catch (error) {
    const detail = error?.body?.detail || error?.message || '';
    const detailString = typeof detail === 'string' ? detail : JSON.stringify(detail);

    if (detailString.includes('dni_ya_activo')) {
      showError(msgEl, 'Tu DNI ya está activo en el sistema. Ingresá con tu cuenta o recuperá tu contraseña.');
      return;
    }

    if (detailString.includes('dni_no_encontrado') || detailString.includes('no_registrado')) {
      showError(msgEl, 'Tu DNI no figura como pre-registrado en el sistema. Contactá a tu empresa.');
      return;
    }

    if (detailString.includes('invite_token_invalido')) {
      showError(msgEl, 'El enlace de invitación es inválido o ya expiró.');
      return;
    }

    showError(msgEl, error);
  }
}

export async function render(container, params) {
  const role = getRole(params);
  const redirect = params?.get ? params.get('redirect') : '';
  const isEmpresa = role === 'empresa';

  container.innerHTML = renderShell(role, redirect);

  const msgEl = el('#msgArea', container);
  const formArea = el('#formArea', container);

  formArea.innerHTML = isEmpresa ? renderEmpresaForm() : renderEmpleadoForm();

  // Autofill from remembered data (email + name only)
  const remembered = loadUserData();
  if (remembered) {
    if (isEmpresa) {
      const emailEl = el('#orgEmail', container);
      const nameEl = el('#orgFullName', container);
      const checkEl = el('#rememberCheckOrg', container);
      if (emailEl && remembered.email) emailEl.value = remembered.email;
      if (nameEl && remembered.name) nameEl.value = remembered.name;
      if (checkEl) checkEl.checked = true;
    } else {
      const emailEl = el('#empEmail', container);
      const nameEl = el('#empFullName', container);
      const checkEl = el('#rememberCheckEmp', container);
      if (emailEl && remembered.email) emailEl.value = remembered.email;
      if (nameEl && remembered.name) nameEl.value = remembered.name;
      if (checkEl) checkEl.checked = true;
    }
  }

  if (isEmpresa) {
    // Redirigir directamente al login si intenta entrar a registro de empresa
    location.hash = '#/login?role=empresa';
    return;
  }

  attachIdentityPreview(container);

  const form = el('#authForm', container);
  form.addEventListener(
    'submit',
    withLoader(async (event) => {
      event.preventDefault();
      await handleEmpleadoSubmit(container, params, msgEl);
    })
  );
}