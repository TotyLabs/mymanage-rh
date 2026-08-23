"""
Tests para el módulo de normalización de Legajos (services/legajo/normalizer.py).

Verifica las reglas estrictas de negocio aplicadas a extra_fields:
  1. Deduplicación semántica vs bloques canónicos
  2. Eliminación de campos de bajo valor / ruido
  3. Política de Grossing Up (solo valores afirmativos)
  4. Traducción inglés→español de claves
  5. Conversión a MAYÚSCULAS y eliminación de prefijo 'Extra.'
  6. Deduplicación interna (mismo valor, diferentes claves)
"""

import sys
import os
import unittest
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

# Bootstrap: add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# Stubs mínimos para poder importar el Normalizer sin deps de BD/config
# ---------------------------------------------------------------------------

class _FakeBlock:
    """Bloque canónico stub: expone atributos con valores de prueba."""
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


@dataclass
class _FakeRecord:
    """Registro canónico stub."""
    identity: Any = field(default_factory=lambda: _FakeBlock(
        dni="29364426",
        cuil="20293644269",
        first_name="Luciano",
        last_name="Scandroli",
        birth_date="1982-03-03",
        gender="M",
        nationality="Argentina",
    ))
    employment: Any = field(default_factory=lambda: _FakeBlock(
        work_location="Administración",
        hire_date="2010-04-05",
        hire_type="permanente",
        job_title=None,
    ))
    address: Any = field(default_factory=lambda: _FakeBlock(
        city="Ituzaingó",
        province="Buenos Aires",
        postal_code="1714",
    ))
    contact: Any = field(default_factory=lambda: _FakeBlock(
        phone="11-3091-5036",
        email="scandroliluciano@gmail.com",
    ))
    banking: Any = field(default_factory=lambda: _FakeBlock())
    pension: Any = field(default_factory=lambda: _FakeBlock())
    documentary: Any = field(default_factory=lambda: _FakeBlock())
    meta: Any = field(default_factory=lambda: _FakeBlock())
    db_fields: Dict[str, Any] = field(default_factory=dict)
    extra_fields: Dict[str, Any] = field(default_factory=dict)
    extra_fields_metadata: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Importar Normalizer (solo la clase, no instancia)
# ---------------------------------------------------------------------------
from services.legajo.normalizer import Normalizer


class NormalizerDeduplicationTests(unittest.TestCase):
    """Suite de tests para _deduplicate_extra_fields y _normalize_extra_key."""

    def setUp(self):
        """Crea un Normalizer sin schema_manager (solo-unit)."""
        self.norm = Normalizer.__new__(Normalizer)
        # Inicializar atributos mínimos que usa el normalizer internamente
        import logging
        self.norm.job_id = "test"
        self.norm._ctx = "[TEST]"

    def _make_record(self, extra: dict, db_fields: dict = None) -> _FakeRecord:
        """Helper: crea un registro fake con extra_fields dados."""
        rec = _FakeRecord()
        rec.extra_fields = dict(extra)
        rec.db_fields = db_fields or {}
        return rec

    # ─────────────────────────────────────────────────────────────────────
    # 1. DEDUPLICACIÓN: campos ya presentes en bloques canónicos
    # ─────────────────────────────────────────────────────────────────────

    def test_eliminacion_campo_duplicado_en_bloque_canonico_por_nombre(self):
        """Un campo cuyo nombre coincide con un atributo canónico debe eliminarse."""
        rec = self._make_record({"dni": "29364426"})
        self.norm._deduplicate_extra_fields(rec)
        self.assertNotIn("DNI", rec.extra_fields, "DNI ya está en identity, debe eliminarse")
        self.assertNotIn("dni", rec.extra_fields, "dni ya está en identity, debe eliminarse")

    def test_eliminacion_campo_duplicado_variante_uppercase(self):
        """Las variantes en mayúsculas también deben identificarse como duplicados."""
        rec = self._make_record({"CUIL": "20293644269"})
        self.norm._deduplicate_extra_fields(rec)
        self.assertNotIn("CUIL", rec.extra_fields)

    def test_eliminacion_campo_ya_en_db_fields(self):
        """Si el campo ya está en db_fields, debe eliminarse de extra_fields."""
        rec = self._make_record(
            extra={"work_location": "Administración"},
            db_fields={"work_location": "Administración"}
        )
        self.norm._deduplicate_extra_fields(rec)
        self.assertNotIn("work_location", rec.extra_fields)
        self.assertNotIn("SECCIÓN", rec.extra_fields)

    def test_campo_no_duplicado_se_preserva(self):
        """Un campo genuinamente nuevo (no en bloques canónicos) debe preservarse."""
        rec = self._make_record({"COMEDOR_EMPRESA": "Sí"})
        self.norm._deduplicate_extra_fields(rec)
        self.assertIn("COMEDOR EMPRESA", rec.extra_fields,
                      "Campo no duplicado debe sobrevivir (normalizado a MAYÚSCULAS)")

    # ─────────────────────────────────────────────────────────────────────
    # 2. ELIMINACIÓN DE RUIDO / BAJO VALOR
    # ─────────────────────────────────────────────────────────────────────

    def test_eliminacion_campo_total_pagina(self):
        rec = self._make_record({"TOTAL_PAGINA": "3"})
        self.norm._deduplicate_extra_fields(rec)
        self.assertEqual(len(rec.extra_fields), 0, "Campos de paginación deben eliminarse")

    def test_eliminacion_campo_fecha_impresion(self):
        rec = self._make_record({"Fecha de Impresion": "2026-05-01"})
        self.norm._deduplicate_extra_fields(rec)
        self.assertEqual(len(rec.extra_fields), 0)

    def test_eliminacion_campo_zedil(self):
        rec = self._make_record({"ZEDIL_REF": "ABC123"})
        self.norm._deduplicate_extra_fields(rec)
        self.assertEqual(len(rec.extra_fields), 0)

    def test_eliminacion_campo_header(self):
        rec = self._make_record({"HEADER": "Empresa SA"})
        self.norm._deduplicate_extra_fields(rec)
        self.assertEqual(len(rec.extra_fields), 0)

    # ─────────────────────────────────────────────────────────────────────
    # 3. POLÍTICA GROSSING UP
    # ─────────────────────────────────────────────────────────────────────

    def test_grossing_up_afirmativo_se_conserva(self):
        """Grossing Up con valor 'Sí' debe conservarse y normalizarse."""
        rec = self._make_record({"grossing_up": "Sí"})
        self.norm._deduplicate_extra_fields(rec)
        self.assertIn("GROSSING UP", rec.extra_fields)

    def test_grossing_up_true_ingles_se_conserva(self):
        """Grossing Up con 'True' (inglés) debe conservarse y valor normalizarse a 'Sí'."""
        rec = self._make_record({"grossing_up": "True"})
        self.norm._deduplicate_extra_fields(rec)
        self.assertIn("GROSSING UP", rec.extra_fields)
        entry = rec.extra_fields["GROSSING UP"]
        val = entry.get("value") if isinstance(entry, dict) else entry
        self.assertEqual(val, "Sí")

    def test_grossing_up_negativo_se_elimina(self):
        """Grossing Up con valor 'No' o vacío debe eliminarse."""
        rec = self._make_record({"grossing_up": "No"})
        self.norm._deduplicate_extra_fields(rec)
        self.assertNotIn("GROSSING UP", rec.extra_fields)

    def test_grossing_up_false_se_elimina(self):
        rec = self._make_record({"Extra.grossing_up": "false"})
        self.norm._deduplicate_extra_fields(rec)
        self.assertNotIn("GROSSING UP", rec.extra_fields)

    def test_grossing_up_vacio_se_elimina(self):
        rec = self._make_record({"grossing_up": ""})
        self.norm._deduplicate_extra_fields(rec)
        self.assertNotIn("GROSSING UP", rec.extra_fields)

    # ─────────────────────────────────────────────────────────────────────
    # 4. FORMATEO DE CLAVES: Traducción + MAYÚSCULAS + Eliminación de 'Extra.'
    # ─────────────────────────────────────────────────────────────────────

    def test_prefijo_extra_se_elimina(self):
        """El prefijo 'Extra.' debe eliminarse de la clave."""
        rec = self._make_record({"Extra.COMEDOR": "Sí"})
        self.norm._deduplicate_extra_fields(rec)
        self.assertIn("COMEDOR", rec.extra_fields)
        self.assertNotIn("Extra.COMEDOR", rec.extra_fields)

    def test_clave_en_ingles_se_traduce_a_espanol(self):
        """Una clave en snake_case inglés debe traducirse al equivalente en español."""
        # 'pension_regime' no está en ningún bloque canónico con valor != None
        # (el bloque pension está vacío en el stub)
        rec = self._make_record({"pension_regime": "SIPA"})
        self.norm._deduplicate_extra_fields(rec)
        self.assertIn("RÉGIMEN PREVISIONAL", rec.extra_fields,
                      "pension_regime debe traducirse a RÉGIMEN PREVISIONAL")

    def test_clave_underscore_a_mayusculas(self):
        """Una clave con underscores debe convertirse a mayúsculas con espacios."""
        rec = self._make_record({"codigo_sucursal": "007"})
        self.norm._deduplicate_extra_fields(rec)
        self.assertIn("CODIGO SUCURSAL", rec.extra_fields)

    def test_normalize_extra_key_basico(self):
        """Test directo de _normalize_extra_key."""
        self.assertEqual(self.norm._normalize_extra_key("first_name"), "NOMBRE")
        self.assertEqual(self.norm._normalize_extra_key("work_location"), "SECCIÓN")
        self.assertEqual(self.norm._normalize_extra_key("Extra.dni"), "DNI")
        self.assertEqual(self.norm._normalize_extra_key("hire_date"), "FECHA DE INGRESO")
        self.assertEqual(self.norm._normalize_extra_key("mi_campo_custom"), "MI CAMPO CUSTOM")

    # ─────────────────────────────────────────────────────────────────────
    # 5. DEDUPLICACIÓN INTERNA (mismo valor, diferente clave)
    # ─────────────────────────────────────────────────────────────────────

    def test_deduplicacion_interna_mismo_valor(self):
        """Dos claves con el mismo valor deben reducirse a una sola."""
        rec = self._make_record({
            "CAMPO_A": "valor_unico_largo",
            "CAMPO_B": "valor_unico_largo",  # Mismo valor → duplicado interno
        })
        self.norm._deduplicate_extra_fields(rec)
        keys = set(rec.extra_fields.keys())
        # Solo una de las dos claves debe sobrevivir
        surviving = keys & {"CAMPO A", "CAMPO B"}
        self.assertEqual(len(surviving), 1,
                         f"Solo una de las claves duplicadas debe sobrevivir, encontradas: {surviving}")

    def test_deduplicacion_interna_no_afecta_valores_cortos(self):
        """Valores muy cortos (≤3 chars) no activan la dedup interna."""
        rec = self._make_record({
            "CODIGO_A": "ok",
            "CODIGO_B": "ok",  # Mismo valor corto → ambos sobreviven
        })
        self.norm._deduplicate_extra_fields(rec)
        # Ambos deben sobrevivir porque el valor es demasiado corto para deduplicar
        self.assertEqual(len(rec.extra_fields), 2)

    # ─────────────────────────────────────────────────────────────────────
    # 6. CAMPO EN FORMATO DICT {'value': ..., 'confidence': ...}
    # ─────────────────────────────────────────────────────────────────────

    def test_campo_en_formato_dict_enriched(self):
        """Campos en formato enriquecido {'value': x, 'source': y} deben procesarse correctamente."""
        rec = self._make_record({
            "pension_regime": {
                "value": "SIPA",
                "confidence": 90,
                "source": "ingestion",
                "detected_at": "2026-05-01T00:00:00"
            }
        })
        self.norm._deduplicate_extra_fields(rec)
        self.assertIn("RÉGIMEN PREVISIONAL", rec.extra_fields)
        entry = rec.extra_fields["RÉGIMEN PREVISIONAL"]
        self.assertIsInstance(entry, dict)
        self.assertEqual(entry.get("value"), "SIPA")

    def test_campo_duplicado_en_formato_dict_se_elimina(self):
        """Un campo enriquecido cuyo nombre ya existe en bloques canónicos debe eliminarse."""
        rec = self._make_record({
            "dni": {
                "value": "29364426",
                "confidence": 100,
                "source": "ingestion",
                "detected_at": "2026-05-01T00:00:00"
            }
        })
        self.norm._deduplicate_extra_fields(rec)
        self.assertNotIn("DNI", rec.extra_fields)
        self.assertNotIn("dni", rec.extra_fields)


if __name__ == "__main__":
    unittest.main(verbosity=2)
