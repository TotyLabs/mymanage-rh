"""
Column Mapping V3 — hybrid mapper for TABLE_MODE + FORM_MODE.

Goals:
- Works with classic tabular headers
- Works with parser-produced semantic keys
- Preserves backward compatibility where possible
- Aligns canonical paths with current normalized JSON schema

Scoring:
  100 = exact normalized match
   90 = direct parser key / known semantic key
   75 = strong contains / alias overlap
   60 = fuzzy token overlap
    0 = no match

Threshold:
  < 50 => ignored
"""

import re
import unicodedata
from typing import Dict, List, Tuple, Optional

MAPPING_VERSION = "3"


# ---------------------------------------------------------------------
# NORMALIZATION
# ---------------------------------------------------------------------
def normalize_header(s: str) -> str:
    """
    Normalizes a header / field name:
    - lowercase
    - removes accents
    - replaces non-alphanumeric with underscore
    - collapses underscores
    Example:
      "N° Documento" -> "n_documento"
      "Fecha Nac."   -> "fecha_nac"
    """
    if not s:
        return ""

    s = str(s).strip().lower()
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s


def token_overlap(a: str, b: str) -> int:
    ta = set(a.split("_"))
    tb = set(b.split("_"))
    if not ta or not tb:
        return 0
    inter = len(ta & tb)
    if inter == 0:
        return 0
    return int((inter / max(1, len(tb))) * 100)


# ---------------------------------------------------------------------
# CANONICAL SEMANTIC MAP
# These aliases cover:
# - user uploaded tables
# - form parser outputs
# - HR / payroll real-world variants
# ---------------------------------------------------------------------
SEMANTIC_FIELD_MAP: Dict[str, List[str]] = {
    # -------------------------
    # Identity
    # -------------------------
    "identity.dni": [
        "dni", "documento", "nro_documento", "numero_documento",
        "doc", "cedula", "dni_empleado", "identificacion",
        "n_documento", "nro_doc", "doc_nro", "document_number"
    ],
    "identity.cuil": [
        "cuil", "cuit", "cuil_cuit", "numero_cuil", "cuil_nro", "cuit_cuil"
    ],
    "identity.first_name": [
        "nombre", "nombres", "first_name", "primer_nombre"
    ],
    "identity.last_name": [
        "apellido", "apellidos", "last_name", "primer_apellido"
    ],
    "identity.full_name": [
        "apellido_y_nombre", "nombre_y_apellido", "nombre_completo", "full_name",
        "empleado", "persona", "nombre_empleado"
    ],
    "identity.gender": [
        "sexo", "genero", "gender"
    ],
    "identity.birth_date": [
        "birth_date", "fecha_nacimiento", "fecha_nac", "fec_nac", "f_nac",
        "nacimiento", "fecha_de_nacimiento"
    ],
    "identity.marital_status": [
        "estado_civil", "civil_status", "marital_status"
    ],
    "identity.nationality": [
        "nacionalidad", "nationality", "pais"
    ],

    # -------------------------
    # Address / Contact
    # -------------------------
    "address.email": [
        "email", "correo", "mail", "e_mail", "correo_electronico",
        "casilla", "gmail", "email_personal", "mail_personal"
    ],
    "address.phone": [
        "telefono", "celular", "tel", "phone", "contacto",
        "telefono_particular", "telefono_celular", "movil", "mobile"
    ],
    "address.address": [
        "domicilio", "calle", "direccion", "street", "vivienda", "address",
        "domicilio_particular", "direccion_particular"
    ],
    "address.city": [
        "localidad", "ciudad", "pueblo", "city"
    ],
    "address.province": [
        "provincia", "estado", "region", "province"
    ],
    "address.postal_code": [
        "codigo_postal", "cp", "postal_code", "zip", "c_postal"
    ],
    "address.address_number": [
        "numero", "numero_domicilio", "nro_domicilio", "nro", "altura",
        "numero_altura", "number", "address_number",
    ],

    # -------------------------
    # Documentary
    # -------------------------
    "documentary.document_type": [
        "tipo_documento", "doc_type", "tipo_doc", "document_type"
    ],
    "documentary.document_number": [
        "numero_documento_otro", "doc_number", "nro_doc_otro", "document_number", "nro_doc", "nro_documento", "document_nro"
    ],
    "documentary.health_insurance": [
        "obra_social", "os", "salud", "cobertura", "health_insurance"
    ],
    "documentary.health_insurance_number": [
        "nro_afiliado_os", "os_number", "afiliado_os", "obra_social_numero", "nro_afiliado", "nro_afiliacion", "obra_social_nro", "afiliado_obra_social"
    ],
    "documentary.union": [
        "sindicato", "union", "gremio"
    ],
    "documentary.union_number": [
        "nro_afiliado_sindicato", "union_number", "afiliado_sindicato", "nro_afiliado_sind", "nro_afiliado_sindical", "nro_afiliado_gremio", "afiliado_sind", "sindicato_nro"
    ],

    # -------------------------
    # Employment
    # -------------------------
    "employment.file_number": [
        "numero_de_legajo", "legajo", "nro_legajo", "file_number",
        "id_empleado", "legajo_nro"
    ],
    "employment.hire_date": [
        "hire_date", "fecha_de_ingreso", "fecha_ingreso", "fecha_ing",
        "fec_ingreso", "f_ing", "f_ingreso", "ingreso", "desde"
    ],
    "employment.termination_date": [
        "termination_date", "fecha_de_egreso", "fecha_egreso", "fecha_baja",
        "f_egreso", "egreso", "hasta", "baja"
    ],
    "employment.job_title": [
        "cargo", "puesto", "job_title", "position", "funcion",
        "job", "job_role"
    ],
    "employment.category": [
        "categoria", "category", "nivel"
    ],
    "employment.task": [
        "tarea", "task"
    ],
    "employment.cost_center": [
        "centro_de_costo", "cost_center", "sector", "area"
    ],
    "employment.union_agreement": [
        "convenio", "cct", "union_agreement"
    ],
    "employment.hire_type": [
        "tipo_contrato", "hire_type", "contract_type", "modalidad_de_contratacion"
    ],
    "employment.work_location": [
        "seccion", "sección", "secci", "seccin", "seccion_laboral", "lugar_trabajo", "work_location", "sede", "lugar_de_trabajo"
    ],
    "employment.status": [
        "estado", "status", "situacion", "situacion_de_revista"
    ],
    "employment.status_reason": [
        "motivo", "status_reason", "observaciones", "motivo_baja"
    ],

    # extra but useful, aligned with parser output
    "employment.section": [
        "section", "seccion", "seccion_laboral"
    ],
    "employment.antiguedad": [
        "antiguedad"
    ],
    "employment.sucursal": [
        "suc", "sucursal"
    ],

    # -------------------------
    # Banking
    # -------------------------
    "banking.bank": [
        "banco", "bank", "entidad"
    ],
    "banking.account_type": [
        "tipo_cuenta", "account_type"
    ],
    "banking.account_number": [
        "cuenta", "numero_cuenta", "nro_cuenta", "box", "account_number", "nro_cta", "nro_cuenta_bancaria", "numero_de_cuenta", "cuenta_bancaria"
    ],
    "extra.ieric_number": [
        "nro_ieric", "numero_ieric", "ieric", "nro_ieric_construccion", "numero_ieric_construccion", "ieric_number"
    ],
    "banking.cbu": [
        "cbu", "c_b_u", "clave_bancaria"
    ],
    "banking.bank_alias": [
        "alias", "bank_alias", "alias_cbu", "alias_cba", "alias_banco"
    ],
    "banking.payment_method": [
        "forma_pago", "payment_method", "forma_de_pago"
    ],
    "banking.payment_place": [
        "lugar_pago", "payment_place", "lugar_de_pago"
    ],

    # -------------------------
    # Pension / Payroll
    # -------------------------
    "pension.pension_regime": [
        "regimen_previsional", "pension_regime"
    ],
    "pension.activity": [
        "actividad", "activity"
    ],
    "pension.labor_condition": [
        "condicion_laboral", "labor_condition"
    ],
    "pension.revista_situation": [
        "situacion_revista", "revista_situation"
    ],

    # -------------------------
    # Dynamic payroll extras that parser already captures
    # They can stay as structured canonical paths too.
    # -------------------------
    "extra.base_aguinaldo": [
        "base_aguinaldo"
    ],
    "extra.tipo_de_remuneracion": [
        "tipo_de_remuneracion"
    ],
    "extra.remuneracion_covenio": [
        "remuneracion_covenio"
    ],
    "extra.remuneracion_reducida": [
        "remuneracion_reducida"
    ],
    "extra.zona_desfavorable": [
        "zona_desfavorable"
    ],
    "extra.grosing_up": [
        "grosing_up"
    ],
    "extra.de_reduccion": [
        "de_reduccion"
    ],
    "extra.tipo_convenio": [
        "tipo_convenio"
    ],
    "extra.grupo_fijo_concepto": [
        "grupo_fijo_concepto"
    ],
    "extra.hs_mens_asignadas": [
        "hs_mens_asignadas"
    ],
    "extra.piso": [
        "piso"
    ],
}


# ---------------------------------------------------------------------
# Parser direct keys
# If parser already extracted this semantic key, bypass weak matching.
# ---------------------------------------------------------------------
DIRECT_FIELD_MAP: Dict[str, str] = {
    # parser output basics
    "dni": "identity.dni",
    "cuil": "identity.cuil",
    "first_name": "identity.first_name",
    "last_name": "identity.last_name",
    "full_name": "identity.full_name",
    "gender": "identity.gender",
    "birth_date": "identity.birth_date",
    "nationality": "identity.nationality",
    "marital_status": "identity.marital_status",

    "email": "address.email",
    "phone": "address.phone",
    "address": "address.address",
    "address_number": "address.address_number",
    "city": "address.city",
    "province": "address.province",
    "postal_code": "address.postal_code",

    "legajo": "employment.file_number",
    "file_number": "employment.file_number",
    "hire_date": "employment.hire_date",
    "baja": "employment.termination_date",
    "termination_date": "employment.termination_date",
    "job_title": "employment.job_title",
    "position": "employment.job_title",
    "category": "employment.category",
    "task": "employment.task",
    "section": "employment.section",
    "antiguedad": "employment.antiguedad",
    "suc": "employment.sucursal",

    "bank": "banking.bank",
    "account_number": "banking.account_number",
    "nro_cuenta": "banking.account_number",
    "nro_cta": "banking.account_number",
    "numero_cuenta": "banking.account_number",
    "cuenta_bancaria": "banking.account_number",
    "cbu": "banking.cbu",
    "bank_alias": "banking.bank_alias",
    "alias": "banking.bank_alias",
    "alias_cbu": "banking.bank_alias",
    "payment_method": "banking.payment_method",
    "forma_de_pago": "banking.payment_method",
    "payment_place": "banking.payment_place",
    "lugar_de_pago": "banking.payment_place",

    "activity": "pension.activity",
    "pension_regime": "pension.pension_regime",
    "labor_condition": "pension.labor_condition",
    "situacion_de_revista": "pension.revista_situation",
    "revista_situation": "pension.revista_situation",

    "obra_social": "documentary.health_insurance",
    "health_insurance": "documentary.health_insurance",
    "health_insurance_number": "documentary.health_insurance_number",
    "nro_afiliado": "documentary.health_insurance_number",
    "nro_afiliado_os": "documentary.health_insurance_number",
    "union": "documentary.union",
    "union_number": "documentary.union_number",
    "nro_afiliado_sind": "documentary.union_number",
    "nro_afiliado_sindicato": "documentary.union_number",
    "nro_doc": "documentary.document_number",
    "nro_documento": "documentary.document_number",
    "document_number": "documentary.document_number",

    # extras already normalized by parser
    "base_aguinaldo": "extra.base_aguinaldo",
    "tipo_de_remuneracion": "extra.tipo_de_remuneracion",
    "remuneracion_covenio": "extra.remuneracion_covenio",
    "remuneracion_reducida": "extra.remuneracion_reducida",
    "zona_desfavorable": "extra.zona_desfavorable",
    "grosing_up": "extra.grosing_up",
    "de_reduccion": "extra.de_reduccion",
    "tipo_convenio": "extra.tipo_convenio",
    "grupo_fijo_concepto": "extra.grupo_fijo_concepto",
    "hs_mens_asignadas": "extra.hs_mens_asignadas",
    "modalidad_de_contratacion": "employment.hire_type",
    "convenio": "employment.union_agreement",
    "forma_pago": "banking.payment_method",
    "lugar_pago": "banking.payment_place",
}


# ---------------------------------------------------------------------
# Export header presentation
# ---------------------------------------------------------------------
EXPORT_DISPLAY_NAMES: Dict[str, str] = {
    "identity.dni": "DNI",
    "identity.cuil": "CUIL",
    "identity.first_name": "Nombre",
    "identity.last_name": "Apellido",
    "identity.full_name": "Nombre Completo",
    "identity.gender": "Género",
    "identity.birth_date": "Fecha Nacimiento",
    "identity.marital_status": "Estado Civil",
    "identity.nationality": "Nacionalidad",

    "address.email": "Email",
    "address.phone": "Teléfono",
    "address.address": "Calle",
    "address.address_number": "Número",
    "address.city": "Localidad",
    "address.province": "Provincia",
    "address.postal_code": "C.P.",

    "documentary.health_insurance": "Obra Social",
    "documentary.health_insurance_number": "Nro Afiliado O.S.",
    "documentary.union": "Sindicato",
    "documentary.union_number": "Nro Afiliado Sindicato",

    "employment.file_number": "Legajo",
    "employment.hire_date": "Fecha Ingreso",
    "employment.termination_date": "Fecha Baja",
    "employment.job_title": "Cargo",
    "employment.category": "Categoría",
    "employment.task": "Tarea",
    "employment.cost_center": "Centro de Costo",
    "employment.union_agreement": "Convenio",
    "employment.hire_type": "Tipo Contrato",
    "employment.work_location": "Sección",
    "employment.status": "Estado",
    "employment.antiguedad": "Antigüedad",
    "employment.sucursal": "Sucursal",

    "banking.bank": "Banco",
    "banking.account_type": "Tipo Cuenta",
    "banking.cbu": "CBU",
    "banking.account_number": "Cuenta Bancaria",
    "banking.bank_alias": "Alias",
    "banking.payment_method": "Forma de Pago",
    "banking.payment_place": "Lugar de Pago",
    "extra.ieric_number": "Nro IERIC",

    "pension.pension_regime": "Régimen Previsional",
    "pension.activity": "Actividad",
    "pension.labor_condition": "Condición Laboral",
    "pension.revista_situation": "Situación de Revista",

    "extra.base_aguinaldo": "Base Aguinaldo",
    "extra.tipo_de_remuneracion": "Tipo de Remuneración",
    "extra.remuneracion_covenio": "Remuneración Convenio",
    "extra.remuneracion_reducida": "Remuneración Reducida",
    "extra.zona_desfavorable": "Zona Desfavorable",
    "extra.grosing_up": "Grosing Up",
    "extra.de_reduccion": "% de Reducción",
    "extra.tipo_convenio": "Tipo Convenio",
    "extra.grupo_fijo_concepto": "Grupo Fijo Concepto",
    "extra.hs_mens_asignadas": "Hs. Mens. Asignadas",
    "extra.piso": "Piso",
}


# ---------------------------------------------------------------------
# COLUMNS_CONFIG — single source of truth; legacy maps derived below
# ---------------------------------------------------------------------
def _build_columns_config() -> Dict[str, dict]:
    config: Dict[str, dict] = {}
    for path, aliases in SEMANTIC_FIELD_MAP.items():
        config[path] = {
            "aliases": list(aliases),
            "display_name": EXPORT_DISPLAY_NAMES.get(path, path.split(".")[-1]),
        }
    config["address.address"]["display_name"] = "Calle"
    config["address.address_number"] = {
        "aliases": list(SEMANTIC_FIELD_MAP["address.address_number"]),
        "display_name": "Número",
        "max_length": 30,
    }
    return config


def _derive_legacy_maps(config: Dict[str, dict]):
    semantic = {path: list(cfg["aliases"]) for path, cfg in config.items()}
    export = {path: cfg["display_name"] for path, cfg in config.items()}
    direct: Dict[str, str] = {}
    for path, cfg in config.items():
        for alias in cfg["aliases"]:
            norm = normalize_header(alias)
            if norm:
                direct[norm] = path
    return semantic, direct, export


COLUMNS_CONFIG: Dict[str, dict] = _build_columns_config()
SEMANTIC_FIELD_MAP, DIRECT_FIELD_MAP, EXPORT_DISPLAY_NAMES = _derive_legacy_maps(COLUMNS_CONFIG)


class ScoringMatcher:
    def __init__(self, field_map: Dict[str, List[str]], direct_field_map: Optional[Dict[str, str]] = None):
        self.field_map = field_map
        self.direct_field_map = {
            normalize_header(k): v for k, v in (direct_field_map or {}).items()
        }

        self.lookup: Dict[str, List[str]] = {}
        for field, aliases in field_map.items():
            self.lookup[field] = [normalize_header(a) for a in aliases]

    def match_header(self, raw_header: str) -> Tuple[Optional[str], int]:
        """
        Hybrid matcher (strict-first):
        1. Exact normalized alias match
        2. Direct parser-field pass-through
        3. Contains / fuzzy overlap (only as last resort)
        """
        norm_header = normalize_header(raw_header)
        if not norm_header:
            return None, 0

        # 1. Exact alias match (highest confidence)
        for field, aliases in self.lookup.items():
            for alias in aliases:
                if norm_header == alias:
                    return field, 100

        # 2. Direct parser field mapping
        if norm_header in self.direct_field_map:
            return self.direct_field_map[norm_header], 90

        best_field = None
        max_score = 0

        # 3. Contains / fuzzy (last resort — avoids ambiguous short headers like "numero")
        for field, aliases in self.lookup.items():
            for alias in aliases:
                score = 0

                if len(alias) >= 4 and len(norm_header) >= 4:
                    if alias in norm_header or norm_header in alias:
                        ratio = min(len(alias), len(norm_header)) / max(len(alias), len(norm_header))
                        score = int(75 * ratio)
                    else:
                        overlap = token_overlap(norm_header, alias)
                        if overlap >= 80:
                            score = 70
                        elif overlap >= 60:
                            score = 60

                if score > max_score:
                    max_score = score
                    best_field = field

        if max_score < 50:
            return None, 0

        return best_field, max_score

    def map_record_keys(self, record: Dict[str, object]) -> Dict[str, Tuple[str, int]]:
        """
        Utility for FORM_MODE or mixed records:
        returns {raw_key: (canonical_path, confidence)}
        """
        result: Dict[str, Tuple[str, int]] = {}
        for raw_key in record.keys():
            result[raw_key] = self.match_header(raw_key)
        return result


# Default matcher instance
DEFAULT_MATCHER = ScoringMatcher(
    field_map=SEMANTIC_FIELD_MAP,
    direct_field_map=DIRECT_FIELD_MAP,
)


# ---------------------------------------------------------------------
# Legacy positional fallback (kept only if still needed elsewhere)
# ---------------------------------------------------------------------
LEGAJO_POSITIONAL_V1 = {
    0: "employment.file_number",
    2: "identity.last_name",
    3: "identity.first_name",
    19: "identity.dni",
    48: "identity.cuil",
}