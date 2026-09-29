"""
Tests for Legajo FormParser changes:
1. NRO DOC autocomplete / DNI alignment.
2. NRO AFILIADO (union_number and health_insurance_number) defaulting to 'NO' if missing, and setting the normalized number if present.
3. NRO CUENTA and ALIAS detection, extraction and normalization.
"""

import sys
import os
import unittest

# Bootstrap: add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.legajo.form_parser import FormParser

class FormParserExtractionTests(unittest.TestCase):
    def setUp(self):
        self.parser = FormParser(mapping_version="3")

    def test_form_parser_extraction_success(self):
        # Create a mock 2D grid simulating an employee form block
        # Columns:
        # Row 0: Header marker to detect block
        # Row 1: Nombre y Apellido
        # Row 2: DNI and CUIL
        # Row 3: Nro. Afiliado (for OS)
        # Row 4: NRO CUENTA and ALIAS
        grid = [
            ["Nombre Empleado", "", "", "", "", "", ""],
            ["Luciano Scandroli", "", "", "", "", "", ""],
            ["DNI:", "29364426", "CUIL:", "20-29364426-9", "", "", ""],
            ["Nro. Afiliado:", "99887766", "", "", "", "", ""],
            ["Nro IERIC:", "9876543210", "", "", "", "", ""],
            ["NRO CUENTA:", "1234-5678", "ALIAS:", "luciano.alias.pay", "", "", ""],
        ]
        
        # We need to padd rows to have enough columns (FormParser loops over raw_grid and scans columns)
        padded_grid = []
        for row in grid:
            padded_grid.append(row + [""] * 40)
            
        records = self.parser.extract(padded_grid)
        self.assertEqual(len(records), 1)
        rec = records[0]
        
        # 1. Check Full Name
        self.assertEqual(rec.get("full_name"), "Luciano Scandroli")
        self.assertEqual(rec.get("first_name"), "Luciano")
        self.assertEqual(rec.get("last_name"), "Scandroli")
        
        # 2. Check DNI and CUIL normalization
        self.assertEqual(rec.get("dni"), "29364426")
        self.assertEqual(rec.get("cuil"), "20293644269")
        
        # 3. Check NRO DOC autocomplete
        self.assertEqual(rec.get("document_number"), "29364426")
        
        # 4. Check NRO AFILIADO logic:
        # health_insurance_number is found -> set to number (normalized to digits)
        self.assertEqual(rec.get("health_insurance_number"), "99887766")
        # union_number not found -> set to "NO"
        self.assertEqual(rec.get("union_number"), "NO")
        
        # 5. Check NRO CUENTA and ALIAS logic
        self.assertEqual(rec.get("account_number"), "12345678")
        self.assertEqual(rec.get("bank_alias"), "luciano.alias.pay")
        self.assertEqual(rec.get("ieric_number"), "9876543210")

    def test_form_parser_missing_dni_uses_nro_doc(self):
        # Simulated grid where DNI label is missing but NRO DOC is present
        grid = [
            ["Nombre Empleado", "", "", "", "", "", ""],
            ["Luciano Scandroli", "", "", "", "", "", ""],
            ["NRO DOC:", "29364426", "CUIL:", "20-29364426-9", "", "", ""],
        ]
        padded_grid = [row + [""] * 40 for row in grid]
        
        records = self.parser.extract(padded_grid)
        self.assertEqual(len(records), 1)
        rec = records[0]
        
        # Should autocomplete DNI from document_number (NRO DOC)
        self.assertEqual(rec.get("document_number"), "29364426")
        self.assertEqual(rec.get("dni"), "29364426")
        
        # Affiliate numbers should default to "NO"
        self.assertEqual(rec.get("union_number"), "NO")
        self.assertEqual(rec.get("health_insurance_number"), "NO")

    def test_form_parser_parse_alias_reads_xls_file(self):
        parser = FormParser(mapping_version="3")
        records = parser.parse(file_path=os.path.join(os.path.dirname(__file__), "fichaempleadozedil.xls"))
        self.assertGreater(len(records), 0)
        self.assertIn("address_number", records[0])
        self.assertIn("full_name", records[0])
        self.assertTrue(records[0].get("full_name"))

    def test_hormicret_task_category_and_hire_date(self):
        workbook_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "fichaempleadohormicret.xls")
        if not os.path.exists(workbook_path):
            self.skipTest("Local Hormicret workbook is not available")

        records = self.parser.parse(file_path=workbook_path)
        employee = next(record for record in records if record.get("legajo") == "9")

        self.assertEqual(employee.get("full_name"), "IBARRA, RAMON ENRIQUE")
        self.assertEqual(employee.get("task"), "SERENO")
        self.assertEqual(employee.get("job_title"), "SERENO")
        self.assertEqual(employee.get("category"), "NIVEL B")
        self.assertEqual(employee.get("hire_date"), "2020-08-03")

        first_category = next(record for record in records if record.get("legajo") == "2")
        second_category = next(record for record in records if record.get("legajo") == "26")
        initial_name = next(record for record in records if record.get("legajo") == "66")
        self.assertEqual(first_category.get("category"), "1ER CATEGORIA")
        self.assertEqual(second_category.get("category"), "MAESTRANZA 2DA")
        self.assertEqual(second_category.get("job_title"), "MAESTRANZA")
        self.assertNotEqual(initial_name.get("_parser_status"), "invalid")


from services.legajo.parsers import ExcelParser
from services.legajo.normalizer import Normalizer
from services.legajo.validator import Validator

class ExcelParserTabularTests(unittest.TestCase):
    def setUp(self):
        self.parser = ExcelParser()
        self.normalizer = Normalizer()
        self.validator = Validator()

    def test_tabular_parser_standard_address_number(self):
        # Case 1: Tabular format with "Número" or "Nro" or "Altura"
        # Columns: DNI, Cuil, Nombre, Apellido, Calle, Altura
        raw_rows = [
            ["DNI", "CUIL", "Nombre", "Apellido", "Calle", "Nro"],
            ["29364426", "20-29364426-9", "Luciano", "Scandroli", "Limay", "504"],
            ["30111222", "27301112229", "Maria", "Gomez", "Av. Mayo", "1024 Bis"],
            ["31111222", "20311112229", "Juan", "Perez", "Ruta 3", "Km 42"]
        ]
        
        # Detect header row and mapping
        idx, mapping, conf, labels = self.normalizer.detect_header_row(raw_rows)
        self.assertEqual(idx, 0)
        self.assertIn("address.address_number", mapping.values())
        
        # Parse using the detected mapping
        parsed = self.parser.parse("test.xlsx", raw_rows=raw_rows, header_row=idx, col_mapping=mapping)
        self.assertEqual(len(parsed), 3)
        
        # Verify first row
        rec1 = self.normalizer.normalize_row(parsed[0], 2)
        self.assertEqual(rec1.address.address, "Limay")
        self.assertEqual(rec1.address.address_number, "504")
        
        # Verify second row (alphanumeric "1024 Bis")
        rec2 = self.normalizer.normalize_row(parsed[1], 3)
        self.assertEqual(rec2.address.address, "Av. Mayo")
        self.assertEqual(rec2.address.address_number, "1024 Bis")
        
        # Verify third row (alphanumeric "Km 42")
        rec3 = self.normalizer.normalize_row(parsed[2], 4)
        self.assertEqual(rec3.address.address, "Ruta 3")
        self.assertEqual(rec3.address.address_number, "Km 42")

    def test_tabular_parser_detects_nro_ieric_header(self):
        raw_rows = [
            ["DNI", "CUIL", "Nro IERIC", "Nombre"],
            ["29364426", "20-29364426-9", "9876543210", "Luciano"],
            ["30111222", "27301112229", "8765432109", "Maria"]
        ]
        idx, mapping, conf, labels = self.normalizer.detect_header_row(raw_rows)
        self.assertEqual(idx, 0)
        self.assertIn("extra.ieric_number", mapping.values())

        parsed = self.parser.parse("test.xlsx", raw_rows=raw_rows, header_row=idx, col_mapping=mapping)
        self.assertEqual(len(parsed), 2)

        rec1 = self.normalizer.normalize_row(parsed[0], 2)
        self.assertEqual(rec1.extra_fields.get("NRO IERIC"), "9876543210")

        rec2 = self.normalizer.normalize_row(parsed[1], 3)
        self.assertEqual(rec2.extra_fields.get("NRO IERIC"), "8765432109")

    def test_tabular_parser_permuted_columns(self):
        # Case 2: Permuted columns order
        raw_rows = [
            ["Nro", "Calle", "Apellido", "Nombre", "CUIL", "DNI"],
            ["504", "Limay", "Scandroli", "Luciano", "20-29364426-9", "29364426"]
        ]
        idx, mapping, conf, labels = self.normalizer.detect_header_row(raw_rows)
        self.assertEqual(idx, 0)
        self.assertIn("address.address_number", mapping.values())
        
        parsed = self.parser.parse("test.xlsx", raw_rows=raw_rows, header_row=idx, col_mapping=mapping)
        self.assertEqual(len(parsed), 1)
        rec = self.normalizer.normalize_row(parsed[0], 2)
        self.assertEqual(rec.address.address, "Limay")
        self.assertEqual(rec.address.address_number, "504")

    def test_tabular_parser_missing_address_number(self):
        # Case 3: Missing address_number column
        raw_rows = [
            ["DNI", "CUIL", "Nombre", "Apellido", "Calle"],
            ["29364426", "20-29364426-9", "Luciano", "Scandroli", "Limay"]
        ]
        idx, mapping, conf, labels = self.normalizer.detect_header_row(raw_rows)
        self.assertEqual(idx, 0)
        self.assertNotIn("address.address_number", mapping.values())
        
        parsed = self.parser.parse("test.xlsx", raw_rows=raw_rows, header_row=idx, col_mapping=mapping)
        self.assertEqual(len(parsed), 1)
        rec = self.normalizer.normalize_row(parsed[0], 2)
        self.assertEqual(rec.address.address, "Limay")
        self.assertIsNone(rec.address.address_number)


if __name__ == "__main__":
    unittest.main()
