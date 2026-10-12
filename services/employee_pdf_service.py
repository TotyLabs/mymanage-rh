import os
import io
import json
from datetime import datetime
from xml.sax.saxutils import escape
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak
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
            name='DocTitle',
            fontSize=16,
            leading=20,
            textColor=self.COLOR_TEXT_MAIN,
            fontName='Helvetica-Bold',
            alignment=1,
        ))
        self.styles.add(ParagraphStyle(
            name='DocText',
            fontSize=10,
            leading=14,
            textColor=self.COLOR_TEXT_MAIN,
            fontName='Helvetica',
        ))
        self.styles.add(ParagraphStyle(
            name='DocField',
            fontSize=10,
            leading=14,
            textColor=self.COLOR_TEXT_MAIN,
            fontName='Helvetica',
        ))
        self.styles.add(ParagraphStyle(
            name='FormHeader',
            fontSize=8,
            leading=10,
            textColor=self.COLOR_LABEL,
            fontName='Helvetica-Bold',
        ))
        self.styles.add(ParagraphStyle(
            name='FormTitle',
            fontSize=12,
            leading=15,
            textColor=colors.white,
            fontName='Helvetica-Bold',
            alignment=1,
        ))
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

    def _safe_value(self, value, placeholder='—'):
        if value is None:
            return placeholder
        if isinstance(value, str):
            text = value.strip()
            return text or placeholder
        return str(value)

    def _employee_name(self, emp):
        return " ".join(part for part in (self._safe_value(getattr(emp, 'first_name', ''), ''), self._safe_value(getattr(emp, 'last_name', ''), '')) if part not in ('', '—')).strip() or 'Empleado'

    def _address_line(self, emp):
        street = self._safe_value(getattr(emp, 'address', ''), '')
        number = self._safe_value(getattr(emp, 'address_number', ''), '')
        city = self._safe_value(getattr(emp, 'city', ''), '')
        province = self._safe_value(getattr(emp, 'province', ''), '')
        postal = self._safe_value(getattr(emp, 'postal_code', ''), '')
        line = f"{street} {number}".strip()
        if city or province or postal:
            suffix = f"{city} {province}".strip()
            if postal:
                suffix = f"{suffix} - CP {postal}".strip()
            line = f"{line}, {suffix}" if line else suffix
        return line or '—'

    def _today_text(self):
        return datetime.now().strftime('%d/%m/%Y')

    def _build_form_page(self, title, body_lines, right_date=None):
        date_text = escape(right_date or self._today_text())
        header = Table(
            [[Paragraph('LEGAJO DEL PERSONAL', self.styles['FormHeader']),
              Paragraph(f'<para align="right">{date_text}</para>', self.styles['MetaValue'])]],
            colWidths=[9.3 * cm, 9.3 * cm],
        )
        header.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), self.COLOR_BG_BLOCK),
            ('LINEBELOW', (0, 0), (-1, -1), 1.1, self.COLOR_TEXT_MAIN),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        title_bar = Table(
            [[Paragraph(escape(title.upper()), self.styles['FormTitle'])]],
            colWidths=[18.6 * cm],
        )
        title_bar.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), self.COLOR_TEXT_MAIN),
            ('BOX', (0, 0), (-1, -1), 0.8, self.COLOR_TEXT_MAIN),
            ('TOPPADDING', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ]))
        return [header, Spacer(1, 12), title_bar, Spacer(1, 16), *body_lines]

    def _form_fields_table(self, fields):
        rows = []
        for index in range(0, len(fields), 2):
            row = []
            for label, value in fields[index:index + 2]:
                row.extend((
                    Paragraph(f'<b>{escape(str(label))}</b>', self.styles['MetaLabel']),
                    Paragraph(f'<u>{escape(self._safe_value(value, "________________"))}</u>', self.styles['GridValue']),
                ))
            if len(row) == 2:
                row.extend(('', ''))
            rows.append(row)
        table = Table(rows, colWidths=[2.35 * cm, 6.95 * cm, 2.35 * cm, 6.95 * cm])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), self.COLOR_BG_TITLE),
            ('BACKGROUND', (2, 0), (2, -1), self.COLOR_BG_TITLE),
            ('BACKGROUND', (1, 0), (1, -1), colors.white),
            ('BACKGROUND', (3, 0), (3, -1), colors.white),
            ('BOX', (0, 0), (-1, -1), 0.8, self.COLOR_BORDER),
            ('INNERGRID', (0, 0), (-1, -1), 0.45, self.COLOR_BORDER),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 7),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ]))
        return table

    def _form_message_box(self, message):
        box = Table([[Paragraph(message, self.styles['DocText'])]], colWidths=[18.6 * cm])
        box.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), self.COLOR_BG_BLOCK),
            ('BOX', (0, 0), (-1, -1), 0.8, self.COLOR_BORDER),
            ('LEFTPADDING', (0, 0), (-1, -1), 12),
            ('RIGHTPADDING', (0, 0), (-1, -1), 12),
            ('TOPPADDING', (0, 0), (-1, -1), 12),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ]))
        return box

    def _form_signature_table(self, labels):
        cells = [Paragraph('<br/><br/>____________________________', self.styles['DocText']) for _ in labels]
        label_cells = [Paragraph(f'<b>{escape(label)}</b>', self.styles['MetaLabel']) for label in labels]
        widths = [18.6 * cm / len(labels)] * len(labels)
        table = Table([cells, label_cells], colWidths=widths)
        table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
            ('LINEABOVE', (0, 1), (-1, 1), 0.8, self.COLOR_BORDER),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        return table

    def _display_form_date(self, value):
        if not value:
            return '________________'
        if hasattr(value, 'strftime'):
            return value.strftime('%d/%m/%Y')
        raw = str(value).strip()
        try:
            return datetime.strptime(raw[:10], '%Y-%m-%d').strftime('%d/%m/%Y')
        except ValueError:
            return raw

    def _build_declaration_domicilio_page(self, emp):
        today = self._today_text()
        body = [
            self._form_fields_table([
                ('Apellido y nombre', self._employee_name(emp)),
                ('DNI', getattr(emp, 'dni', '')),
                ('Calle', getattr(emp, 'address', '')),
                ('Número', getattr(emp, 'address_number', '')),
                ('Piso', getattr(emp, 'floor', '')),
                ('Departamento', getattr(emp, 'apartment', '')),
                ('Torre', getattr(emp, 'tower', '')),
                ('Localidad', getattr(emp, 'city', '')),
                ('Provincia', getattr(emp, 'province', '')),
                ('Código postal', getattr(emp, 'postal_code', '')),
            ]),
            Spacer(1, 16),
            self._form_message_box('Declaro que mi domicilio actual se encuentra situado en el lugar indicado y me comprometo a informar cualquier modificación.'),
            Spacer(1, 42),
            self._form_signature_table(['Firma del trabajador/a', 'Aclaración y DNI']),
        ]
        return self._build_form_page('DECLARACIÓN DE DOMICILIO', body, right_date=today)

    def _build_family_page(self, emp):
        today = self._today_text()
        extra = getattr(emp, 'extra_fields', {}) or {}
        if isinstance(extra, str):
            try:
                extra = json.loads(extra)
            except (TypeError, ValueError):
                extra = {}
        members = extra.get('family_members', []) if isinstance(extra, dict) else []
        body = [
            Paragraph('<b>DATOS DEL TRABAJADOR</b>', self.styles['SectionHeaderTitle']),
            self._form_fields_table([
                ('Apellido y nombre', self._employee_name(emp)),
                ('DNI', getattr(emp, 'dni', '')),
            ]),
            Spacer(1, 12),
            Paragraph(f'<b>ASOCIACIONES FAMILIARES ({len(members)})</b>', self.styles['SectionHeaderTitle']),
        ]
        family_fields = [
            ('Vínculo', 'vinculo'), ('C.U.I.L.', 'cuil'),
            ('Tipo y N° documento', 'documento'), ('Apellido y nombre', 'nombre'),
            ('Fecha de nacimiento', 'fecha_nacimiento'), ('Nivel escolar', 'nivel_escolar'),
            ('Documentación entregada', 'documentacion'), ('Tomo', 't'),
            ('Folio', 'f'), ('Acta', 'acta'),
        ]
        if members:
            for index, member in enumerate(members, start=1):
                body.extend([
                    Spacer(1, 6),
                    Paragraph(f'<b>FAMILIAR {index}</b>', self.styles['MetaLabel']),
                    self._form_fields_table([(label, member.get(key, '')) for label, key in family_fields]),
                ])
        else:
            body.extend([Spacer(1, 6), self._form_fields_table([(label, '') for label, _ in family_fields])])
        body.extend([
            Spacer(1, 12),
            self._form_message_box('Por medio de la presente y de acuerdo a la Ley 22.163, Art. 2° inc. "C", se solicita informar y remitir la documentación correspondiente a las cargas de familia. Me responsabilizo de la exactitud de los datos arriba mencionados, me comprometo a desempeñar con eficiencia mis tareas y a cumplir los reglamentos en vigencia, así como también a entregar la documentación requerida por la empresa en un plazo no mayor de sesenta (60) días.'),
            Spacer(1, 28),
            self._form_signature_table(['Firma del trabajador/a', 'Aclaración y DNI']),
        ])
        return self._build_form_page('ASOCIACIONES FAMILIARES Y CARGAS DE FAMILIA', body, right_date=today)

    def _build_ropa_page(self, emp):
        today = self._today_text()
        extra = getattr(emp, 'extra_fields', {}) or {}
        if isinstance(extra, str):
            try:
                extra = json.loads(extra)
            except (TypeError, ValueError):
                extra = {}
        clothes = extra.get('ropa_trabajo', {}) if isinstance(extra, dict) else {}
        body = [
            self._form_fields_table([
                ('Empleado/a', self._employee_name(emp)),
                ('DNI', getattr(emp, 'dni', '')),
                ('Obra / lugar de trabajo', getattr(emp, 'work_location', '')),
                ('Período desde', self._display_form_date(clothes.get('desde'))),
                ('Período hasta', self._display_form_date(clothes.get('hasta'))),
                ('Vencimiento de la entrega', self._display_form_date(clothes.get('vencimiento'))),
                ('Próximo vencimiento', self._display_form_date(clothes.get('proximo_vencimiento'))),
            ]),
            Spacer(1, 12),
            self._form_message_box('Período de cumplimiento Art. 35 Conv. 76/75. Res. M.T. 98/86. Se deja constancia de la entrega de ropa de trabajo correspondiente al período consignado.'),
            Spacer(1, 42),
            self._form_signature_table(['Firma del trabajador/a', 'Aclaración y DNI']),
        ]
        return self._build_form_page('CONSTANCIA DE ENTREGA DE ROPA DE TRABAJO', body, right_date=today)

    def _build_sindicato_page(self, emp):
        today = self._today_text()
        body = [
            self._form_fields_table([
                ('Apellido y nombre', self._employee_name(emp)),
                ('DNI', getattr(emp, 'dni', '')),
                ('Sindicato', getattr(emp, 'union', '')),
                ('N° de afiliado', getattr(emp, 'union_number', '')),
                ('N° de miembro', getattr(emp, 'union_member_number', '')),
            ]),
            Spacer(1, 16),
            self._form_message_box('Sr. Empleador: solicito se me efectúe el aporte sindical voluntario con destino al sindicato consignado.'),
            Spacer(1, 12),
            Paragraph('<b>Autorizo el aporte sindical voluntario:</b> &nbsp;&nbsp;&nbsp; [  ] SI &nbsp;&nbsp;&nbsp; [  ] NO', self.styles['DocText']),
            Spacer(1, 42),
            self._form_signature_table(['Firma del trabajador/a', 'Aclaración y DNI']),
        ]
        return self._build_form_page('DECLARACIÓN DE AFILIACIÓN SINDICAL', body, right_date=today)

    def _generate_legacy_record_pdf(self, employee_id: str, organization_id: str) -> bytes:
        emp = self.db.execute(
            text("""
                  SELECT e.*, ed.floor, ed.apartment, ed.tower, ed.paraje,
                       ed.union_member_number, ed.unemployment_fund_account,
                      ed.legajo_number, ed.card_number, ed.ieric_number
                FROM employees e
                LEFT JOIN employee_extra_data ed ON ed.employee_id = e.id
                WHERE e.id = :id AND e.organization_id = :org
            """),
            {"id": employee_id, "org": organization_id}
        ).fetchone()

        if not emp:
            raise ValueError("employee_not_found")

        org = self.db.execute(
            text("SELECT name, logo_path FROM organizations WHERE id = :id"),
            {"id": organization_id}
        ).fetchone()

        buffer = io.BytesIO()

        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=1.2*cm,
            leftMargin=1.2*cm,
            topMargin=1.2*cm,
            bottomMargin=1.2*cm
        )

        elements = []

        logo = None
        if org and getattr(org, 'logo_path', None) and os.path.exists(org.logo_path):
            try:
                logo = Image(org.logo_path, width=1.6*cm, height=1.6*cm, kind='proportional')
            except Exception:
                logo = None

        title_block = [
            Paragraph(f"<b>{getattr(org, 'name', 'EMPRESA').upper() if org else 'EMPRESA'}</b>", self.styles['CorpTitle']),
            Spacer(1, 3),
            Paragraph("FICHA DE REGISTRO / LEGAJO DE PERSONAL", self.styles['CorpSubtitle'])
        ]

        meta_table_data = [
            [Paragraph("Registro", self.styles['MetaLabel']), Paragraph("REG-RH-004", self.styles['MetaValue'])],
            [Paragraph("Versión", self.styles['MetaLabel']), Paragraph("1.2", self.styles['MetaValue'])],
            [Paragraph("Fecha", self.styles['MetaLabel']), Paragraph(self._today_text(), self.styles['MetaValue'])],
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

        personal_data = [
            ("Apellido y Nombre", f"{self._safe_value(getattr(emp, 'last_name', ''), '')}, {self._safe_value(getattr(emp, 'first_name', ''), '')}".strip(", ")),
            ("Documento (DNI)", self._safe_value(getattr(emp, 'dni', ''), '—')),
            ("CUIL", self._safe_value(getattr(emp, 'cuil', ''), '—')),
            ("Fecha de Nacimiento", getattr(emp, 'birth_date', None).strftime('%d/%m/%Y') if getattr(emp, 'birth_date', None) else '—'),
            ("Email", self._safe_value(getattr(emp, 'email', ''), '—')),
            ("Teléfono de Contacto", self._safe_value(getattr(emp, 'phone', ''), '—')),
            ("Domicilio", self._safe_value(getattr(emp, 'address', ''), '') + (f" {self._safe_value(getattr(emp, 'address_number', ''), '')}" if self._safe_value(getattr(emp, 'address_number', ''), '') != '—' else '') if getattr(emp, 'address', None) else '—'),
            ("Localidad / Provincia", f"{self._safe_value(getattr(emp, 'city', ''), '')} {self._safe_value(getattr(emp, 'province', ''), '')}".strip() or '—')
        ]
        elements.append(self._create_matrix_section("Datos Personales", personal_data))
        elements.append(Spacer(1, 14))

        file_num_raw = getattr(emp, 'file_number', None)
        if file_num_raw is not None:
            try:
                file_number_clean = str(int(float(file_num_raw)))
            except (ValueError, TypeError):
                file_number_clean = str(file_num_raw)
        else:
            file_number_clean = '—'

        seniority = self._calculate_seniority_internal(getattr(emp, 'hire_date', None))
        laboral_data = [
            ("Nro. Legajo Interno", file_number_clean),
            ("Fecha de Ingreso", getattr(emp, 'hire_date', None).strftime('%d/%m/%Y') if getattr(emp, 'hire_date', None) else '—'),
            ("Puesto / Cargo", self._safe_value(getattr(emp, 'job_title', ''), '—')),
            ("Antigüedad", seniority),
            ("Tipo de Contrato", self._safe_value(getattr(emp, 'hire_type', ''), '—')),
            ("Sección", self._safe_value(getattr(emp, 'work_location', ''), '—')),
            ("Centro de Costos", self._safe_value(getattr(emp, 'cost_center', ''), '—')),
            ("Obra Social", self._safe_value(getattr(emp, 'health_insurance', ''), '—'))
        ]
        elements.append(self._create_matrix_section("Datos Laborales", laboral_data))
        elements.append(Spacer(1, 14))

        bank_data = [
            ("Entidad Bancaria", self._safe_value(getattr(emp, 'bank', ''), '—')),
            ("Tipo de Cuenta", self._safe_value(getattr(emp, 'account_type', ''), '—')),
            ("Número de Cuenta", self._safe_value(getattr(emp, 'account_number', ''), '—')),
            ("CBU", self._safe_value(getattr(emp, 'cbu', ''), '—')),
            ("Alias", self._safe_value(getattr(emp, 'bank_alias', ''), '—')),
            ("Forma de Pago", self._safe_value(getattr(emp, 'payment_method', ''), '—'))
        ]
        elements.append(self._create_matrix_section("Datos Bancarios", bank_data))
        elements.append(Spacer(1, 45))

        sig_data = [
            [""],
            [Paragraph("Firma del Empleado", self.styles['GridLabel'])],
            [Paragraph("Aclaración:", self.styles['GridLabel'])],
            [Paragraph("Fecha: ____/____/_______", self.styles['GridLabel'])]
        ]
        sig_table = Table(sig_data, colWidths=[7.5*cm], rowHeights=[50, 14, 14, 14])
        sig_table.setStyle(TableStyle([
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('LINEABOVE', (0,1), (0,1), 1.25, self.COLOR_TEXT_MAIN),
            ('TOPPADDING', (0,1), (-1,-1), 5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 2),
        ]))
        footer_wrapper = Table([[sig_table]], colWidths=[18.6*cm])
        footer_wrapper.setStyle(TableStyle([
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('LEFTPADDING', (0,0), (-1,-1), 5.55*cm),
        ]))
        elements.append(footer_wrapper)

        elements.append(PageBreak())
        elements.extend(self._build_declaration_domicilio_page(emp))
        elements.append(PageBreak())
        elements.extend(self._build_family_page(emp))
        elements.append(PageBreak())
        elements.extend(self._build_ropa_page(emp))
        elements.append(PageBreak())
        elements.extend(self._build_sindicato_page(emp))

        full_name = self._employee_name(emp)
        def set_pdf_metadata(canvas, _document):
            canvas.setTitle(f"LEGAJO - {full_name}")
            canvas.setAuthor(getattr(org, 'name', 'MyManageRH') if org else 'MyManageRH')

        doc.build(elements, onFirstPage=set_pdf_metadata)
        return buffer.getvalue()

    def generate_record_pdf(
        self,
        employee_id: str,
        organization_id: str,
        include_termination_notice: bool = False,
        include_pages=None,
    ) -> bytes:
        emp = self.db.execute(
            text("""
                SELECT e.*, ed.floor, ed.apartment, ed.tower, ed.paraje,
                       ed.union_member_number, ed.unemployment_fund_account,
                       ed.legajo_number, ed.card_number
                FROM employees e
                LEFT JOIN employee_extra_data ed ON ed.employee_id = e.id
                WHERE e.id = :id AND e.organization_id = :org
            """),
            {"id": employee_id, "org": organization_id}
        ).fetchone()
        if not emp:
            raise ValueError("employee_not_found")

        org = self.db.execute(
            text("SELECT name, logo_path FROM organizations WHERE id = :id"),
            {"id": organization_id}
        ).fetchone()

        from services.employee_legajo_template import EmployeeLegajoTemplate
        return EmployeeLegajoTemplate(
            emp, org, include_termination_notice, include_pages=include_pages
        ).generate()
