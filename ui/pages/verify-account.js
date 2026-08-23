import { apiFetch, showError, withLoader, showToast } from '../common.js';

function el(id, ctx = document) {
  return (ctx || document).querySelector(id.startsWith('#') ? id : `#${id}`);
}

export async function render(container, params) {
  const email = params?.get ? params.get('email') : '';
  const redirect = params?.get ? params.get('redirect') : '';
  
  container.innerHTML = `
    <section class="auth-shell">
      <div class="card auth-card auth-card-main">
        <div class="auth-header">
          <div class="auth-icon" aria-hidden="true">
            <svg width="24" height="24" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"></path>
            </svg>
          </div>
          <h1 class="auth-title">Verificá tu cuenta</h1>
          <p class="auth-subtitle">
            Ingresá el código de 6 dígitos que enviamos a <strong id="displayEmail"></strong>.
          </p>
        </div>

        <div id="verifyMsg" class="mb-24"></div>

        <div class="otp-container mb-32">
          <input type="text" class="otp-input" maxlength="1" data-index="0" />
          <input type="text" class="otp-input" maxlength="1" data-index="1" />
          <input type="text" class="otp-input" maxlength="1" data-index="2" />
          <input type="text" class="otp-input" maxlength="1" data-index="3" />
          <input type="text" class="otp-input" maxlength="1" data-index="4" />
          <input type="text" class="otp-input" maxlength="1" data-index="5" />
        </div>

        <button id="btnVerify" class="btn btn-primary btn-lg w-full mb-16" disabled>
          Verificar cuenta
        </button>

        <div class="flex-center flex-col gap-12">
          <div id="timerContainer" class="small-muted">
            Podrás reenviar el código en <span id="timerSeconds">30</span>s
          </div>
          <button id="btnResend" class="btn btn-ghost btn-sm hidden">
            Reenviar código
          </button>
        </div>

        <div class="auth-backlink mt-24">
          <a class="link" href="#/login">← Volver al login</a>
        </div>
      </div>
    </section>

    <style>
      .otp-container {
        display: flex;
        gap: 12px;
        justify-content: center;
      }
      .otp-input {
        width: 48px;
        height: 56px;
        border: 2px solid var(--border-strong);
        border-radius: 8px;
        text-align: center;
        font-size: 24px;
        font-weight: 700;
        background: var(--bg-card);
        color: var(--text-main);
        transition: all 0.2s;
      }
      .otp-input:focus {
        border-color: var(--accent);
        outline: none;
        box-shadow: 0 0 0 4px var(--accent-alpha);
        transform: translateY(-2px);
      }
      .otp-input.filled {
        border-color: var(--accent-subtle);
      }
      @media (max-width: 480px) {
        .otp-input {
          width: 40px;
          height: 48px;
          font-size: 20px;
        }
        .otp-container {
          gap: 8px;
        }
      }
    </style>
  `;

  const msgEl = el('verifyMsg', container);
  const inputs = container.querySelectorAll('.otp-input');
  const btnVerify = el('btnVerify', container);
  const btnResend = el('btnResend', container);
  const timerContainer = el('timerContainer', container);
  const timerSeconds = el('timerSeconds', container);

  el('displayEmail', container).textContent = email || 'tu correo/teléfono';

  let countdown = 30;
  let timerInterval = null;

  function startTimer() {
    countdown = 30;
    btnResend.classList.add('hidden');
    timerContainer.classList.remove('hidden');
    timerSeconds.textContent = countdown;
    
    if (timerInterval) clearInterval(timerInterval);
    
    timerInterval = setInterval(() => {
      countdown--;
      timerSeconds.textContent = countdown;
      if (countdown <= 0) {
        clearInterval(timerInterval);
        timerContainer.classList.add('hidden');
        btnResend.classList.remove('hidden');
      }
    }, 1000);
  }

  async function sendAutomaticOtp() {
    try {
      // Small delay to avoid racing with the registration response if just redirected
      setTimeout(async () => {
        try {
          await apiFetch('/api/verification/resend', {
            method: 'POST',
            body: { identifier: email }
          });
          showToast('Código enviado a tu casilla', 'info');
        } catch (e) {
          // If it fails (e.g. rate limit), we ignore it since it might have been sent during registration
          console.warn('Auto-resend ignored:', e);
        }
      }, 500);
    } catch (e) {}
  }

  sendAutomaticOtp();
  startTimer();

  function getFullCode() {
    return Array.from(inputs).map(i => i.value).join('');
  }

  function updateButtonState() {
    btnVerify.disabled = getFullCode().length !== 6;
    inputs.forEach(input => {
      if (input.value) input.classList.add('filled');
      else input.classList.remove('filled');
    });
  }

  inputs.forEach((input, idx) => {
    input.addEventListener('input', (e) => {
      const val = e.data || e.target.value;
      if (val && val.length > 0) {
        input.value = val.slice(-1);
        const next = inputs[idx + 1];
        if (next) next.focus();
      }
      updateButtonState();
      if (getFullCode().length === 6) doVerify();
    });

    input.addEventListener('keydown', (e) => {
      if (e.key === 'Backspace' && !input.value) {
        const prev = inputs[idx - 1];
        if (prev) {
          prev.focus();
          prev.value = '';
          updateButtonState();
        }
      }
    });

    input.addEventListener('paste', (e) => {
      e.preventDefault();
      const data = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, 6);
      if (data) {
        data.split('').forEach((char, i) => {
          if (inputs[idx + i]) {
            inputs[idx + i].value = char;
            inputs[idx + i].classList.add('filled');
          }
        });
        const nextFocus = inputs[idx + data.length] || inputs[5];
        nextFocus.focus();
        updateButtonState();
        if (getFullCode().length === 6) doVerify();
      }
    });
    
    // Highlight focus
    input.addEventListener('focus', () => input.select());
  });

  // Auto-focus first input
  setTimeout(() => inputs[0].focus(), 100);

  async function doVerify() {
    const code = getFullCode();
    if (code.length !== 6) return;

    msgEl.innerHTML = '';
    btnVerify.disabled = true;

    try {
      await apiFetch('/api/verification/verify', {
        method: 'POST',
        body: { email, code }
      });
      
      // Clear router cache so it fetches fresh status
      window.__USER_CACHE__ = null;
      
      showToast('¡Cuenta verificada con éxito!', 'success');
      
      // Post-verification redirect based on REAL profile or explicit redirect param
      if (redirect && redirect.startsWith('#/')) {
        location.hash = redirect;
        return;
      }

      const { getMe } = await import('../common.js');
      try {
        const me = await getMe();
        const user = me?.user || me;
        if (user?.role === 'admin') location.hash = '#/empresa/dashboard';
        else if (user?.role === 'employee') location.hash = '#/empleado/recibos';
        else location.hash = '#/login';
      } catch (err) {
        location.hash = '#/login';
      }
    } catch (e) {
      showError(msgEl, e);
      btnVerify.disabled = false;
      inputs.forEach(i => { i.value = ''; i.classList.remove('filled'); });
      inputs[0].focus();
    }
  }

  btnVerify.onclick = withLoader(doVerify);

  btnResend.onclick = async () => {
    try {
      await apiFetch('/api/verification/resend', {
        method: 'POST',
        body: { identifier: email }
      });
      showToast('Código reenviado', 'success');
      startTimer();
    } catch (e) {
      showError(msgEl, e);
    }
  };
}
