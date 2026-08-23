"""
Legajo Exporters â€” drivers for different file formats.

Contract: input is a list of CanonicalEmployeeRecord.
"""

import csv
import io
import logging
from datetime import date, datetime
from typing import List, Any
from dataclasses import dataclass
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment

from .canonical import CanonicalEmployeeRecord
from .txt_spec import TXT_577_SPEC_V1
from .mapping import EXPORT_DISPLAY_NAMES

logger = logging.getLogger(__name__)

# --- Export Configuration (Senior Refinement) ---
EXPORT_SCHEMA = {
    "Identidad": [
        "identity.dni", "identity.cuil", "identity.first_name", "identity.last_name", 
        "identity.full_name", "identity.gender", "identity.birth_date"
    ],
    "Contacto": [
        "address.email", "address.phone", "address.address", "address.city", 
        "address.province", "address.postal_code"
    ],
    "Laboral": [
        "employment.file_number", "employment.hire_date", "employment.job_title", 
        "employment.category", "employment.section", "employment.cost_center", "employment.status"
    ],
    "Bancario": [
        "banking.bank", "banking.account_number", "banking.cbu", "banking.bank_alias", "banking.payment_method"
    ],
    "Previsional": [
        "pension.pension_regime", "pension.activity", "pension.labor_condition", "pension.revista_situation"
    ]
}

# Flatten the whitelist for CSV/Excel
BUSINESS_WHITELIST = [path for section in EXPORT_SCHEMA.values() for path in section]

class BaseExporter:
    def export(self, records: List[CanonicalEmployeeRecord], mode: str = "business") -> bytes:
        raise NotImplementedError()

    def _clean_value(self, val: Any) -> Any:
        """
        Semantic Label Sanitization. 
        Strips prefixes like 'Lugar de Pago:' safely.
        """
        if not isinstance(val, str):
            return val
        
        s = val.strip()
        if not s:
            return ""
            
        # If it looks like 'Label: Value' and the label is short (max 25 chars)
        if ":" in s:
            parts = s.split(":", 1)
            label = parts[0]
            if len(label) < 25:
                # Value is the second part
                content = parts[1].strip()
                # Special case: if value is empty after label, it was just a label
                return content
                
        return s

    def _get_display_name(self, path: str) -> str:
        return EXPORT_DISPLAY_NAMES.get(path, path.split(".")[-1].replace("_", " ").title())


class CsvExporter(BaseExporter):
    def export(self, records: List[CanonicalEmployeeRecord], mode: str = "business") -> bytes:
        output = io.StringIO()
        if not records:
            return b""
        
        # 1. Header Logic: Whitelist (Business) vs Full (Debug)
        if mode == "debug":
            sample_dict = records[0].to_dict()
            header_paths = self._get_flat_header(sample_dict)
        else:
            header_paths = BUSINESS_WHITELIST
        
        display_header = [self._get_display_name(p) for p in header_paths]
        
        writer = csv.DictWriter(output, fieldnames=display_header, delimiter=";")
        writer.writeheader()
        
        # 2. Data Writing
        for rec in records:
            flat_rec = self._flatten_dict(rec.to_dict())
            display_rec = {}
            for path in header_paths:
                raw_val = flat_rec.get(path)
                display_rec[self._get_display_name(path)] = self._clean_value(raw_val)
            writer.writerow(display_rec)
            
        # Return UTF-8 WITHOUT BOM (Senior refinement: avoid breaking integrations)
        return output.getvalue().encode("utf-8")

    def _get_flat_header(self, d: dict, prefix="") -> List[str]:
        keys = []
        for k, v in d.items():
            if isinstance(v, dict):
                keys.extend(self._get_flat_header(v, f"{prefix}{k}."))
            else:
                keys.append(f"{prefix}{k}")
        return keys

    def _flatten_dict(self, d: dict, prefix="") -> dict:
        flat = {}
        for k, v in d.items():
            if isinstance(v, dict):
                flat.update(self._flatten_dict(v, f"{prefix}{k}."))
            else:
                val = v
                if isinstance(v, date):
                    val = v.strftime("%d/%m/%Y")
                flat[f"{prefix}{k}"] = val
        return flat


class ExcelExporter(BaseExporter):
    def export(self, records: List[CanonicalEmployeeRecord], mode: str = "business") -> bytes:
        wb = Workbook()
        ws = wb.active
        ws.title = "Legajos"

        if not records:
            out = io.BytesIO()
            wb.save(out)
            return out.getvalue()

        # 1. Header Setup: Uses Sections if mode==business
        header_paths = BUSINESS_WHITELIST if mode == "business" else self._get_flat_header(records[0].to_dict())
        
        for col_num, path in enumerate(header_paths, 1):
            display_name = self._get_display_name(path)
            cell = ws.cell(row=1, column=col_num, value=display_name)
            cell.font = Font(bold=True)

        # 2. Row Data
        for row_num, rec in enumerate(records, 2):
            flat_rec = self._flatten_dict(rec.to_dict())
            for col_num, path in enumerate(header_paths, 1):
                raw_val = flat_rec.get(path)
                ws.cell(row=row_num, column=col_num, value=self._clean_value(raw_val))

        out = io.BytesIO()
        wb.save(out)
        return out.getvalue()

    def _get_flat_header(self, d: dict, prefix="") -> List[str]:
        keys = []
        for k, v in d.items():
            if isinstance(v, dict):
                keys.extend(self._get_flat_header(v, f"{prefix}{k}."))
            else:
                keys.append(f"{prefix}{k}")
        return keys

    def _flatten_dict(self, d: dict, prefix="") -> dict:
        flat = {}
        for k, v in d.items():
            if isinstance(v, dict):
                flat.update(self._flatten_dict(v, f"{prefix}{k}."))
            else:
                flat[f"{prefix}{k}"] = v
        return flat


class TxtFixedExporter(BaseExporter):
    """
    Fixed-width exporter — Banking Data Only.
    Exports only the fields relevant for bank integration:
    DNI, CUIL, Employee Name, Bank Code, Account Number, Account Type, CBU, Payment Method.
    """

    # Banking-only field spec (simplified fixed-width)
    BANKING_FIELDS = [
        # (canonical_field, length, align, fill, label)
        ("identity.dni",                 10, "right", "0"),
        ("identity.cuil",                13, "right", "0"),
        ("identity.last_name",           20, "left",  " "),
        ("identity.first_name",          20, "left",  " "),
        ("banking.bank",                 30, "left",  " "),
        ("banking.account_number",       20, "right", "0"),
        ("banking.cbu",                  25, "right", "0"),
        ("banking.bank_alias",           20, "left",  " "),
        ("banking.payment_method",       15, "left",  " "),
    ]

    # Total line width = sum of all field lengths
    LINE_WIDTH = sum(f[1] for f in BANKING_FIELDS)

    def export(self, records: List[CanonicalEmployeeRecord], mode: str = "business") -> bytes:
        lines = []
        for rec in records:
            lines.append(self._format_record(rec))
        
        # Use ascii with 'replace' to ensure compatibility with legacy systems
        return "\n".join(lines).encode("ascii", errors="replace")

    def _sanitize_isis_text(self, text: str, length: int) -> str:
        """
        Ensures text is ASCII compatible (no accents/ñ) and fits in specified length.
        """
        if not text:
            return ""
        
        # 1. Normalize to remove accents
        import unicodedata
        normalized = "".join(
            c for c in unicodedata.normalize("NFKD", text)
            if not unicodedata.combining(c)
        )
        # 2. Convert to ASCII
        ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
        # 3. Truncate
        return ascii_text[:length]

    def _format_record(self, record: CanonicalEmployeeRecord) -> str:
        record_flat = self._flatten_record(record)
        parts = []

        for field_path, length, align, fill in self.BANKING_FIELDS:
            raw_val = record_flat.get(field_path)
            clean = self._clean_value(raw_val)
            s = str(clean).strip() if clean is not None else ""

            # Truncate to field length
            s = s[:length]

            if align == "left":
                parts.append(s.ljust(length, " "))
            else:
                fill_char = fill if s.isdigit() else " "
                parts.append(s.rjust(length, fill_char))

        return "".join(parts)

    def _flatten_record(self, record: CanonicalEmployeeRecord) -> dict:
        res = {}
        d = record.to_dict()
        for block_name, block_data in d.items():
            for attr, val in block_data.items():
                res[f"{block_name}.{attr}"] = val
        return res



class ExporterFactory:
    @staticmethod
    def get_exporter(fmt: str) -> BaseExporter:
        fmt = fmt.lower()
        if fmt == "csv": return CsvExporter()
        if fmt in ("xlsx", "excel"): return ExcelExporter()
        if fmt in ("txt", "fixed"): return TxtFixedExporter()
        if fmt == "isis_txt": return IsisTxtExporter()
        if fmt == "isis_txt_v3": return IsisTxtExporter(version="V3")
        if fmt == "isis_xlsx": return IsisExcelExporter()
        if fmt == "isis_xlsx_v3": return IsisExcelExporter(version="V3")
        raise ValueError(f"Unsupported export format: {fmt}")


# --- ISIS PAYROLL SPECIFIC EXPORTERS ---

@dataclass(frozen=True)
class IsisField:
    desc: str
    pos: int
    length: int
    db_field: str
    pad_type: str  # 'text', 'num', 'date', 'code'

# Updated EXACT positions from FACU POSICIONES image
# Re-verified with Column B (Posicion) and Column D (Longitud)
ISIS_SPEC_V2: List[IsisField] = [
    IsisField("Cod. Legajo",           1,   4,   "employment.file_number",    "num"),
    IsisField("Tarjeta Reloj",         5,   4,   "_skip",                     "num"),
    IsisField("Apellido",              9,   20,  "identity.last_name",        "text"),
    IsisField("Nombres",               29,  20,  "identity.first_name",       "text"),
    IsisField("Calle",                 49,  25,  "address.address",           "text"),
    IsisField("Numero",                74,  6,   "_skip",                     "num"),
    IsisField("Piso",                  80,  2,   "_skip",                     "text"),
    IsisField("Depto",                 82,  5,   "_skip",                     "text"),
    IsisField("Torre",                 87,  10,  "_skip",                     "text"),
    IsisField("CP",                    97,  4,   "address.postal_code",       "text"),
    IsisField("Localidad",             101, 25,  "address.city",              "text"),
    IsisField("Provincia",             151, 2,   "address.province",          "code"),
    IsisField("Email",                 203, 40,  "address.email",             "text"),
    IsisField("Nro Documento",         251, 9,   "identity.dni",              "num"),
    IsisField("Sexo",                  264, 1,   "identity.gender",           "code"),
    IsisField("Fecha Nac",             265, 10,  "identity.birth_date",       "date"),
    IsisField("Categoria",             277, 3,   "employment.category",       "code"),
    IsisField("Tarea",                 286, 6,   "employment.task",           "code"),
    IsisField("Cargo",                 292, 3,   "employment.job_title",      "code"),
    IsisField("CC",                    295, 6,   "employment.cost_center",    "code"),
    IsisField("Regimen",               301, 3,   "pension.pension_regime",    "code"),
    IsisField("F Ingreso",             304, 10,  "employment.hire_date",       "date"),
    IsisField("Antiguedad",            336, 4,   "_skip",                     "num"),
    IsisField("F Egreso",              344, 10,  "employment.termination_date", "date"),
    IsisField("Actividad",             358, 6,   "pension.activity",          "code"),
    IsisField("CUIL",                  443, 13,  "identity.cuil",             "num"),
    IsisField("CBU",                   411, 25,  "banking.cbu",               "text"),
    IsisField("Cod. Banco",            392, 3,   "banking.bank_code",         "num"),
    IsisField("Nro. Cuenta",           395, 15,  "banking.account_number",    "text"),
    IsisField("Tipo Cuenta",           410, 1,   "_bank_account_type",        "num"),
    IsisField("Forma de Pago",         436, 1,   "banking.payment_method",    "code"),
    IsisField("O.Social",              437, 6,   "documentary.health_insurance", "code"),
]

# FULL VERSION V3 - Balanced sequentially to avoid overlaps while respecting screenshot offsets
# Logic: use Pos from screenshot if possible, else use next available char.
ISIS_SPEC_V3: List[IsisField] = [
    IsisField("Cod. Legajo",           1,   6,   "employment.file_number",    "num"),
    IsisField("Tarjeta Reloj",         7,   10,  "payroll.card_number",       "num"),
    IsisField("Apellido",              17,  20,  "identity.last_name",        "text"),
    IsisField("Nombres",               37,  20,  "identity.first_name",       "text"),
    IsisField("Calle",                 57,  25,  "address.address",           "text"),
    IsisField("Numero",                82,  6,   "_skip",                     "num"),
    IsisField("Piso",                  88,  2,   "_skip",                     "text"),
    IsisField("Depto",                 90,  5,   "_skip",                     "text"),
    IsisField("Torre",                 95,  10,  "_skip",                     "text"),
    IsisField("Cod. Categoria",        105, 4,   "employment.category",       "code"),
    IsisField("Cod. Cargo",            109, 10,  "employment.job_title",      "code"),
    IsisField("Cod. Nacionalidad",     119, 4,   "identity.nationality",      "code"),
    IsisField("Cod. Sexo",             123, 1,   "identity.gender",           "code"),
    IsisField("Cod. Estado Civil",     124, 2,   "identity.marital_status",   "code"),
    IsisField("Pais",                  126, 20,  "identity.nationality",      "text"),
    IsisField("Telefono",              146, 30,  "address.phone",             "text"),
    IsisField("Email",                 176, 60,  "address.email",             "text"),
    IsisField("Cod. Tipo Doc",         236, 2,   "documentary.document_type", "code"),
    IsisField("Nro Documento",         238, 10,  "identity.dni",              "num"),
    IsisField("CUIL/CUIT",             248, 13,  "identity.cuil",             "num"),
    IsisField("Cod. Regimen",          261, 6,   "pension.pension_regime",    "code"),
    IsisField("Cod. Obra Social",      267, 7,   "documentary.health_insurance", "code"),
    IsisField("F. Nacimiento",         274, 10,  "identity.birth_date",       "date"),
    IsisField("F. Ingreso",            284, 10,  "employment.hire_date",       "date"),
    IsisField("Edad",                  294, 2,   "_skip",                     "num"),
    IsisField("Cod. Seccion",          296, 6,   "employment.section",        "code"),
    IsisField("Cod. Tarea",            302, 6,   "employment.task",           "code"),
    IsisField("Cod. Centro Costo",     308, 6,   "employment.cost_center",    "code"),
    IsisField("Antiguedad",            314, 4,   "_skip",                     "num"),
    IsisField("Antiguedad Ant",        318, 4,   "_skip",                     "num"),
    IsisField("F. Egreso",             322, 10,  "employment.termination_date", "date"),
    IsisField("Cod. Forma Pago",       332, 4,   "banking.payment_method",    "code"),
    IsisField("Cod. Banco",            336, 6,   "banking.bank_code",         "num"),
    IsisField("Nro. Cuenta",           342, 20,  "banking.account_number",    "text"),
    IsisField("Tipo Cuenta",           362, 8,   "_bank_account_type",        "num"),
    IsisField("CBU",                   370, 25,  "banking.cbu",               "text"),
    IsisField("Cod. Actividad",        395, 6,   "pension.activity",          "code"),
    IsisField("Cod. Condicion",        401, 4,   "pension.labor_condition",   "code"),
    IsisField("Cod. Modalidad",        405, 6,   "employment.hire_type",      "code"),
    IsisField("Cod. AFIP Revista",     411, 4,   "pension.revista_situation", "code"),
    IsisField("Cod. AFIP Locality",    415, 4,   "_skip",                     "code"),
    IsisField("Grupo Conceptos",       419, 4,   "_skip",                     "code"),
    IsisField("Cod. Sindicato",        423, 4,   "documentary.union",         "code"),
    IsisField("Cod. Convenio Sind.",   427, 6,   "employment.union_agreement", "code"),
    IsisField("Remuneracion",          433, 11,  "_skip",                     "num"),
    IsisField("Baja Transitoria",      444, 1,   "_skip",                     "num"),
    IsisField("Baja Definitiva",       445, 1,   "_skip",                     "num"),
    IsisField("Tipo Remun",            446, 1,   "_skip",                     "num"),
    IsisField("Tipo Convenio",         447, 1,   "_skip",                     "num"),
    IsisField("Hs Mensuales",          448, 6,   "_skip",                     "num"),
    IsisField("Grossing Up",           454, 1,   "_skip",                     "num"),
    IsisField("Zona Desfav.",          455, 1,   "_skip",                     "num"),
    IsisField("Afecta Est.",           456, 1,   "_skip",                     "num"),
    IsisField("Cod. Siniestrado",      457, 2,   "_skip",                     "num"),
    IsisField("Lugar Pago",            459, 4,   "banking.payment_place",     "code"),
    IsisField("Base Aguinaldo",        463, 9,   "_skip",                     "num"),
    IsisField("Nro Afiliado Sind.",    472, 20,  "documentary.union_number",  "text"),
    IsisField("Fondo Desempleo",       492, 22,  "_skip",                     "text"),
    IsisField("Localidad",             514, 25,  "address.city",              "text"),
    IsisField("Paraje",                539, 25,  "_skip",                     "text"),
    IsisField("CP",                    564, 10,  "address.postal_code",       "text"),
    IsisField("Provincia",             574, 2,   "address.province",          "code"),
    IsisField("Nro IERIC",             576, 12,  "_skip",                     "num"),
    IsisField("Grupo Legajo",          588, 25,  "_skip",                     "text"),
    IsisField("Jornada Reducida",      613, 1,   "_skip",                     "num"),
    IsisField("% Remuneracion",        614, 6,   "_skip",                     "num"),
]

TOTAL_ISIS_WIDTH_V2 = 584
TOTAL_ISIS_WIDTH_V3 = 620 # Buffer for V3

# --- ISIS PAYROLL SHARED LOGIC ---

class IsisBase:
    def _flatten_record(self, record: CanonicalEmployeeRecord) -> dict:
        res = {}
        d = record.to_dict()
        for block_name, block_data in d.items():
            for attr, val in block_data.items(): res[f"{block_name}.{attr}"] = val
        return res

    def _get_val(self, flat: dict, field: IsisField) -> str:
        if field.db_field == "_skip": return ""
        if field.db_field == "_bank_account_type": return "2" # Default Cta Cte
        raw = flat.get(field.db_field)
        if field.pad_type == "date" and isinstance(raw, (date, datetime)):
            return raw.strftime("%d/%m/%Y")
        if field.db_field == "identity.gender":
            g = str(raw).lower()
            return "1" if "m" in g else ("2" if "f" in g else "0")
        return str(raw) if raw is not None else ""

    def _sanitize_isis_text(self, text: str, length: int) -> str:
        if not text: return ""
        import unicodedata
        normalized = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
        ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
        return ascii_text[:length]

class IsisTxtExporter(BaseExporter, IsisBase):
    def __init__(self, version="V2"):
        self.version = version
        self.spec = ISIS_SPEC_V3 if version == "V3" else ISIS_SPEC_V2
        self.width = TOTAL_ISIS_WIDTH_V3 if version == "V3" else TOTAL_ISIS_WIDTH_V2

    def export(self, records: List[CanonicalEmployeeRecord], mode: str = "business") -> bytes:
        lines = []
        for rec in records:
            lines.append(self._format_line(rec))
        # DOS/Windows style usually expected by legacy systems
        return "\r\n".join(lines).encode("latin-1", errors="replace")

    def _format_line(self, record: CanonicalEmployeeRecord) -> str:
        buffer = [" "] * self.width
        flat_rec = self._flatten_record(record)
        for field in self.spec:
            val = self._get_val(flat_rec, field)
            # Sanitization applied before padding
            sanitized = self._sanitize_isis_text(val, field.length)
            padded = self._pad(sanitized, field)
            start = field.pos - 1
            for i, ch in enumerate(padded):
                if start + i < self.width:
                    buffer[start + i] = ch
        return "".join(buffer)

    def _pad(self, val: str, field: IsisField) -> str:
        s = val[:field.length]
        if field.pad_type in ("num", "code"): return s.rjust(field.length, "0")
        return s.ljust(field.length, " ")


class IsisExcelExporter(BaseExporter, IsisBase):
    def __init__(self, version="V2"):
        self.version = version
        self.spec = ISIS_SPEC_V3 if version == "V3" else ISIS_SPEC_V2

    def export(self, records: List[CanonicalEmployeeRecord], mode: str = "business") -> bytes:
        wb = Workbook()
        ws = wb.active
        ws.title = f"Legajos ISIS {self.version}"
        for col, field in enumerate(self.spec, 1):
            cell = ws.cell(row=1, column=col, value=field.desc)
            cell.font = Font(bold=True)
        for row_num, rec in enumerate(records, 2):
            flat = self._flatten_record(rec)
            for col, field in enumerate(self.spec, 1):
                # Use shared value retrieval and sanitization for Excel too
                val = self._get_val(flat, field)
                sanitized = self._sanitize_isis_text(val, field.length)
                ws.cell(row=row_num, column=col, value=sanitized)
        out = io.BytesIO()
        wb.save(out)
        return out.getvalue()
