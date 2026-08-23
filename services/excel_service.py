from openpyxl import Workbook
from typing import List, Dict, Any
from io import BytesIO


def _safe(value: Any) -> Any:
    """
    Sanitiza valores para evitar None, objetos raros o strings vacíos.
    """
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return value
    return str(value).strip()


def _append_rows(ws, headers: List[str], rows: List[List[Any]]):
    """
    Helper para evitar duplicación.
    """
    ws.append(headers)
    for row in rows:
        ws.append([_safe(v) for v in row])


def generate_employee_multisheet_excel(
    data: Dict[str, List[Dict[str, Any]]]
) -> BytesIO:
    """
    Genera un Excel multi-hoja robusto y consistente.

    Espera keys:
    - personal
    - labor
    - financial
    - family

    Output:
    - BytesIO listo para descarga o almacenamiento
    """

    wb = Workbook()

    # =========================
    # 🟢 HOJA 1: PERSONAL
    # =========================
    ws_personal = wb.active
    ws_personal.title = "Datos Personales"

    headers_personal = [
        "CUIL",
        "Nombre Completo",
        "DNI",
        "Fecha Nacimiento",
        "Nacionalidad",
        "Estado Civil",
        "Nivel Estudios",
        "Email",
    ]

    rows_personal = [
        [
            r.get("cuil"),
            r.get("full_name"),
            r.get("dni"),
            r.get("fecha_nacimiento"),
            r.get("nacionalidad"),
            r.get("estado_civil"),
            r.get("nivel_estudios"),
            r.get("email_personal"),
        ]
        for r in data.get("personal", [])
    ]

    _append_rows(ws_personal, headers_personal, rows_personal)

    # =========================
    # 🔵 HOJA 2: LABORAL
    # =========================
    ws_labor = wb.create_sheet("Datos Laborales")

    headers_labor = [
        "CUIL",
        "Fecha Ingreso",
        "Categoría",
        "Puesto",
        "Función",
        "Centro Costo",
        "ART",
        "Obra Social",
    ]

    rows_labor = [
        [
            r.get("cuil"),
            r.get("fecha_ingreso"),
            r.get("categoria"),
            r.get("puesto"),
            r.get("funcion"),
            r.get("centro_costo"),
            r.get("art"),
            r.get("obra_social_nombre"),
        ]
        for r in data.get("labor", [])
    ]

    _append_rows(ws_labor, headers_labor, rows_labor)

    # =========================
    # 🟡 HOJA 3: BANCARIA
    # =========================
    ws_financial = wb.create_sheet("Datos Bancarios")

    headers_financial = [
        "CUIL",
        "Banco",
        "CBU",
        "Alias",
        "Número Cuenta",
        "Contacto Emergencia",
        "Teléfono Emergencia",
    ]

    rows_financial = [
        [
            r.get("cuil"),
            r.get("banco"),
            r.get("cbu"),
            r.get("alias"),
            r.get("numero_cuenta"),
            r.get("contacto_emergencia_nombre"),
            r.get("contacto_emergencia_telefono"),
        ]
        for r in data.get("financial", [])
    ]

    _append_rows(ws_financial, headers_financial, rows_financial)

    # =========================
    # 🔴 HOJA 4: FAMILIA
    # =========================
    ws_family = wb.create_sheet("Familia")

    headers_family = [
        "CUIL Empleado",
        "Nombre",
        "Vínculo",
        "CUIL Pariente",
        "Fecha Nacimiento",
    ]

    rows_family = [
        [
            r.get("employee_cuil"),
            r.get("nombre"),
            r.get("vinculo"),
            r.get("cuil"),
            r.get("fecha_nacimiento"),
        ]
        for r in data.get("family", [])
    ]

    _append_rows(ws_family, headers_family, rows_family)

    # =========================
    # 📦 OUTPUT
    # =========================
    output = BytesIO()
    wb.save(output)
    output.seek(0)

    return output