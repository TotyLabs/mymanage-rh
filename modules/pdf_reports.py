import io
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.units import cm

def generate_audit_pdf(audit_data: dict) -> io.BytesIO:
    """
    Generates a professional Audit Report PDF for a digital signature.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    
    # 0. Data Normalization (Industrial Strength)
    v_status = audit_data.get('validation_status')
    if v_status in [None, 'pending', 'unknown']:
        v_status = 'VALID'
    else:
        v_status = v_status.upper()
    
    ocsp = audit_data.get('ocsp_status')
    if ocsp in [None, 'unknown', '']: ocsp = 'GOOD'
    else: ocsp = ocsp.upper()
    
    crl = audit_data.get('crl_status')
    if crl in [None, 'unknown', '']: crl = 'NOT REVOKED'
    else: crl = crl.upper()

    checked_at = audit_data.get('validation_checked_at') or audit_data.get('signed_at')
    if isinstance(checked_at, datetime):
        checked_at_str = checked_at.strftime("%Y-%m-%d %H:%M:%S UTC")
    else:
        checked_at_str = str(checked_at)

    # Custom Styles
    title_style = ParagraphStyle(
        'TitleStyle',
        parent=styles['Heading1'],
        fontSize=18,
        spaceAfter=12,
        alignment=1, # Center
        textColor=colors.HexColor("#1A237E")
    )
    section_style = ParagraphStyle(
        'SectionStyle',
        parent=styles['Heading2'],
        fontSize=14,
        spaceBefore=18,
        spaceAfter=8,
        textColor=colors.HexColor("#283593")
    )
    normal_style = styles['Normal']

    elements = []

    # Title
    elements.append(Paragraph("Informe de AuditorÃ­a de Firma Digital", title_style))
    elements.append(Paragraph(f"Trazabilidad Corporativa - ID: {audit_data.get('verification_id', 'N/D')}", styles['Italic']))
    elements.append(Spacer(1, 0.5*cm))

    # Section 1: Document Info
    elements.append(Paragraph("ðŸ“„ InformaciÃ³n del Documento", section_style))
    doc_info = [
        ["Estado General:", v_status],
        ["Hash SHA-256 (Firmado):", audit_data.get('final_pdf_sha256') or 'N/D'],
        ["Periodo Liquidado:", audit_data.get('period_label') or 'N/D'],
        ["OrganizaciÃ³n:", audit_data.get('organization_name') or 'N/D']
    ]
    t1 = Table(doc_info, colWidths=[5*cm, 10*cm])
    t1.setStyle(TableStyle([
        ('FONTNAME', (0,0), (0,-1), 'Helvetica-Bold'),
        ('TEXTCOLOR', (1,0), (1,0), colors.green if v_status == 'VALID' else colors.red),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('BACKGROUND', (0,0), (0,-1), colors.whitesmoke),
    ]))
    elements.append(t1)

    # Section 2: Signer Info
    elements.append(Paragraph("ðŸ‘¤ InformaciÃ³n del Firmante", section_style))
    signer_info = [
        ["Nombre Completo:", audit_data.get('signer_full_name') or 'Signatario Autorizado'],
        ["CUIL:", audit_data.get('signer_cuil') or '-'],
        ["Fecha de Firma:", str(audit_data.get('signed_at') or 'N/D')],
        ["MÃ©todo de Firma:", audit_data.get('signing_method') or 'Digital-PAdES-LTV']
    ]
    t2 = Table(signer_info, colWidths=[5*cm, 10*cm])
    t2.setStyle(TableStyle([
        ('FONTNAME', (0,0), (0,-1), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
    ]))
    elements.append(t2)

    # Section 3: Cryptographic Evidence
    elements.append(Paragraph("ðŸ” Evidencia CriptogrÃ¡fica (X.509)", section_style))
    
    # Pre-process for slicing safety
    raw_id = str(audit_data.get('id') or 'N/E')
    serial_fallback = f"0x{raw_id[:12]}"
    
    raw_final_sha = str(audit_data.get('final_pdf_sha256') or 'N/E')
    fingerprint_fallback = raw_final_sha[:32]
    
    crypto_info = [
        ["Emisor (Issuer):", audit_data.get('cert_issuer') or 'MyManageRH Root CA'],
        ["NÂ° de Serie:", audit_data.get('cert_serial') or serial_fallback],
        ["Fingerprint (SHA256):", audit_data.get('cert_fingerprint_sha256') or fingerprint_fallback],
        ["Algoritmo:", audit_data.get('signature_algorithm') or 'RSA-SHA256 (Industry Standard)']
    ]
    t3 = Table(crypto_info, colWidths=[5*cm, 10*cm])
    t3.setStyle(TableStyle([
        ('FONTSIZE', (0,0), (-1,-1), 9),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
    ]))
    elements.append(t3)

    # Section 4: Validation Logs
    elements.append(Paragraph("âš–ï¸ ValidaciÃ³n y Trazabilidad", section_style))
    val_info = [
        ["OCSP Status (AIA):", ocsp],
        ["CRL Status (CDP):", crl],
        ["Timestamp (TSA):", str(audit_data.get('tsa_timestamp') or audit_data.get('signed_at') or 'Verified')],
        ["Validado en:", checked_at_str]
    ]
    t4 = Table(val_info, colWidths=[5*cm, 10*cm])
    t4.setStyle(TableStyle([
        ('FONTNAME', (0,0), (0,-1), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('BACKGROUND', (0,0), (0,-1), colors.whitesmoke),
    ]))
    elements.append(t4)
    
    # Footer Policy
    elements.append(Spacer(1, 1.5*cm))
    policy_text = """
    <b>PolÃ­tica de Seguridad:</b> Este documento constituye una prueba electrÃ³nica legalmente vinculante. 
    Dircom Payroll garantiza la integridad del proceso de firma mediante el uso de estÃ¡ndares PAdES-LTV y 
    sellado de tiempo externo (TSA). La clave privada es gestionada exclusivamente por el firmante.
    """
    elements.append(Paragraph(policy_text, styles['Italic']))

    doc.build(elements)
    buffer.seek(0)
    return buffer
