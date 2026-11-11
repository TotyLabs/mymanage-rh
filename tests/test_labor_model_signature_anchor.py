import os
import re
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import fitz
import pytest
from PIL import Image

os.environ.setdefault("SECRET_KEY", "test")

from modules.signature import SignatureEngine, SignatureError
from services.labor_model_service import MODEL_CATALOG, ROOT


def test_tlg_int_001_seal_replaces_template_anchor(tmp_path):
    template = ROOT / MODEL_CATALOG["TLG-INT-001"]["template_path"]
    with fitz.open(template) as source:
        anchor = source[0].search_for("{{empresa.campo_firma_sello}}")[0]

    image = Image.new("RGBA", (240, 80), (0, 0, 0, 255))
    image_buffer = BytesIO()
    image.save(image_buffer, format="PNG")

    engine = SignatureEngine(storage_path=tmp_path / "signature-storage")
    output_path = tmp_path / "tlg-signed.pdf"
    result = engine.stamp_signature_from_bytes(
        pdf_path=str(template),
        signature_bytes=image_buffer.getvalue(),
        role="employer",
        signer_name="Firmante de prueba",
        signer_tax_id="30712345678",
        signer_identity={
            "dni": "30712345678",
            "full_name": "Firmante de prueba",
            "role": "employer",
        },
        timestamp=datetime.now(timezone.utc),
        output_path=str(output_path),
        doc_type="LABOR_MODEL",
        source="labor_model",
    )

    with fitz.open(result["signed_pdf_path"]) as signed:
        page_text = signed[0].get_text()
        assert "{{empresa.campo_firma_sello}}" not in page_text
        assert "Documento: Telegrama de Intimación" in page_text
        assert "Documento: Recibo de Haberes" not in page_text

        seal_position = re.search(
            r"seal:employer:[^:]+:(\d+),(\d+);",
            signed.metadata.get("keywords", ""),
        )
        assert seal_position
        seal_x, seal_y = map(int, seal_position.groups())
        assert abs(seal_x + 135 - (anchor.x0 + anchor.width / 2)) <= 1
        assert abs(seal_y + 25 - (anchor.y0 + anchor.height / 2)) <= 1


def test_labor_model_stamp_rejects_missing_anchor(tmp_path):
    source = tmp_path / "missing-anchor.pdf"
    with fitz.open() as document:
        document.new_page().insert_text((72, 72), "Documento sin ancla de firma")
        document.save(source)

    image = Image.new("RGBA", (240, 80), (0, 0, 0, 255))
    image_buffer = BytesIO()
    image.save(image_buffer, format="PNG")
    engine = SignatureEngine(storage_path=tmp_path / "signature-storage")

    with pytest.raises(SignatureError, match="labor_model_seal_anchor_missing"):
        engine.stamp_signature_from_bytes(
            pdf_path=str(source),
            signature_bytes=image_buffer.getvalue(),
            role="employer",
            signer_name="Firmante de prueba",
            signer_tax_id="30712345678",
            signer_identity={
                "dni": "30712345678",
                "full_name": "Firmante de prueba",
                "role": "employer",
            },
            timestamp=datetime.now(timezone.utc),
            output_path=str(tmp_path / "must-not-sign.pdf"),
            doc_type="LABOR_MODEL",
            source="labor_model",
        )


def test_receipt_stamp_keeps_receipt_document_type(tmp_path):
    source = tmp_path / "receipt.pdf"
    with fitz.open() as document:
        document.new_page().insert_text((72, 72), "Recibo de prueba")
        document.save(source)

    image = Image.new("RGBA", (240, 80), (0, 0, 0, 255))
    image_buffer = BytesIO()
    image.save(image_buffer, format="PNG")
    engine = SignatureEngine(storage_path=tmp_path / "signature-storage")
    result = engine.stamp_signature_from_bytes(
        pdf_path=str(source),
        signature_bytes=image_buffer.getvalue(),
        role="employee",
        signer_name="Empleado de prueba",
        signer_tax_id="20123456786",
        signer_identity={
            "dni": "12345678",
            "full_name": "Empleado de prueba",
            "role": "employee",
            "email": "empleado@example.com",
        },
        timestamp=datetime.now(timezone.utc),
        output_path=str(tmp_path / "receipt-signed.pdf"),
    )

    with fitz.open(result["signed_pdf_path"]) as signed:
        assert "Documento: Recibo de Haberes" in signed[0].get_text()
        assert "Documento: Legajo de Personal" not in signed[0].get_text()


def test_employee_legajo_signature_is_stamped_on_every_page(tmp_path):
    source = tmp_path / "employee-legajo.pdf"
    anchor_rects = []
    with fitz.open() as document:
        for page_number in range(3):
            page = document.new_page()
            page.insert_text((72, 72), f"Legajo página {page_number + 1}")
            page.insert_text((250, 200 + page_number * 100), "{{legajo.sello_firma}}", fontsize=1, color=(1, 1, 1))
            anchor_rects.append(page.search_for("{{legajo.sello_firma}}")[0])
        document.save(source)

    image = Image.new("RGBA", (240, 80), (0, 0, 0, 255))
    image_buffer = BytesIO()
    image.save(image_buffer, format="PNG")
    engine = SignatureEngine(storage_path=tmp_path / "signature-storage")
    result = engine.stamp_signature_from_bytes(
        pdf_path=str(source),
        signature_bytes=image_buffer.getvalue(),
        role="employee",
        signer_name="Empleado de prueba",
        signer_tax_id="20123456786",
        signer_identity={
            "dni": "12345678",
            "full_name": "Empleado de prueba",
            "role": "employee",
            "email": "empleado@example.com",
        },
        timestamp=datetime.now(timezone.utc),
        output_path=str(tmp_path / "employee-legajo-signed.pdf"),
        doc_type="EMPLOYEE_LEGAJO",
        source="employee_legajo",
        apply_to_all_pages=True,
    )

    with fitz.open(result["signed_pdf_path"]) as signed:
        assert signed.page_count == 3
        seal_positions = re.findall(
            r"seal:employee:[^:]+:(\d+),(\d+);",
            signed.metadata.get("keywords", ""),
        )
        assert len(seal_positions) == 3
        for page, anchor_rect, seal_position in zip(signed, anchor_rects, seal_positions):
            image_rects = [
                rect
                for image in page.get_images(full=True)
                for rect in page.get_image_rects(image[0])
            ]
            assert len(image_rects) >= 2
            assert all(page.rect.contains(rect) for rect in image_rects)
            assert "{{legajo.sello_firma}}" not in page.get_text()
            assert "Documento: Legajo de Personal" in page.get_text()
            seal_x, seal_y = map(int, seal_position)
            assert abs(seal_x + 135 - anchor_rect.x0 - anchor_rect.width / 2) <= 1
            assert abs(seal_y + 25 - anchor_rect.y0 - anchor_rect.height / 2) <= 1


def test_employee_legajo_signature_rejects_missing_seal_field(tmp_path):
    source = tmp_path / "employee-legajo-without-anchor.pdf"
    with fitz.open() as document:
        document.new_page().insert_text((72, 72), "Legajo sin campo de firma")
        document.save(source)

    image = Image.new("RGBA", (240, 80), (0, 0, 0, 255))
    image_buffer = BytesIO()
    image.save(image_buffer, format="PNG")
    engine = SignatureEngine(storage_path=tmp_path / "signature-storage")

    with pytest.raises(SignatureError, match="employee_legajo_seal_anchor_missing"):
        engine.stamp_signature_from_bytes(
            pdf_path=str(source),
            signature_bytes=image_buffer.getvalue(),
            role="employee",
            signer_name="Empleado de prueba",
            signer_tax_id="20123456786",
            signer_identity={
                "dni": "12345678",
                "full_name": "Empleado de prueba",
                "role": "employee",
                "email": "empleado@example.com",
            },
            timestamp=datetime.now(timezone.utc),
            output_path=str(tmp_path / "employee-legajo-without-anchor-signed.pdf"),
            doc_type="EMPLOYEE_LEGAJO",
            source="employee_legajo",
            apply_to_all_pages=True,
        )


def test_employee_legajo_legacy_signature_line_positions_seal_above_line(tmp_path):
    source = tmp_path / "legacy-employee-legajo.pdf"
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((100, 320), "Firma del Trabajador:", fontsize=9)
        label_rect = page.search_for("Firma del Trabajador:")[0]
        line_y = label_rect.y0 - 3.6
        page.draw_line(fitz.Point(100, line_y), fitz.Point(400, line_y))
        document.save(source)

    image = Image.new("RGBA", (240, 80), (0, 0, 0, 255))
    image_buffer = BytesIO()
    image.save(image_buffer, format="PNG")
    engine = SignatureEngine(storage_path=tmp_path / "signature-storage")
    result = engine.stamp_signature_from_bytes(
        pdf_path=str(source),
        signature_bytes=image_buffer.getvalue(),
        role="employee",
        signer_name="Empleado de prueba",
        signer_tax_id="20123456786",
        signer_identity={
            "dni": "12345678",
            "full_name": "Empleado de prueba",
            "role": "employee",
            "email": "empleado@example.com",
        },
        timestamp=datetime.now(timezone.utc),
        output_path=str(tmp_path / "legacy-employee-legajo-signed.pdf"),
        doc_type="EMPLOYEE_LEGAJO",
        source="employee_legajo",
        apply_to_all_pages=True,
    )

    with fitz.open(result["signed_pdf_path"]) as signed:
        seal_position = re.search(
            r"seal:employee:[^:]+:(\d+),(\d+);",
            signed.metadata.get("keywords", ""),
        )
        assert seal_position
        seal_x, seal_y = map(int, seal_position.groups())
        assert abs(seal_x + 135 - 250) <= 1
        assert abs(seal_y + 25 - (line_y - 30)) <= 1
        assert "Documento: Legajo de Personal" in signed[0].get_text()