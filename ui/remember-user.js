/**
 * Remember User Data — localStorage utility for non-sensitive form autofill.
 *
 * SECURITY: NEVER stores passwords, tokens, sessions, DNI, CUIL, or any PII.
 * Only stores: email, name (optional).
 * Storage keys are prefixed with `yc_` to avoid collisions.
 */

const STORAGE_KEYS = {
  email: 'yc_remember_email',
  name: 'yc_remember_name',
  enabled: 'yc_remember_enabled',
};

/**
 * Saves non-sensitive user data to localStorage.
 * @param {{ email?: string, name?: string }} data
 */
export function saveUserData({ email, name } = {}) {
  try {
    if (email) localStorage.setItem(STORAGE_KEYS.email, email);
    if (name) localStorage.setItem(STORAGE_KEYS.name, name);
    localStorage.setItem(STORAGE_KEYS.enabled, 'true');
  } catch (e) {
    // Silent fail (e.g., private browsing, storage full)
  }
}

/**
 * Loads previously saved user data from localStorage.
 * @returns {{ email: string, name: string } | null}
 */
export function loadUserData() {
  try {
    const enabled = localStorage.getItem(STORAGE_KEYS.enabled);
    if (enabled !== 'true') return null;

    const email = localStorage.getItem(STORAGE_KEYS.email) || '';
    const name = localStorage.getItem(STORAGE_KEYS.name) || '';

    if (!email && !name) return null;
    return { email, name };
  } catch (e) {
    return null;
  }
}

/**
 * Clears all remembered user data from localStorage.
 * Called when the user unchecks "Recordar mis datos".
 */
export function clearUserData() {
  try {
    localStorage.removeItem(STORAGE_KEYS.email);
    localStorage.removeItem(STORAGE_KEYS.name);
    localStorage.removeItem(STORAGE_KEYS.enabled);
  } catch (e) {
    // Silent fail
  }
}

/**
 * Returns true if "remember" was previously enabled.
 */
export function isRememberEnabled() {
  try {
    return localStorage.getItem(STORAGE_KEYS.enabled) === 'true';
  } catch (e) {
    return false;
  }
}
