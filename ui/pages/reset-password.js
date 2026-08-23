/**
 * Reset Password: Consume un token de restablecimiento y establece una nueva contraseña.
 * UX: Validación de contraseña en tiempo real + confirmación.
 */
import { apiFetch, showError, showSuccess, showToast, withLoader } from '../common.js';

function el(id, ctx = document) {
  return (ctx || document).querySelector(id.startsWith('#') ? id : `#${id}`);
}

function validatePasswordClient(password) {
  if (!password || password.length < 8) return 'La contraseña debe tener al menos 8 caracteres.';
  if (!/[a-zA-Z]/.test(password)) return 'La contraseña debe contener al menos una letra.';
  if (!/[0-9]/.test(password)) return 'La contraseña debe contener al menos un número.';
  return null;
}

export async function render(container, params) {
  const email = params?.get ? params.get('email') : '';
  let role = params?.get ? params.get('role') : null;

  // Persist or retrieve role from session to avoid loss on reload
  if (role) {
    sessionStorage.setItem('reset_role', role);
  } else {
    role = sessionStorage.getItem('reset_role') || 'empleado';
  }

  const isEmpresa = role === 'empresa';

  if (!email) {
    container.innerHTML = `
      <section class="auth-shell">
        <div class="card auth-card auth-card-main">
          <div class="auth-header">
            <h1 class="auth-title">Falta información</h1>
            <p class="auth-subtitle">
              No se ha provisto un correo electrónico para el restablecimiento.
            </p>
          </div>
          <div class="auth-backlink">
            <a class="link" href="#/forgot-password">Volver a intentar</a>
          </div>
        </div>
      </section>
    `;
    return;
  }

  // For employees, we check remember preference
  let rememberChecked = false;
  if (!isEmpresa) {
    const { isRememberEnabled } = await import('../remember-user.js');
    rememberChecked = isRememberEnabled();
  }

  const title = isEmpresa ? 'Generar nueva clave' : 'Nueva contraseña';
  const subtitle = isEmpresa 
    ? `Ingresá el código enviado a <strong>${email}</strong> para obtener tu nueva clave de acceso.`
    : `Ingresá el código enviado a <strong>${email}</strong> y tu nueva contraseña.`;

  container.innerHTML = `
    <section class="auth-shell">
      <div class="card auth-card auth-card-main">
        <div class="auth-header">
          <div class="auth-icon" aria-hidden="true">
            <svg width="24" height="24" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"></path>
            </svg>
          </div>

          <h1 class="auth-title">${title}</h1>
          <p class="auth-subtitle">${subtitle}</p>
        </div>

        <div id="resetMsg" class="mb-16"></div>

        <div id="newClaveResult" class="hidden text-center mb-24">
          <p class="text-sm text-muted mb-8">Esta es tu nueva clave de acceso corporativa:</p>
          <div class="bg-gray-100 p-24 rounded-lg border-2 border-dashed border-primary mb-16">
            <span id="displayClave" class="font-mono text-2xl font-bold tracking-widest text-primary"></span>
          </div>
          <p class="text-xs text-warning font-semibold mb-16">
            ⚠️ Copiala ahora. Por seguridad, no se volverá a mostrar.
          </p>
          <button id="btnCopyClave" class="btn btn-ghost btn-sm">Copiar clave</button>
          <hr class="my-24 border-gray-200">
          <a class="btn btn-primary w-full" href="#/login?role=empresa">Ir al inicio de sesión</a>
        </div>

        <form id="resetForm" class="auth-form" novalidate>
          <div class="form-group">
            <label for="resetOtp">Código de seguridad (OTP)</label>
            <input
              id="resetOtp"
              type="text"
              class="input text-center font-mono text-lg"
              placeholder="000000"
              maxlength="6"
              autocomplete="one-time-code"
            />
          </div>

          ${isEmpresa ? `
          <div class="form-group">
            <label>Tipo de clave de acceso</label>
            <div class="flex gap-16 mt-8">
              <label class="radio-label">
                <input type="radio" name="claveType" value="auto" checked />
                <span>Aleatoria</span>
              </label>
              <label class="radio-label">
                <input type="radio" name="claveType" value="manual" />
                <span>Personalizada</span>
              </label>
            </div>
          </div>

          <div id="manualClaveGroup" class="form-group hidden">
            <label for="customClave">Definí tu clave personalizada</label>
            <input
              id="customClave"
              type="text"
              class="input font-mono"
              placeholder="Escribí al menos 18 caracteres"
            />
            <p class="text-xs text-muted mt-4">Por seguridad, la clave debe tener un mínimo de 18 caracteres.</p>
          </div>
          ` : `
          <div class="form-group">
            <label for="resetPassword">Nueva contraseña</label>
            <input
              id="resetPassword"
              type="password"
              class="input"
              placeholder="Mínimo 8 caracteres"
              autocomplete="new-password"
            />
            <div id="passwordStrength" class="badge mt-8 hidden"></div>
          </div>

          <div class="form-group">
            <label for="resetPasswordConfirm">Confirmar contraseña</label>
            <input
              id="resetPasswordConfirm"
              type="password"
              class="input"
              placeholder="Repetir contraseña"
              autocomplete="new-password"
            />
          </div>

          <div class="form-group">
            <label class="checkbox-label">
              <input id="rememberCheckReset" type="checkbox" ${rememberChecked ? 'checked' : ''} />
              <span>Recordar mis datos para el próximo inicio de sesión</span>
            </label>
          </div>
          `}

          <button id="btnReset" type="submit" class="btn btn-primary btn-lg w-full">
            ${isEmpresa ? 'Obtener nueva clave' : 'Restablecer contraseña'}
          </button>
        </form>

        <div class="auth-backlink">
          <a class="link" href="#/forgot-password?role=${role}">¿No recibiste el código? Solicitar uno nuevo</a>
        </div>
      </div>
    </section>
  `;

  const msgEl = el('resetMsg', container);
  const formEl = el('resetForm', container);
  const otpInput = el('resetOtp', container);
  const resultArea = el('newClaveResult', container);
  
  const passwordInput = el('resetPassword', container);
  const confirmInput = el('resetPasswordConfirm', container);
  const strengthBadge = el('passwordStrength', container);
  const rememberCheck = el('rememberCheckReset', container);

  if (isEmpresa) {
    const radioAuto = container.querySelector('input[value="auto"]');
    const radioManual = container.querySelector('input[value="manual"]');
    const manualGroup = el('manualClaveGroup', container);
    const customInput = el('customClave', container);

    radioAuto.addEventListener('change', () => manualGroup.classList.add('hidden'));
    radioManual.addEventListener('change', () => {
      manualGroup.classList.remove('hidden');
      customInput.focus();
    });
  } else if (passwordInput) {
    passwordInput.addEventListener('input', () => {
      const val = passwordInput.value;
      if (!val) {
        strengthBadge.className = 'badge mt-8 hidden';
        return;
      }
      strengthBadge.classList.remove('hidden');
      const error = validatePasswordClient(val);
      if (error) {
        strengthBadge.className = 'badge warning mt-8';
        strengthBadge.textContent = error;
      } else {
        strengthBadge.className = 'badge success mt-8';
        strengthBadge.textContent = 'Contraseña válida ✓';
      }
    });
  }

  otpInput.addEventListener('input', () => {
    otpInput.value = otpInput.value.replace(/[^0-9]/g, '');
  });

  formEl.addEventListener(
    'submit',
    withLoader(async (event) => {
      event.preventDefault();
      msgEl.innerHTML = '';

      const otp = otpInput.value.trim();
      if (otp.length !== 6) {
        showError(msgEl, 'El código debe tener 6 dígitos.');
        return;
      }

      if (isEmpresa) {
        const isManual = container.querySelector('input[value="manual"]').checked;
        const customKey = el('customClave', container).value.trim();

        if (isManual && customKey.length < 18) {
          showError(msgEl, 'La clave personalizada debe tener al menos 18 caracteres.');
          return;
        }

        try {
          const res = await apiFetch('/api/auth/reset-clave-empresa', {
            method: 'POST',
            body: { email, otp, custom_key: isManual ? customKey : null },
          });

          if (res?.status === 'error') {
            showError(msgEl, res.message || 'Error al restablecer la clave.');
            return;
          }

          // Show the result and hide the form
          formEl.classList.add('hidden');
          resultArea.classList.remove('hidden');
          el('displayClave', resultArea).textContent = res.new_clave;
          
          el('btnCopyClave', resultArea).onclick = () => {
            navigator.clipboard.writeText(res.new_clave);
            showToast('Clave copiada al portapapeles', 'success');
          };
          
          showSuccess(msgEl, res.message);
        } catch (error) {
          showError(msgEl, error);
        }
      } else {
        const password = passwordInput.value;
        const confirm = confirmInput.value;

        const clientError = validatePasswordClient(password);
        if (clientError) {
          showError(msgEl, clientError);
          return;
        }

        if (password !== confirm) {
          showError(msgEl, 'Las contraseñas no coinciden.');
          return;
        }

        try {
          const res = await apiFetch('/api/auth/reset-password', {
            method: 'POST',
            body: { email, otp, new_password: password },
          });

          if (res?.status === 'error') {
            showError(msgEl, res.message || 'Error al restablecer la contraseña.');
            return;
          }

          showSuccess(msgEl, res?.message || 'Tu contraseña fue restablecida exitosamente.');
          showToast('Contraseña restablecida. Redirigiendo...', 'success');

          const { saveUserData, clearUserData } = await import('../remember-user.js');
          if (rememberCheck.checked) saveUserData({ email });
          else clearUserData();

          setTimeout(() => {
            location.hash = '#/login?role=empleado';
          }, 2500);
        } catch (error) {
          showError(msgEl, error);
        }
      }
    })
  );

  otpInput.focus();
}
