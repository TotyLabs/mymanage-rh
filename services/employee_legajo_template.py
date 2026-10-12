import base64
import io
import json
import re
import unicodedata
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path

from bs4 import BeautifulSoup
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas


TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "Modelos Laborales" / "nuevo_legajo.html"
PAGE_WIDTH, PAGE_HEIGHT = letter
CONTENT_LEFT = 40
CONTENT_RIGHT = 572
CONTENT_WIDTH = CONTENT_RIGHT - CONTENT_LEFT


@lru_cache(maxsize=1)
def _template_backgrounds() -> dict[int, bytes]:
    soup = BeautifulSoup(TEMPLATE_PATH.read_text(encoding="utf-8"), "html.parser")
    backgrounds = {}
    for page_number in range(1, 10):
        page = soup.find("div", id=f"pf{page_number}")
        image = page.select_one("img.bi") if page else None
        source = image.get("src", "") if image else ""
        if source.startswith("data:image/png;base64,"):
            backgrounds[page_number] = base64.b64decode(source.partition(",")[2])
    return backgrounds


class EmployeeLegajoTemplate:
    OPTIONAL_PAGES = {
        "clothing": "_clothing_page",
        "unemployment_booklet": "_unemployment_booklet_page",
    }

    def __init__(self, employee, organization, include_termination_notice=False, include_pages=None):
        self.employee = employee
        self.organization = organization
        self.extra = self._mapping(getattr(employee, "extra_fields", {}))
        self.data = self._mapping(self.extra.get("nuevo_legajo", {}))
        self.clothing = self._mapping(self.extra.get("ropa_trabajo", {}))
        self.family = self._family_members()
        self.today = date.today()
        self.include_termination_notice = include_termination_notice
        self.include_pages = tuple(include_pages or ())
        if len(self.include_pages) != len(set(self.include_pages)):
            raise ValueError("duplicate_optional_legajo_page")
        unknown_pages = set(self.include_pages) - self.OPTIONAL_PAGES.keys()
        if unknown_pages:
            raise ValueError("invalid_optional_legajo_page")

    @staticmethod
    def _mapping(value):
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (TypeError, ValueError):
                return {}
        return value if isinstance(value, dict) else {}

    def _value(self, name, fallback=""):
        value = getattr(self.employee, name, None)
        return self._safe(value if value not in (None, "") else fallback)

    @staticmethod
    def _safe(value, placeholder=""):
        if value is None:
            return placeholder
        if isinstance(value, (date, datetime)):
            return value.strftime("%d/%m/%Y")
        return str(value).strip() or placeholder

    @staticmethod
    def _date(value):
        if not value:
            return ""
        if isinstance(value, (date, datetime)):
            return value.strftime("%d/%m/%Y")
        raw = str(value).strip()
        try:
            return datetime.strptime(raw[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
        except ValueError:
            return raw

    def _employee_name(self):
        return " ".join(part for part in (self._value("last_name"), self._value("first_name")) if part)

    def _marital_status(self):
        labels = {
            "single": "Soltero/a",
            "married": "Casado/a",
            "divorced": "Divorciado/a",
            "widowed": "Viudo/a",
        }
        value = self._value("marital_status")
        return labels.get(value.lower(), value)

    @staticmethod
    def _choice_key(value):
        normalized = unicodedata.normalize("NFKD", str(value or ""))
        normalized = normalized.encode("ascii", "ignore").decode("ascii").upper()
        return re.sub(r"[^A-Z0-9]+", "_", normalized).strip("_").lower()

    @classmethod
    def _document_type_key(cls, value):
        key = cls._choice_key(value).upper()
        aliases = {
            "DOCUMENTO_NACIONAL_DE_IDENTIDAD": "DNI",
            "CEDULA_DE_IDENTIDAD": "CI",
            "CEDULA_IDENTIDAD": "CI",
            "LIBRETA_CIVICA": "LC",
            "LIBRETA_DE_ENROLAMIENTO": "LE",
            "PASSPORT": "PASAPORTE",
            "CERTIFICADO_MIGRATORIO": "CERT_MIGRATORIO",
            "CERTIFICADO_DE_MIGRACION": "CERT_MIGRATORIO",
            "CERT_MIGRATORIO": "CERT_MIGRATORIO",
        }
        return aliases.get(key, key)

    def _company_name(self):
        return self._safe(getattr(self.organization, "name", "EMPRESA"), "EMPRESA").upper()

    def _family_members(self):
        members = self.extra.get("family_members", [])
        if isinstance(members, dict) and "value" in members:
            members = members["value"]
        return [member for member in members if isinstance(member, dict)] if isinstance(members, list) else []

    @staticmethod
    def _domicile_sketch(pdf, x, top, width, height):
        def line(x1, y1, x2, y2):
            pdf.line(
                x + x1 * width,
                PAGE_HEIGHT - top - y1 * height,
                x + x2 * width,
                PAGE_HEIGHT - top - y2 * height,
            )

        pdf.saveState()
        pdf.setStrokeColorRGB(0.35, 0.35, 0.35)
        pdf.setLineWidth(0.8)

        # Central block and the interrupted outlines of the surrounding blocks form the map.
        for segment in (
            (0.21, 0.08, 0.29, 0.08),
            (0.29, 0.08, 0.29, 0.22),
            (0.39, 0.08, 0.86, 0.08),
            (0.86, 0.08, 0.86, 0.22),
            (0.21, 0.92, 0.29, 0.92),
            (0.29, 0.78, 0.29, 0.92),
            (0.39, 0.92, 0.86, 0.92),
            (0.86, 0.78, 0.86, 0.92),
            (0.08, 0.14, 0.08, 0.22),
            (0.08, 0.22, 0.19, 0.22),
            (0.08, 0.35, 0.08, 0.78),
            (0.08, 0.78, 0.19, 0.78),
            (0.92, 0.14, 0.92, 0.22),
            (0.81, 0.22, 0.92, 0.22),
            (0.92, 0.35, 0.92, 0.78),
            (0.81, 0.78, 0.92, 0.78),
            (0.29, 0.25, 0.86, 0.25),
            (0.29, 0.25, 0.29, 0.75),
            (0.86, 0.25, 0.86, 0.75),
            (0.29, 0.75, 0.86, 0.75),
        ):
            line(*segment)

        pdf.restoreState()

    def _background(self, pdf, page_number):
        raw = _template_backgrounds().get(page_number)
        if raw:
            pdf.drawImage(ImageReader(io.BytesIO(raw)), 0, 0, width=PAGE_WIDTH, height=PAGE_HEIGHT)
            pdf.saveState()
            pdf.setFillColorRGB(1, 1, 1)
            pdf.rect(29, 29, PAGE_WIDTH - 58, PAGE_HEIGHT - 58, fill=1, stroke=0)
            pdf.restoreState()

    @staticmethod
    def _draw_text(pdf, x, top, value, size=10, bold=False, width=None, align="left"):
        value = str(value or "")
        font = "Times-Bold" if bold else "Times-Roman"
        if width is not None:
            while size > 6 and stringWidth(value, font, size) > width:
                size -= 0.25
        pdf.setFont(font, size)
        baseline = PAGE_HEIGHT - top - size
        if align == "center":
            pdf.drawCentredString(x, baseline, value)
        elif align == "right":
            pdf.drawRightString(x, baseline, value)
        else:
            pdf.drawString(x, baseline, value)

    def _field(self, pdf, x, top, label, value, width, size=10, bold=False):
        font = "Times-Bold" if bold else "Times-Roman"
        label_width = stringWidth(label, font, size)
        value_x = x + label_width + 4
        value_width = max(8, width - label_width - 4)
        self._draw_text(pdf, x, top, label, size, bold)
        dot_width = stringWidth(".", "Times-Roman", size)
        dots = "." * max(3, int(value_width / max(dot_width, 1)))
        self._draw_text(pdf, value_x, top, dots, size, width=value_width)
        clean_value = self._safe(value)
        if clean_value:
            fitted_size = size
            while fitted_size > 6 and stringWidth(clean_value, "Times-Roman", fitted_size) > value_width - 2:
                fitted_size -= 0.25
            pdf.saveState()
            pdf.setFillColorRGB(1, 1, 1)
            pdf.rect(value_x - 1, PAGE_HEIGHT - top - size - 1, value_width + 1, size + 3, fill=1, stroke=0)
            pdf.restoreState()
            self._draw_text(pdf, value_x, top, clean_value, fitted_size, width=value_width - 2)

    def _section_title(self, pdf, text, top, boxed=False):
        if boxed:
            pdf.setLineWidth(1.1)
            box_width = stringWidth(text, "Times-Bold", 11) + 20
            x = (PAGE_WIDTH - box_width) / 2
            pdf.rect(x, PAGE_HEIGHT - top - 15, box_width, 18, stroke=1, fill=0)
            pdf.rect(x + 2, PAGE_HEIGHT - top - 13, box_width - 4, 14, stroke=1, fill=0)
            self._draw_text(pdf, PAGE_WIDTH / 2, top + 2, text, 11, bold=True, align="center")
        else:
            self._draw_text(pdf, PAGE_WIDTH / 2, top, text, 12, bold=True, align="center")

    def _date_line(self, pdf, top, city="Buenos Aires"):
        month = self.today.strftime("%m/%Y")
        self._draw_text(pdf, CONTENT_RIGHT, top, f"{city}, {self.today.day:02d}/{month}", 10, align="right")

    def _paragraph(self, pdf, x, top, text, width=CONTENT_WIDTH, size=9, leading=12, bold=False):
        font = "Times-Bold" if bold else "Times-Roman"
        lines = simpleSplit(str(text), font, size, width)
        for index, line in enumerate(lines):
            self._draw_text(pdf, x, top + index * leading, line, size, bold)
        return top + len(lines) * leading

    def _checkbox(self, pdf, x, top, label, checked=False, size=9):
        box = 8
        pdf.setLineWidth(0.8)
        pdf.rect(x, PAGE_HEIGHT - top - box, box, box, stroke=1, fill=0)
        if checked:
            pdf.setLineWidth(1.2)
            pdf.line(x + 1.5, PAGE_HEIGHT - top - 4, x + 3.3, PAGE_HEIGHT - top - 6.5)
            pdf.line(x + 3.3, PAGE_HEIGHT - top - 6.5, x + 7, PAGE_HEIGHT - top - 1.5)
        self._draw_text(pdf, x + box + 4, top - 1, label, size)

    def _signature(self, pdf, x, top, width, label):
        pdf.setLineWidth(0.7)
        pdf.line(x, PAGE_HEIGHT - top, x + width, PAGE_HEIGHT - top)
        self._draw_text(pdf, x, top + 4, label, 9, bold=True)

    def _page_one(self, pdf):
        self._background(pdf, 1)
        legajo_number = self._value("file_number") or self._value("legajo_number", self.extra.get("legajo_number"))
        self._draw_text(pdf, 484, 34, "LEG N°:", 9, bold=True)
        self._draw_text(pdf, 531, 52, legajo_number, 11, bold=True, align="center")
        self._draw_text(pdf, PAGE_WIDTH / 2, 32, "FICHA DE INGRESO", 14, bold=True, align="center")
        self._section_title(pdf, "DATOS PERSONALES DEL TRABAJADOR", 62, boxed=True)
        self._field(pdf, 42, 88, "Apellido:", self._value("last_name"), 245)
        self._field(pdf, 310, 88, "Nombre:", self._value("first_name"), 255)
        self._field(pdf, 42, 111, "Domicilio:", self._value("address"), 370)
        self._field(pdf, 423, 111, "N°:", self._value("address_number"), 145)
        self._field(pdf, 42, 134, "Piso:", self._value("floor", self.extra.get("floor")), 94)
        self._field(pdf, 142, 134, "Depto:", self._value("apartment", self.extra.get("apartment")), 100)
        self._field(pdf, 248, 134, "C. Postal:", self._value("postal_code"), 115)
        self._field(pdf, 370, 134, "Localidad:", self._value("city"), 198)
        self._field(pdf, 42, 157, "Teléfono:", self._value("phone"), 165)
        self._field(pdf, 220, 157, "Estado Civil:", self._marital_status(), 160)
        self._field(pdf, 390, 157, "Nacionalidad:", self._value("nationality"), 178)
        self._field(pdf, 42, 180, "F. Nacimiento:", self._date(getattr(self.employee, "birth_date", None)), 165)
        self._field(pdf, 220, 180, "Estudios cursados:", self.data.get("studies_completed"), 348)
        self._draw_text(pdf, 245, 194, "(en caso de estudios incompletos, informar último grado/año cursado)", 7)
        doc_type = self._document_type_key(self._value("document_type", "DNI"))
        self._draw_text(pdf, 42, 216, "Tipo de Documento:", 10, bold=True)
        doc_types = [("DNI", 153), ("CI", 207), ("LC", 238), ("LE", 269), ("Pasaporte", 301), ("Cert. Migratorio", 378)]
        for option, x in doc_types:
            option_key = self._document_type_key(option)
            self._checkbox(pdf, x, 216, option, checked=doc_type == option_key, size=8)
        self._field(pdf, 42, 240, "N° de Documento:", self._value("document_number") or self._value("dni"), 270)
        self._field(pdf, 324, 240, "N° Expediente:", self.data.get("document_expediente"), 244)

        self._section_title(pdf, "DATOS LABORALES DEL TRABAJADOR", 274, boxed=True)
        cuil = self._value("cuil")
        if len(cuil) == 11 and cuil.isdigit():
            cuil = f"{cuil[:2]}-{cuil[2:10]}-{cuil[10]}"
        self._field(pdf, 42, 302, "N° de C.U.I.T./C.U.I.L.:", cuil, 335)
        self._field(pdf, 386, 302, "F. Ingreso:", self._date(getattr(self.employee, "hire_date", None)), 182)
        self._field(pdf, 42, 325, "Categoría:", self._value("category"), 260)
        self._field(pdf, 316, 325, "Tarea:", self._value("task"), 252)
        self._field(pdf, 42, 348, "Sección:", self._value("work_location"), 526)
        self._field(pdf, 42, 371, "Domicilio Sección:", self.data.get("section_address"), 360)
        section_locality = self.data.get("section_locality") or self._value("city")
        self._field(pdf, 412, 371, "Localidad:", section_locality, 160)

        self._section_title(pdf, "INSCRIPCIONES", 398, boxed=True)
        plan = self._choice_key(self.data.get("retirement_plan") or self._value("pension_regime"))
        plan = {
            "afjp": "capitalizacion",
            "sipa": "reparto",
            "sistema_integrado_previsional_argentino": "reparto",
            "sistema_de_reparto": "reparto",
        }.get(plan, plan)
        self._draw_text(pdf, 42, 426, "Régimen Previsional:", 10, bold=True)
        self._checkbox(pdf, 184, 426, "Reparto", checked=plan == "reparto")
        self._checkbox(pdf, 267, 426, "Capitalización", checked=plan == "capitalizacion")
        self._field(pdf, 355, 426, "AFJP:", self.data.get("afjp"), 217)
        self._field(pdf, 42, 449, "Obra Social:", self._value("health_insurance"), 390)
        self._field(pdf, 442, 449, "Código:", self.data.get("health_insurance_code"), 130)
        self._field(pdf, 42, 472, "N° Cta. Bancaria:", self._value("account_number"), 260)
        self._field(pdf, 312, 472, "C.B.U.:", self._value("cbu"), 260)
        self._field(pdf, 42, 495, "Libreta Fdo. Desempleo N°:", self.data.get("booklet_number") or self._value("unemployment_fund_account"), 300)
        ieric_number = (
            self._value("ieric_number")
            or self._value("card_number", self.extra.get("card_number"))
        )
        self._field(pdf, 354, 495, "Tarjeta IERIC:", ieric_number, 218)
        ieric_state = self._choice_key(self.data.get("ieric_delivery_status"))
        ieric_state = {
            "entregado": "entregada",
            "entrega": "entregada",
        }.get(ieric_state, ieric_state)
        for label, x, value in (("A Tramitar", 42, "a_tramitar"), ("A Entregar", 198, "a_entregar"), ("Entregada", 354, "entregada")):
            self._checkbox(pdf, x, 516, label, checked=ieric_state == value)

        pdf.setLineWidth(1.1)
        pdf.rect(34, PAGE_HEIGHT - 612 - 42, 532, 42, fill=0, stroke=1)
        self._paragraph(
            pdf, 47, 619,
            "Dejo constancia que los datos que figuran en la presente son correctos, comprometiéndome a comunicar cualquier modificación. Declaro bajo juramento no ser beneficiario de jubilación, pensión, retiro o prestación no contributiva. Asimismo me comprometo a presentar la Libreta de Aportes Patronales al Fondo de Desempleo o proporcionar los datos necesarios para su inscripción.",
            width=CONTENT_WIDTH - 26, size=6.5, leading=8,
        )
        self._signature(pdf, 352, 718, 215, "Firma Trabajador/a")
        pdf.setLineWidth(0.6)
        pdf.rect(476, PAGE_HEIGHT - 27 - 64, 110, 64, fill=0, stroke=1)
        pdf.showPage()

    def _family_page(self, pdf, page_number, member):
        self._background(pdf, page_number)
        self._section_title(pdf, "ASIGNACIONES FAMILIARES", 42)
        self._draw_text(pdf, CONTENT_LEFT, 78, f"{page_number - 1})", 10, bold=True)
        self._field(pdf, 60, 78, "Vínculo:", member.get("vinculo"), 260)
        self._field(pdf, 330, 78, "C.U.I.L.:", member.get("cuil"), 238)
        self._field(pdf, 42, 106, "Tipo y N° Documento:", member.get("documento"), 526)
        self._field(pdf, 42, 134, "Apellido y Nombre:", member.get("nombre"), 390)
        self._field(pdf, 442, 134, "F. Nac.:", self._date(member.get("fecha_nacimiento")), 126)
        self._field(pdf, 42, 162, "Documentación Entregada:", member.get("documentacion"), 526)
        self._field(pdf, 42, 190, "T°:", member.get("t"), 110)
        self._field(pdf, 166, 190, "F°:", member.get("f"), 110)
        self._field(pdf, 290, 190, "ACTA:", member.get("acta"), 278)
        self._field(pdf, 42, 218, "Nivel Escolar:", member.get("nivel_escolar"), 526)
        self._paragraph(
            pdf, 42, 277,
            "Me responsabilizo de la exactitud de los datos arriba mencionados, me comprometo a desempeñar con eficiencia mis tareas y a cumplir los reglamentos en vigencia, así como también a entregar la documentación requerida por la empresa en un plazo no mayor de sesenta (60) días.",
            width=CONTENT_WIDTH, size=9, leading=13,
        )
        self._signature(pdf, 205, 660, 205, "Firma del Trabajador/a")
        pdf.showPage()

    def _domicile_page(self, pdf):
        self._background(pdf, 4)
        self._section_title(pdf, "DECLARACIÓN DE DOMICILIO", 36)
        self._field(pdf, 42, 75, "Empresa:", self._company_name(), 526)
        self._field(pdf, 42, 102, "Apellido y Nombre del Trabajador:", self._employee_name(), 526, size=9)
        self._draw_text(pdf, 42, 133, "Declaro que mi domicilio actual se encuentra situado en:", 10)
        self._field(pdf, 42, 158, "Calle:", self._value("address"), 278)
        self._field(pdf, 326, 158, "N°:", self._value("address_number"), 86)
        self._field(pdf, 418, 158, "Piso:", self._value("floor", self.extra.get("floor")), 74)
        self._field(pdf, 498, 158, "Dpto:", self._value("apartment", self.extra.get("apartment")), 70)
        self._field(pdf, 42, 183, "Código Postal:", self._value("postal_code"), 140)
        self._field(pdf, 190, 183, "Localidad:", self._value("city"), 250)
        self._field(pdf, 448, 183, "Prov:", self._value("province"), 120)
        self._domicile_sketch(pdf, 190, 232, 232, 150)
        self._paragraph(
            pdf, 42, 420,
            "DECLARO QUE EL DOMICILIO CONSIGNADO ES CORRECTO Y QUE SE DEBERÁ TOMAR COMO VÁLIDO PARA TODOS LOS EFECTOS LEGALES, COMPROMETIÉNDOME A INFORMAR CUALQUIER CAMBIO FUTURO QUE SE PRODUZCA SOBRE EL MISMO.",
            width=CONTENT_WIDTH, size=10, leading=14,
        )
        self._signature(pdf, 42, 575, 280, "Firma del Trabajador:")
        self._signature(pdf, 42, 620, 280, "Aclaración:")
        self._signature(pdf, 42, 665, 280, "D.N.I.:")
        pdf.showPage()

    def _family_declaration_page(self, pdf):
        self._background(pdf, 5)
        self._date_line(pdf, 42)
        self._section_title(pdf, "REQUERIMIENTO INFORME CARGAS DE FAMILIA", 72)
        self._draw_text(pdf, 42, 122, "De nuestra mayor consideración:", 10)
        body = (
            "Por medio de la presente y de acuerdo a la Ley 22.161, Art. 2° inciso C, solicitamos que dentro de los diez días hábiles de su ingreso informe y/o denuncie su estado civil y cargas familiares, y presente las declaraciones juradas y toda otra documentación requerida. Vencido el plazo sin presentar la documentación necesaria para la percepción de las asignaciones familiares, se suspenderá su pago, que se reanudará una vez cumplido el requisito, sin derecho a retroactividad."
        )
        next_top = self._paragraph(pdf, 55, 158, body, width=CONTENT_WIDTH - 15, size=9, leading=13)
        next_top = self._paragraph(pdf, 42, next_top + 18, "Declaro bajo juramento que las cargas de familia detalladas en el presente legajo residen en:", size=9, leading=12)
        self._field(pdf, 42, next_top + 8, "", self.data.get("family_residence"), CONTENT_WIDTH, size=10)
        self._draw_text(pdf, 42, 385, "Quedando usted informado.", 10, bold=True)
        self._signature(pdf, 42, 620, 280, "Firma del Trabajador:")
        self._signature(pdf, 42, 650, 280, "Aclaración:")
        self._signature(pdf, 42, 680, 280, "D.N.I.:")
        pdf.showPage()

    def _clothing_page(self, pdf):
        self._background(pdf, 6)
        self._date_line(pdf, 42)
        self._section_title(pdf, "CONSTANCIA DE ENTREGA DE ROPA DE TRABAJO", 72)
        top = self._paragraph(pdf, 42, 116, "Por la presente declaro recibir en este acto de:", size=10)
        self._field(pdf, 250, 116, "", self._company_name(), 318)
        body = (
            "Un equipo completo de ropa que consta de pantalón y camisa de trabajo, botines y casco, con devolución al momento de la finalización de obra; de acuerdo a lo dispuesto en el Art. 35 del Convenio Colectivo de Trabajo N° 76/75, Art. 26 del mismo Convenio y la Resolución M.T. 98/86 para los trabajadores de la Industria de la Construcción."
        )
        self._paragraph(pdf, 42, top + 25, body, width=CONTENT_WIDTH, size=9, leading=15)
        self._draw_text(pdf, 42, 260, "Período de cumplimiento Art. 35 Conv. 76/75. Res. M.T. 98/86:", 10)
        self._field(pdf, 42, 286, "Desde:", self._date(self.clothing.get("desde")), 205, bold=True)
        self._field(pdf, 262, 286, "Hasta:", self._date(self.clothing.get("hasta")), 205, bold=True)
        self._field(pdf, 42, 314, "Vencimiento de la entrega:", self._date(self.clothing.get("vencimiento")), 340, bold=True)
        self._field(pdf, 42, 342, "Próximo vencimiento:", self._date(self.clothing.get("proximo_vencimiento")), 340, bold=True)
        self._draw_text(pdf, 42, 383, "Asimismo se deja constancia que el trabajador se compromete a usar los elementos recibidos.", 9)
        self._signature(pdf, 42, 440, 285, "Firma del Trabajador:")
        self._signature(pdf, 42, 468, 285, "Aclaración:")
        self._signature(pdf, 42, 496, 285, "Obra:")
        pdf.showPage()

    def _unemployment_booklet_page(self, pdf):
        self._background(pdf, 7)
        self._date_line(pdf, 42)
        self._section_title(pdf, "ENTREGA DE LIBRETA DE FONDO DE DESEMPLEO", 72)
        self._paragraph(pdf, 42, 130, "Por medio de la presente declaro bajo juramento recibir de:", size=10)
        self._field(pdf, 290, 130, "", self._company_name(), 278)
        booklet = self.data.get("booklet_number") or self._value("unemployment_fund_account")
        self._field(pdf, 42, 166, "N° en Registro de la Industria de la Construcción:", booklet, 526)
        self._field(pdf, 42, 194, "Rubricada el día:", self._date(self.data.get("booklet_rubric_date")), 260)
        self._paragraph(
            pdf, 42, 230,
            "Declaro recibir la libreta de Aportes Patronales con sus aportes y demás haberes correspondientes al día, dejando constancia que no se me adeuda importe alguno bajo ningún concepto.",
            width=CONTENT_WIDTH, size=10, leading=15,
        )
        self._signature(pdf, 42, 430, 300, "Firma del Trabajador:")
        self._signature(pdf, 42, 472, 300, "Aclaración:")
        self._signature(pdf, 42, 514, 300, "D.N.I.:")
        pdf.showPage()

    def _union_page(self, pdf):
        self._background(pdf, 8)
        self._date_line(pdf, 42)
        self._field(pdf, 42, 88, "Apellido y Nombre del Trabajador:", self._employee_name(), 526, size=9)
        self._draw_text(pdf, 42, 164, "Sr. Empleador:", 10)
        union = self._value("union")
        self._paragraph(
            pdf, 42, 205,
            f"Solicito se me efectúe el aporte sindical voluntario con destino al SINDICATO {union} que me representa, en razón de",
            width=CONTENT_WIDTH, size=10, leading=14,
        )
        authorization = self._choice_key(self.data.get("union_voluntary"))
        if not authorization and union:
            authorization = "si"
        self._checkbox(pdf, 42, 244, "SI", checked=authorization in ("si", "yes", "true", "1"), size=10)
        self._draw_text(pdf, 77, 244, "/", 10, bold=True)
        self._checkbox(pdf, 92, 244, "NO", checked=authorization in ("no", "false", "0"), size=10)
        self._draw_text(pdf, 124, 244, "encontrarme afiliado al mismo.", 10)
        self._signature(pdf, 42, 405, 300, "Firma del Trabajador:")
        self._signature(pdf, 42, 448, 300, "Aclaración:")
        self._signature(pdf, 42, 491, 300, "D.N.I.:")
        pdf.showPage()

    def _termination_page(self, pdf):
        self._background(pdf, 9)
        self._date_line(pdf, 42)
        self._field(pdf, 42, 93, "Sr.:", self._employee_name(), 526)
        self._field(pdf, 42, 122, "D.N.I.:", self._value("dni"), 300)
        self._paragraph(
            pdf, 42, 190,
            f"Por medio de la presente comunicamos a usted que a partir de la fecha {self._date(getattr(self.employee, 'termination_date', None))} prescindimos de sus servicios, como así también notificamos que se encuentran a su disposición los haberes y la Libreta de Fondo de Desempleo dentro de los plazos establecidos por la Ley 22.250.",
            width=CONTENT_WIDTH, size=10, leading=16,
        )
        self._signature(pdf, 42, 375, 300, "Firma del Empleador:")
        self._signature(pdf, 42, 418, 300, "Aclaración:")
        self._signature(pdf, 42, 461, 300, "D.N.I.:")
        self._draw_text(pdf, 42, 510, "Me notifico del despido precedente acusando recibo de la misma", 10)
        self._signature(pdf, 42, 583, 300, "Firma del Trabajador:")
        self._signature(pdf, 42, 626, 300, "Aclaración:")
        self._signature(pdf, 42, 669, 300, "D.N.I.:")
        pdf.showPage()

    def generate(self) -> bytes:
        if self.include_termination_notice and not getattr(self.employee, "termination_date", None):
            raise ValueError("termination_date_required")
        output = io.BytesIO()
        pdf = canvas.Canvas(output, pagesize=letter, pageCompression=1)
        pdf.setTitle(f"Legajo - {self._employee_name()}")
        pdf.setAuthor(self._company_name())
        self._page_one(pdf)
        for index, member in enumerate(self.family[:2], start=2):
            self._family_page(pdf, index, member)
        for page_number in range(len(self.family) + 2, 4):
            self._family_page(pdf, 3 if page_number == 3 else 2, {})
        for index, member in enumerate(self.family[2:], start=4):
            self._family_page(pdf, 3, member)
        self._domicile_page(pdf)
        self._family_declaration_page(pdf)
        for page_name in ("clothing", "unemployment_booklet"):
            if page_name in self.include_pages:
                getattr(self, self.OPTIONAL_PAGES[page_name])(pdf)
        self._union_page(pdf)
        if self.include_termination_notice:
            self._termination_page(pdf)
        pdf.save()
        return output.getvalue()
