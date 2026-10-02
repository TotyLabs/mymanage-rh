"""Domain service for structured Labor Model instances."""

from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import fitz
from sqlalchemy import text
from sqlalchemy.orm import Session

import config
from payroll_core import ALLOWED_STORAGE_DIR, audit, safe_join_under_storage, utc_now


MODEL_CATALOG = {
    "TLG-INT-001": {
        "code": "TLG-INT-001",
        "category": "Abandono de trabajo",
        "title": "Telegrama de intimación al trabajador",
        "description": "Modelo de intimación para reanudación de tareas ante ausencia sin aviso.",
        "version": "1.1",
        "template_path": "Plantilla Telegrama de Intimación MyManageRH (7).pdf",
        "fields": [
            {"key": "empresa.localidad_emision", "label": "Lugar de emisión", "group": "Automáticos", "required": True, "source": "organization.city"},
            {"key": "documento.fecha_emision", "label": "Fecha de emisión", "group": "Automáticos", "required": True, "source": "system.today"},
            {"key": "empresa.razon_social", "label": "Razón social", "group": "Empresa", "required": True, "source": "organization.name"},
            {"key": "empleado.apellido_y_nombre", "label": "Nombre y apellido", "group": "Empleado", "required": True, "source": "employee.full_name"},
            {"key": "empleado.cuil", "label": "DNI/CUIL", "group": "Empleado", "required": True, "source": "employee.cuil_or_dni"},
            {"key": "empleado.domicilio_completo", "label": "Domicilio", "group": "Empleado", "required": True, "source": "employee.address"},
            {"key": "incidencia.fecha_inicio_ausencia", "label": "Fecha de inicio de ausencia", "group": "Caso", "required": True, "source": "manual"},
            {"key": "intimacion.plazo_horas", "label": "Plazo de intimación (horas)", "group": "Caso", "required": True, "default": "72", "source": "template.default"},
        ],
    }
}


def catalog() -> list[dict[str, Any]]:
    return list(MODEL_CATALOG.values())


def get_model(code: str) -> dict[str, Any]:
    try:
        return MODEL_CATALOG[code]
    except KeyError as exc:
        raise ValueError("labor_model_not_found") from exc


def _address(row: Any) -> str:
    street = " ".join(part for part in (row["address"], row["address_number"]) if part)
    locality = ", ".join(part for part in (row["city"], row["province"]) if part)
    postal = f"CP {row['postal_code']}" if row["postal_code"] else ""
    return ", ".join(part for part in (street, locality, postal) if part)


def resolve_fields(db: Session, organization_id: str, employee_id: Optional[str] = None) -> dict[str, Any]:
    organization = db.execute(text("""
        SELECT id, name, cuit, city, province, zip_code
        FROM organizations WHERE id = :org
    """), {"org": organization_id}).mappings().first()
    if not organization:
        raise ValueError("organization_not_found")

    employee = None
    if employee_id:
        employee = db.execute(text("""
            SELECT id, first_name, last_name, dni, cuil, address, address_number,
                   city, province, postal_code
            FROM employees
            WHERE id = :employee AND organization_id = :org
              AND is_deleted = false AND is_active = true
        """), {"employee": employee_id, "org": organization_id}).mappings().first()
        if not employee:
            raise ValueError("employee_not_found")

    today = datetime.now().strftime("%d/%m/%Y")
    today_iso = datetime.now().strftime("%Y-%m-%d")
    fields = {
        "empresa.localidad_emision": organization["city"] or "",
        "documento.fecha_emision": today,
        "empresa.razon_social": organization["name"] or "",
        "empleado.apellido_y_nombre": "",
        "empleado.cuil": "",
        "empleado.domicilio_completo": "",
        "incidencia.fecha_inicio_ausencia": today_iso,
        "intimacion.plazo_horas": "72",
    }
    if employee:
        fields.update({
            "empleado.apellido_y_nombre": " ".join(part for part in (employee["first_name"], employee["last_name"]) if part),
            "empleado.cuil": employee["cuil"] or employee["dni"] or "",
            "empleado.domicilio_completo": _address(employee),
        })
    return fields


def pending_fields(fields: dict[str, Any], code: str) -> list[str]:
    model = get_model(code)
    return [field["key"] for field in model["fields"] if field["required"] and not str(fields.get(field["key"], "")).strip()]


def _normalize_display_date(value: str) -> str:
    if not value:
        return ""
    candidate = str(value).strip()
    if not candidate:
        return ""
    try:
        if len(candidate) == 10 and candidate[4] == '-' and candidate[7] == '-':
            dt = datetime.strptime(candidate, "%Y-%m-%d")
            return dt.strftime("%d/%m/%Y")
    except ValueError:
        pass
    if "/" in candidate:
        return candidate
    try:
        dt = datetime.strptime(candidate, "%d/%m/%Y")
        return dt.strftime("%d/%m/%Y")
    except ValueError:
        pass
    return candidate


def _fit_font(value: str, rect: fitz.Rect, max_size: float = 11.8) -> float:
    size = max_size
    while size > 7 and fitz.get_text_length(value, fontname="helv", fontsize=size) > rect.width:
        size -= 0.25
    return size


def _replace(page: fitz.Page, placeholder: str, value: str, prefer_last: bool = False) -> int:
    boxes = page.search_for(placeholder)
    if not boxes or not value:
        return 0
    if prefer_last:
        last_box = sorted(boxes, key=lambda box: (box.y0, box.x0))[-1]
        for box in boxes:
            page.add_redact_annot(box, fill=(1, 1, 1))
        page.apply_redactions()
        page.insert_text(fitz.Point(last_box.x0, last_box.y1 - 1.2), value, fontname="helv", fontsize=_fit_font(value, last_box), color=(0.06, 0.09, 0.16), overlay=True)
        return len(boxes)
    for box in boxes:
        page.add_redact_annot(box, fill=(1, 1, 1))
    page.apply_redactions()
    for box in boxes:
        page.insert_text(fitz.Point(box.x0, box.y1 - 1.2), value, fontname="helv", fontsize=_fit_font(value, box), color=(0.06, 0.09, 0.16), overlay=True)
    return len(boxes)


def _replace_variants(page: fitz.Page, value: str, candidates: list[str], prefer_last: bool = False) -> int:
    if not value:
        return 0
    for candidate in candidates:
        replaced = _replace(page, candidate, value, prefer_last=prefer_last)
        if replaced:
            return replaced
    return 0


def render_instance(db: Session, document_id: str, organization_id: str) -> dict[str, Any]:
    row = db.execute(text("""
        SELECT id, template_code, template_path, fields, employee_id, status
        FROM labor_model_documents
        WHERE id = :id AND organization_id = :org
    """), {"id": document_id, "org": organization_id}).mappings().first()
    if not row:
        raise ValueError("labor_document_not_found")
    if row["status"] in ("FIRMADO", "ENVIADO"):
        raise ValueError("labor_document_locked")

    template = Path(row["template_path"])
    if not template.is_absolute():
        template = ROOT / template
    if not template.exists():
        raise FileNotFoundError("labor_model_template_missing")

    fields = row["fields"] or {}
    output_rel = f"labor_models/{organization_id}/{document_id}/rendered.pdf"
    output = Path(ALLOWED_STORAGE_DIR) / output_rel
    output.parent.mkdir(parents=True, exist_ok=True)
    document = fitz.open(str(template))
    page = document[0]
    emission_date = _normalize_display_date(fields.get("documento.fecha_emision", "") or datetime.now().strftime("%Y-%m-%d"))
    absence_date = _normalize_display_date(fields.get("incidencia.fecha_inicio_ausencia", "") or datetime.now().strftime("%Y-%m-%d"))

    occurrences = {
        "empresa.localidad_emision": _replace_variants(page, fields.get("empresa.localidad_emision", ""), ["[Lugar de Emisión]", "[Lugar de Emision]", "[Lugar Emisión]"]),
        "documento.fecha_emision": _replace_variants(page, emission_date, ["[Fecha de Emisión]", "[Fecha de Emision]", "[Fecha Emision]"]),
        "empleado.apellido_y_nombre": _replace_variants(page, fields.get("empleado.apellido_y_nombre", ""), ["[Nombre y Apellido]", "[Nombre y apellido]", "[Apellido y Nombre]"]),
        "empleado.cuil": _replace_variants(page, fields.get("empleado.cuil", ""), ["[CUIL / DNI]", "[CUIL / Dni]", "[CUIL o DNI]"]),
        "empleado.domicilio_completo": _replace_variants(page, fields.get("empleado.domicilio_completo", ""), ["[Domicilio del Trabajador]", "[Domicilio]"]),
        "empresa.razon_social": _replace_variants(page, fields.get("empresa.razon_social", ""), ["[Razón Social de la Empresa]", "[Razon Social de la Empresa]", "[Razón Social]"]),
        "incidencia.fecha_inicio_ausencia": _replace_variants(page, absence_date, ["[Fecha Inicio Ausencia]", "[Fecha de Inicio de Ausencia]", "[Fecha Inicio Ausencia ]"]),
        "intimacion.plazo_horas": _replace_variants(page, f"{fields.get('intimacion.plazo_horas', '72')} horas", ["[72 horas]", "[72 Horas]", "72 horas"]),
    }
    document.set_metadata({"title": f"{row['template_code']} - MyManageRH", "subject": "Modelo Laboral"})
    document.save(str(output), garbage=4, deflate=True)
    document.close()
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    db.execute(text("""
        UPDATE labor_model_documents
        SET rendered_pdf_path = :path, rendered_pdf_sha256 = :hash,
            updated_at = :now,
            status = CASE WHEN status = 'BORRADOR' THEN 'LISTO_PARA_FIRMAR' ELSE status END
        WHERE id = :id AND organization_id = :org
    """), {"path": output_rel, "hash": digest, "now": utc_now(), "id": document_id, "org": organization_id})
    db.commit()
    return {"path": str(output), "sha256": digest, "occurrences": occurrences}


ROOT = Path(__file__).resolve().parents[1]