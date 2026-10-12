/**
 * TOS Acceptance State Management
 * Handles localStorage caching and backend persistence.
 */
import { apiFetch, showToast } from './common.js?v=118';
import { TOS_VERSION } from './constants.js?v=118';

const STORAGE_KEY = 'tos_acceptance_v1';

export const tosAcceptance = {
  /**
   * Checks if TOS is accepted for the current session/user.
   * Logic:
   * 1. Check localStorage for immediate UI gate.
   * 2. Logic in router will also verify against the user object from /api/auth/me.
   */
  check(user) {
    // If not logged in, we only care about the UI gate for the session if needed,
    // but usually TOS is enforced AFTER login for protected routes.
    if (!user) return true; // Public pages are allowed

    // 1. Check user object from backend (Source of Truth)
    if (user.tos_accepted && user.tos_version === TOS_VERSION) {
      this._saveToLocal(user.id, TOS_VERSION);
      return true;
    }

    // 2. Check localStorage (Cache)
    const cached = this._loadFromLocal(user.id);
    if (cached && cached.tosVersion === TOS_VERSION) {
      return true;
    }

    return false;
  },

  /**
   * Persists acceptance to backend and cache.
   */
  async accept(user) {
    if (!user) return;

    try {
      await apiFetch('/api/auth/accept-tos', {
        method: 'POST',
        body: { tos_version: TOS_VERSION }
      });

      this._saveToLocal(user.id, TOS_VERSION);
      return true;
    } catch (error) {
      console.error('Failed to persist TOS acceptance:', error);
      showToast('Error al guardar la aceptación. Reintentá.', 'error');
      return false;
    }
  },

  _saveToLocal(userId, version) {
    const data = {
      userId,
      acceptedAt: new Date().toISOString(),
      tosVersion: version
    };
    localStorage.setItem(`${STORAGE_KEY}_${userId}`, JSON.stringify(data));
  },

  _loadFromLocal(userId) {
    const raw = localStorage.getItem(`${STORAGE_KEY}_${userId}`);
    if (!raw) return null;
    try {
      return JSON.parse(raw);
    } catch (e) {
      return null;
    }
  }
};
