"""
tests/test_signature_service.py

Tests unitarios para SignatureEngine y flujo de firma.
Validar nueva arquitectura y hardening.
"""

import os
import tempfile
import time
from pathlib import Path
from datetime import datetime, timezone

import pytest
from modules.signature import SignatureEngine, SignatureError


# Tests para SignatureEngine
class TestSignatureEngine:
    """Tests de la clase SignatureEngine."""
    
    @pytest.fixture
    def engine(self):
        """Crear instancia de SignatureEngine con temp dir."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Mock de config se asume de config.py o se inyecta
            engine = SignatureEngine(
                storage_path=tmpdir,
                signature_positions={"employer": {"x": 100, "y": 100}, "employee": {"x": 50, "y": 50}},
                signature_mode="hybrid"
            )
            yield engine
    
    @pytest.fixture
    def temp_pdf(self):
        """Crear un PDF mÃ­nimo para tests."""
        from reportlab.pdfgen import canvas
        
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            c = canvas.Canvas(f.name)
            c.drawString(100, 750, "Recibo de Haberes")
            c.drawString(100, 200, "Firma del empleador: ___________")
            c.drawString(100, 100, "Firma del empleado: ____________")
            c.save()
            pdf_path = f.name
        yield pdf_path
        if os.path.exists(pdf_path):
            os.unlink(pdf_path)

    @pytest.fixture
    def large_pdf(self):
        """Crear un PDF con muchas pÃ¡ginas para test de hardening."""
        from reportlab.pdfgen import canvas
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            c = canvas.Canvas(f.name)
            for i in range(60): # Mayor que el lÃ­mite de 50
                c.drawString(100, 750, f"PÃ¡gina {i+1}")
                c.showPage()
            c.save()
            pdf_path = f.name
        yield pdf_path
        if os.path.exists(pdf_path):
            os.unlink(pdf_path)
    
    @pytest.fixture
    def temp_png(self):
        """Crear un PNG mÃ­nimo para tests."""
        from PIL import Image
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            img = Image.new("RGBA", (100, 50), color=(255, 255, 255, 0))
            img.save(f.name, "PNG")
            png_path = f.name
        yield png_path
        if os.path.exists(png_path):
            os.unlink(png_path)
    
    def test_save_signature_image(self, engine):
        """Test guardar firma."""
        from PIL import Image
        from io import BytesIO
        img = Image.new("RGBA", (100, 50), color=(255, 255, 255, 0))
        buf = BytesIO()
        img.save(buf, "PNG")
        png_bytes = buf.getvalue()
        
        result = engine.save_signature_image(
            role="employee",
            entity_id="f47ac10b-58cc-4372-a567-0e02b2c3d479",
            image_bytes=png_bytes,
            parent_id="550e8400-e29b-41d4-a716-446655440000"
        )
        
        assert "path" in result
        assert "sha256" in result
        assert os.path.exists(result["path"])
        assert "signatures/employee/550e8400-e29b-41d4-a716-446655440000" in result["path"].replace("\\", "/")
    
    def test_hardening_page_limit(self, engine, large_pdf, temp_png):
        """Test que rechaza PDFs con demasiadas pÃ¡ginas."""
        engine.max_pages = 50
        with pytest.raises(SignatureError, match="too many pages"):
            engine.stamp_signature_on_pdf(
                pdf_path=large_pdf,
                signature_image_path=temp_png,
                role="employer"
            )

    def test_hardening_timeout(self, engine, temp_pdf, temp_png):
        """Test que respeta el timeout."""
        engine.timeout = 0 # Forzar timeout inmediato
        with pytest.raises(SignatureError, match="timeout"):
            engine.stamp_signature_on_pdf(
                pdf_path=temp_pdf,
                signature_image_path=temp_png,
                role="employer"
            )

    def test_stamp_signature_from_bytes(self, engine, temp_pdf):
        """Test estampado directo desde bytes."""
        from PIL import Image
        from io import BytesIO
        img = Image.new("RGBA", (100, 50), color=(0, 0, 0, 255))
        buf = BytesIO()
        img.save(buf, "PNG")
        png_bytes = buf.getvalue()
        
        out_path = engine.stamp_signature_from_bytes(
            pdf_path=temp_pdf,
            signature_bytes=png_bytes,
            role="employee",
            signer_name="Test User",
            timestamp=datetime.now()
        )
        
        assert os.path.exists(out_path)
        assert out_path.endswith("_signed.pdf")

# Cleanup de imports que ya no existen en core
def test_core_cleanup():
    import payroll_core
    # Estas ya no deberÃ­an existir en el namespace de core (si se eliminaron bien)
    assert not hasattr(core, "apply_signature_bytes_to_pdf")
    assert not hasattr(core, "save_signature_png")
    assert not hasattr(core, "get_signature_service")

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
