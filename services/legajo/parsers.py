"""
Legajo Parsers — extracts raw data from files.
"""

import csv
import logging
import os
from abc import ABC, abstractmethod
from typing import Any, Optional, List, Dict

import xlrd
import openpyxl
from .mapping import normalize_header
from .txt_spec import TXT_577_SPEC_V1, TOTAL_LINE_WIDTH

logger = logging.getLogger(__name__)


def build_canonical_row(
    raw_row: List[Any],
    col_mapping: Optional[Dict[int, str]] = None,
    headers: Optional[List[Any]] = None,
) -> Dict[str, Any]:
    """
    Builds a row dict keyed by canonical paths.
    Mapped columns use canonical paths; unknown columns use normalized header text.
    """
    row_dict: Dict[str, Any] = {}
    for c, val in enumerate(raw_row):
        if val is None or (isinstance(val, str) and val == ""):
            continue
        if col_mapping and c in col_mapping:
            row_dict[col_mapping[c]] = val
        elif headers and c < len(headers) and headers[c]:
            norm_key = normalize_header(str(headers[c]))
            if norm_key:
                row_dict[norm_key] = val
        elif not col_mapping:
            row_dict[c] = val
    return row_dict


class BaseParser(ABC):
    @abstractmethod
    def parse(self, file_path: str, **kwargs) -> List[Any]:
        pass

    @abstractmethod
    def get_raw_sheets(self, file_path: str) -> Dict[str, List[List[Any]]]:
        pass


class ExcelParser(BaseParser):
    def parse(self, file_path: str, sheet_name: Optional[str] = None, 
              header_row: Optional[int] = None, raw: bool = False,
              col_mapping: Optional[Dict[int, str]] = None,
              raw_rows: Optional[List[List[Any]]] = None, **kwargs) -> List[Any]:
        if raw_rows is not None:
            return self._parse_grid(raw_rows, header_row, raw, col_mapping)
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".xls":
            return self._parse_xls(file_path, sheet_name, header_row, raw, col_mapping)
        elif ext == ".xlsx":
            return self._parse_xlsx(file_path, sheet_name, header_row, raw, col_mapping)
        else:
            raise ValueError(f"Formato Excel no soportado: {ext}")

    def _parse_grid(self, raw_rows: List[List[Any]], header_row: Optional[int],
                    raw: bool, col_mapping: Optional[Dict[int, str]]) -> List[Any]:
        if raw:
            return raw_rows
        headers = None
        start_row = 0
        if header_row is not None and header_row < len(raw_rows):
            headers = raw_rows[header_row]
            start_row = header_row + 1
        rows = []
        for raw_row in raw_rows[start_row:]:
            if not any(v is not None and v != "" for v in raw_row):
                continue
            if col_mapping:
                row_dict = build_canonical_row(list(raw_row), col_mapping, headers)
            elif headers:
                row_dict = build_canonical_row(list(raw_row), None, headers)
            else:
                row_dict = {c: v for c, v in enumerate(raw_row)}
            if row_dict:
                rows.append(row_dict)
        return rows

    def get_raw_sheets(self, file_path: str) -> Dict[str, List[List[Any]]]:
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".xls":
            wb = xlrd.open_workbook(file_path, formatting_info=False)
            sheets = {}
            for name in wb.sheet_names():
                sh = wb.sheet_by_name(name)
                sheets[name] = [[sh.cell_value(r, c) for c in range(sh.ncols)] for r in range(sh.nrows)]
            return sheets
        elif ext == ".xlsx":
            wb = openpyxl.load_workbook(file_path, data_only=True, read_only=True)
            sheets = {}
            for name in wb.sheetnames:
                sh = wb[name]
                rows = []
                for row in sh.values:
                    if row is None:  # Merged cell produces None row
                        continue
                    # Replace None cells with empty string for consistency
                    rows.append([v if v is not None else "" for v in row])
                sheets[name] = rows
            wb.close()
            return sheets
        else:
            raise ValueError(f"Formato Excel no soportado: {ext}")

    def _parse_xls(self, file_path: str, sheet_name: Optional[str], 
                   header_row: Optional[int], raw: bool,
                   col_mapping: Optional[Dict[int, str]] = None) -> List[Any]:
        wb = xlrd.open_workbook(file_path, formatting_info=False)
        sh = wb.sheet_by_name(sheet_name) if sheet_name else wb.sheet_by_index(0)
        grid = [[sh.cell_value(r, c) for c in range(sh.ncols)] for r in range(sh.nrows)]
        return self._parse_grid(grid, header_row, raw, col_mapping)

    def _parse_xlsx(self, file_path: str, sheet_name: Optional[str], 
                    header_row: Optional[int], raw: bool,
                    col_mapping: Optional[Dict[int, str]] = None) -> List[Any]:
        wb = openpyxl.load_workbook(file_path, data_only=True, read_only=True)
        sh = wb[sheet_name] if sheet_name else wb.active
        grid = []
        for row in sh.values:
            if row is None:
                continue
            grid.append([v if v is not None else "" for v in row])
        wb.close()
        return self._parse_grid(grid, header_row, raw, col_mapping)


class CsvParser(BaseParser):
    def parse(self, file_path: str, header_row: Optional[int] = None, 
              raw: bool = False, col_mapping: Optional[Dict[int, str]] = None,
              raw_rows: Optional[List[List[Any]]] = None, **kwargs) -> List[Any]:
        if raw_rows is not None:
            return self._parse_grid(raw_rows, header_row, raw, col_mapping)
        encodings = ["utf-8-sig", "utf-8", "latin-1", "cp1252"]
        for enc in encodings:
            try:
                with open(file_path, "r", encoding=enc) as f:
                    content = f.read(4000)
                    f.seek(0)
                    
                    dialect = None
                    try:
                        sniffer = csv.Sniffer()
                        dialect = sniffer.sniff(content, delimiters=",; \t")
                    except Exception:
                        # Fallback to semicolon if we see it, otherwise comma
                        if ";" in content and content.count(";") > content.count(","):
                            dialect = csv.excel
                            dialect.delimiter = ";"
                        else:
                            dialect = csv.excel
                    
                    reader = csv.reader(f, dialect=dialect)
                    reader_raw = list(reader)
                    if not reader_raw: return []
                    
                    if raw:
                        return [list(row) for row in reader_raw]
                    
                    return self._parse_grid(reader_raw, header_row, False, col_mapping)
            except Exception:
                continue
        raise ValueError(f"No se pudo parsear CSV: {file_path}")

    def _parse_grid(self, raw_rows: List[List[Any]], header_row: Optional[int],
                    raw: bool, col_mapping: Optional[Dict[int, str]]) -> List[Any]:
        if raw:
            return [list(row) for row in raw_rows]
        headers = None
        start_idx = 0
        if header_row is not None and header_row < len(raw_rows):
            headers = raw_rows[header_row]
            start_idx = header_row + 1
        rows = []
        for row_vals in raw_rows[start_idx:]:
            if not any(str(v).strip() for v in row_vals if v is not None):
                continue
            if col_mapping:
                row_dict = build_canonical_row(list(row_vals), col_mapping, headers)
            elif headers:
                row_dict = build_canonical_row(list(row_vals), None, headers)
            else:
                row_dict = {c: v for c, v in enumerate(row_vals)}
            if row_dict:
                rows.append(row_dict)
        return rows

    def get_raw_sheets(self, file_path: str) -> Dict[str, List[List[Any]]]:
        return {"csv": self.parse(file_path, raw=True)}

class TxtParser(BaseParser):
    def parse(self, file_path: str, raw: bool = False, **kwargs) -> List[Any]:
        encodings = ["utf-8-sig", "utf-8", "latin-1", "cp1252"]
        for enc in encodings:
            try:
                with open(file_path, "r", encoding=enc) as f:
                    # splitlines() is safer than readlines() for various OS line endings
                    # and it preserves trailing spaces while removing the newline
                    lines = [line for line in f.read().splitlines() if line.strip()]
                    if not lines: return []

                    # Detect if this is the Fixed-Width 577 format
                    first_len = len(lines[0])
                    logger.info(f"TXT Trace: first_line_len={first_len}, expected={TOTAL_LINE_WIDTH}")
                    
                    is_fixed = all(abs(len(line) - TOTAL_LINE_WIDTH) <= 2 for line in lines[:20])
                    
                    if is_fixed:
                        logger.info("Fixed-width 577 format detected in TXT file.")
                        grid = []
                        # Human-readable header for Normalizer to detect Tabular Mode correctly
                        # (Using simple names that match SEMANTIC_FIELD_MAP aliases)
                        header = [f.canonical_field.split('.')[-1] for f in TXT_577_SPEC_V1]
                        
                        for line in lines:
                            row_vals = []
                            for spec in TXT_577_SPEC_V1:
                                start = spec.start - 1
                                end = start + spec.length
                                if len(line) < end: 
                                    row_vals.append(None)
                                    continue
                                val = line[start:end].strip()
                                # Clean up null-fill values (e.g., '000000')
                                if val == spec.null_fill:
                                    val = None
                                row_vals.append(val)
                        if raw:
                            # We MUST return the header so SheetSelectionEngine (ImportService) 
                            # can detect keywords like "dni" or "cuil" in the first row. 
                            # This also allows Normalizer to find a header row (Score > 300).
                            return [header] + grid
                        else:
                            # Return list of dicts for tabular ingestion
                            return [dict(zip(header, row)) for row in grid]
                    
                    if raw:
                        # Return as a 1-column grid for FormParser compatibility
                        return [[line] for line in lines]
                    
                    # If not raw, just return rows of dicts {line: line} (minimal support)
                    return [{ "content": line } for line in lines]
            except Exception as e:
                logger.warning(f"Error parsing TXT with encoding {enc}: {e}")
                continue
        raise ValueError(f"No se pudo parsear TXT: {file_path}")

    def get_raw_sheets(self, file_path: str) -> Dict[str, List[List[Any]]]:
        return {"text": self.parse(file_path, raw=True)}


class ParserFactory:
    @staticmethod
    def get_parser(file_path: str) -> BaseParser:
        ext = os.path.splitext(file_path)[1].lower()
        if ext in [".xls", ".xlsx"]: return ExcelParser()
        if ext == ".csv": return CsvParser()
        if ext == ".txt": return TxtParser()
        raise ValueError(f"Extensión no soportada: {ext}. Formatos válidos: .xls, .xlsx, .csv, .txt")

