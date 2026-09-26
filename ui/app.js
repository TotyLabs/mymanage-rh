import { renderLayout, bindHeader } from './layout.js?v=69';
import { initRouter } from './router.js?v=69';

document.addEventListener('DOMContentLoaded', () => {
  const app = document.getElementById('app');

  if (!app) {
    console.error('No se encontró el contenedor principal #app.');
    return;
  }

  try {
    renderLayout(app);
    bindHeader();
    initRouter();
  } catch (error) {
    console.error('Error al inicializar la aplicación:', error);
    app.innerHTML = `
      <div class="error">
        No se pudo inicializar la aplicación.
      </div>
    `;
  }
});