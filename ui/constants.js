export const SYSTEM_VERSION = "v1.2.5-industrial";

export const LABELS = {
  // Navigation & Heads
  dashboard: "Panel de control",
  employees: "Empleados",
  receipts: "Recibos",
  history: "Historial",
  configuration: "Configuración",
  
  // Domains
  employee: "Empleado",
  nomina: "Nómina",
  receipt: "Recibo",
  receiptbatch: "Lote de Recibos",
  
  // Actions
  uploadReceipts: "Subir recibos",
  bulkActions: "Acciones de lote",
  deleteSelection: "Eliminar selección",
  uploadSignature: "Subir firma",
  refresh: "Actualizar sección",
  
  // Common UI
  loading: "Cargando...",
  saving: "Guardando...",
  save: "Guardar",
  saveChanges: "Guardar cambios",
  cancel: "Cancelar",
  close: "Cerrar",
  delete: "Eliminar",
  create: "Crear",
  edit: "Editar",
  search: "Buscar",
  view: "Ver",
  download: "Descargar",
  print: "Imprimir",
  sign: "Firmar",
  reject: "Rechazar",
  confirm: "Confirmar",
  
  // States
  pending: "Pendiente",
  signed: "Firmado",
  orphan: "Sin vincular",
  processed: "Procesado"
};

export const TOS_VERSION = "2026.04.27";

export const ROUTES = {
  // Common
  root: "#/",
  selectRole: "#/select-role",
  auth: "#/auth",
  documentation: "#/documentacion",
  tosGate: "#/tos-gate",
  
  // Admin Routes
  dashboard: "#/empresa/dashboard",
  employees: "#/empresa/empleados",
  history: "#/empresa/historial",
  configuration: "#/empresa/configuracion",
  onboarding: "#/empresa/onboarding",
  
  // Employee Routes
  home: "#/empleado/home",
  myReceipts: "#/empleado/recibos",
  myProfile: "#/empleado/perfil",
  
  // Auth
  login: "#/login",
  logout: "#/logout",
  verifyAccount: "#/verify-account",
  
  // Public/Special
  sign: "#/sign",
  verify: "#/verify"
};

export const DOMAINS = {
  STATUSES: {
    ACTIVE: "active",
    PRE_REGISTERED: "pre_registered",
    REGISTERED: "registered",
    INVITED: "invited",
    INACTIVE: "inactive",
    PENDING: "pending",
    SIGNED: "signed",
    PENDING_MATCH: "pending_match",
    REJECTED: "rejected",
    PENDING_EMPLOYEE_SIGNATURE: "pending_employee_signature",
    PENDING_EMPLOYER_SIGNATURE: "pending_employer_signature"
  },

  MOVEMENT_TYPES: {
    receipt: "comprobante",
    movement: "movimiento",
    transfer: "transferencia",
    audit: "auditoría"
  },
  
  RECEIPT_FLOW: {
    UPLOADED: { id: "pending_match", label: "Subido / Por vincular", icon: "upload" },
    PROCESSED: { id: "pending", label: "Procesado / Esperando Firma", icon: "check" },
    SIGNING_EMPLOYER: { id: "pending_employer_signature", label: "Firma de Empresa", icon: "pen" },
    SIGNING_EMPLOYEE: { id: "pending_employee_signature", label: "Firma de Empleado", icon: "user" },
    ARCHIVED: { id: "signed", label: "Archivado / Válido", icon: "archive" },
    REJECTED: { id: "rejected", label: "Observado", icon: "x" }
  }
};
