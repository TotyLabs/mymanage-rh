import os
import io
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.units import cm
from sqlalchemy import text

class EmployeePDFService:
    def __init__(self, db):
        self.db = db
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()

    def _setup_custom_styles(self):
        # Paleta institucional corporativa (Negro Técnico, Gris Estructura y Slate Neutral)
        self.COLOR_TEXT_MAIN = colors.HexColor('#0f172a')  # Slate 900 (Valores de datos)
        self.COLOR_LABEL = colors.HexColor('#475569')      # Slate 600 (Etiquetas fijas)
        self.COLOR_BORDER = colors.HexColor('#94a3b8')     # Slate 400 (Bordes y líneas divisorias)
        self.COLOR_BG_BLOCK = colors.HexColor('#f8fafc')   # Slate 50 (Fondo sutil de datos)
        self.COLOR_BG_TITLE = colors.HexColor('#e2e8f0')   # Slate 200 (Fondo sólido de cabeceras de sección)

        self.styles.add(ParagraphStyle(
            name='CorpTitle',
            fontSize=14,
            leading=16,
            textColor=self.COLOR_TEXT_MAIN,
            fontName='Helvetica-Bold',
        ))
        self.styles.add(ParagraphStyle(
            name='CorpSubtitle',
            fontSize=10,
            leading=13,
            textColor=self.COLOR_LABEL,
            fontName='Helvetica-Bold',
        ))
        self.styles.add(ParagraphStyle(
            name='SectionHeaderTitle',
            fontSize=9.5,
            leading=12,
            textColor=self.COLOR_TEXT_MAIN,
            fontName='Helvetica-Bold',
        ))
        self.styles.add(ParagraphStyle(
            name='MetaLabel',
            fontSize=8,
            leading=10,
            textColor=self.COLOR_LABEL,
            fontName='Helvetica',
        ))
        self.styles.add(ParagraphStyle(
            name='MetaValue',
            fontSize=8,
            leading=10,
            textColor=self.COLOR_TEXT_MAIN,
            fontName='Helvetica-Bold',
        ))
        self.styles.add(ParagraphStyle(
            name='GridLabel',
            fontSize=8.5,
            leading=11,
            textColor=self.COLOR_LABEL,
            fontName='Helvetica',
        ))
        self.styles.add(ParagraphStyle(
            name='GridValue',
            fontSize=9,
            leading=12,
            textColor=self.COLOR_TEXT_MAIN,
            fontName='Helvetica-Bold',
        ))

    def _calculate_seniority_internal(self, hire_date) -> str:
        """Cálculo interno para evitar dependencias circulares con la API."""
        if not hire_date:
            return "n/a"
        from datetime import date
        today = date.today()
        years = today.year - hire_date.year
        months = today.month - hire_date.month
        if months < 0:
            years -= 1
            months += 12
        parts = []
        if years > 0:
            parts.append(f"{years} {'año' if years == 1 else 'años'}")
        if months > 0:
            parts.append(f"{months} {'mes' if months == 1 else 'meses'}")
        return ", ".join(parts) if parts else "Recién ingresado"

    def _create_matrix_section(self, title: str, data_items: list) -> Table:
        """Genera un bloque de sección estructurado en formato de matriz cerrada tipo ficha técnica."""
        title_p = Paragraph(title.upper(), self.styles['SectionHeaderTitle'])
        
        # Reorganizamos la data en pares para la grilla simétrica
        grid_rows = []
        for i in range(0, len(data_items), 2):
            chunk = data_items[i:i+2]
            row_cells = []
            for label, value in chunk:
                cell_content = [
                    Paragraph(f"<b>{label}:</b>", self.styles['GridLabel']),
                    Spacer(1, 2),
                    Paragraph(str(value) if value is not None and str(value).strip() != "" else "—", self.styles['GridValue'])
                ]
                row_cells.append(cell_content)
            if len(row_cells) < 2:
                row_cells.append([]) # Celda vacía de balanceo
            grid_rows.append(row_cells)

        full_table_data = [[title_p, '']]  # Fila de título colapsada
        for r in grid_rows:
            full_table_data.append(r)

        # Ancho exacto ampliado para márgenes optimizados de 1.2cm: 18.6 cm (9.3 cm por columna)
        matrix_table = Table(full_table_data, colWidths=[9.3*cm, 9.3*cm])
        
        t_style = [
            # Configuración de cabecera de sección (Esponjado sutil para llenar la hoja)
            ('SPAN', (0, 0), (1, 0)),
            ('BACKGROUND', (0, 0), (-1, 0), self.COLOR_BG_TITLE),
            ('TOPPADDING', (0, 0), (-1, 0), 6),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
            ('LEFTPADDING', (0, 0), (-1, 0), 8),
            
            # Configuración del cuerpo de datos
            ('VALIGN', (0, 1), (-1, -1), 'TOP'),
            ('BACKGROUND', (0, 1), (-1, -1), self.COLOR_BG_BLOCK),
            ('TOPPADDING', (0, 1), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
            ('LEFTPADDING', (0, 1), (-1, -1), 8),
            ('RIGHTPADDING', (0, 1), (-1, -1), 8),
            
            # Bordes exteriores e interiores
            ('BOX', (0, 0), (-1, -1), 1, self.COLOR_BORDER),
            ('LINEBELOW', (0, 0), (-1, 0), 1, self.COLOR_BORDER), 
            ('LINEBEFORE', (1, 1), (1, -1), 0.5, self.COLOR_BORDER), 
        ]
        
        for row_idx in range(1, len(full_table_data) - 1):
            t_style.append(('LINEBELOW', (0, row_idx), (-1, row_idx), 0.5, self.COLOR_BORDER))

        matrix_table.setStyle(TableStyle(t_style))
        return matrix_table

    def generate_record_pdf(self, employee_id: str, organization_id: str) -> bytes:
        emp = self.db.execute(
            text("SELECT * FROM employees WHERE id = :id AND organization_id = :org"),
            {"id": employee_id, "org": organization_id}
        ).fetchone()

        if not emp:
            raise ValueError("employee_not_found")

        org = self.db.execute(
            text("SELECT name, logo_path FROM organizations WHERE id = :id"),
            {"id": organization_id}
        ).fetchone()

        buffer = io.BytesIO()
        
        # Configuración optimizada de márgenes para forzar ocupación simétrica de 1 sola página
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=1.2*cm,
            leftMargin=1.2*cm,
            topMargin=1.2*cm,
            bottomMargin=1.2*cm
        )

        elements = []

        # ==========================================
        # HEADER MATRICIAL TÉCNICO
        # ==========================================
        logo = None
        if org and org.logo_path and os.path.exists(org.logo_path):
            try:
                logo = Image(org.logo_path, width=1.6*cm, height=1.6*cm, kind='proportional')
            except:
                logo = None
        
        title_block = [
            Paragraph(f"<b>{org.name.upper() if org else 'EMPRESA'}</b>", self.styles['CorpTitle']),
            Spacer(1, 3),
            Paragraph("FICHA DE REGISTRO / LEGAJO DE PERSONAL", self.styles['CorpSubtitle'])
        ]
        
        meta_table_data = [
            [Paragraph("Registro", self.styles['MetaLabel']), Paragraph("REG-RH-004", self.styles['MetaValue'])],
            [Paragraph("Versión", self.styles['MetaLabel']), Paragraph("1.2", self.styles['MetaValue'])],
            [Paragraph("Fecha", self.styles['MetaLabel']), Paragraph(datetime.now().strftime('%d/%m/%Y'), self.styles['MetaValue'])],
            [Paragraph("Página", self.styles['MetaLabel']), Paragraph("1 de 1", self.styles['MetaValue'])]
        ]
        meta_table = Table(meta_table_data, colWidths=[1.8*cm, 2.7*cm], rowHeights=[12, 12, 12, 12])
        meta_table.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BOX', (0,0), (-1,-1), 0.75, self.COLOR_BORDER),
            ('INNERGRID', (0,0), (-1,-1), 0.5, self.COLOR_BORDER),
            ('TOPPADDING', (0,0), (-1,-1), 2),
            ('BOTTOMPADDING', (0,0), (-1,-1), 2),
            ('LEFTPADDING', (0,0), (-1,-1), 5),
            ('RIGHTPADDING', (0,0), (-1,-1), 5),
            ('BACKGROUND', (0,0), (0,-1), self.COLOR_BG_BLOCK),
        ]))

        # Ajuste de ancho total a 18.6 cm para mantener simetría con el nuevo layout
        header_table = Table([[logo, title_block, meta_table]], colWidths=[2.2*cm, 11.9*cm, 4.5*cm])
        header_table.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('LEFTPADDING', (0,0), (-1,-1), 0),
            ('RIGHTPADDING', (0,0), (-1,-1), 0),
            ('BOTTOMPADDING', (0,0), (-1,-1), 8),
            ('LINEBELOW', (0,0), (-1,-1), 1.5, self.COLOR_TEXT_MAIN)
        ]))
        elements.append(header_table)
        elements.append(Spacer(1, 14))



        # ==========================================
        # BLOQUE 1: Datos Personales
        # ==========================================
        personal_data = [
            ("Apellido y Nombre", f"{emp.last_name or ''}, {emp.first_name or ''}".strip(", ")),
            ("Documento (DNI)", emp.dni),
            ("CUIL", emp.cuil),
            ("Fecha de Nacimiento", emp.birth_date.strftime('%d/%m/%Y') if emp.birth_date else "—"),
            ("Email", emp.email),
            ("Teléfono de Contacto", emp.phone),
            ("Domicilio", f"{emp.address or ''}{(' ' + emp.address_number) if emp.address_number else ''}".strip()),
            ("Localidad / Provincia", f"{emp.city or ''} {emp.province or ''}".strip())
        ]
        elements.append(self._create_matrix_section("Datos Personales", personal_data))
        elements.append(Spacer(1, 14))



        # ==========================================
        # BLOQUE 2: Datos Laborales
        # ==========================================
        # Tratamiento estricto anti-decimales para el Nro. de Legajo
        file_num_raw = emp.file_number
        if file_num_raw is not None:
            try:
                # Si es flotante o string convertible, remueve el ".0" transformándolo en entero puro
                file_number_clean = str(int(float(file_num_raw)))
            except (ValueError, TypeError):
                # Si contiene letras o caracteres especiales, lo expone tal como está en la DB
                file_number_clean = str(file_num_raw)
        else:
            file_number_clean = "—"

        seniority = self._calculate_seniority_internal(emp.hire_date)
        laboral_data = [
            ("Nro. Legajo Interno", file_number_clean),
            ("Fecha de Ingreso", emp.hire_date.strftime('%d/%m/%Y') if emp.hire_date else "—"),
            ("Puesto / Cargo", emp.job_title),
            ("Antigüedad", seniority),
            ("Tipo de Contrato", emp.hire_type),
            ("Sección", emp.work_location),
            ("Centro de Costos", emp.cost_center),
            ("Obra Social", emp.health_insurance)
        ]
        elements.append(self._create_matrix_section("Datos Laborales", laboral_data))
        elements.append(Spacer(1, 14))



        # ==========================================
        # BLOQUE 3: Datos Bancarios
        # ==========================================
        bank_data = [
            ("Entidad Bancaria", emp.bank),
            ("Tipo de Cuenta", emp.account_type),
            ("Número de Cuenta", emp.account_number),
            ("CBU", emp.cbu),
            ("Alias", emp.bank_alias),
            ("Forma de Pago", emp.payment_method)
        ]
        elements.append(self._create_matrix_section("Datos Bancarios", bank_data))

        # Espaciador incrementado con precisión para empujar el footer hacia la base de la hoja
        elements.append(Spacer(1, 45))



        # ==========================================
        # FOOTER: Área de Firma Técnica Unificada
        # ==========================================
        sig_data = [
            [""],
            [Paragraph("Firma del Empleado", self.styles['GridLabel'])],
            [Paragraph("Aclaración:", self.styles['GridLabel'])],
            [Paragraph("Fecha: ____/____/_______", self.styles['GridLabel'])]
        ]
        
        # Ampliamos la altura de firma (50) para un calce perfecto en la base
        sig_table = Table(sig_data, colWidths=[7.5*cm], rowHeights=[50, 14, 14, 14])
        sig_table.setStyle(TableStyle([
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('LINEABOVE', (0,1), (0,1), 1.25, self.COLOR_TEXT_MAIN),
            ('TOPPADDING', (0,1), (-1,-1), 5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 2),
        ]))
        
        # Envoltorio escalado al ancho total de 18.6 cm para un centrado perfecto
        footer_wrapper = Table([[sig_table]], colWidths=[18.6*cm])
        footer_wrapper.setStyle(TableStyle([
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('LEFTPADDING', (0,0), (-1,-1), 5.55*cm), 
        ]))
        
        elements.append(footer_wrapper)

        # Compilación final del lienzo corporativo de una página
        doc.build(elements)
        return buffer.getvalue()
