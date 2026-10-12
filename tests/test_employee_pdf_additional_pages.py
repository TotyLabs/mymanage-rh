from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import fitz

from services.employee_pdf_service import EmployeePDFService


def make_employee_pdf(include_termination_notice=False, family_members=None):
    db = MagicMock()
    employee = SimpleNamespace(
        id="emp-1",
        organization_id="org-1",
        first_name="Ana",
        last_name="García",
        dni="30123456",
        cuil="20301234567",
        birth_date=date(1990, 4, 12),
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
        termination_date=date(2026, 10, 1),
        extra_fields={
            "family_members": family_members if family_members is not None else [{
                    "vinculo": "Hija",
                    "cuil": "27301234569",
                    "documento": "DNI 45123456",
                    "nombre": "Lucía García",
                    "fecha_nacimiento": "2015-04-03",
                    "documentacion": "Partida de nacimiento",
                    "nivel_escolar": "Primario",
                }],
            "ropa_trabajo": {
                "desde": "2026-01-01",
                "hasta": "2026-06-30",
                "vencimiento": "2026-06-30",
                "proximo_vencimiento": "2026-12-31",
            },
            "nuevo_legajo": {
                "studies_completed": "Secundario",
                "union_voluntary": "si",
            },
        },
    )
    org = SimpleNamespace(name="Mi Empresa", logo_path=None)

    db.execute.side_effect = [
        MagicMock(fetchone=MagicMock(return_value=employee)),
        MagicMock(fetchone=MagicMock(return_value=org)),
    ]

    pdf_bytes = EmployeePDFService(db).generate_record_pdf(
        "emp-1", "org-1", include_termination_notice=include_termination_notice
    )
    return fitz.open(stream=pdf_bytes, filetype="pdf")


def test_legajo_uses_new_template_and_populates_employee_data():
    pdf = make_employee_pdf()

    assert len(pdf) == 8
    assert pdf[0].rect.width == 612
    assert pdf[0].rect.height == 792
    assert "FICHA DE INGRESO" in pdf[0].get_text()
    assert "Secundario" in pdf[0].get_text()
    assert "Lucía García" in pdf[1].get_text()
    assert "27301234569" in pdf[1].get_text()
    assert "DECLARACIÓN DE DOMICILIO" in pdf[3].get_text()
    assert "CONSTANCIA DE ENTREGA DE ROPA DE TRABAJO" in pdf[5].get_text()
    assert "01/01/2026" in pdf[5].get_text()
    assert "31/12/2026" in pdf[5].get_text()
    assert "ENTREGA DE LIBRETA DE FONDO DE DESEMPLEO" in pdf[6].get_text()
    assert "SI" in pdf[7].get_text()
    assert "Me notifico del despido precedente" not in " ".join(page.get_text() for page in pdf)


def test_termination_notice_is_only_added_when_explicitly_requested():
    pdf = make_employee_pdf(include_termination_notice=True)

    assert len(pdf) == 9
    assert "Me notifico del despido precedente" in pdf[8].get_text()


def test_legajo_keeps_two_family_sheets_and_adds_pages_for_more_members():
    no_members = make_employee_pdf(family_members=[])
    three_members = make_employee_pdf(family_members=[
        {"nombre": "Familiar Uno"},
        {"nombre": "Familiar Dos"},
        {"nombre": "Familiar Tres"},
    ])

    assert len(no_members) == 8
    assert "ASIGNACIONES FAMILIARES" in no_members[1].get_text()
    assert "ASIGNACIONES FAMILIARES" in no_members[2].get_text()
    assert len(three_members) == 9
    assert "Familiar Tres" in three_members[3].get_text()
