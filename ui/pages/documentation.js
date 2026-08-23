/**
 * Documentation Page
 * Layout: Sidebar (categories) | Main Panel (markdown viewer) | Top bar (title + metadata)
 */
import { docsContent } from '../docs-content.js';

export const render = async (container, params = {}) => {
  const docId = params.get('docId') || 'tos';
  const doc = docsContent[docId] || docsContent['tos'];

  container.innerHTML = `
    <div class="docs-container">
      <aside class="docs-sidebar">
        <div class="docs-sidebar-header">
          <h3>Documentación</h3>
        </div>
        <nav class="docs-nav">
          ${renderCategory('Legal', ['tos', 'privacy'], docId)}
        </nav>
      </aside>
      
      <main class="docs-main">
        <header class="docs-header">
          <div class="docs-header-left">
            <h1>${doc.title}</h1>
            <span class="docs-meta">Última actualización: ${doc.lastUpdated}</span>
          </div>
          <div class="docs-header-right">
            <button class="btn btn-outline btn-sm" onclick="window.print()">
              <i class="fas fa-print"></i> Imprimir
            </button>
          </div>
        </header>
        
        <article class="docs-content markdown-body">
          ${doc.html}
        </article>
      </main>
    </div>
  `;
};

function renderCategory(name, ids, currentId) {
  return `
    <div class="docs-nav-category">
      <span class="category-label">${name}</span>
      <ul>
        ${ids.map(id => {
          const d = docsContent[id];
          return `
            <li class="${id === currentId ? 'active' : ''}">
              <a href="#/documentacion?docId=${id}">${d.title}</a>
            </li>
          `;
        }).join('')}
      </ul>
    </div>
  `;
}
