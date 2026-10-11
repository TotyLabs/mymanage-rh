from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

from services.employee_pdf_service import EmployeePDFService


def test_employee_pdf_includes_legal_pages():
    db = MagicMock()
    employee = SimpleNamespace(
        id="emp-1",
        organization_id="org-1",
        first_name="Ana",
        last_name="García",
        dni="30123456",
        cuil="20301234567",
        birth_date=None,
        email="ana@example.com",
        phone="1122334455",
        address="Belgrano",
        address_number="1234",
        city="CABA",
        province="CABA",
        postal_code="1224",
        floor="3",
        apartment="B",
        tower="",
        file_number="101",
        hire_date=date(2023, 1, 10),
        job_title="Administrativa",
        hire_type="permanente",
        work_location="Oficina Central",
        cost_center="CC-1",
        health_insurance="OSDE",
        bank="Macro",
        account_type="Cuenta corriente",
        account_number="123",
        cbu="1234567890123456789012",
        bank_alias="ana.garcia",
        payment_method="transferencia",
        union="SINDICATO",
        union_number="456",
    )
    org = SimpleNamespace(name="Mi Empresa", logo_path=None)

    db.execute.side_effect = [
        MagicMock(fetchone=MagicMock(return_value=employee)),
        MagicMock(fetchone=MagicMock(return_value=org)),
    ]

    pdf_bytes = EmployeePDFService(db).generate_record_pdf("emp-1", "org-1")

    assert pdf_bytes
    assert pdf_bytes.count(b"/Type /Page") >= 5


def test_legal_pages_include_family_and_clothing_data():
    employee = SimpleNamespace(
        first_name="Ana",
        last_name="García",
        dni="30123456",
        work_location="Obra Central",
        union="SINDICATO",
        union_number="456",
        union_member_number="789",
        extra_fields={
            "family_members": [{
                "vinculo": "Hija",
                "cuil": "27301234569",
                "documento": "DNI 45123456",
                "nombre": "Lucía García",
                "fecha_nacimiento": "2015-04-03",
                "nivel_escolar": "Primario",
                "documentacion": "Partida de nacimiento",
            }],
            "ropa_trabajo": {
                "desde": "2026-01-01",
                "hasta": "2026-06-30",
                "vencimiento": "2026-06-30",
                "proximo_vencimiento": "2026-12-31",
            },
        },
    )
    service = EmployeePDFService(MagicMock())

    def collect_text(value):
        if isinstance(value, (list, tuple)):
            return " ".join(collect_text(item) for item in value)
        if hasattr(value, "getPlainText"):
            return value.getPlainText()
        if hasattr(value, "_cellvalues"):
            return collect_text(value._cellvalues)
        return ""

    family_text = collect_text(service._build_family_page(employee))
    clothing_text = collect_text(service._build_ropa_page(employee))

    assert "Lucía García" in family_text
    assert "27301234569" in family_text
    assert "01/01/2026" in clothing_text
    assert "31/12/2026" in clothing_text
