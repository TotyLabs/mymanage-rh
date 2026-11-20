import io
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import fitz
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.sign import fields, signers
from pyhanko.sign.diff_analysis.policy_api import ModificationLevel
from pyhanko.sign.validation import validate_pdf_signature
from PIL import Image, ImageDraw

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-signature-field-tests")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")

from services.x509_service import _prepare_signature_fields
from modules.signature import SignatureEngine


def _minimal_pdf():
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << >> /Contents 4 0 R >>",
        b"<< /Length 0 >>\nstream\n\nendstream",
    ]

    for number, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{number} 0 obj\n".encode() + body + b"\nendobj\n")

    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n".encode()
    )
    return bytes(output)


def _test_signer(tmp_path):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Temporary Test Signer")])
    now = datetime.now(timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=True,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=None,
                decipher_only=None,
            ),
            critical=True,
        )
        .sign(private_key, hashes.SHA256())
    )
    p12_path = tmp_path / "temporary-test-signer.p12"
    p12_path.write_bytes(
        pkcs12.serialize_key_and_certificates(
            b"test",
            private_key,
            certificate,
            None,
            serialization.BestAvailableEncryption(b"test-password"),
        )
    )
    return signers.SimpleSigner.load_pkcs12(
        str(p12_path),
        passphrase=b"test-password",
    )


def _sign_revision(
    pdf_bytes,
    role,
    signer,
    prepare_next_signer=False,
    signature_appearance=None,
    next_signer_field_box=None,
):
    source = io.BytesIO(pdf_bytes)
    writer = IncrementalPdfFileWriter(source)
    field_name = _prepare_signature_fields(
        writer,
        role,
        prepare_next_signer=prepare_next_signer,
        next_signer_field_box=next_signer_field_box,
    )
    stamp_style = None
    if signature_appearance:
        from pyhanko.pdf_utils.images import PdfImage
        from pyhanko.stamp import StaticStampStyle

        stamp_style = StaticStampStyle(
            border_width=0,
            background=PdfImage(Image.open(io.BytesIO(signature_appearance))),
            background_opacity=1,
        )
    pdf_signer = signers.PdfSigner(
        signature_meta=signers.PdfSignatureMetadata(
            field_name=field_name,
            reason="Test signature",
            certify=prepare_next_signer,
            docmdp_permissions=fields.MDPPerm.FILL_FORMS,
        ),
        signer=signer,
        stamp_style=stamp_style,
    )
    output = io.BytesIO()
    pdf_signer.sign_pdf(
        writer,
        existing_fields_only=True,
        output=output,
    )
    return output.getvalue()


def test_precreated_employee_field_allows_incremental_second_signature(tmp_path):
    signer = _test_signer(tmp_path)
    employer_signed = _sign_revision(
        _minimal_pdf(),
        "employer",
        signer,
        prepare_next_signer=True,
        next_signer_field_box=(30, 600, 210, 760),
    )
    final_pdf = _sign_revision(employer_signed, "employee", signer)

    reader = PdfFileReader(io.BytesIO(final_pdf))
    signature_fields = list(fields.enumerate_sig_fields(reader))
    assert [(name, value is not None) for name, value, _ in signature_fields] == [
        ("MyManageRH_EmployerSignature", True),
        ("MyManageRH_EmployeeSignature", True),
    ]
    assert len(reader.embedded_signatures) == 2

    statuses = [validate_pdf_signature(signature) for signature in reader.embedded_signatures]
    assert all(status.intact for status in statuses)
    assert statuses[0].diff_result.modification_level == ModificationLevel.FORM_FILLING
    assert statuses[0].diff_result.changed_form_fields == {"MyManageRH_EmployeeSignature"}
    assert statuses[1].diff_result.modification_level == ModificationLevel.NONE

def test_visual_employee_seal_is_added_inside_certified_signature_field(tmp_path):
    signer = _test_signer(tmp_path)

    signature_image = Image.new("RGBA", (320, 120), (255, 255, 255, 0))
    ImageDraw.Draw(signature_image).line(
        (20, 92, 82, 25, 144, 90, 225, 28, 295, 88),
        fill=(15, 15, 15, 255),
        width=9,
    )
    image_bytes = io.BytesIO()
    signature_image.save(image_bytes, format="PNG")
    source_path = tmp_path / "receipt-source.pdf"
    source_path.write_bytes(_minimal_pdf())

    engine = SignatureEngine()
    employer_visual = engine.stamp_signature_from_bytes(
        pdf_path=str(source_path),
        signature_bytes=image_bytes.getvalue(),
        role="employer",
        signer_name="Empresa",
        signer_tax_id="30123456789",
        timestamp=datetime.now(timezone.utc),
        output_path=str(tmp_path / "employer-visual.pdf"),
        signer_identity={
            "role": "employer",
            "full_name": "Empresa",
            "dni": "30123456789",
        },
        prepare_next_signer=True,
    )
    employer_signed = _sign_revision(
        Path(employer_visual["signed_pdf_path"]).read_bytes(),
        "employer",
        signer,
        prepare_next_signer=True,
        next_signer_field_box=employer_visual["next_signer_field_box"],
    )
    employer_signed_path = tmp_path / "employer-signed.pdf"
    employer_signed_path.write_bytes(employer_signed)

    employee_visual_path = tmp_path / "employee-visual.pdf"
    employee_visual = engine.stamp_signature_from_bytes(
        pdf_path=str(employer_signed_path),
        signature_bytes=image_bytes.getvalue(),
        role="employee",
        signer_name="Empleado",
        signer_tax_id="20123456789",
        timestamp=datetime.now(timezone.utc),
        output_path=str(employee_visual_path),
        signer_identity={
            "role": "employee",
            "full_name": "Empleado",
            "dni": "20123456789",
        },
    )
    assert employee_visual_path.read_bytes() == employer_signed
    assert employee_visual["field_appearance_png"].startswith(b"\x89PNG")

    final_pdf = _sign_revision(
        employee_visual_path.read_bytes(),
        "employee",
        signer,
        signature_appearance=employee_visual["field_appearance_png"],
    )
    reader = PdfFileReader(io.BytesIO(final_pdf))
    statuses = [validate_pdf_signature(signature) for signature in reader.embedded_signatures]

    assert len(statuses) == 2
    assert all(status.intact for status in statuses)
    assert all(status.docmdp_ok for status in statuses)
    assert statuses[0].diff_result.modification_level == ModificationLevel.FORM_FILLING
    assert statuses[0].diff_result.changed_form_fields == {"MyManageRH_EmployeeSignature"}
    assert statuses[1].diff_result.modification_level == ModificationLevel.NONE

    with fitz.open(stream=final_pdf, filetype="pdf") as document:
        rendered = Image.open(io.BytesIO(document[0].get_pixmap().tobytes("png")))
        x0, y0, x1, y1 = employer_visual["next_signer_field_box"]
        field_region = rendered.crop(
            (x0, 792 - y1, x1, 792 - y0)
        ).convert("RGB")
        assert min(field_region.getextrema()[0]) < 245
