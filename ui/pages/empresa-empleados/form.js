import { apiFetch, el, showToast, validateCuil, closeModal } from '../../common.js';

export function initEmployeeForm(container, { onSave }) {
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
    talle_camisa: 'empTalleCamisa',
    talle_pantalon: 'empTallePantalon',
    talle_zapato: 'empTalleZapato',
    estudios_cursados: 'empEstudiosCursados',
    antecedentes_laborales: 'empAntecedentesLaborales',
    datos_familiares: 'empDatosFamiliares',
  };

  const btnSubmit = el('btnSaveEmployee', container) || el('employeeSubmit', container);
  
  if (btnSubmit) {
    btnSubmit.onclick = async () => {
      const fd = new FormData();
      let hasError = false;

      // Basic validation
      ['empFirstName', 'empLastName', 'empDni', 'empCuil'].forEach(id => {
        const val = el(id, container)?.value?.trim();
        if (!val) hasError = true;
      });

      if (hasError) {
        showToast('Campos obligatorios faltantes', 'error');
        return;
      }

      const cuil = el('empCuil', container).value.trim();
      if (!validateCuil(cuil)) {
        showToast('CUIL inválido', 'error');
        return;
      }

      Object.entries(fields).forEach(([key, id]) => {
        const val = el(id, container)?.value?.trim();
        if (val) fd.append(key, val);
      });

      try {
        await apiFetch('/api/employees', { method: 'POST', body: fd });
        showToast('Legajo guardado', 'success');
        onSave();
        closeModal('employeeModal', container);
      } catch (e) {
        showToast(e.message || 'Error al guardar', 'error');
      }
    };
  }

  // Tab logic
  container.querySelectorAll('.tab-btn').forEach(btn => {
    btn.onclick = () => {
      container.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      container.querySelectorAll('.tab-panel').forEach(p => p.classList.add('hidden'));
      btn.classList.add('active');
      el(btn.dataset.tab, container).classList.remove('hidden');
    };
  });
}
