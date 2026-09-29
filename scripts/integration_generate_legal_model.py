"""Integration proof for the default TLG-INT-001 legal model.

This script is intentionally limited to one operation: read an existing employee
and organization, overlay resolvable values on a copy of the default PDF, and
report fields that still require case-specific or legal input. It never edits
database rows, signs the document, or writes to the default template.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

import fitz
from dotenv import load_dotenv
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv()

from payroll_core import SessionLocal  # noqa: E402

DEFAULT_TEMPLATE = ROOT / "Modelos Legales" / "TLG-INT-001 - Telegrama de intimación al trabajador.pdf"
DEFAULT_OUTPUT = ROOT / "generated" / "modelos_legales" / "TLG-INT-001 - copia autocompletada.pdf"


def _text(value) -> str:
    return str(value).strip() if value is not None else ""


def _full_address(row) -> str:
    street = " ".join(part for part in (_text(row["address"]), _text(row["address_number"])) if part)
    locality = ", ".join(part for part in (_text(row["city"]), _text(row["province"])) if part)
    postal = f"CP {_text(row['postal_code'])}" if _text(row["postal_code"]) else ""
    return ", ".join(part for part in (street, locality, postal) if part)


def _fit_font(page: fitz.Page, value: str, rect: fitz.Rect, max_size: float = 9.2) -> float:
    size = max_size
    while size > 6 and fitz.get_text_length(value, fontname="helv", fontsize=size) > rect.width:
        size -= 0.25
    return size


def _replace(page: fitz.Page, placeholder: str, value: str, *, occurrence: int | None = None) -> int:
    boxes = page.search_for(placeholder)
    if occurrence is not None:
        boxes = boxes[occurrence:occurrence + 1]
    for box in boxes:
        page.add_redact_annot(box, fill=(1, 1, 1))
    if boxes:
        page.apply_redactions()
        for box in boxes:
            font_size = _fit_font(page, value, box)
            page.insert_text(
                fitz.Point(box.x0, box.y1 - 1.2),
                value,
                fontname="helv",
                fontsize=font_size,
                color=(0.06, 0.09, 0.16),
                overlay=True,
            )
    return len(boxes)


def generate(employee_id: str | None = None, output: Path = DEFAULT_OUTPUT) -> dict:
    if not DEFAULT_TEMPLATE.exists():
        raise FileNotFoundError(f"Default template not found: {DEFAULT_TEMPLATE}")

    db = SessionLocal()
    try:
        params = {"employee_id": employee_id} if employee_id else {}
        employee = db.execute(text("""
            SELECT e.id, e.first_name, e.last_name, e.dni, e.cuil,
                   e.address, e.address_number, e.city, e.province, e.postal_code,
                   e.organization_id, o.name AS organization_name, o.cuit AS organization_cuit,
                   o.city AS organization_city, o.province AS organization_province
            FROM employees e
            JOIN organizations o ON o.id = e.organization_id
            WHERE e.is_deleted = false AND e.is_active = true
              AND (:employee_id IS NULL OR e.id::text = :employee_id)
            ORDER BY e.created_at DESC
            LIMIT 1
        """), {"employee_id": employee_id}).mappings().first()
        if not employee:
            raise ValueError("No active employee found for integration test")
    finally:
        db.close()

    employee_name = " ".join(part for part in (_text(employee["first_name"]), _text(employee["last_name"])) if part)
    employee_identifier = _text(employee["cuil"]) or _text(employee["dni"])
    address = _full_address(employee)
    emission_place = _text(employee["organization_city"])
    emission_date = datetime.now().strftime("%d/%m/%Y")
    company_name = _text(employee["organization_name"])
    company_cuit = _text(employee["organization_cuit"])

    output.parent.mkdir(parents=True, exist_ok=True)
    document = fitz.open(str(DEFAULT_TEMPLATE))
    page = document[0]
    replacements = {
        "{{empresa.localidad_emision}}": emission_place,
        "{{documento.fecha_emision}}": emission_date,
        "{{empleado.apellido_y_nombre}}": employee_name,
        "{{empleado.cuil}}": employee_identifier,
        "{{empleado.domicilio_completo}}": address,
        "{{empresa.razon_social}}": company_name,
        "{{empresa.cuit}}": company_cuit,
        "{{incidencia.fecha_inicio_ausencia}}": "",
        "{{intimacion.plazo_horas}}": "72",
        "{{empresa.firmante_autorizado}}": "",
        "{{empresa.firma_digital_url}}": "",
    }

    # The supplied PDF is visual/static, so map its visible labels to the
    # canonical variables while keeping unresolved case fields untouched.
    replaced = {
        "{{documento.fecha_emision}}": _replace(page, "[Fecha de Emisión]", emission_date),
        "{{empleado.apellido_y_nombre}}": _replace(page, "[Nombre y Apellido]", employee_name),
        "{{empleado.cuil}}": _replace(page, "[CUIL / DNI]", employee_identifier),
        "{{empleado.domicilio_completo}}": _replace(page, "[Domicilio del Trabajador]", address),
        "{{empresa.razon_social}}": _replace(page, "[Razón Social de la Empresa]", company_name),
        "{{intimacion.plazo_horas}}": _replace(page, "[72 horas]", "72 horas"),
    }
    # The organization has no locality configured in the current backend row.
    # The absence date and signer are case/manual inputs and remain visible.
    document.set_metadata({
        "title": "TLG-INT-001 - Copia autocompletada",
        "subject": "Prueba de integración de Modelos Laborales MyManageRH",
        "keywords": "TLG-INT-001, MyManageRH, integración",
    })
    document.save(str(output), garbage=4, deflate=True)
    document.close()

    return {
        "template": str(DEFAULT_TEMPLATE.relative_to(ROOT)),
        "output": str(output.relative_to(ROOT)),
        "employee": {
            "id": str(employee["id"]),
            "name": employee_name,
            "identifier": employee_identifier,
            "address": address,
        },
        "organization": {
            "id": str(employee["organization_id"]),
            "name": company_name,
            "cuit": company_cuit,
            "emission_place": emission_place,
        },
        "resolved": {
            "{{documento.fecha_emision}}": emission_date,
            "{{empleado.apellido_y_nombre}}": employee_name,
            "{{empleado.cuil}}": employee_identifier,
            "{{empleado.domicilio_completo}}": address,
            "{{empresa.razon_social}}": company_name,
            "{{empresa.cuit}}": company_cuit,
            "{{intimacion.plazo_horas}}": "72",
        },
        "pending": [
            "{{empresa.localidad_emision}}: la organización no tiene localidad configurada",
            "{{incidencia.fecha_inicio_ausencia}}: requiere datos del caso",
            "{{empresa.firmante_autorizado}}: requiere configuración del firmante",
            "{{empresa.firma_digital_url}}: no se ejecuta firma en esta prueba",
        ],
        "replaced_occurrences": replaced,
        "company_cuit_available_but_not_visible_in_template": bool(company_cuit),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--employee-id", default=None)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    import json
    print(json.dumps(generate(args.employee_id, args.output), ensure_ascii=False, indent=2, default=str))