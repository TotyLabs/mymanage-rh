from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import fitz

from services.employee_pdf_service import EmployeePDFService


def make_employee_pdf(
    include_termination_notice=False,
    family_members=None,
    include_pages=None,
    city="CABA",
    file_number="101",
    legacy_legajo_number=None,
    section_locality=None,
    document_type=None,
    pension_regime=None,
    retirement_plan=None,
    ieric_number=None,
    ieric_delivery_status=None,
    union="SINDICATO",
    union_voluntary="si",
):
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
        city=city,
        province="CABA",
        postal_code="1224",
        floor="3",
        apartment="B",
        tower="",
        file_number=file_number,
        legajo_number=legacy_legajo_number,
        document_type=document_type,
        pension_regime=pension_regime,
        ieric_number=ieric_number,
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
        union=union,
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
                "union_voluntary": union_voluntary,
                "retirement_plan": retirement_plan,
                "ieric_delivery_status": ieric_delivery_status,
                "section_locality": section_locality,
            },
        },
    )
    org = SimpleNamespace(name="Mi Empresa", logo_path=None)

    db.execute.side_effect = [
        MagicMock(fetchone=MagicMock(return_value=employee)),
        MagicMock(fetchone=MagicMock(return_value=org)),
    ]

    pdf_bytes = EmployeePDFService(db).generate_record_pdf(
        "emp-1",
        "org-1",
        include_termination_notice=include_termination_notice,
        include_pages=include_pages,
    )
    return fitz.open(stream=pdf_bytes, filetype="pdf")


def test_legajo_uses_new_template_and_populates_employee_data():
    pdf = make_employee_pdf()

    assert len(pdf) == 6
    assert pdf[0].rect.width == 612
    assert pdf[0].rect.height == 792
    assert "FICHA DE INGRESO" in pdf[0].get_text()
    assert "Secundario" in pdf[0].get_text()
    assert "Lucía García" in pdf[1].get_text()
    assert "27301234569" in pdf[1].get_text()
    assert "DECLARACIÓN DE DOMICILIO" in pdf[3].get_text()
    assert "Hurlingham" not in " ".join(page.get_text() for page in pdf)
    assert "SI" in pdf[5].get_text()
    assert "Me notifico del despido precedente" not in " ".join(page.get_text() for page in pdf)


def test_legajo_number_box_bottom_border_is_not_erased_by_field_values():
    pdf = make_employee_pdf()
    pixmap = pdf[0].get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
    x_start, x_end = 476 * 2, 586 * 2
    y_start, y_end = 89 * 2, 93 * 2
    dark_pixels = sum(
        max(pixmap.pixel(x, y)) < 180
        for y in range(y_start, y_end)
        for x in range(x_start, x_end)
    )

    assert dark_pixels > 300


def test_legajo_prints_employee_locality_consistently_on_repeated_pages():
    pdf = make_employee_pdf(city="Hurlingham")
    locality_occurrences = sum(page.get_text().count("Hurlingham") for page in pdf)

    assert locality_occurrences == 3


def test_legajo_uses_section_locality_when_company_provides_a_distinct_value():
    pdf = make_employee_pdf(city="Villa Celina", section_locality="Obra Localidad")

    assert pdf[0].get_text().count("Villa Celina") == 1
    assert "Obra Localidad" in pdf[0].get_text()
    assert "Villa Celina" in pdf[3].get_text()


def test_domicile_declaration_draws_original_street_sketch_instead_of_empty_box():
    from services.employee_legajo_template import EmployeeLegajoTemplate

    canvas = MagicMock()
    EmployeeLegajoTemplate._domicile_sketch(canvas, 190, 232, 232, 150)

    assert canvas.line.call_count == 20
    assert canvas.rect.call_count == 0
    canvas.line.assert_any_call(238.72, 548.0, 257.28, 548.0)
    canvas.line.assert_any_call(257.28, 522.5, 389.52, 522.5)


def test_legajo_checks_dni_for_common_document_type_variants(monkeypatch):
    from services.employee_legajo_template import EmployeeLegajoTemplate

    checked_boxes = []
    original_checkbox = EmployeeLegajoTemplate._checkbox

    def capture_checkbox(self, pdf, x, top, label, checked=False, size=8):
        if label == "DNI":
            checked_boxes.append(checked)
        return original_checkbox(self, pdf, x, top, label, checked, size)

    monkeypatch.setattr(EmployeeLegajoTemplate, "_checkbox", capture_checkbox)
    make_employee_pdf(document_type=" Documento Nacional de Identidad ")

    assert checked_boxes[0] is True
    assert checked_boxes.count(True) == 1


def test_legajo_normalizes_previsional_ieric_and_union_checkbox_values(monkeypatch):
    from services.employee_legajo_template import EmployeeLegajoTemplate

    checked_boxes = []
    original_checkbox = EmployeeLegajoTemplate._checkbox

    def capture_checkbox(self, pdf, x, top, label, checked=False, size=8):
        if label in {
            "Reparto", "Capitalización", "A Tramitar", "A Entregar",
            "Entregada", "SI", "NO",
        }:
            checked_boxes.append((label, checked))
        return original_checkbox(self, pdf, x, top, label, checked, size)

    monkeypatch.setattr(EmployeeLegajoTemplate, "_checkbox", capture_checkbox)
    pdf = make_employee_pdf(
        retirement_plan="AFJP",
        pension_regime="",
        ieric_number="9876543210",
        ieric_delivery_status=" A ENTREGAR ",
        union="UOCRA",
        union_voluntary=None,
    )
    selections = dict(checked_boxes)

    assert selections["Capitalización"] is True
    assert selections["Reparto"] is False
    assert selections["A Entregar"] is True
    assert selections["A Tramitar"] is False
    assert selections["Entregada"] is False
    assert selections["SI"] is True
    assert selections["NO"] is False
    assert "9876543210" in pdf[0].get_text()
    assert "UOCRA" in pdf[5].get_text()

    checked_boxes.clear()
    make_employee_pdf(pension_regime="SIPA", retirement_plan=None, union_voluntary="no")
    legacy_selections = dict(checked_boxes)
    assert legacy_selections["Reparto"] is True
    assert legacy_selections["Capitalización"] is False


def test_legajo_honors_explicit_no_for_union_authorization(monkeypatch):
    from services.employee_legajo_template import EmployeeLegajoTemplate

    checked_boxes = []
    original_checkbox = EmployeeLegajoTemplate._checkbox

    def capture_checkbox(self, pdf, x, top, label, checked=False, size=8):
        if label in {"SI", "NO"}:
            checked_boxes.append((label, checked))
        return original_checkbox(self, pdf, x, top, label, checked, size)

    monkeypatch.setattr(EmployeeLegajoTemplate, "_checkbox", capture_checkbox)
    make_employee_pdf(union="UOCRA", union_voluntary=" NO ")

    assert ("SI", False) in checked_boxes
    assert ("NO", True) in checked_boxes


def test_legajo_prefers_canonical_file_number_and_falls_back_to_historical_number():
    canonical = make_employee_pdf(file_number="101", legacy_legajo_number="202")
    historical_fallback = make_employee_pdf(file_number=None, legacy_legajo_number="202")

    def printed_legajo_number(pdf):
        page_text = pdf[0].get_text()
        legajo_field = page_text.split("LEG N°:", 1)[1]
        return legajo_field.splitlines()[1].strip()

    assert printed_legajo_number(canonical) == "101"
    assert printed_legajo_number(historical_fallback) == "202"
    assert "LEG N°:" not in canonical[5].get_text()


def test_optional_legajo_pages_can_be_selected_independently():
    base = make_employee_pdf()
    clothing = make_employee_pdf(include_pages=["clothing"])
    booklet = make_employee_pdf(include_pages=["unemployment_booklet"])
    both = make_employee_pdf(include_pages=["clothing", "unemployment_booklet"])

    assert len(base) == 6
    assert "CONSTANCIA DE ENTREGA DE ROPA DE TRABAJO" not in " ".join(page.get_text() for page in base)
    assert "ENTREGA DE LIBRETA DE FONDO DE DESEMPLEO" not in " ".join(page.get_text() for page in base)

    assert len(clothing) == 7
    assert "CONSTANCIA DE ENTREGA DE ROPA DE TRABAJO" in clothing[5].get_text()
    assert "01/01/2026" in clothing[5].get_text()
    assert "31/12/2026" in clothing[5].get_text()
    assert "ENTREGA DE LIBRETA DE FONDO DE DESEMPLEO" not in " ".join(page.get_text() for page in clothing)

    assert len(booklet) == 7
    assert "ENTREGA DE LIBRETA DE FONDO DE DESEMPLEO" in booklet[5].get_text()
    assert "CONSTANCIA DE ENTREGA DE ROPA DE TRABAJO" not in " ".join(page.get_text() for page in booklet)

    assert len(both) == 8
    assert "CONSTANCIA DE ENTREGA DE ROPA DE TRABAJO" in both[5].get_text()
    assert "ENTREGA DE LIBRETA DE FONDO DE DESEMPLEO" in both[6].get_text()
    assert "SI" in both[7].get_text()


def test_legajo_rejects_unknown_or_duplicate_optional_pages():
    from services.employee_legajo_template import EmployeeLegajoTemplate

    employee = SimpleNamespace(extra_fields={})
    organization = SimpleNamespace(name="Mi Empresa")

    for pages, expected_error in (
        (["invalid"], "invalid_optional_legajo_page"),
        (["clothing", "clothing"], "duplicate_optional_legajo_page"),
    ):
        try:
            EmployeeLegajoTemplate(employee, organization, include_pages=pages)
        except ValueError as error:
            assert str(error) == expected_error
        else:
            raise AssertionError(f"Expected {expected_error}")


def test_termination_notice_is_only_added_when_explicitly_requested():
    pdf = make_employee_pdf(include_termination_notice=True)

    assert len(pdf) == 7
    assert "Me notifico del despido precedente" in pdf[6].get_text()


def test_legajo_keeps_two_family_sheets_and_adds_pages_for_more_members():
    no_members = make_employee_pdf(family_members=[])
    three_members = make_employee_pdf(family_members=[
        {"nombre": "Familiar Uno"},
        {"nombre": "Familiar Dos"},
        {"nombre": "Familiar Tres"},
    ])

    assert len(no_members) == 6
    assert "ASIGNACIONES FAMILIARES" in no_members[1].get_text()
    assert "ASIGNACIONES FAMILIARES" in no_members[2].get_text()
    assert len(three_members) == 7
    assert "Familiar Tres" in three_members[3].get_text()
