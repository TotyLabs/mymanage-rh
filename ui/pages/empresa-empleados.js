import {
  apiFetch,
  apiUrl,
  showError,
  withLoader,
  showToast,
  confirmAction,
  getApiBase,
} from '../common.js';

function el(id, ctx = document) {
  return (ctx || document).querySelector(`#${id}`);
}

function badgeForEmpStatus(status) {
  const span = document.createElement('span');
  span.className = 'badge';

  if (status === 'active') {
    span.classList.add('success');
    span.textContent = 'Activo';
  } else if (status === 'pre_registered') {
    span.classList.add('warning');
    span.textContent = 'Pre-registrado';
  } else if (status === 'registered') {
    span.classList.add('success');
    span.textContent = 'Registrado';
  } else if (status === 'invited') {
    span.classList.add('neutral');
    span.textContent = 'Invitado';
  } else if (status === 'inactive') {
    span.classList.add('neutral');
    span.textContent = 'Inactivo';
  } else {
    span.classList.add('neutral');
    span.textContent = status || 'N/D';
  }

  return span;
}

function openUiModal(id, container) {
  const modal = el(id, container);
  if (!modal) return;
  modal.classList.remove('hidden');
  modal.setAttribute('aria-hidden', 'false');
}

function closeUiModal(id, container) {
  const modal = el(id, container);
  if (!modal) return;
  modal.classList.add('hidden');
  modal.setAttribute('aria-hidden', 'true');
}

function resetTabs(container) {
  container.querySelectorAll('.tab-btn').forEach((btn) => btn.classList.remove('active'));
  container.querySelectorAll('.tab-panel').forEach((panel) => panel.classList.add('hidden'));

  const firstBtn = container.querySelector('.tab-btn[data-tab="tab-filiacion"]');
  const firstPanel = el('tab-filiacion', container);

  if (firstBtn) firstBtn.classList.add('active');
  if (firstPanel) firstPanel.classList.remove('hidden');
}

function formatFullAddress(emp) {
  const street = (emp.address || '').trim();
  const number = (emp.address_number || '').trim();
  const city = (emp.city || '').trim();
  const province = (emp.province || '').trim();

  let line = '';
  if (street && number) line = `${street} ${number}`;
  else if (street) line = street;
  else if (number) line = number;

  if (city || province) {
    const loc = city && province ? `${city} (${province})` : (city || province);
    line = line ? `${line}, ${loc}` : loc;
  }
  return line || null;
}

export async function render(container) {
  container.innerHTML = `
    <section>
      <div class="flex-between mb-24 empresa-empleados-topbar">
        <div>
          <h1 class="card-title empresa-page-title mb-8">Nómina de Empleados</h1>
          <div class="small-muted">Gestioná personal, legajos y documentación laboral.</div>
        </div>

        <div class="flex items-center gap-12 empresa-empleados-actions">
          <input id="empSearch" class="input empresa-search-input" placeholder="Buscar por DNI o nombre..." />

          <div class="empresa-export-menu-wrap">
            <button id="btnExportMenu" class="btn btn-ghost">Exportar ▾</button>

            <div id="exportDropdown" class="card empresa-export-dropdown hidden">
              <div class="empresa-export-debug">
                <label class="empresa-export-debug-label">
                  <input type="checkbox" id="exportDebugMode" />
                  <span>Modo depuración</span>
                </label>
              </div>

              <div class="flex-col gap-4">
                <button class="btn btn-ghost btn-sm btn-export empresa-export-btn" data-format="csv">CSV (Excel)</button>
                <button class="btn btn-ghost btn-sm btn-export empresa-export-btn" data-format="xlsx">Excel (XLSX)</button>
                <button class="btn btn-ghost btn-sm btn-export empresa-export-btn" data-format="txt">Legajo fijo (TXT)</button>
              </div>
            </div>
          </div>

          <input id="searchEmployees" class="input empresa-search-input" placeholder="Buscar por DNI o nombre..." style="max-width:300px" />
          <button id="btnShowDeleted" class="btn btn-ghost" style="color:var(--danger)">Bajas</button>
          <button id="btnImportLegajo" class="btn btn-secondary">Importar legajo</button>
          <button id="btnNewEmployee" class="btn btn-primary empresa-employee-action empresa-new-employee">
            <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" d="M12 5v14m-7-7h14"></path>
            </svg>
            <span>Nuevo empleado</span>
          </button>
          <button id="btnBack" class="btn btn-ghost">Volver</button>
        </div>
      </div>

      <section class="card empresa-table-card">
        <div id="bulkActions" class="empresa-bulk-bar hidden">
          <span id="selectedCount" class="small-muted empresa-bulk-count"></span>
          <button id="btnBulkDelete" class="btn btn-danger btn-sm">Eliminar lote</button>
        </div>

        <div id="employeesEmpty" class="hidden"></div>

        <div id="employeesTableWrap" class="table-container empresa-table-wrap">
          <table id="employeesTable" class="table">
            <thead>
              <tr>
                <th class="empresa-check-col"><input type="checkbox" id="selectAllEmployees" /></th>
                <th class="sortable" data-sort="last_name" style="cursor:pointer">Empleado ↕</th>
                <th class="sortable" data-sort="file_number" style="cursor:pointer">Legajo ↕</th>
                <th class="sortable" data-sort="dni" style="cursor:pointer">DNI ↕</th>
                <th class="sortable" data-sort="cuil" style="cursor:pointer">CUIL ↕</th>
                <th class="sortable" data-sort="status" style="cursor:pointer">Estado ↕</th>
                <th>Recibos</th>
                <th>Acciones</th>
              </tr>
            </thead>
            <tbody></tbody>
          </table>
        </div>
      </section>

      <!-- Modal crear / editar empleado -->
      <div id="employeeModal" class="modal hidden" aria-hidden="true">
        <div class="modal-content empresa-modal-xl">
          <div class="modal-header">
            <h3 id="modalTitle" class="modal-title">Ficha del Empleado</h3>
          </div>

          <div class="modal-body">
            <div id="employeeMsg" class="mb-16"></div>
            <input type="hidden" id="empId" />

            <div class="empresa-tabs-scroll">
              <div class="empresa-tabs-row">
                <button class="tab-btn active" data-tab="tab-filiacion">Filiacion</button>
                <button class="tab-btn" data-tab="tab-inscripciones">Inscripciones</button>
                <button class="tab-btn" data-tab="tab-afip">AFIP</button>
                <button class="tab-btn" data-tab="tab-laborales">Laborales</button>
                <button class="tab-btn" data-tab="tab-otros-datos">Otros Datos</button>
                <button class="tab-btn" data-tab="tab-liquidacion">Liquidacion</button>
              </div>
            </div>

            <!-- 1. Filiacion -->
            <div id="tab-filiacion" class="tab-panel">
              <div class="empresa-form-grid">
                <div class="form-group">
                  <label for="empFirstName">Nombre *</label>
                  <input class="input" id="empFirstName" placeholder="Nombre" />
                </div>

                <div class="form-group">
                  <label for="empLastName">Apellido *</label>
                  <input class="input" id="empLastName" placeholder="Apellido" />
                </div>

                <div class="form-group">
                  <label for="empDni">DNI *</label>
                  <input class="input" id="empDni" placeholder="8 dígitos" />
                </div>

                <div class="form-group">
                  <label for="empCuil">CUIL *</label>
                  <input class="input" id="empCuil" placeholder="11 dígitos" maxlength="30" />
                </div>
                
                <div class="form-group">
                  <label for="empDocType">Tipo documento</label>
                  <select class="input" id="empDocType">
                    <option value="DNI">DNI</option>
                    <option value="LC">LC</option>
                    <option value="LE">LE</option>
                    <option value="PASAPORTE">Pasaporte</option>
                  </select>
                </div>

                <div class="form-group">
                  <label for="empDocNumber">Nro documento</label>
                  <input class="input" id="empDocNumber" placeholder="Si es distinto al DNI" />
                </div>

                <div class="form-group">
                  <label for="empBirthDate">Fecha de nacimiento *</label>
                  <input class="input" id="empBirthDate" type="date" />
                </div>

                <div class="form-group">
                  <label for="empGender">Sexo</label>
                  <select class="input" id="empGender">
                    <option value="">Seleccionar</option>
                    <option value="M">Masculino</option>
                    <option value="F">Femenino</option>
                    <option value="X">No binario / Otro</option>
                  </select>
                </div>

                <div class="form-group">
                  <label for="empMaritalStatus">Estado civil</label>
                  <select class="input" id="empMaritalStatus">
                    <option value="">Sin especificar</option>
                    <option value="single">Soltero/a</option>
                    <option value="married">Casado/a</option>
                    <option value="divorced">Divorciado/a</option>
                    <option value="widowed">Viudo/a</option>
                  </select>
                </div>

                <div class="form-group">
                  <label for="empNationality">Nacionalidad</label>
                  <input class="input" id="empNationality" placeholder="Argentina" />
                </div>

                <div class="form-group">
                  <label for="empEmail">Email</label>
                  <input class="input" id="empEmail" type="email" placeholder="empleado@email.com" />
                </div>

                <div class="form-group">
                  <label for="empPhone">Teléfono</label>
                  <input class="input" id="empPhone" placeholder="11..." />
                </div>

                <div class="form-group">
                  <label for="empAddress">Calle / Domicilio</label>
                  <input class="input" id="empAddress" placeholder="Limay" />
                </div>

                <div class="form-group">
                  <label for="empAddressNumber">Número</label>
                  <input class="input" id="empAddressNumber" placeholder="504 / S/N / 504 Bis" />
                </div>

                <div class="form-group">
                  <label for="empCity">Localidad / Ciudad</label>
                  <input class="input" id="empCity" placeholder="CABA" />
                </div>

                <div class="form-group">
                  <label for="empProvince">Provincia</label>
                  <input class="input" id="empProvince" placeholder="Buenos Aires" />
                </div>

                <div class="form-group">
                  <label for="empPostalCode">Código postal</label>
                  <input class="input" id="empPostalCode" placeholder="1406" />
                </div>
              </div>
            </div>

            <!-- 2. Inscripciones -->
            <div id="tab-inscripciones" class="tab-panel hidden">
              <div class="empresa-form-grid">
                <div class="form-group">
                  <label for="empHealthInsurance">Obra social</label>
                  <input class="input" id="empHealthInsurance" placeholder="OSECAC" />
                </div>

                <div class="form-group">
                  <label for="empHealthInsuranceNumber">Nro afiliado O.S.</label>
                  <input class="input" id="empHealthInsuranceNumber" />
                </div>

                <div class="form-group">
                  <label for="empUnion">Sindicato</label>
                  <input class="input" id="empUnion" placeholder="SEC" />
                </div>

                <div class="form-group">
                  <label for="empUnionNumber">Nro afiliado sindicato</label>
                  <input class="input" id="empUnionNumber" />
                </div>
              </div>
            </div>
            
            <!-- 3. AFIP -->
            <div id="tab-afip" class="tab-panel hidden">
              <div class="empresa-form-grid">
                <div class="form-group">
                  <label for="empPensionRegime">Régimen previsional</label>
                  <input class="input" id="empPensionRegime" placeholder="SIPA" />
                </div>

                <div class="form-group">
                  <label for="empActivity">Actividad</label>
                  <input class="input" id="empActivity" />
                </div>

                <div class="form-group">
                  <label for="empLaborCondition">Condición laboral</label>
                  <input class="input" id="empLaborCondition" />
                </div>

                <div class="form-group">
                  <label for="empRevistaSituation">Situación revista</label>
                  <input class="input" id="empRevistaSituation" />
                </div>
              </div>
            </div>

            <!-- 4. Laborales -->
            <div id="tab-laborales" class="tab-panel hidden">
              <div class="empresa-form-grid">
                <div class="form-group">
                  <label for="empFileNumber">Nro legajo</label>
                  <input class="input" id="empFileNumber" placeholder="001" />
                </div>

                <div class="form-group">
                  <label for="empIericNumber">Nro IERIC</label>
                  <input class="input" id="empIericNumber" placeholder="1234567890" />
                </div>

                <div class="form-group">
                  <label for="empHireDate">Fecha de ingreso *</label>
                  <input class="input" id="empHireDate" type="date" />
                </div>

                <div class="form-group">
                  <label>Antigüedad</label>
                  <div id="displaySeniority" class="empresa-seniority-display">-</div>
                </div>

                <div class="form-group">
                  <label for="empJobTitle">Cargo / puesto</label>
                  <input class="input" id="empJobTitle" placeholder="Ej: Vendedor" />
                </div>

                <div class="form-group">
                  <label for="empCategory">Categoría</label>
                  <input class="input" id="empCategory" placeholder="Administrativo A" />
                </div>

                <div class="form-group">
                  <label for="empTask">Tarea / función</label>
                  <input class="input" id="empTask" />
                </div>

                <div class="form-group">
                  <label for="empCostCenter">Centro de costo</label>
                  <input class="input" id="empCostCenter" />
                </div>

                <div class="form-group">
                  <label for="empUnionAgreement">Convenio colectivo</label>
                  <input class="input" id="empUnionAgreement" placeholder="130/75" />
                </div>

                <div class="form-group">
                  <label for="empHireType">Tipo contrato</label>
                  <select class="input" id="empHireType">
                    <option value="">Seleccionar</option>
                    <option value="permanente">Permanente</option>
                    <option value="temporal">Temporal / Plazo Fijo</option>
                    <option value="pasante">Pasantía</option>
                  </select>
                </div>

                <div class="form-group">
                  <label for="empWorkLocation">Lugar de trabajo</label>
                  <input class="input" id="empWorkLocation" placeholder="Sucursal 1 / Remoto" />
                </div>

                <div class="form-group">
                  <label for="empStatus">Estado *</label>
                  <select class="input" id="empStatus">
                    <option value="pre_registered">Pre-registrado</option>
                    <option value="active">Activo</option>
                    <option value="inactive">Inactivo</option>
                  </select>
                </div>

                <div class="form-group" id="groupTermination">
                  <label for="empTerminationDate">Fecha de Baja</label>
                  <input class="input" id="empTerminationDate" type="date" />
                </div>

                <div class="form-group empresa-form-full">
                  <label for="empStatusReason">Motivo cambio / baja</label>
                  <input class="input" id="empStatusReason" placeholder="Renuncia / Despido / Licencia" />
                </div>
              </div>
            </div>

            <!-- 5. Otros Datos -->
            <div id="tab-otros-datos" class="tab-panel hidden">
              <div class="empresa-form-grid">
                <div class="form-group">
                  <label for="empTalleCamisa">Talle de Camisa</label>
                  <input class="input" id="empTalleCamisa" placeholder="S / M / L / XL" />
                </div>

                <div class="form-group">
                  <label for="empTallePantalon">Talle de Pantalón</label>
                  <input class="input" id="empTallePantalon" placeholder="30 / 32 / 34" />
                </div>

                <div class="form-group">
                  <label for="empTalleZapato">Talle de Zapato</label>
                  <input class="input" id="empTalleZapato" placeholder="38 / 40 / 42" />
                </div>

                <div class="form-group empresa-form-full">
                  <label for="empEstudiosCursados">Estudios Cursados</label>
                  <textarea class="input" id="empEstudiosCursados" placeholder="Secundario, Universitario, Cursos especializados, etc."></textarea>
                </div>

                <div class="form-group empresa-form-full">
                  <label for="empAntecedentesLaborales">Antecedentes Laborales</label>
                  <textarea class="input" id="empAntecedentesLaborales" placeholder="Experiencia laboral anterior"></textarea>
                </div>

                <div class="form-group empresa-form-full">
                  <label for="empDatosFamiliares">Datos Familiares</label>
                  <textarea class="input" id="empDatosFamiliares" placeholder="¿Tiene hijos? Nombres. ¿Tiene cónyuge? Nombre. Otros datos familiares."></textarea>
                </div>
              </div>
            </div>

            <!-- 6. Liquidacion -->
            <div id="tab-liquidacion" class="tab-panel hidden">
              <div class="empresa-form-grid">
                <div class="form-group">
                  <label for="empBankCode">Banco</label>
                  <select class="input" id="empBankCode">
                    <option value="">Seleccionar banco...</option>
                  </select>
                  <input type="hidden" id="empBank" />
                </div>

                <div class="form-group">
                  <label for="empAccType">Tipo de cuenta</label>
                  <select class="input" id="empAccType">
                    <option value="">Seleccionar</option>
                    <option value="caja_ahorro">Caja de ahorro</option>
                    <option value="cuenta_corriente">Cuenta corriente</option>
                  </select>
                </div>

                <div class="form-group">
                  <label for="empAccNumber">Nro de cuenta</label>
                  <input class="input" id="empAccNumber" />
                </div>

                <div class="form-group">
                  <label for="empCbu">CBU (22 dígitos)</label>
                  <input class="input" id="empCbu" maxlength="30" />
                </div>

                <div class="form-group">
                  <label for="empAlias">Alias</label>
                  <input class="input" id="empAlias" />
                </div>

                <div class="form-group">
                  <label for="empPaymentMethod">Forma de pago</label>
                  <select class="input" id="empPaymentMethod">
                    <option value="transferencia">Transferencia</option>
                    <option value="efectivo">Efectivo</option>
                    <option value="cheque">Cheque</option>
                  </select>
                </div>

                <div class="form-group">
                  <label for="empPaymentPlace">Lugar de pago</label>
                  <input class="input" id="empPaymentPlace" />
                </div>
              </div>
            </div>
          </div>

          <div class="modal-footer">
            <button id="empClose" class="btn btn-ghost">Cancelar</button>
            <button id="empSubmit" class="btn btn-primary">Guardar registro</button>
          </div>
        </div>
      </div>

      <!-- Modal perfil -->
      <div id="empProfileModal" class="modal hidden" aria-hidden="true">
        <div class="modal-content empresa-modal-lg">
          <div class="modal-header empresa-profile-header">
            <div>
              <h3 id="empProfileTitle" class="modal-title">Legajo electrónico</h3>
              <div id="empProfileStatusBadge" class="mt-8"></div>
            </div>

            <div class="flex items-center gap-8">
              <button id="empPrintRecord" class="btn btn-primary btn-sm empresa-employee-action">Imprimir legajo</button>
              <button id="empProfileEdit" class="btn btn-ghost btn-sm empresa-employee-action">Modificar</button>
            </div>
          </div>

          <div class="modal-body">
            <div id="empProfileBody"></div>
          </div>

          <div class="modal-footer">
            <button id="empProfileClose" class="btn btn-ghost">Cerrar</button>
          </div>
        </div>
      </div>

      <!-- Modal upload DNI -->
      <div id="dniUploadModal" class="modal hidden" aria-hidden="true">
        <div class="modal-content empresa-modal-sm">
          <div class="modal-header">
            <h3 class="modal-title">Procesamiento de DNI</h3>
          </div>

          <div class="modal-body">
            <p class="small-muted mb-16">
              El sistema escaneará el frente del documento y guardará ambas caras.
            </p>

            <div id="dniUploadMsg" class="mb-16"></div>
            <input type="hidden" id="dniUploadEmpId" />

            <div class="form-group mb-16">
              <label for="dniFileFront">Anverso DNI (JPG / PNG)</label>
              <input type="file" id="dniFileFront" class="input" accept="image/*" />
            </div>

            <div class="form-group">
              <label for="dniFileBack">Reverso DNI (JPG / PNG)</label>
              <input type="file" id="dniFileBack" class="input" accept="image/*" />
            </div>
          </div>

          <div class="modal-footer">
            <button id="dniUploadClose" class="btn btn-ghost">Cancelar</button>
            <button id="dniUploadSubmit" class="btn btn-primary">Iniciar escaneo</button>
          </div>
        </div>
      </div>

      <!-- Modal OCR -->
      <div id="dniOcrModal" class="modal hidden" aria-hidden="true">
        <div class="modal-content empresa-modal-md">
          <div class="modal-body">
            <h3 class="card-title">Confirmar datos detectados</h3>
            <p class="small-muted">Verificá y corregí la información extraída antes de guardar.</p>

            <div id="ocrMsg" class="mb-16"></div>

            <div class="empresa-form-grid">
              <input type="hidden" id="ocrEmpId" />

              <div class="form-group">
                <label for="ocrFirstName">Nombre</label>
                <input class="input" id="ocrFirstName" />
              </div>

              <div class="form-group">
                <label for="ocrLastName">Apellido</label>
                <input class="input" id="ocrLastName" />
              </div>

              <div class="form-group">
                <label for="ocrDni">DNI</label>
                <input class="input" id="ocrDni" />
              </div>

              <div class="form-group">
                <label for="ocrBirthDate">Fecha de nacimiento</label>
                <input class="input" id="ocrBirthDate" type="date" />
              </div>
            </div>
          </div>

          <div class="modal-footer">
            <button id="ocrClose" class="btn btn-ghost">Editar manualmente</button>
            <button id="ocrConfirm" class="btn btn-primary">Confirmar y guardar</button>
          </div>
        </div>
      </div>

      <!-- Modal import -->
      <div id="importModal" class="modal hidden" aria-hidden="true">
        <div class="modal-content empresa-modal-import">
          <div class="modal-header empresa-import-header">
            <h2 class="modal-title">Ingesta masiva de legajos</h2>
            <button id="importCloseTop" class="btn btn-ghost btn-sm empresa-close-x">&times;</button>
          </div>

          <div class="modal-body">
            <div id="importStep1">
              <p class="mb-24">Importación compatible con XLSX, XLS, CSV y TXT.</p>

              <div class="form-group mb-24">
                <label for="importFileInput">Seleccionar archivo de origen</label>
                <input type="file" id="importFileInput" class="input" accept=".xlsx,.xls,.csv,.txt" />
              </div>

              <div class="empresa-import-mode-grid">
                <label class="card empresa-import-mode-card">
                  <div class="flex items-center gap-8 mb-8">
                    <input type="radio" name="importMode" value="merge" checked />
                    <span class="empresa-import-mode-title">Intersección (Merge)</span>
                  </div>
                  <small class="small-muted">
                    Actualiza únicamente los campos presentes en el archivo.
                  </small>
                </label>

                <label class="card empresa-import-mode-card">
                  <div class="flex items-center gap-8 mb-8">
                    <input type="radio" name="importMode" value="replace" />
                    <span class="empresa-import-mode-title">Reemplazo absoluto (Replace)</span>
                  </div>
                  <small class="text-danger">
                    Puede sobrescribir o vaciar datos no presentes en el archivo.
                  </small>
                </label>
              </div>

              <div class="empresa-import-footer">
                <button id="importCancel" class="btn btn-ghost">Cancelar</button>
                <button id="btnDoPreview" class="btn btn-primary">Ejecutar previsualización</button>
              </div>
            </div>

            <div id="importStep2" class="hidden">
              <div class="empresa-import-summary" id="importSummary"></div>

              <div class="table-container mb-24">
                <table class="table" id="importPreviewTable">
                  <thead>
                    <tr>
                      <th>Línea</th>
                      <th>ID primario</th>
                      <th>Individuo</th>
                      <th>Operación</th>
                      <th>Estado</th>
                    </tr>
                  </thead>
                  <tbody></tbody>
                </table>
              </div>

              <div class="empresa-import-footer empresa-import-footer-between">
                <button id="btnRestartImport" class="btn btn-secondary">Volver</button>

                <div class="flex gap-12">
                  <button id="importCancel2" class="btn btn-ghost">Descartar</button>
                  <button id="btnExecuteImport" class="btn btn-primary">Impactar registros</button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Modal Vista Previa Legajo -->
      <div id="importRawModal" class="modal hidden" aria-hidden="true">
        <div class="modal-content empresa-modal-md">
          <div class="modal-body">
            <h3 class="card-title">Vista previa del legajo</h3>
            <p class="small-muted mb-16">
              Verificá que los datos detectados sean correctos antes de importar.
            </p>

            <div id="importRawContent" class="empresa-preview-box"></div>
          </div>

          <div class="modal-footer mt-16">
            <button id="importRawClose" class="btn btn-primary">Entendido</button>
          </div>
        </div>
      </div>

      <!-- Modal Bajas -->
      <div id="deletedEmployeesModal" class="modal hidden" aria-hidden="true">
        <div class="modal-content empresa-modal-lg">
          <div class="modal-header">
            <h3 class="modal-title">Bajas</h3>
          </div>
          <div class="modal-body">
            <p class="small-muted mb-16">Empleados que fueron dados de baja. Podés volver a activarlos (Dar de Alta) o eliminarlos definitivamente.</p>
            <div id="deletedEmployeesMsg"></div>
            
            <div id="deletedBulkActions" class="empresa-bulk-bar hidden" style="margin-bottom:12px; padding:8px; background:var(--bg-subtle); border-radius:8px; display:flex; gap:12px; align-items:center;">
              <span id="deletedBulkCount" class="small-bold">0 seleccionados</span>
              <button id="btnDeletedBulkRestore" class="btn btn-success btn-sm">Dar de Alta seleccionados</button>
              <button id="btnDeletedBulkHardDelete" class="btn btn-danger btn-sm">Baja Definitiva seleccionados</button>
            </div>

            <div class="table-container" style="overflow-x: auto;">
              <table class="table" id="deletedEmployeesTable">
                <thead>
                  <tr>
                    <th class="empresa-check-col" style="width: 40px;"><input type="checkbox" id="selectAllDeleted" /></th>
                    <th>Empleado</th>
                    <th>DNI</th>
                    <th>Fecha de Baja</th>
                    <th>Acciones</th>
                  </tr>
                </thead>
                <tbody></tbody>
              </table>
            </div>
          </div>
          <div class="modal-footer">
            <button id="deletedEmployeesClose" class="btn btn-ghost">Cerrar</button>
          </div>
        </div>
      </div>
    </section>
  `;

  let employees = [];
  let selectedIds = new Set();
  let currentJobId = null;
  let bankMaster = [];
  let sortField = 'last_name';
  let sortOrder = 'asc';
  let searchText = '';

  async function loadBanks() {
    try {
      const res = await apiFetch('/api/banks');
      bankMaster = res?.banks || [];
      const select = el('empBankCode', container);
      if (select) {
        select.innerHTML = '<option value="">Seleccionar banco...</option>';
        bankMaster.forEach((b) => {
          const opt = document.createElement('option');
          opt.value = b.code;
          opt.textContent = `${b.name} (${b.branch})`;
          select.appendChild(opt);
        });
      }
    } catch (e) {
      console.warn('Error loading bank master:', e);
    }
  }

  function handleBankChange() {
    const code = el('empBankCode', container).value;
    const bank = bankMaster.find((b) => b.code === code);
    if (bank) {
      el('empBank', container).value = bank.name;
      // Also potentially auto-fill other fields if empty
      const accType = el('empAccType', container);
      if (accType && !accType.value) {
        // Map account type code or text if available
        if (bank.account_type === 'Cuenta') accType.value = 'cuenta_corriente';
        else if (bank.account_type === 'Caja') accType.value = 'caja_ahorro';
      }
    } else {
      el('empBank', container).value = '';
    }
  }

  let isLoadingEmployees = false;
  async function loadEmployees() {
    if (isLoadingEmployees) return;
    isLoadingEmployees = true;
    try {
      const res = await apiFetch('/api/employees?all=true');
      employees = res?.employees || [];
      renderEmployees();
    } catch (e) {
      showError(container, e);
      console.error('Error cargando empleados:', e);
    } finally {
      isLoadingEmployees = false;
    }
  }

  function renderEmployees() {
    const tbody = container.querySelector('#employeesTable tbody');
    const emptyEl = el('employeesEmpty', container);
    const wrapEl = el('employeesTableWrap', container);

    tbody.innerHTML = '';

    let visible = [...employees];

    if (searchText) {
      const q = searchText.toLowerCase();
      visible = visible.filter(e => 
        (e.first_name + ' ' + e.last_name).toLowerCase().includes(q) ||
        (e.dni || '').toLowerCase().includes(q) ||
        (e.file_number || '').toLowerCase().includes(q)
      );
    }

    visible.sort((a, b) => {
      let valA = (a[sortField] || '').toString().toLowerCase();
      let valB = (b[sortField] || '').toString().toLowerCase();
      
      if (sortField === 'last_name') {
        valA = ((a.last_name || '') + ' ' + (a.first_name || '')).toLowerCase();
        valB = ((b.last_name || '') + ' ' + (b.first_name || '')).toLowerCase();
      }

      const res = valA.localeCompare(valB, undefined, { numeric: true });
      return sortOrder === 'asc' ? res : -res;
    });

    if (!visible.length) {
      emptyEl.innerHTML = `
        <div class="empty-state">
          <div class="empty-title">La nómina está vacía</div>
          <div class="empty-desc">
            Todavía no hay empleados registrados para esta organización.
          </div>
        </div>
      `;
      emptyEl.classList.remove('hidden');
      wrapEl.classList.add('hidden');
      return;
    }

    emptyEl.classList.add('hidden');
    wrapEl.classList.remove('hidden');

    visible.forEach((emp) => {
      const isDeleted = emp.is_deleted;
      const tr = document.createElement('tr');
      if (isDeleted) {
        tr.classList.add('empresa-row-deleted');
        tr.style.opacity = '0.6';
        tr.style.backgroundColor = 'var(--bg-subtle)';
      }

      const tdCheck = document.createElement('td');
      const ck = document.createElement('input');
      ck.type = 'checkbox';
      ck.className = 'emp-checkbox';
      ck.dataset.id = emp.id;
      ck.checked = selectedIds.has(emp.id);
      tdCheck.appendChild(ck);

      const tdName = document.createElement('td');
      const nameBox = document.createElement('div');
      nameBox.className = 'empresa-employee-name';
      nameBox.textContent = `${emp.last_name || ''}, ${emp.first_name || ''}`;
      const emailBox = document.createElement('div');
      emailBox.className = 'small-muted';
      emailBox.textContent = emp.email || '';
      tdName.append(nameBox, emailBox);

      const tdFile = document.createElement('td');
      tdFile.textContent = emp.file_number || '-';

      const tdDni = document.createElement('td');
      tdDni.textContent = emp.dni || '-';

      const dniBtnBox = document.createElement('div');
      dniBtnBox.className = 'mt-8';

      const dniBtn = document.createElement('button');
      dniBtn.className = emp.dni_image_uploaded
        ? 'btn btn-ghost btn-sm btn-dni-upload'
        : 'btn btn-secondary btn-sm btn-dni-upload';
      dniBtn.textContent = emp.dni_image_uploaded ? 'Actualizar DNI' : 'Subir DNI';

      dniBtnBox.appendChild(dniBtn);
      tdDni.appendChild(dniBtnBox);

      const tdCuil = document.createElement('td');
      tdCuil.textContent = emp.cuil || '-';

      const tdStatus = document.createElement('td');
      if (isDeleted) {
        const span = document.createElement('span');
        span.className = 'badge danger';
        span.textContent = 'Baja';
        tdStatus.appendChild(span);
      } else {
        tdStatus.appendChild(badgeForEmpStatus(emp.status));
      }

      const tdReceipts = document.createElement('td');
      tdReceipts.className = 'text-center';
      const rBadge = document.createElement('span');
      rBadge.className = 'badge neutral';
      rBadge.textContent = parseInt(emp.receipts_count, 10) || 0;
      tdReceipts.appendChild(rBadge);

      const tdActions = document.createElement('td');
      tdActions.className = 'table-actions';

      const actionBox = document.createElement('div');
      actionBox.className = 'flex items-center gap-4 empresa-employee-action-group';

      const btnProfile = document.createElement('button');
      btnProfile.className = 'btn btn-ghost btn-sm empresa-icon-btn empresa-employee-action btn-profile';
      btnProfile.title = 'Previsualizar legajo';
      btnProfile.setAttribute('aria-label', 'Previsualizar legajo');

      btnProfile.innerHTML = `
        <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path>
          <path stroke-linecap="round" stroke-linejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"></path>
        </svg>
      `;

      const btnDownload = document.createElement('button');
      btnDownload.className = 'btn btn-ghost btn-sm empresa-icon-btn empresa-employee-action btn-download';
      btnDownload.title = 'Imprimir legajo';
      btnDownload.setAttribute('aria-label', 'Imprimir legajo');
      btnDownload.innerHTML = `
        <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z"></path>
        </svg>
      `;

      const btnEdit = document.createElement('button');
      btnEdit.className = 'btn btn-ghost btn-sm empresa-icon-btn empresa-employee-action btn-edit';
      btnEdit.title = 'Modificar legajo';
      btnEdit.setAttribute('aria-label', 'Modificar legajo');

      btnEdit.innerHTML = `
        <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"></path>
        </svg>
      `;

      const btnDel = document.createElement('button');
      if (isDeleted) {
        btnDel.className = 'btn btn-success btn-sm empresa-icon-btn empresa-employee-action btn-restore';
        btnDel.title = 'Dar de alta';
        btnDel.innerHTML = `
          <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7"></path>
          </svg>
          <span>Dar de alta</span>
        `;
      } else {
        btnDel.className = 'btn btn-danger btn-sm empresa-icon-btn empresa-employee-action btn-delete';
        btnDel.title = 'Dar de baja';
        btnDel.innerHTML = `
          <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path>
          </svg>
          <span>Dar de baja</span>
        `;
      }

      actionBox.append(btnProfile, btnDownload, btnEdit, btnDel);
      tdActions.appendChild(actionBox);

      btnDownload.onclick = () => {
        const url = apiUrl(`/api/employees/${emp.id}/record-pdf`);
        const link = document.createElement('a');
        link.href = url;
        link.download = `legajo_${emp.id.substring(0,8)}.pdf`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
      };

      tr.append(tdCheck, tdName, tdFile, tdDni, tdCuil, tdStatus, tdReceipts, tdActions);
      tbody.appendChild(tr);

      ck.onchange = (e) => {
        if (e.target.checked) selectedIds.add(emp.id);
        else selectedIds.delete(emp.id);
        updateBulkUI();
      };

      btnProfile.onclick = () => openProfile(emp.id);
      btnEdit.onclick = () => {
        if (isDeleted) {
          showToast('Debe dar de alta al empleado para editarlo', 'warning');
          return;
        }
        openEditModal(emp.id);
      };
      btnDel.onclick = () => {
        if (isDeleted) {
          handleRestore(emp.id, `${emp.first_name} ${emp.last_name}`);
        } else {
          handleDelete(emp.id, `${emp.first_name} ${emp.last_name}`);
        }
      };
      dniBtn.onclick = () => openDniUpload(emp.id);
    });

    const allChecked = visible.length > 0 && visible.every((item) => selectedIds.has(item.id));
    el('selectAllEmployees', container).checked = allChecked;
    updateBulkUI();
  }

  function updateBulkUI() {
    const bar = el('bulkActions', container);
    const count = selectedIds.size;

    if (count > 0) {
      bar.classList.remove('hidden');
      el('selectedCount', container).innerText = `${count} seleccionados`;
    } else {
      bar.classList.add('hidden');
      el('selectAllEmployees', container).checked = false;
    }
  }

  function openModal() {
    el('modalTitle', container).textContent = 'Crear empleado — Legajo';
    el('empId', container).value = '';
    el('employeeMsg', container).textContent = '';
    el('displaySeniority', container).textContent = '-';

    const fields = [
      'empFirstName', 'empLastName', 'empDni', 'empCuil', 'empBirthDate', 'empGender', 'empMaritalStatus', 'empNationality',
      'empEmail', 'empPhone', 'empAddress', 'empAddressNumber', 'empCity', 'empProvince', 'empPostalCode',
      'empDocType', 'empDocNumber', 'empHealthInsurance', 'empHealthInsuranceNumber', 'empUnion', 'empUnionNumber',
      'empFileNumber', 'empIericNumber', 'empHireDate', 'empJobTitle', 'empCategory', 'empTask', 'empCostCenter', 'empUnionAgreement',
    ];

    fields.forEach((id) => {
      const field = el(id, container);
      if (field) {
        field.value = id === 'empDocType' ? 'DNI' : (id === 'empStatus' ? 'pre_registered' : '');
      }
    });

    el('groupTermination', container).classList.add('hidden');
    resetTabs(container);
    openUiModal('employeeModal', container);
  }

  async function openEditModal(employeeId) {
    el('modalTitle', container).textContent = 'Editar empleado — Legajo';
    const msg = el('employeeMsg', container);
    msg.textContent = 'Cargando datos...';
    msg.className = 'small-muted';
    el('empId', container).value = employeeId;

    resetTabs(container);
    openUiModal('employeeModal', container);

    try {
      const res = await apiFetch(`/api/employees/${employeeId}`);
      const emp = res.employee || res;
      msg.textContent = '';

      const fieldMap = {
        empFirstName: emp.first_name,
        empLastName: emp.last_name,
        empDni: emp.dni,
        empCuil: emp.cuil,
        empBirthDate: emp.birth_date,
        empGender: emp.gender,
        empMaritalStatus: emp.marital_status,
        empNationality: emp.nationality,
        empEmail: emp.email,
        empPhone: emp.phone,
        empAddress: emp.address,
        empAddressNumber: emp.address_number,
        empCity: emp.city,
        empProvince: emp.province,
        empPostalCode: emp.postal_code,
        empDocType: emp.document_type || 'DNI',
        empDocNumber: emp.document_number,
        empHealthInsurance: emp.health_insurance,
        empHealthInsuranceNumber: emp.health_insurance_number,
        empUnion: emp.union,
        empUnionNumber: emp.union_number,
        empFileNumber: emp.file_number,
        empIericNumber: emp.ieric_number || (emp.extra_fields?.['NRO IERIC']?.value || emp.extra_fields?.['NRO IERIC'] || emp.extra_fields?.['ieric_number']?.value || emp.extra_fields?.['ieric_number']),
        empHireDate: emp.hire_date,
        empJobTitle: emp.job_title,
        empCategory: emp.category,
        empTask: emp.task,
        empCostCenter: emp.cost_center,
        empUnionAgreement: emp.union_agreement,
        empHireType: emp.hire_type,
        empWorkLocation: emp.work_location,
        empStatus: emp.status?.value || emp.status || 'pre_registered',
        empTerminationDate: emp.termination_date,
        empStatusReason: emp.status_reason,
        empPensionRegime: emp.pension_regime,
        empActivity: emp.activity,
        empLaborCondition: emp.labor_condition,
        empRevistaSituation: emp.revista_situation,
        empBank: emp.bank,
        empAccType: emp.account_type,
        empAccNumber: emp.account_number,
        empCbu: emp.cbu,
        empAlias: emp.bank_alias,
        empPaymentMethod: emp.payment_method,
        empPaymentPlace: emp.payment_place,
        empTalleCamisa: emp.talle_camisa || '',
        empTallePantalon: emp.talle_pantalon || '',
        empTalleZapato: emp.talle_zapato || '',
        empEstudiosCursados: emp.estudios_cursados || '',
        empAntecedentesLaborales: emp.antecedentes_laborales || '',
        empDatosFamiliares: emp.datos_familiares || '',
      };

      Object.entries(fieldMap).forEach(([id, value]) => {
        const field = el(id, container);
        if (field) field.value = value || '';
      });

      // Special case for Bank select
      if (emp.bank_code) {
        const sel = el('empBankCode', container);
        if (sel) sel.value = emp.bank_code;
      }

      // Update seniority display
      el('displaySeniority', container).innerText = emp.seniority_text || '-';

      if (fieldMap.empStatus === 'inactive') {
        el('groupTermination', container).classList.remove('hidden');
      } else {
        el('groupTermination', container).classList.add('hidden');
      }
    } catch {
      msg.textContent = 'Error al cargar datos';
      msg.className = 'error';
    }
  }

  function closeModal() {
    closeUiModal('employeeModal', container);
  }

  async function submitEmployee() {
    const fn = el('empFirstName', container).value.trim();
    const ln = el('empLastName', container).value.trim();
    const dni = el('empDni', container).value.trim();
    
    const email = el('empEmail', container).value.trim();
    const phone = el('empPhone', container).value.trim();
    const hireDate = el('empHireDate', container).value.trim();

    if (!fn || !ln || !dni || !hireDate) {
      const msg = el('employeeMsg', container);
      msg.textContent = 'Nombre, apellido, DNI y fecha de ingreso son obligatorios.';
      msg.className = 'error';

      if (!hireDate) {
        container.querySelector('.tab-btn[data-tab="tab-laborales"]').click();
      } else {
        container.querySelector('.tab-btn[data-tab="tab-filiacion"]').click();
      }
      return;
    }

    if (!email && !phone) {
      const msg = el('employeeMsg', container);
      msg.textContent = 'Debe ingresar al menos un correo electrónico o teléfono.';
      msg.className = 'error';

      container.querySelector('.tab-btn[data-tab="tab-filiacion"]').click();
      return;
    }

    const msg = el('employeeMsg', container);
    const submitBtn = el('empSubmit', container);
    const originalBtnText = submitBtn.textContent;

    submitBtn.disabled = true;
    submitBtn.textContent = 'Guardando...';
    msg.textContent = 'Guardando...';
    msg.className = 'small-muted';

    try {
      const fd = new FormData();

      const fields = {
        first_name: 'empFirstName',
        last_name: 'empLastName',
        dni: 'empDni',
        cuil: 'empCuil',
        birth_date: 'empBirthDate',
        gender: 'empGender',
        marital_status: 'empMaritalStatus',
        nationality: 'empNationality',
        email: 'empEmail',
        phone: 'empPhone',
        address: 'empAddress',
        address_number: 'empAddressNumber',
        city: 'empCity',
        province: 'empProvince',
        postal_code: 'empPostalCode',
        document_type: 'empDocType',
        document_number: 'empDocNumber',
        health_insurance: 'empHealthInsurance',
        health_insurance_number: 'empHealthInsuranceNumber',
        union: 'empUnion',
        union_number: 'empUnionNumber',
        file_number: 'empFileNumber',
        ieric_number: 'empIericNumber',
        hire_date: 'empHireDate',
        job_title: 'empJobTitle',
        category: 'empCategory',
        task: 'empTask',
        cost_center: 'empCostCenter',
        union_agreement: 'empUnionAgreement',
        hire_type: 'empHireType',
        work_location: 'empWorkLocation',
        status: 'empStatus',
        termination_date: 'empTerminationDate',
        status_reason: 'empStatusReason',
        pension_regime: 'empPensionRegime',
        activity: 'empActivity',
        labor_condition: 'empLaborCondition',
        revista_situation: 'empRevistaSituation',
        bank: 'empBank',
        bank_code: 'empBankCode',
        account_type: 'empAccType',
        account_number: 'empAccNumber',
        cbu: 'empCbu',
        bank_alias: 'empAlias',
        payment_method: 'empPaymentMethod',
        payment_place: 'empPaymentPlace',
      };

      const employeeId = el('empId', container).value.trim();
      const requestUrl = employeeId ? `${getApiBase()}/api/employees/${employeeId}` : `${getApiBase()}/api/employees`;
      const requestMethod = employeeId ? 'PATCH' : 'POST';

      // Limpiar CUIL de guiones antes de enviarlo
      const cuilEl = el('empCuil', container);
      if (cuilEl && cuilEl.value) {
        cuilEl.value = cuilEl.value.replace(/[^0-9]/g, '');
      }

      Object.entries(fields).forEach(([key, id]) => {
        const fieldEl = el(id, container);
        const value = fieldEl?.value?.trim();
        if (value) fd.append(key, value);
      });

      // Append branch if bank selected
      const selectedBankCode = el('empBankCode', container)?.value;
      const bankData = bankMaster.find(b => b.code === selectedBankCode);
      if (bankData && bankData.branch) {
        fd.append('bank_branch', bankData.branch);
      }

      const res = await fetch(requestUrl, {
        method: requestMethod,
        body: fd,
        credentials: 'include',
        headers: {
          'X-Requested-With': 'XMLHttpRequest'
        }
      });

      const data = await res.json().catch(() => ({}));

      if (!res.ok || data.status === 'failed') {
        const errorMsg = data.errors?.[0]?.message || data.detail || 'Error al guardar. Verifique los datos.';
        throw new Error(errorMsg);
      }

      showToast('Legajo guardado', 'success');
      
      closeModal();
      await loadEmployees();

    } catch (e) {
      console.error('Submit Employee Error:', e);
      msg.textContent = e.message;
      msg.className = 'error';
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = originalBtnText;
    }
  }

  async function handleDelete(id, name) {
    const ok = await confirmAction(`¿Dar de baja legajo de ${name}?`);
    if (!ok) return;

    try {
      await apiFetch(`/api/employees/${id}`, { method: 'DELETE' });
      showToast('Legajo dado de baja', 'success');
      await loadEmployees();
    } catch {
      showToast('No se pudo dar de baja el legajo', 'error');
    }
  }

  async function handleRestore(id, name) {
    const ok = await confirmAction(`¿Dar de alta legajo de ${name}?`);
    if (!ok) return;

    try {
      await apiFetch(`/api/employees/${id}/restore`, { method: 'POST' });
      showToast('Legajo dado de alta', 'success');
      await loadEmployees();
    } catch {
      showToast('No se pudo dar de alta el legajo', 'error');
    }
  }

  async function handleBulkDelete() {
    const ids = Array.from(selectedIds);
    if (!ids.length) return;

    const ok = await confirmAction(`¿Eliminar ${ids.length} legajos?`);
    if (!ok) return;

    try {
      await apiFetch('/api/employees/bulk-delete', {
        method: 'POST',
        body: { ids },
      });

      selectedIds.clear();
      showToast('Eliminación masiva completada', 'success');
      await loadEmployees();
    } catch {
      showToast('No se pudo completar la eliminación masiva', 'error');
    }
  }

  async function openProfile(employeeId) {
    const body = el('empProfileBody', container);
    body.innerHTML = '<div class="small-muted">Cargando...</div>';
    openUiModal('empProfileModal', container);

    el('empPrintRecord', container).onclick = () => {
      window.open(apiUrl(`/api/employees/${employeeId}/record-pdf`), '_blank');
    };

    el('empProfileEdit', container).onclick = () => {
      closeUiModal('empProfileModal', container);
      openEditModal(employeeId);
    };

    try {
      const res = await apiFetch(`/api/employees/${employeeId}`);
      const emp = res.employee || res;

      el('empProfileTitle', container).innerText = `${emp.last_name}, ${emp.first_name}`;

      const statusBadge = el('empProfileStatusBadge', container);
      statusBadge.innerHTML = '';
      statusBadge.appendChild(badgeForEmpStatus(emp.status));

      const prettyLabels = {
        regimen_previsional: 'Régimen previsional',
        actividad: 'Actividad',
        condicion_laboral: 'Condición laboral',
        situacion_revista: 'Situación de revista',
        zona_desfavorable: 'Zona desfavorable',
        grupo_fijo_concepto: 'Grupo fijo',
        modalidad_de_contratacion: 'Modalidad de contratación',
        situacion_de_revista: 'Situación de revista',
        nro_afiliado_sindicato: 'Afiliado sindicato',
        section: 'Sección',
        baja: 'Baja',
        suc: 'Sucursal',
      };

      const renderValue = (value) => {
        if (value === null || value === undefined || value === '' || value === 'null' || value === 'none') {
          return '<span class="small-muted">—</span>';
        }
        if (typeof value === 'object' && value !== null) {
          return renderValue(value.value);
        }
        return value;
      };

      body.innerHTML = '';

      const renderSection = (title, items) => {
        const sec = document.createElement('section');
        sec.className = 'empresa-profile-section';

        const head = document.createElement('div');
        head.className = 'empresa-profile-section-title';
        head.textContent = title;

        const grid = document.createElement('div');
        grid.className = 'empresa-profile-grid';

        items.forEach((item) => {
          const box = document.createElement('div');
          box.className = 'dl-item';

          const lbl = document.createElement('div');
          lbl.className = 'dl-label';
          lbl.textContent = item.label;

          const val = document.createElement('div');
          val.className = 'dl-value';
          val.innerHTML = renderValue(item.value);

          box.append(lbl, val);
          grid.appendChild(box);
        });

        sec.append(head, grid);
        return sec;
      };

      body.append(
        renderSection('Datos personales', [
          { label: 'Nombre completo', value: `${emp.first_name} ${emp.last_name}` },
          { label: 'DNI', value: emp.dni },
          { label: 'CUIL', value: emp.cuil },
          { label: 'Fecha nac.', value: emp.birth_date },
          { label: 'Sexo', value: emp.gender },
          { label: 'Nacionalidad', value: emp.nationality },
          { label: 'Estado civil', value: emp.marital_status },
          { label: 'Email', value: emp.email },
          { label: 'Teléfono', value: emp.phone },
          { label: 'Dirección', value: formatFullAddress(emp) },
        ]),
        renderSection('Documentación', [
          { label: 'Tipo doc', value: emp.document_type },
          { label: 'Nro doc', value: emp.document_number },
          { label: 'Obra social', value: emp.health_insurance },
          { label: 'Nro afiliado O.S.', value: emp.health_insurance_number },
          { label: 'Sindicato', value: emp.union },
          { label: 'Nro afiliado sindicato', value: emp.union_number },
        ]),
        renderSection('Datos laborales', [
          { label: 'Legajo', value: emp.file_number },
          { label: 'Fecha ingreso', value: emp.hire_date },
          { label: 'Cargo', value: emp.job_title },
          { label: 'Categoría', value: emp.category },
          { label: 'Lugar trabajo', value: emp.work_location },
          { label: 'Tipo contrato', value: emp.hire_type },
          { label: 'Convenio', value: emp.union_agreement },
        ]),
        renderSection('Datos bancarios', [
          { label: 'Banco', value: emp.bank },
          { label: 'Tipo cuenta', value: emp.account_type },
          { label: 'Nro cuenta', value: emp.account_number },
          { label: 'CBU', value: emp.cbu },
          { label: 'Alias', value: emp.alias },
          { label: 'Forma pago', value: emp.payment_method },
        ]),
        renderSection('Datos previsionales', [
          { label: 'Régimen', value: emp.pension_regime },
          { label: 'Actividad', value: emp.activity },
          { label: 'Condición laboral', value: emp.labor_condition },
          { label: 'Situación revista', value: emp.revista_situation },
        ])
      );

      el('empPrintRecord', container).onclick = () => {
        const url = apiUrl(`/api/employees/${employeeId}/record-pdf`);
        const link = document.createElement('a');
        link.href = url;
        link.download = `legajo_${employeeId.substring(0,8)}.pdf`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
      };

    } catch {
      body.innerHTML = '<div class="error">No se pudo cargar el perfil.</div>';
    }
  }

  function toggleExportMenu() {
    const menu = el('exportDropdown', container);
    menu.classList.toggle('hidden');
  }

  async function handleExport(format) {
    el('exportDropdown', container).classList.add('hidden');

    try {
      const debug = el('exportDebugMode', container)?.checked || false;
      const url = apiUrl(`/api/legajo/export?format=${format}${debug ? '&debug=true' : ''}`);

      const link = document.createElement('a');
      link.href = url;
      link.download = `legajo_export_${new Date().toISOString().split('T')[0]}.${format === 'xlsx' ? 'xlsx' : (format === 'txt' ? 'txt' : 'csv')}`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);

      showToast('Exportación iniciada', 'success');
    } catch {
      showToast('No se pudo iniciar la exportación', 'error');
    }
  }

  function openImportModal() {
    el('importStep1', container).classList.remove('hidden');
    el('importStep2', container).classList.add('hidden');
    el('importFileInput', container).value = '';
    openUiModal('importModal', container);
  }

  async function handleFilePreview() {
    const fileInput = el('importFileInput', container);
    const mode = container.querySelector('input[name="importMode"]:checked').value;

    if (!fileInput.files.length) {
      showToast('Seleccioná un archivo', 'warning');
      return;
    }

    if (mode === 'replace') {
      const ok = await confirmAction(
        'Atención: el modo reemplazar puede sobrescribir datos existentes. ¿Deseás continuar?'
      );
      if (!ok) return;
    }

    const formData = new FormData();
    formData.append('file', fileInput.files[0]);
    formData.append('mode', mode);

    const btn = el('btnDoPreview', container);
    const originalText = btn.textContent;
    btn.disabled = true;
    btn.textContent = 'Procesando archivo...';

    try {
      const res = await apiFetch('/api/legajo/preview', {
        method: 'POST',
        body: formData,
      });

      currentJobId = res.id;
      renderImportPreview(res);

      el('importStep1', container).classList.add('hidden');
      el('importStep2', container).classList.remove('hidden');
    } catch (e) {
      showToast(e.body?.detail || 'No se pudo procesar el archivo', 'error');
    } finally {
      btn.disabled = false;
      btn.textContent = originalText;
    }
  }

  function renderImportPreview(job) {
    const summary = el('importSummary', container);
    summary.innerHTML = `
      <div class="kpi-card">
        <div class="kpi-value">${job.total_rows}</div>
        <div class="kpi-label">Filas totales</div>
      </div>
      <div class="kpi-card empresa-kpi-success">
        <div class="kpi-value">${job.inserted_count || 0}</div>
        <div class="kpi-label">Nuevos</div>
      </div>
      <div class="kpi-card empresa-kpi-info">
        <div class="kpi-value">${job.updated_count || 0}</div>
        <div class="kpi-label">Actualizados</div>
      </div>
      <div class="kpi-card empresa-kpi-error">
        <div class="kpi-value">${job.invalid_rows || 0}</div>
        <div class="kpi-label">Errores</div>
      </div>
    `;

    const tbody = el('importPreviewTable', container).querySelector('tbody');
    tbody.innerHTML = '';
    
    // Selection state for import
    const selectedIndices = new Set();
    let currentPreviewPage = 1;
    const PAGE_SIZE = 50;

    const addRowsToTable = (rows, startIndex) => {
      rows.forEach((row, idx) => {
        const absoluteIndex = startIndex + idx;
        const tr = document.createElement('tr');

        const actionMap = {
          insert: { label: 'Nuevo', cls: 'success' },
          update: { label: 'Actualizar', cls: 'warning' },
          reactivate: { label: 'Reactivar', cls: 'info' },
          skip: { label: 'Ignorado', cls: 'muted' },
          invalid: { label: 'Invalido', cls: 'error' }
        };

        const act = actionMap[row.planned_action] || { label: row.planned_action, cls: 'muted' };
        const reason = (row.resolution_status === 'invalid' && row.validation_errors_json?.length)
          ? `: ${row.validation_errors_json[0]}`
          : '';

        const firstName = row.normalized_data_json?.identity?.first_name || '';
        const lastName = row.normalized_data_json?.identity?.last_name || '';
        const fullName = (firstName || lastName)
          ? `${firstName} ${lastName}`.trim()
          : 'Nombre no detectable';

        const isSelectable = row.planned_action === 'insert' || row.planned_action === 'update' || row.planned_action === 'reactivate';
        
        // Auto-select if valid (User requested "todos por defecto")
        if (isSelectable) selectedIndices.add(absoluteIndex);

        tr.innerHTML = `
          <td class="text-center">
            <input type="checkbox" class="row-select" ${selectedIndices.has(absoluteIndex) ? 'checked' : ''} ${!isSelectable ? 'disabled' : ''} data-index="${absoluteIndex}" />
          </td>
          <td>${row.source_row_number}</td>
          <td class="small-muted">${row.external_key || '-'}</td>
          <td class="empresa-import-name">${fullName}</td>
          <td>
            <span class="badge ${act.cls}">${act.label}${reason}</span>
          </td>
          <td>
            <button class="btn btn-ghost btn-sm btn-view-raw">Ver</button>
          </td>
        `;

        const ck = tr.querySelector('.row-select');
        ck.onchange = (e) => {
          if (e.target.checked) selectedIndices.add(absoluteIndex);
          else selectedIndices.delete(absoluteIndex);
          updateImportSummary();
        };

        tr.querySelector('.btn-view-raw').onclick = () => {
          showRawDataModal(row.normalized_data_json);
        };

        tbody.appendChild(tr);
      });
      updateImportSummary();
    };

    const updateImportSummary = () => {
      const btnExecute = el('btnExecuteImport', container);
      btnExecute.disabled = selectedIndices.size === 0;
      
      // Update counts in UI header if needed (optional)
      const countLabel = el('importSelectedCount', container);
      if (countLabel) countLabel.textContent = `Seleccionados: ${selectedIndices.size}`;
    };

    // Initial Load (already includes first page usually, but let's be explicit)
    const initialRows = (job.rows || []).slice(0, PAGE_SIZE);
    addRowsToTable(initialRows, 0);

    // Handle "Load More"
    if (job.total_rows > PAGE_SIZE) {
      const loadMoreContainer = document.createElement('div');
      loadMoreContainer.className = 'text-center p-16';
      loadMoreContainer.innerHTML = `<button class="btn btn-secondary btn-sm" id="btnLoadMoreRows">Ver más (${job.total_rows - PAGE_SIZE} restantes)</button>`;
      tbody.parentNode.after(loadMoreContainer);

      const btnLoadMore = loadMoreContainer.querySelector('#btnLoadMoreRows');
      btnLoadMore.onclick = async () => {
        currentPreviewPage++;
        btnLoadMore.disabled = true;
        btnLoadMore.textContent = 'Cargando...';
        
        try {
          const nextRows = await apiFetch(`/api/legajo/import/jobs/${job.id}/rows?page=${currentPreviewPage}&page_size=${PAGE_SIZE}`);
          addRowsToTable(nextRows, (currentPreviewPage - 1) * PAGE_SIZE);
          
          const remaining = job.total_rows - (currentPreviewPage * PAGE_SIZE);
          if (remaining <= 0) {
            loadMoreContainer.remove();
          } else {
            btnLoadMore.disabled = false;
            btnLoadMore.textContent = `Ver más (${remaining} restantes)`;
          }
        } catch (e) {
          showToast('Error al cargar más filas', 'error');
          btnLoadMore.disabled = false;
        }
      };
    }

    // Handle Select All in Preview
    const th = el('importPreviewTable', container).querySelector('thead tr');
    if (th && !th.querySelector('.select-all-import')) {
      const checkTh = document.createElement('th');
      checkTh.className = 'text-center';
      checkTh.innerHTML = '<input type="checkbox" class="select-all-import" checked />';
      th.prepend(checkTh);
      
      th.querySelector('.select-all-import').onchange = (e) => {
        const checked = e.target.checked;
        container.querySelectorAll('.row-select').forEach(ck => {
          if (!ck.disabled) {
            ck.checked = checked;
            const idx = parseInt(ck.dataset.index);
            if (checked) selectedIndices.add(idx);
            else selectedIndices.delete(idx);
          }
        });
        updateImportSummary();
      };
    }

    el('btnExecuteImport', container).onclick = async () => {
      const selected = Array.from(selectedIndices);
      if (selected.length === 0) {
        showToast('Debes seleccionar al menos un registro', 'warning');
        return;
      }

      // UX Premium: Confirmation with backend-calculated counts
      try {
        const summary = await apiFetch('/api/legajo/preview-execution', {
          method: 'POST',
          body: { job_id: job.id, selected_rows: selected }
        });

        const ok = await confirmAction(
          `Vas a importar ${summary.total_selected} empleados:\n` +
          `• ${summary.new_count} nuevos\n` +
          `• ${summary.update_count} a actualizar\n\n` +
          `¿Confirmar operación?`
        );
        if (!ok) return;

        await executeImport(job.id, selected);
      } catch (e) {
        showToast('Error al obtener resumen de ejecución', 'error');
      }
    };

    el('btnExecuteImport', container).disabled = job.valid_rows === 0;
  }

  function showRawDataModal(data) {
    const box = el('importRawContent', container);
    
    const formatRawAddress = () => {
      const street = data.address?.address || data.address || '';
      const number = data.address?.address_number || data.address_number || '';
      const city = data.address?.city || data.city || '';
      const province = data.address?.province || data.province || '';

      let formatted = '';
      if (street && number) formatted = `${street} ${number}`;
      else if (street) formatted = street;
      else if (number) formatted = number;

      if (city || province) {
        const loc = city && province ? `${city} (${province})` : (city || province);
        formatted = formatted ? `${formatted}, ${loc}` : loc;
      }

      return formatted || null;
    };

    const sections = [
      { title: 'Personal', fields: { 
          'Nombre': `${data.identity?.first_name || ''} ${data.identity?.last_name || ''}`,
          'DNI': data.identity?.dni,
          'CUIL': data.identity?.cuil,
          'Nacimiento': data.identity?.birth_date,
          'Género': data.identity?.gender
      }},
      { title: 'Contacto', fields: { 
          'Email': data.address?.email,
          'Teléfono': data.address?.phone,
          'Dirección': formatRawAddress(),
          'Ciudad': data.address?.city
      }},
      { title: 'Laboral', fields: { 
          'Ingreso': data.employment?.hire_date,
          'Puesto': data.employment?.job_title,
          'Categoría': data.employment?.category,
          'C. Costo': data.employment?.cost_center,
          'Contrato': data.employment?.hire_type
      }},
      { title: 'Bancario', fields: { 
          'Banco': data.banking?.bank,
          'CBU': data.banking?.cbu,
          'Alias': data.banking?.bank_alias,
          'Met. Pago': data.banking?.payment_method
      }}
    ];

    let html = '<div class="preview-sections-grid">';
    sections.forEach(s => {
      const hasAny = Object.values(s.fields).some(v => v);
      if (!hasAny) return;

      html += `
        <div class="preview-section">
          <div class="preview-section-title">${s.title}</div>
          <div class="preview-section-body">
            ${Object.entries(s.fields).map(([label, val]) => val ? `
              <div class="preview-field">
                <span class="preview-field-label">${label}:</span>
                <span class="preview-field-value">${val}</span>
              </div>
            ` : '').join('')}
          </div>
        </div>
      `;
    });
    html += '</div>';

    box.innerHTML = html;
    openUiModal('importRawModal', container);
  }

  async function executeImport(jobId, selectedRows) {
    const btn = el('btnExecuteImport', container);
    const originalText = btn.textContent;
    btn.disabled = true;
    
    btn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" style="width:1.2em; height:1.2em; vertical-align:middle; margin-right:8px; animation: spin 1s linear infinite; display:inline-block;"><style>@keyframes spin { 100% { transform: rotate(360deg); } }</style><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" style="opacity:0.25"></circle><path fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" style="opacity:0.75"></path></svg> Impactando registros...`;

    try {
      const res = await apiFetch('/api/legajo/execute', {
        method: 'POST',
        body: { job_id: jobId, selected_rows: selectedRows },
      });

      showToast(`Importación exitosa: ${res.inserted || 0} creados, ${res.updated || 0} actualizados`, 'success');
      closeUiModal('importModal', container);
      
      setTimeout(() => {
        window.location.reload();
      }, 1500);
      
    } catch (e) {
      showToast(e.body?.detail || 'No se pudo ejecutar la importación', 'error');
      btn.disabled = false;
      btn.textContent = originalText;
    }
  }

  async function openDniUpload(employeeId) {
    el('dniUploadEmpId', container).value = employeeId;
    el('dniFileFront', container).value = '';
    el('dniFileBack', container).value = '';
    el('dniUploadMsg', container).textContent = '';
    openUiModal('dniUploadModal', container);
  }

  async function handleDniUpload() {
    const fileFront = el('dniFileFront', container).files[0];
    const fileBack = el('dniFileBack', container).files[0];
    const employeeId = el('dniUploadEmpId', container).value;

    if (!fileFront || !fileBack) {
      const msg = el('dniUploadMsg', container);
      msg.textContent = 'Seleccioná frente y dorso del DNI.';
      msg.className = 'error';
      return;
    }

    const msgArea = el('dniUploadMsg', container);
    msgArea.textContent = 'Procesando documentos...';
    msgArea.className = 'small-muted';
    el('dniUploadSubmit', container).disabled = true;

    try {
      const base = getApiBase();

      const fdBack = new FormData();
      fdBack.append('side', 'back');
      fdBack.append('file', fileBack);

      const resBack = await fetch(`${base}/api/employees/${employeeId}/dni-upload`, {
        method: 'POST',
        body: fdBack,
        credentials: 'include',
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
      });

      if (!resBack.ok) throw new Error('No se pudo subir el dorso del DNI.');

      const fdFront = new FormData();
      fdFront.append('side', 'front');
      fdFront.append('file', fileFront);

      const resFront = await fetch(`${base}/api/employees/${employeeId}/dni-upload`, {
        method: 'POST',
        body: fdFront,
        credentials: 'include',
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
      });

      const data = await resFront.json();

      if (resFront.ok && data.success) {
        closeUiModal('dniUploadModal', container);
        showOcrConfirmation(data.data, employeeId);
      } else {
        throw new Error(data.detail || data.error || 'No se pudo procesar el frente del DNI.');
      }
    } catch (e) {
      msgArea.textContent = `No se pudo procesar el DNI: ${e.message}`;
      msgArea.className = 'error';
    } finally {
      el('dniUploadSubmit', container).disabled = false;
    }
  }

  function showOcrConfirmation(data, employeeId) {
    el('ocrEmpId', container).value = employeeId;
    el('ocrFirstName', container).value = data.first_name || '';
    el('ocrLastName', container).value = data.last_name || '';
    el('ocrDni', container).value = data.dni || '';
    el('ocrBirthDate', container).value = data.birth_date || '';

    const msgArea = el('ocrMsg', container);
    msgArea.textContent = '';

    if (data.error) {
      msgArea.innerHTML = '<div class="error">No se pudieron extraer todos los datos automáticamente.</div>';
    }

    openUiModal('dniOcrModal', container);
  }

  async function confirmOcr() {
    const employeeId = el('ocrEmpId', container).value;
    const payload = {
      first_name: el('ocrFirstName', container).value.trim(),
      last_name: el('ocrLastName', container).value.trim(),
      dni: el('ocrDni', container).value.trim(),
      birth_date: el('ocrBirthDate', container).value,
    };

    try {
      await apiFetch(`/api/employees/${employeeId}`, {
        method: 'PATCH',
        body: payload,
      });

      showToast('Datos confirmados y guardados', 'success');
      closeUiModal('dniOcrModal', container);
      await loadEmployees();
    } catch (e) {
      el('ocrMsg', container).innerHTML = `<div class="error">Error al guardar: ${e.message}</div>`;
    }
  }

  el('btnImportLegajo', container).onclick = openImportModal;
  el('btnExportMenu', container).onclick = (e) => {
    e.stopPropagation();
    toggleExportMenu();
  };

  container.querySelectorAll('.btn-export').forEach((btn) => {
    btn.onclick = () => handleExport(btn.dataset.format);
  });

  window.addEventListener('click', () => {
    const menu = el('exportDropdown', container);
    if (menu) menu.classList.add('hidden');
  });

  el('importCloseTop', container).onclick = () => closeUiModal('importModal', container);
  el('importCancel', container).onclick = () => closeUiModal('importModal', container);
  el('importCancel2', container).onclick = () => closeUiModal('importModal', container);
  el('btnDoPreview', container).onclick = handleFilePreview;
  el('btnRestartImport', container).onclick = () => {
    el('importStep1', container).classList.remove('hidden');
    el('importStep2', container).classList.add('hidden');
  };
  el('btnExecuteImport', container).onclick = executeImport;
  el('importRawClose', container).onclick = () => closeUiModal('importRawModal', container);

  el('btnNewEmployee', container).onclick = openModal;
  el('empClose', container).onclick = closeModal;
  el('empSubmit', container).onclick = withLoader(submitEmployee);
  el('btnBulkDelete', container).onclick = handleBulkDelete;
  el('btnBack', container).onclick = () => {
    location.hash = '#/empresa/dashboard';
  };
  el('empProfileClose', container).onclick = () => closeUiModal('empProfileModal', container);

  el('selectAllEmployees', container).onchange = (e) => {
    employees.forEach((emp) => {
      if (e.target.checked) selectedIds.add(emp.id);
      else selectedIds.clear();
    });
    updateBulkUI();
    renderEmployees();
  };

  el('searchEmployees', container).addEventListener('input', (e) => {
    searchText = e.target.value;
    renderEmployees();
  });

  container.querySelector('#employeesTable thead').addEventListener('click', (e) => {
    const th = e.target.closest('th.sortable');
    if (!th) return;

    const field = th.dataset.sort;
    if (sortField === field) {
      sortOrder = sortOrder === 'asc' ? 'desc' : 'asc';
    } else {
      sortField = field;
      sortOrder = 'asc';
    }
    renderEmployees();
  });

  el('empSearch', container).oninput = (e) => {
    const search = e.target.value.toLowerCase();

    const filtered = employees.filter((emp) =>
      (emp.first_name || '').toLowerCase().includes(search) ||
      (emp.last_name || '').toLowerCase().includes(search) ||
      (emp.dni || '').toLowerCase().includes(search)
    );

    renderEmployees(filtered);
  };

  const statusEl = el('empStatus', container);
  if (statusEl) {
    statusEl.onchange = (e) => {
      if (e.target.value === 'inactive') {
        el('groupTermination', container).classList.remove('hidden');
      } else {
        el('groupTermination', container).classList.add('hidden');
      }
    };
  }

  container.querySelectorAll('.tab-btn').forEach((btn) => {
    btn.onclick = () => {
      const targetId = btn.dataset.tab;

      container.querySelectorAll('.tab-btn').forEach((b) => b.classList.remove('active'));
      container.querySelectorAll('.tab-panel').forEach((panel) => panel.classList.add('hidden'));

      btn.classList.add('active');
      el(targetId, container).classList.remove('hidden');
    };
  });

  el('dniUploadClose', container).onclick = () => closeUiModal('dniUploadModal', container);
  el('dniUploadSubmit', container).onclick = handleDniUpload;
  el('ocrClose', container).onclick = () => {
    closeUiModal('dniOcrModal', container);
    openEditModal(el('ocrEmpId', container).value);
  };
  el('ocrConfirm', container).onclick = confirmOcr;

  // Bank change
  const bankSelect = el('empBankCode', container);
  if (bankSelect) {
    bankSelect.onchange = handleBankChange;
  }

  // --- TRASH BIN LOGIC ---
  async function openDeletedEmployees() {
    openUiModal('deletedEmployeesModal', container);
    await loadDeletedEmployees();
  }

  async function loadDeletedEmployees() {
    const tbody = el('deletedEmployeesTable', container).querySelector('tbody');
    const msg = el('deletedEmployeesMsg', container);
    const selectAll = el('selectAllDeleted', container);
    
    tbody.innerHTML = '<tr><td colspan="5" class="text-center small-muted">Cargando...</td></tr>';
    msg.textContent = '';
    selectAll.checked = false;
    updateDeletedBulkBar();

    try {
      const res = await apiFetch('/api/employees/deleted');
      const deleted = res.employees || [];

      if (!deleted.length) {
        tbody.innerHTML = '<tr><td colspan="5" class="text-center small-muted">No hay empleados en la sección de bajas.</td></tr>';
        return;
      }

      tbody.innerHTML = '';
      deleted.forEach(emp => {
        const tr = document.createElement('tr');
        
        const tdCheck = document.createElement('td');
        tdCheck.className = 'empresa-check-col';
        const check = document.createElement('input');
        check.type = 'checkbox';
        check.className = 'deleted-row-check';
        check.dataset.id = emp.id;
        check.onchange = updateDeletedBulkBar;
        tdCheck.appendChild(check);

        const tdName = document.createElement('td');
        tdName.innerHTML = `<strong>${emp.full_name}</strong><br><span class="small-muted">${emp.email || 'Sin email'}</span>`;
        
        const tdDni = document.createElement('td');
        tdDni.textContent = emp.dni || '-';

        const tdDate = document.createElement('td');
        tdDate.textContent = emp.deleted_at ? new Date(emp.deleted_at).toLocaleDateString() : '-';

        const tdActions = document.createElement('td');
        const actionBox = document.createElement('div');
        actionBox.className = 'flex gap-8';

        const btnRestore = document.createElement('button');
        btnRestore.className = 'btn btn-success btn-sm';
        btnRestore.textContent = 'Dar de Alta';
        btnRestore.onclick = async () => {
          const ok = await confirmAction(`¿Dar de alta a ${emp.full_name}?`);
          if (!ok) return;

          try {
            await apiFetch(`/api/employees/${emp.id}/restore`, { method: 'POST' });
            showToast('Empleado dado de alta', 'success');
            await loadDeletedEmployees();
            await loadEmployees();
          } catch (e) {
            showToast(e.body?.detail || 'Error al dar de alta', 'error');
          }
        };

        const btnHardDelete = document.createElement('button');
        btnHardDelete.className = 'btn btn-danger btn-sm';
        btnHardDelete.textContent = 'Baja definitiva';
        btnHardDelete.onclick = async () => {
          const ok = await confirmAction(`¿ELIMINAR DEFINITIVAMENTE a ${emp.full_name}? Esta acción no se puede deshacer.`);
          if (!ok) return;

          try {
            await apiFetch(`/api/employees/${emp.id}/hard`, { method: 'DELETE' });
            showToast('Empleado eliminado definitivamente', 'success');
            await loadDeletedEmployees();
          } catch (e) {
            showToast(e.body?.detail || 'Error en la baja definitiva', 'error');
          }
        };

        actionBox.append(btnRestore, btnHardDelete);
        tdActions.appendChild(actionBox);

        tr.append(tdCheck, tdName, tdDni, tdDate, tdActions);
        tbody.appendChild(tr);
      });

    } catch (e) {
      tbody.innerHTML = '<tr><td colspan="5" class="text-center text-danger">Error al cargar las bajas.</td></tr>';
      msg.textContent = 'No se pudieron cargar los empleados dados de baja.';
      msg.className = 'error mb-16';
    }
  }

  function updateDeletedBulkBar() {
    const checks = container.querySelectorAll('.deleted-row-check:checked');
    const bar = el('deletedBulkActions', container);
    const count = el('deletedBulkCount', container);
    const selectAll = el('selectAllDeleted', container);
    const allChecks = container.querySelectorAll('.deleted-row-check');

    if (checks.length > 0) {
      bar.classList.remove('hidden');
      count.textContent = `${checks.length} seleccionados`;
    } else {
      bar.classList.add('hidden');
    }

    if (allChecks.length > 0 && checks.length === allChecks.length) {
      selectAll.checked = true;
    } else {
      selectAll.checked = false;
    }
  }

  el('selectAllDeleted', container).onchange = (e) => {
    const checked = e.target.checked;
    container.querySelectorAll('.deleted-row-check').forEach(c => c.checked = checked);
    updateDeletedBulkBar();
  };

  el('btnDeletedBulkRestore', container).onclick = async () => {
    const checks = container.querySelectorAll('.deleted-row-check:checked');
    const ids = Array.from(checks).map(c => c.dataset.id);
    if (!ids.length) return;

    const ok = await confirmAction(`¿Dar de alta a ${ids.length} empleados seleccionados?`);
    if (!ok) return;

    try {
      const res = await apiFetch('/api/employees/bulk-restore', {
        method: 'POST',
        body: { employee_ids: ids }
      });
      showToast(`${res.restored} empleados dados de alta`, 'success');
      await loadDeletedEmployees();
      await loadEmployees();
    } catch (e) {
      showToast(e.body?.detail || 'Error en restauración masiva', 'error');
    }
  };

  el('btnDeletedBulkHardDelete', container).onclick = async () => {
    const checks = container.querySelectorAll('.deleted-row-check:checked');
    const ids = Array.from(checks).map(c => c.dataset.id);
    if (!ids.length) return;

    const ok = await confirmAction(`¿ELIMINAR DEFINITIVAMENTE a ${ids.length} empleados? Esta acción NO se puede deshacer.`);
    if (!ok) return;

    try {
      const res = await apiFetch('/api/employees/bulk-hard-delete', {
        method: 'POST',
        body: { employee_ids: ids }
      });
      showToast(`${res.deleted} empleados eliminados definitivamente`, 'success');
      await loadDeletedEmployees();
    } catch (e) {
      showToast(e.body?.detail || 'Error en baja definitiva masiva', 'error');
    }
  };

  el('btnShowDeleted', container).onclick = openDeletedEmployees;
  el('deletedEmployeesClose', container).onclick = () => closeUiModal('deletedEmployeesModal', container);

  // Parallel data loading
  try {
    await Promise.all([
      loadEmployees(),
      loadBanks()
    ]);
  } catch (e) {
    console.error("Init error:", e);
  }
}