import {
  apiFetch,
  showError,
  showToast,
  getMe,
  confirmAction,
  navigate,
  el,
  openModal,
  closeModal,
  Store
} from '../../common.js';
import { LABELS, ROUTES } from '../../constants.js';
import { renderEmployeesTable } from './table.js';
import { initEmployeeForm } from './form.js';

export async function render(container) {
  const state = {
    employees: [],
    search: '',
    selectedIds: new Set(),
  };

  container.innerHTML = `
    <section>
      <div class="flex-between mb-24 empresa-empleados-topbar">
        <div>
          <h1 class="card-title empresa-page-title mb-8">${LABELS.nomina}</h1>
          <div class="small-muted">Gestioná personal, legajos y documentación.</div>
        </div>

        <div class="flex items-center gap-12">
          <input id="empSearch" class="input" placeholder="Buscar..." />
          <button id="btnImport" class="btn btn-secondary">Importar</button>
          <button id="btnNewEmployee" class="btn btn-primary">Nuevo Empleado</button>
          <button id="btnBack" class="btn btn-ghost">Volver</button>
        </div>
      </div>

      <section class="card empresa-table-card">
        <div id="bulkActions" class="empresa-bulk-bar hidden">
          <span id="selectedCount" class="small-muted"></span>
          <button id="btnBulkDelete" class="btn btn-danger btn-sm">${LABELS.deleteSelection}</button>
        </div>
        <div id="employeesEmpty" class="hidden"></div>
        <div id="employeesTableWrap" class="table-container">
          <table id="employeesTable" class="table">
            <thead>
              <tr>
                <th><input type="checkbox" id="selectAllEmployees" /></th>
                <th>Nombre</th><th>Legajo</th><th>DNI</th><th>CUIL</th><th>Estado</th><th>Recibos</th><th>Acciones</th>
              </tr>
            </thead>
            <tbody></tbody>
          </table>
        </div>
      </section>

      <!-- Employee Modal -->
      <div id="employeeModal" class="modal hidden" aria-hidden="true">
        <div class="modal-content empresa-modal-xl">
          <div class="modal-header"><h3 class="modal-title">Ficha del colaborador</h3></div>
          <div class="modal-body">
            <div class="empresa-tabs-row mb-16">
              <button class="tab-btn active" data-tab="tab-filiacion">Filiación</button>
              <button class="tab-btn" data-tab="tab-laborales">Laborales</button>
            </div>
            <div id="tab-filiacion" class="tab-panel">
               <div class="empresa-form-grid">
                  <div class="form-group"><label>Nombre</label><input id="empFirstName" class="input"></div>
                  <div class="form-group"><label>Apellido</label><input id="empLastName" class="input"></div>
                  <div class="form-group"><label>DNI</label><input id="empDni" class="input"></div>
                  <div class="form-group"><label>CUIL</label><input id="empCuil" class="input"></div>
               </div>
            </div>
            <div id="tab-laborales" class="tab-panel hidden">
               <div class="empresa-form-grid">
                  <div class="form-group"><label>Legajo</label><input id="empFileNumber" class="input"></div>
                  <div class="form-group"><label>Cargo</label><input id="empJobTitle" class="input"></div>
               </div>
            </div>
          </div>
          <div class="modal-footer">
            <button id="btnCancelEmployee" class="btn btn-ghost">Cancelar</button>
            <button id="employeeSubmit" class="btn btn-primary">Guardar</button>
          </div>
        </div>
      </div>
    </section>
  `;

  async function loadEmployees() {
    try {
      const res = await apiFetch('/api/employees');
      state.employees = res?.employees || [];
      renderEmployeesTable(container, state, {
        onView: (id) => showToast('Perfil próximamente modularizado', 'info'),
        onEdit: (id) => openModal('employeeModal', container),
        onDniOcr: (id) => showToast('OCR próximamente modularizado', 'info'),
        onSelectionChange: () => {
          const count = state.selectedIds.size;
          const bar = el('bulkActions', container);
          if (count > 0) {
            bar.classList.remove('hidden');
            el('selectedCount', container).innerText = `${count} seleccionados`;
          } else {
            bar.classList.add('hidden');
          }
        }
      });
    } catch (err) {
      showError(container, err);
    }
  }

  // Bindings
  el('btnBack', container).onclick = () => navigate('empresa/dashboard');
  el('btnNewEmployee', container).onclick = () => openModal('employeeModal', container);
  el('btnCancelEmployee', container).onclick = () => closeModal('employeeModal', container);
  el('empSearch', container).oninput = (e) => {
    state.search = e.target.value;
    renderEmployeesTable(container, state, {});
  };

  initEmployeeForm(container, { onSave: loadEmployees });

  await loadEmployees();
}
