/**
 * use-mobile.js
 * Utilidad simple para detección de viewport móvil
 */

const MOBILE_QUERY = '(max-width: 767px)';

export function isMobile() {
  return window.matchMedia(MOBILE_QUERY).matches;
}

export function setupMobileDetection(callback) {
  if (typeof callback !== 'function') {
    throw new TypeError('setupMobileDetection requiere un callback válido.');
  }

  const mediaQuery = window.matchMedia(MOBILE_QUERY);

  const handleChange = () => {
    callback(mediaQuery.matches);
  };

  if (typeof mediaQuery.addEventListener === 'function') {
    mediaQuery.addEventListener('change', handleChange);
  } else {
    mediaQuery.addListener(handleChange);
  }

  handleChange();

  return () => {
    if (typeof mediaQuery.removeEventListener === 'function') {
      mediaQuery.removeEventListener('change', handleChange);
    } else {
      mediaQuery.removeListener(handleChange);
    }
  };
}