"""
Legajo Normalizer — transforms raw dicts into CanonicalEmployeeRecord using semantic mapping.

Handles:
- Semantic Mapping (Scoring-based).
- Dynamic Header Detection.
- Null character normalization.
- Type coercion (Date, Float, Int).
- String trimming and case normalization.
"""

import logging
import re
import datetime
from collections import defaultdict
from typing import Any, Optional, Dict, List, Tuple

from .canonical import (
    CanonicalEmployeeRecord, IdentityBlock, AddressBlock, 
    DocumentaryBlock, EmploymentBlock, BankingBlock, PensionBlock, MetaBlock
)
from .mapping import SEMANTIC_FIELD_MAP, ScoringMatcher, normalize_header
from .schema_manager import SchemaManager

logger = logging.getLogger(__name__)

# --- Configuration ---
MAX_EXTRA_FIELDS = 100
MAX_FIELD_VALUE_LENGTH = 500 # NEW: Truncate very long unknown values

NULL_VALUES = {
    "", " ", "0", "0.0", "0,0", "none", "null", "undefined", 
    "#n/a", "#ref!", "#value!", "00:00:00", "nan", "nil"
}

RE_NON_DIGITS = re.compile(r"[^\d]")

SPANISH_MONTH_MAP = {
    "enero": "01", "ene": "01",
    "febrero": "02", "feb": "02",
    "marzo": "03", "mar": "03",
    "abril": "04", "abr": "04",
    "mayo": "05", "may": "05",
    "junio": "06", "jun": "06",
    "julio": "07", "jul": "07",
    "agosto": "08", "ago": "08",
    "septiembre": "09", "sep": "09", "setiembre": "09", "set": "09",
    "octubre": "10", "oct": "10",
    "noviembre": "11", "nov": "11",
    "diciembre": "12", "dic": "12"
}


from .mapping import SEMANTIC_FIELD_MAP, DIRECT_FIELD_MAP, ScoringMatcher, normalize_header

class Normalizer:
    def __init__(self, schema_manager: SchemaManager = None, mapping_version: str = "3", job_id: str = "unknown"):
        self.mapping_version = mapping_version
        self.schema_manager = schema_manager
        self.matcher = ScoringMatcher(SEMANTIC_FIELD_MAP, DIRECT_FIELD_MAP)
        self.job_id = job_id
        
        self.active_mapping: Dict[str, str] = {} # raw_header -> logical_path or col_name
        self.active_confidence: Dict[str, int] = {}
        self.missing_columns_counter = defaultdict(int)
        self._ctx = f"[IMPORT {self.job_id}]"

    def set_mapping(self, mapping: Dict[str, str], confidence: Dict[str, int]):
        """Sets the mapping to use for normalize_row."""
        self.active_mapping = mapping
        self.active_confidence = confidence
        if not mapping:
            logger.info(f"{self._ctx} Normalizer initialized for FORM_MODE: using Identity Mapping (Dynamic Recognition)")
        else:
            logger.info(f"{self._ctx} Normalizer active mapping set: {len(mapping)} fields detected.")

    def log_missing_columns_summary(self):
        """Logs a summary of columns that were not found in the schema."""
        if self.missing_columns_counter:
            summary = dict(self.missing_columns_counter)
            logger.warning(f"{self._ctx} Missing columns summary (sent to extra_fields): {summary}")
        else:
            logger.debug(f"{self._ctx} Normalizer: No missing columns encountered.")

    def detect_header_row(self, raw_rows: List[List[Any]], max_scan: int = 15) -> Tuple[int, Dict[int, str], Dict[int, int], Dict[int, str]]:
        """
        Scans top rows to find the one that best matches SEMANTIC_FIELD_MAP.
        Returns (row_index, col_mapping, confidence_scores, header_labels).
        col_mapping maps column index -> canonical path (e.g. 3 -> "address.address_number").
        """
        best_row_idx = -1
        max_total_score = 0
        best_mapping: Dict[int, str] = {}
        best_confidences: Dict[int, int] = {}
        best_labels: Dict[int, str] = {}

        for i, row in enumerate(raw_rows[:max_scan]):
            current_mapping: Dict[int, str] = {}
            current_confidences: Dict[int, int] = {}
            current_labels: Dict[int, str] = {}
            total_score = 0
            matches_found = 0

            for col_idx, cell in enumerate(row):
                if cell is None or (isinstance(cell, str) and not cell.strip()):
                    continue
                cell_str = str(cell).strip()
                if not cell_str:
                    continue

                field_path, score = self.matcher.match_header(cell_str)
                if field_path:
                    current_mapping[col_idx] = field_path
                    current_confidences[col_idx] = score
                    current_labels[col_idx] = cell_str
                    total_score += score
                    matches_found += 1

            if matches_found >= 3 and total_score > max_total_score:
                max_total_score = total_score
                best_row_idx = i
                best_mapping = current_mapping
                best_confidences = current_confidences
                best_labels = current_labels

        return best_row_idx, best_mapping, best_confidences, best_labels

    def normalize_row(self, raw_data: Dict[str, Any], 
                      source_row_num: int) -> CanonicalEmployeeRecord:
        """
        Normalizes a single raw row using the active_mapping and schema knowledge.
        Robust pre-cleaning applied here.
        """
        record = CanonicalEmployeeRecord()
        record.meta.source_row_number = source_row_num
        record.meta.mapping_version = self.mapping_version

        extra_count = 0
        now_iso = datetime.datetime.now().isoformat()

        # 1. Clean row (Standardized logic across all modes)
        clean_row = self._clean_row(raw_data)

        for raw_key, v in clean_row.items():
            field_path = self.active_mapping.get(raw_key)
            
            # 🔥 REDIRECCIÓN PARA CAMPOS EXTRA (MAPPING V3)
            # extra.foo -> record.extra_fields['foo']
            if field_path and field_path.startswith("extra."):
                attr = field_path.split(".", 1)[1]
                record.extra_fields[attr] = v
                continue

            # IDENTITY MAPPING: If no mapping, try to match key to path or column
            if not field_path:
                # Is it a path?
                if "." in raw_key: 
                    field_path = raw_key
                # Is it a column name already? Or a direct path match in SEMANTIC_FIELD_MAP?
                else:
                    norm_k = normalize_header(raw_key)
                    # Simple heuristic: If it matches a column in DB directly
                    if self.schema_manager and norm_k in self.schema_manager.columns:
                        field_path = norm_k # Will be resolved below
                    else:
                        # Try semantic matcher on the single key
                        field_path, score = self.matcher.match_header(raw_key)

            if field_path:
                # 1. ALWAYS populate canonical record (Identity, Employment, etc)
                # This ensures UI consistency even if DB schema is out of sync
                self._set_canonical_value(record, field_path, v)
                
                # 2. Extract col_name for DB flattened storage
                col_name = field_path
                if self.schema_manager:
                    col_name = self.schema_manager.get_column_for_path(field_path)
                
                # 3. DB Field Storage (Only if col exists in DB)
                if self.schema_manager and col_name in self.schema_manager.columns:
                    normalized_val = self.coerce_value(col_name, v)
                    record.db_fields[col_name] = normalized_val
                    # High-frequency log moved to DEBUG
                    logger.debug(f"{self._ctx} Normalizer: SUCCESS set DB field {col_name} = {normalized_val}")
                else:
                    # Deduplicate: increment counter instead of logging for every row
                    self.missing_columns_counter[col_name] += 1
                    logger.debug(f"{self._ctx} Normalizer: col_name '{col_name}' NOT in schema columns. Value preserved in canonical blocks and extra_fields fallback.")
                    # Enriched extra_fields fallback for unmapped DB columns
                    if extra_count < MAX_EXTRA_FIELDS:
                        norm_key = normalize_header(raw_key)
                        if norm_key:
                            # Use canonical name if possible, else raw
                            storage_key = col_name if col_name else norm_key
                            final_val = str(v) if v is not None else None
                            if final_val and len(final_val) > MAX_FIELD_VALUE_LENGTH:
                                final_val = final_val[:MAX_FIELD_VALUE_LENGTH] + "..."

                            record.extra_fields[storage_key] = final_val
                            record.extra_fields_metadata[storage_key] = {
                                "detected_at": now_iso,
                                "confidence": self.active_confidence.get(raw_key, 0) or 100,
                                "source": "identity_mapping"
                            }
                            extra_count += 1
            else:
                # 2. Unknown Field
                if extra_count < MAX_EXTRA_FIELDS:
                    norm_key = normalize_header(raw_key)
                    if norm_key:
                        # Truncate long values to prevent bloat
                        final_val = str(v) if v is not None else None
                        if final_val and len(final_val) > MAX_FIELD_VALUE_LENGTH:
                            final_val = final_val[:MAX_FIELD_VALUE_LENGTH] + "..."

                        record.extra_fields[norm_key] = final_val
                        record.extra_fields_metadata[norm_key] = {
                            "detected_at": now_iso,
                            "confidence": 0, # Unknown
                            "source": "raw_header"
                        }
                        extra_count += 1

        # Post-process: Split Full Name if first/last are missing
        # ... (rest of the logic remains same)
        full_name = record.db_fields.get("full_name") or record.identity.full_name
        first_name = record.db_fields.get("first_name") or record.identity.first_name
        last_name = record.db_fields.get("last_name") or record.identity.last_name

        if full_name and (not first_name or not last_name):
            if "," in full_name: # "Perez, Juan"
                parts = full_name.split(",", 1)
                last_name = parts[0].strip()
                first_name = parts[1].strip()
            else: # "Juan Perez"
                parts = full_name.rsplit(" ", 1)
                if len(parts) > 1:
                    first_name = parts[0].strip()
                    last_name = parts[1].strip()
                else:
                    first_name = full_name.strip()
            
            # Sync back to record
            record.db_fields["first_name"] = first_name
            record.db_fields["last_name"] = last_name
            record.identity.first_name = first_name
            record.identity.last_name = last_name

        # Post-process: Extract DNI from CUIL if DNI is missing (Senior Refinement)
        dni = record.db_fields.get("dni") or record.identity.dni
        cuil = record.db_fields.get("cuil") or record.identity.cuil
        
        if cuil and not dni:
            # Clean symbols for extraction
            clean_cuil = str(cuil).replace("-", "").replace(".", "").strip()
            if len(clean_cuil) == 11 and clean_cuil.isdigit():
                # Middle 8 digits are the DNI
                derived_dni = clean_cuil[2:10].lstrip("0")
                if derived_dni and derived_dni != "00000000":
                    record.db_fields["dni"] = derived_dni
                    record.identity.dni = derived_dni
                    logger.debug(f"{self._ctx} Normalizer: Derived DNI {derived_dni} from CUIL {clean_cuil}")

        # -------------------------
        # FORCE CRITICAL DATES & ALIGN PAYLOAD
        # -------------------------
        
        def safe_iso(v):
            if isinstance(v, (datetime.date, datetime.datetime)):
                return v.strftime("%Y-%m-%d")
            return v

        if not record.identity.birth_date and record.db_fields.get("birth_date"):
            record.identity.birth_date = safe_iso(record.db_fields["birth_date"])

        if not record.employment.hire_date and record.db_fields.get("hire_date"):
            record.employment.hire_date = safe_iso(record.db_fields["hire_date"])

        if not record.employment.termination_date and record.db_fields.get("termination_date"):
            record.employment.termination_date = safe_iso(record.db_fields["termination_date"])
        elif not record.employment.termination_date and record.db_fields.get("baja"):
            record.employment.termination_date = safe_iso(record.db_fields["baja"])

        # Serialize any residual floating dates to strings so standard JSON doesn't drop them
            record.db_fields[k] = safe_iso(v)

        # --- DEDUPLICATION PASS ---
        # Resolve redundant extra_fields (e.g. employment_section vs employment.section)
        self._deduplicate_extra_fields(record)

        # --- BANK AUTO-DETECTION ---
        # If bank name exists but no bank_code, try to match against master
        try:
            from .banks import detect_bank
            bank_name = record.banking.bank or record.db_fields.get("bank")
            if bank_name and not record.db_fields.get("bank_code"):
                matched = detect_bank(bank_name)
                if matched:
                    record.db_fields["bank_code"] = matched.code
                    record.db_fields["bank_branch"] = matched.branch
                    record.banking.bank_code = matched.code
                    record.banking.bank_branch = matched.branch
                    logger.debug(f"{self._ctx} Normalizer: Auto-detected bank '{matched.name}' (code={matched.code}) from '{bank_name}'")
        except Exception as e:
            logger.warning(f"{self._ctx} Normalizer: Bank auto-detection failed (non-blocking): {e}")

        return record

    def _clean_row(self, raw_row: Dict[str, Any]) -> Dict[str, Any]:
        """
        Robust pre-cleaning:
        - Trims whitespace
        - Normalizes encoding (UTF-8 safe)
        - Normalizes empty strings/placeholders to None
        - Strips BOM, control characters, zero-width spaces
        """
        cleaned = {}
        for k, v in raw_row.items():
            if k is None: continue
            
            # Key normalization
            clean_k = self._sanitize_str(str(k))
            
            # Value normalization
            if v is None:
                cleaned[clean_k] = None
            else:
                s_val = self._sanitize_str(str(v))
                if s_val == "" or s_val.lower() in NULL_VALUES:
                    cleaned[clean_k] = None
                else:
                    cleaned[clean_k] = s_val
                    
        return cleaned

    @staticmethod
    def _sanitize_str(s: str) -> str:
        """Strips BOM, control chars, zero-width spaces, normalizes whitespace."""
        if not s:
            return ""
        # Remove BOM and zero-width chars
        s = s.replace('\ufeff', '').replace('\u200b', '').replace('\u200c', '').replace('\u200d', '')
        # Strip control characters (except newline/tab)
        s = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', s)
        # Normalize whitespace
        s = re.sub(r'\s+', ' ', s).strip()
        return s

    # ─────────────────────────────────────────────────────────────────────────
    # MAPA DE TRADUCCIÓN: Términos ingleses / técnicos → Español RR.HH.
    # Se aplica a las CLAVES de extra_fields durante la normalización.
    # ─────────────────────────────────────────────────────────────────────────
    _KEY_TRANSLATION_MAP = {
        # Identidad
        "first_name":          "NOMBRE",
        "last_name":           "APELLIDO",
        "full_name":           "NOMBRE COMPLETO",
        "birth_date":          "FECHA DE NACIMIENTO",
        "gender":              "SEXO",
        "nationality":         "NACIONALIDAD",
        "marital_status":      "ESTADO CIVIL",
        "document_type":       "TIPO DE DOCUMENTO",
        "document_number":     "NÚMERO DE DOCUMENTO",
        "dni":                 "DNI",
        "cuil":                "CUIL",
        # Laboral
        "hire_date":           "FECHA DE INGRESO",
        "termination_date":    "FECHA DE EGRESO",
        "hire_type":           "TIPO DE CONTRATO",
        "work_location":       "SECCIÓN",
        "job_title":           "CARGO",
        "category":            "CATEGORÍA",
        "task":                "TAREA",
        "cost_center":         "CENTRO DE COSTO",
        "file_number":         "LEGAJO",
        "labor_condition":     "CONDICIÓN LABORAL",
        "revista_situation":   "SITUACIÓN DE REVISTA",
        "union":               "SINDICATO",
        "union_number":        "NRO. AFILIACIÓN SINDICAL",
        "union_agreement":     "CONVENIO COLECTIVO",
        # Previsional
        "pension_regime":      "RÉGIMEN PREVISIONAL",
        "activity":            "ACTIVIDAD",
        # Bancario
        "bank":                "BANCO",
        "account_number":      "NÚMERO DE CUENTA",
        "account_type":        "TIPO DE CUENTA",
        "payment_method":      "FORMA DE PAGO",
        "payment_place":       "LUGAR DE PAGO",
        "cbu":                 "CBU",
        "bank_alias":          "ALIAS CBU",
        "bank_code":           "CÓDIGO BANCO",
        "bank_branch":         "SUCURSAL BANCO",
        "ieric_number":        "NRO IERIC",
        # Domicilio
        "address":             "DOMICILIO",
        "city":                "LOCALIDAD",
        "province":            "PROVINCIA",
        "postal_code":         "CÓDIGO POSTAL",
        # Contacto
        "phone":               "TELÉFONO",
        "email":               "EMAIL",
        # Salud
        "health_insurance":    "OBRA SOCIAL",
        "health_insurance_number": "NRO. OBRA SOCIAL",
        # Liquidación (términos técnicos frecuentes en planillas)
        "grossing_up":         "GROSSING UP",
        "gross_salary":        "SALARIO BRUTO",
        "net_salary":          "SALARIO NETO",
        "total_remuneration":  "REMUNERACIÓN TOTAL",
        "basic_salary":        "SUELDO BÁSICO",
        "overtime":            "HORAS EXTRA",
        "bonus":               "BONO",
        "allowance":           "ASIGNACIÓN",
        "deduction":           "DEDUCCIÓN",
        "absence":             "AUSENCIA",
        "vacation":            "VACACIONES",
        "aguinaldo":           "SUELDO ANUAL COMPLEMENTARIO",
        "sac":                 "SUELDO ANUAL COMPLEMENTARIO",
    }

    # Palabras clave que identifican claves de bajo valor para ser eliminadas
    _NOISE_KEYWORDS = [
        "TOTAL", "PAGINA", "PÁGINA", "FECHA DE IMPRESION", "FECHA DE IMPRESIÓN",
        "ZEDIL", "NUMERO DE PAGINA", "NÚMERO DE PÁGINA", "IMPRESO EL",
        "PAGE", "PRINT DATE", "PRINTED", "FOOTER", "HEADER",
    ]

    # Valores que indican "activo" para Grossing Up (política de negocio)
    _GROSSING_UP_POSITIVE = {"sí", "si", "true", "1", "yes", "activo", "activado"}

    def _normalize_extra_key(self, raw_key: str) -> str:
        """
        Normaliza una clave de extra_fields aplicando:
        1. Elimina prefijo 'Extra.' (insensible a mayúsculas)
        2. Reemplaza underscores por espacios
        3. Convierte a MAYÚSCULAS
        4. Traduce al español si existe en el mapa
        """
        # 1. Eliminar prefijo 'Extra.' (y variantes con distinto case)
        k = re.sub(r'^[Ee]xtra\.', '', raw_key).strip()

        # 2. Traducción directa por clave normalizada (snake_case → español)
        normalized_lower = k.lower().replace(' ', '_').replace('-', '_')
        if normalized_lower in self._KEY_TRANSLATION_MAP:
            return self._KEY_TRANSLATION_MAP[normalized_lower]

        # 3. Reemplazar separadores y convertir a MAYÚSCULAS
        k = k.replace('_', ' ').replace('-', ' ')
        k = re.sub(r'\s+', ' ', k).strip().upper()

        # 4. Segunda pasada de traducción (si tras limpieza matchea)
        k_lower_pass2 = k.lower().replace(' ', '_')
        if k_lower_pass2 in self._KEY_TRANSLATION_MAP:
            return self._KEY_TRANSLATION_MAP[k_lower_pass2]

        return k

    def _deduplicate_extra_fields(self, record: CanonicalEmployeeRecord):
        """
        REGLAS ESTRICTAS DE NEGOCIO — Limpieza de Metadatos de Liquidación y Control:

        1. DEDUPLICACIÓN SEMÁNTICA: Elimina claves de extra_fields si el dato ya
           existe en algún bloque canónico (identity, employment, address, etc.),
           comparando tanto por nombre exacto como por variantes de nomenclatura.

        2. ELIMINACIÓN DE BAJO VALOR: Elimina campos de ruido reconocibles:
           totales de página, fechas de impresión, encabezados/pies de planilla.

        3. POLÍTICA GROSSING UP: Solo se conserva si el valor es afirmativo
           ("Sí", "True", "1", etc.). Si es negativo o vacío, se elimina.

        4. FORMATEO DE CLAVES: Traduce términos ingleses/técnicos a español,
           elimina prefijos "Extra.", convierte a MAYÚSCULAS.
        """
        # ── PASO 1: Construir el conjunto de valores canónicos ya capturados ──
        # Se indexan tanto los nombres de atributo como sus valores normalizados
        # para detectar duplicados semánticos (ej: 'dni' vs 'DNI' vs 'identity_dni')
        canonical_attr_names: set = set()
        canonical_values: set = set()  # valores en minúsculas para comparación

        CANONICAL_BLOCKS = [
            "identity", "address", "documentary", "employment",
            "banking", "pension", "meta", "contact"
        ]

        for block_name in CANONICAL_BLOCKS:
            if not hasattr(record, block_name):
                continue
            block = getattr(record, block_name)
            for attr in vars(block) if hasattr(block, '__dict__') else dir(block):
                if attr.startswith("_"):
                    continue
                val = getattr(block, attr, None)
                if val is None:
                    continue

                # Registrar nombre de atributo y sus variantes
                canonical_attr_names.add(attr)                         # work_location
                canonical_attr_names.add(attr.upper())                 # WORK_LOCATION
                canonical_attr_names.add(f"{block_name}.{attr}")       # employment.work_location
                canonical_attr_names.add(f"{block_name}_{attr}")       # employment_work_location
                # Traducción al español
                translated = self._KEY_TRANSLATION_MAP.get(attr.lower())
                if translated:
                    canonical_attr_names.add(translated)               # SECCIÓN

                # Registrar el valor normalizado para detectar duplicados por contenido
                str_val = str(val).strip().lower()
                if str_val and str_val not in {"", "none", "null"}:
                    canonical_values.add(str_val)

        # Incluir también los campos DB (columnas planas ya guardadas)
        for db_col, db_val in record.db_fields.items():
            canonical_attr_names.add(db_col)
            canonical_attr_names.add(db_col.upper())
            translated = self._KEY_TRANSLATION_MAP.get(db_col.lower())
            if translated:
                canonical_attr_names.add(translated)

        # ── PASO 2: Reformatear y filtrar extra_fields ──
        new_extra: dict = {}
        new_extra_meta: dict = {}

        for raw_key, entry in list(record.extra_fields.items()):
            # Extraer el valor real (puede estar envuelto en dict con 'value')
            if isinstance(entry, dict) and "value" in entry:
                raw_value = entry.get("value")
                entry_meta = {k: v for k, v in entry.items() if k != "value"}
            else:
                raw_value = entry
                entry_meta = record.extra_fields_metadata.get(raw_key, {})

            str_value = str(raw_value).strip() if raw_value is not None else ""

            # ── REGLA A: Eliminar si es ruido/bajo valor ──
            raw_upper = raw_key.upper().replace('_', ' ').replace('-', ' ')
            if any(noise in raw_upper for noise in self._NOISE_KEYWORDS):
                logger.debug(f"extra_fields.dedup: eliminando ruido: '{raw_key}'")
                continue

            # ── REGLA B: Eliminar si ya existe en bloques canónicos ──
            # Comparación por nombre
            normalized_key_for_dedup = (
                re.sub(r'^[Ee]xtra\.', '', raw_key)  # quitar prefijo Extra.
                .replace(' ', '_').replace('-', '_').lower()
            )
            if (raw_key in canonical_attr_names
                    or raw_key.upper() in canonical_attr_names
                    or normalized_key_for_dedup in canonical_attr_names
                    or normalized_key_for_dedup.upper() in canonical_attr_names):
                logger.debug(f"extra_fields.dedup: clave '{raw_key}' ya existe en bloque canónico")
                continue

            # Comparación por valor (evita duplicar el mismo dato con diferente etiqueta)
            if str_value and str_value.lower() in canonical_values:
                # Solo eliminar si no es un valor genérico que podría repetirse (ej: "Argentina")
                if len(str_value) > 3:
                    logger.debug(f"extra_fields.dedup: valor '{str_value}' ya capturado en bloque canónico, eliminando clave '{raw_key}'")
                    continue

            # ── REGLA C: Política de Grossing Up ──
            key_norm = raw_key.lower().replace(' ', '_').replace('-', '_')
            key_norm_no_prefix = re.sub(r'^extra\.', '', key_norm)
            is_grossing_up = (
                'grossing' in key_norm_no_prefix
                or 'gross_up' in key_norm_no_prefix
                or key_norm_no_prefix == 'grossing_up'
            )
            if is_grossing_up:
                if str_value.lower() not in self._GROSSING_UP_POSITIVE:
                    logger.debug(f"extra_fields.dedup: Grossing Up no activo ('{str_value}'), eliminando")
                    continue
                # Normalizar valor a 'Sí' para consistencia
                str_value = "Sí"
                if isinstance(entry, dict) and "value" in entry:
                    entry = {**entry, "value": "Sí"}
                else:
                    entry = "Sí"

            # ── PASO 3: Normalizar clave al formato de negocio (MAYÚSCULAS + Español) ──
            normalized_key = self._normalize_extra_key(raw_key)

            # Preservar: el campo sobrevive
            new_extra[normalized_key] = entry
            if entry_meta:
                new_extra_meta[normalized_key] = entry_meta

        # ── PASO 4: Detectar y eliminar duplicados INTERNOS (mismo valor, diferente clave) ──
        # Ejemplo: 'SECCIÓN' y 'LUGAR DE TRABAJO' pueden tener el mismo valor tras la traducción
        seen_values: dict = {}  # valor_normalizado -> primera_clave
        final_extra: dict = {}
        for key, entry in new_extra.items():
            if isinstance(entry, dict) and "value" in entry:
                raw_v = str(entry.get("value", "")).strip().lower()
            else:
                raw_v = str(entry).strip().lower() if entry is not None else ""

            if raw_v and len(raw_v) > 2:  # Ignorar valores muy cortos (ej: '1')
                if raw_v in seen_values:
                    # Mantener la clave que aparece primero (ya ordenada/normalizada)
                    logger.debug(
                        f"extra_fields.dedup: valor interno duplicado '{raw_v}': "
                        f"manteniendo '{seen_values[raw_v]}', eliminando '{key}'"
                    )
                    continue
                seen_values[raw_v] = key

            final_extra[key] = entry

        # Reemplazar in-place
        record.extra_fields.clear()
        record.extra_fields.update(final_extra)
        record.extra_fields_metadata.clear()
        record.extra_fields_metadata.update(new_extra_meta)

        logger.debug(
            f"extra_fields.dedup: {len(final_extra)} campo(s) conservado(s) "
            f"en 'Metadatos de Liquidación y Control'"
        )

    def _set_canonical_value(self, record: CanonicalEmployeeRecord, field_path: str, raw_val: Any):
        """Sets a value in the nested Canonical record based on a dot-path or flat attribute."""
        if not field_path:
            return

        try:
            # --- Path-based Setting ---
            if "." in field_path:
                block_name, attr_name = field_path.split(".", 1)
                
                # 1. SPECIAL CASE: extra_fields redirection
                if block_name == "extra":
                    record.extra_fields[attr_name] = raw_val
                    return

                # 2. Whitelist check for canonical blocks
                VALID_BLOCKS = ["identity", "address", "documentary", "employment", "banking", "pension", "meta", "contact"]
                if block_name in VALID_BLOCKS and hasattr(record, block_name):
                    block = getattr(record, block_name)
                    normalized_val = self.coerce_value(attr_name, raw_val)
                    if hasattr(block, attr_name):
                        setattr(block, attr_name, normalized_val)
                    else:
                        # If block exists but attr doesn't, it might be a dynamic extra in a block
                        record.extra_fields[f"{block_name}_{attr_name}"] = raw_val
                else:
                    # Treat as a flat attribute if block is unknown (handles labels like 'Suc.')
                    self._set_flat_canonical(record, field_path, raw_val)
            
            # --- Flat Setting ---
            else:
                self._set_flat_canonical(record, field_path, raw_val)

        except Exception as e:
            logger.error(f"Error setting {field_path}: {e}")

    def _set_flat_canonical(self, record: CanonicalEmployeeRecord, attr_name: str, raw_val: Any):
        """Internal helper for flat attribute placement across blocks."""
        normalized_val = self.coerce_value(attr_name, raw_val)
        for block_name in ["identity", "employment", "address", "contact", "banking"]:
            if hasattr(record, block_name):
                block = getattr(record, block_name)
                if hasattr(block, attr_name):
                    setattr(block, attr_name, normalized_val)
                    return
        # If no block has it, it's just an extra field
        record.extra_fields[attr_name] = raw_val

    def coerce_value(self, attr_name: str, val: Any) -> Any:
        """Coerces a raw value based on the attribute name and context."""
        if val is None:
            return None

        s_val = str(val).strip().lower()
        
        # --- Contextual Null Cleaning ---
        # "0" is valid for file numbers or codes, but usually null for names/dni
        is_code = any(x in attr_name for x in ["code", "number", "cbu", "cuil"])
        
        if s_val in NULL_VALUES:
            # If it's "0" and NOT a code, it's null
            if s_val == "0" and not is_code:
                return None
            # If it's #N/A, NULL, etc., it's always null
            if s_val != "0":
                return None

        # --- Type-specific coercion ---
        
        # 1. Dates
        if "date" in attr_name:
            return self._to_date(val)

        # 2. Floats
        if "amount" in attr_name or "salary" in attr_name:
            return self._to_float(val)

        # 3. Integers
        if "hours" in attr_name:
            return self._to_int(val)

        # 4. Identity Strings (DNI, CUIL) - Normalize to digits & strip leading zeros
        if "dni" in attr_name or "cuil" in attr_name:
            s_val = str(val)
            if s_val.endswith(".0"):
                s_val = s_val[:-2]
            clean_code = RE_NON_DIGITS.sub("", s_val).lstrip("0")
            return clean_code if clean_code else None

        # 5. File Number / Legajo - strip trailing .0 if representing an integer
        if attr_name == "file_number" or attr_name == "legajo":
            s_val = str(val).strip()
            if s_val.endswith(".0"):
                try:
                    float_val = float(s_val)
                    if float_val.is_integer():
                        return str(int(float_val))
                except ValueError:
                    pass
            return s_val

        # 6. Address number - strip Excel float artifacts (504.0 -> 504)
        if attr_name == "address_number":
            s_val = str(val).strip()
            if s_val.endswith(".0"):
                try:
                    float_val = float(s_val)
                    if float_val.is_integer():
                        return str(int(float_val))
                except ValueError:
                    pass
            return re.sub(r'\s+', ' ', s_val)

        if attr_name == "status":
            s = str(val).strip().lower()
            s = s.replace("_", " ").replace("-", " ")
            if any(x in s for x in ["inactivo", "baja", "retirado", "desactivado"]):
                return "inactive"
            if any(x in s for x in ["activo", "funcion", "en funcion", "en función", "vigente"]):
                return "active"
            if any(x in s for x in ["pendiente", "pending"]):
                return "pending_verification"
            if s in ["pre_registered", "pre-registered", "pre registered"]:
                return "pre_registered"
            return str(val).strip()
        
        return str(val).strip()

    def _to_date(self, val: Any) -> Optional[datetime.date]:
        """Robust date parser covering all Argentine HR formats."""
        if isinstance(val, datetime.date): return val
        if isinstance(val, datetime.datetime): return val.date()
        
        # Excel serial number detection (e.g. 44927 = 2023-01-01)
        if isinstance(val, (int, float)):
            serial = int(val)
            if 10000 < serial < 60000:  # Plausible Excel date range
                try:
                    # Excel epoch: 1899-12-30 (with the Lotus 1-2-3 bug)
                    return datetime.date(1899, 12, 30) + datetime.timedelta(days=serial)
                except (ValueError, OverflowError):
                    return None
            return None
        
        if isinstance(val, str):
            # 1. Pipeline Correcto: Limpiar String
            # Use normalize_header for common noise removal, then expand
            s = normalize_header(val).replace("_", " ").lower()
            if not s:
                return None
            
            # 2. Detectar Patrón Español & Normalizar
            # Replace Spanish months and common noise words
            for month_name, month_num in SPANISH_MONTH_MAP.items():
                s = re.sub(rf"\b{month_name}\b", month_num, s)
            
            s = s.replace(" de ", "/").replace(" ", "/").replace("-", "/").replace(".", "/")
            s = re.sub(r"/+", "/", s).strip("/")

            # 3. Parsear
            # Full year formats
            formats_4y = [
                "%d/%m/%Y", "%Y/%m/%d", "%m/%d/%Y",
            ]
            for fmt in formats_4y:
                try:
                    return datetime.datetime.strptime(s, fmt).date()
                except ValueError:
                    continue
            
            # 2-digit year formats
            formats_2y = ["%d/%m/%y"]
            for fmt in formats_2y:
                try:
                    return datetime.datetime.strptime(s, fmt).date()
                except ValueError:
                    continue
            
            # ISO / datetime fallback
            try:
                return datetime.datetime.fromisoformat(val.replace('Z', '+00:00')).date()
            except (ValueError, AttributeError):
                pass
        
        return None

    def _to_float(self, val: Any) -> Optional[float]:
        if isinstance(val, (int, float)): return float(val)
        if isinstance(val, str):
            raw = val.strip()
            if not raw:
                return None
            # Determine decimal/thousands strategy
            has_dot = '.' in raw
            has_comma = ',' in raw
            if has_dot and has_comma:
                # Argentine: 1.234.567,89 → thousands=dot, decimal=comma
                normalized = raw.replace('.', '').replace(',', '.')
            elif has_comma and not has_dot:
                # Only comma → decimal separator: 1234,56 → 1234.56
                normalized = raw.replace(',', '.')
            else:
                # Standard or integer: 1234.56 or 1234
                normalized = raw
            try:
                return float(normalized)
            except ValueError:
                pass
        return None

    def _to_int(self, val: Any) -> Optional[int]:
        if isinstance(val, int): return val
        try:
            return int(float(val))
        except (ValueError, TypeError):
            pass
        return None