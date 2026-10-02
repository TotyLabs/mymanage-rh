import asyncio

from services.email_service import EmailService


def test_build_message_includes_pdf_attachment():
    service = EmailService()

    message = service._build_message(
        to="recipient@example.com",
        subject="Documento laboral",
        body_html="<p>Se adjunta el documento.</p>",
        attachments=[{
            "filename": "documento.pdf",
            "content": b"%PDF-test-content",
            "subtype": "pdf",
        }],
    )

    parts = list(message.walk())
    attachment = next(part for part in parts if part.get_filename() == "documento.pdf")

    assert message.get_content_type() == "multipart/mixed"
    assert attachment.get_content_type() == "application/pdf"
    assert attachment.get_payload(decode=True) == b"%PDF-test-content"


def test_smtp_transport_receives_attachments():
    service = EmailService()
    service._has_primary_config = lambda: True
    attachments = [{"filename": "documento.pdf", "content": b"%PDF", "subtype": "pdf"}]
    sent = []

    async def capture_attempt(**kwargs):
        sent.append(kwargs)

    service._attempt_send = capture_attempt
    asyncio.run(service._send_smtp_async(
        to="recipient@example.com",
        subject="Documento laboral",
        body_html="<p>Se adjunta el documento.</p>",
        attachments=attachments,
    ))

    assert sent[0]["attachments"] == attachments