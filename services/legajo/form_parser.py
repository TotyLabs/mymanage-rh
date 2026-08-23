import logging
import re
import math
import xlrd
from typing import Any, Optional, Dict, List, Tuple
from .mapping import SEMANTIC_FIELD_MAP, DIRECT_FIELD_MAP, ScoringMatcher, normalize_header

logger = logging.getLogger(__name__)

# --- Configuration ---
MAX_FORM_SCAN_COLS = 50
MIN_ROW_DISTANCE = 15
MAX_SEGMENT_ROWS = 100
MIN_SEGMENT_SCORE = 60
MAX_EXTRA_UNMAPPED = 20

class FormParser:
    """
    FormParser — Industrial Refactor (Block-First Strategy).
    
    Identifies records using 'Nombre Empleado' as the primary boundary marker.
    Extraction is strictly scoped within detected blocks to ensure data isolation.
    """

    def __init__(self, mapping_version: str = "3", job_id: str = None):
        self.mapping_version = mapping_version
        self.matcher = ScoringMatcher(SEMANTIC_FIELD_MAP, DIRECT_FIELD_MAP)
        self.job_id = job_id or "unknown"
        self._ctx = f"[IMPORT {self.job_id}]"

    # ---------------------------------------------------------------------
    # AUXILIARY HEURISTICS
    # ---------------------------------------------------------------------
    def _match_label(self, cell_val: Any) -> Tuple[Optional[str], int]:
        if cell_val is None or not isinstance(cell_val, str):
            return None, 0
        return self.matcher.match_header(cell_val)

    def _sanitize_text(self, text: Any) -> str:
        if text is None: return ""
        s = str(text).replace("\ufeff", "").replace("\u200b", "").strip()
        # Remove extra whitespace and noise
        return re.sub(r"\s+", " ", s)

    def _normalize_digits(self, val: Any) -> str:
        if val is None: return ""
        s = str(val)
        if s.endswith(".0"): s = s[:-2]
        return re.sub(r"\D", "", s)

    def _strip_accents(self, s: str) -> str:
        import unicodedata
        return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")

    def _looks_like_person_name(self, text: str) -> bool:
        if not text: return False
        norm_val = self._strip_accents(text).upper()
        
        # Expanded Blacklist (Non-human labels often found in payroll sheets)
        NOISE = [
            "OP", "OPERARIO", "ADMIN", "ADMINISTRACION", "MIXER", "JEFE", "SUPERVISOR", 
            "TECNICO", "OBRA", "PLANTA", "SECTOR", "AREA", "ÁREA", "BUENOS AIRES", "CAPITAL", 
            "CABA", "PROVINCIA", "ARGENTINA", "DATOS", "INFORMACION", "IDENTIFICACION", 
            "OBRA SOCIAL", "PLANILLA", "CONCEPTO", "EMPRESA", "FICHA", "INGRESO", "BAJA", 
            "TOTAL", "PAGINA", "FECHA", "CONTROL", "REPETIR", "DOMICILIO", "NACIMIENTO", 
            "AÑOS", "EFECTIVO", "HUMANA", "CONSTRUCCION", "OBREROS", "ZONA", "VZ HUMANA"
        ]
        if any(noise in norm_val for noise in NOISE):
            return False

        words = text.replace(",", " ").split()
        if len(words) < 2: return False
        if any(any(ch.isdigit() for ch in w) for w in words): return False
        
        # Heuristic: Valid words are usually > 2 chars
        alpha_words = [w for w in words if w.upper() not in {"DE", "LA", "Y", "DEL"}]
        if any(len(w) <= 2 for w in alpha_words): return False
        
        return True

    def _is_label_like(self, val: Any) -> bool:
        if not isinstance(val, str): return False
        s = val.strip()
        if not s: return False
        return s.endswith(":") or len(s) < 20 and self._match_label(s)[0] is not None

    def _looks_like_date_text(self, val: Any) -> bool:
        if isinstance(val, (int, float)):
            return 10000 < val < 60000 # Excel date serials
        s = str(val).lower()
        return any(k in s for k in ["/", "-", ".", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"])

    # ---------------------------------------------------------------------
    # BLOCK DETECTION (BLOCK-FIRST STRATEGY)
    # ---------------------------------------------------------------------
    def _detect_blocks(self, grid: List[List[Any]]) -> List[int]:
        """
        Identifies block boundaries by searching for the 'Nombre Empleado' label.
        This is the foundation of the Block-First Strategy.
        """
        block_starts = []
        for r in range(len(grid)):
            row = grid[r]
            for c_idx, cell in enumerate(row[:MAX_FORM_SCAN_COLS]):
                if cell is None: continue
                label, confidence = self._match_label(cell)
                if label == "identity.full_name" and confidence >= 85:
                    block_starts.append(r)
                    break
        return block_starts

    # ---------------------------------------------------------------------
    # SCOPED EXTRACTION CORE
    # ---------------------------------------------------------------------
    def _extract_segment(self, raw_grid: List[List[Any]], global_grid: List[List[Any]] = None, start_row: int = 0) -> Dict[str, Any]:
        """Wrapper with timeout safety."""
        import time
        start = time.time()
        def check_timeout():
            if time.time() - start > 20: raise TimeoutError("Segment processing timeout")
        return self._extract_segment_internal(raw_grid, global_grid, start_row, check_timeout)

    def _extract_segment_internal(self, raw_grid: List[List[Any]], global_grid: List[List[Any]] = None, start_row: int = 0, check_timeout=None) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        used_coords = set()
        label_cache = {}

        def get_label(cell_val):
            key = str(cell_val)
            if key in label_cache: return label_cache[key]
            res = self._match_label(cell_val)
            label_cache[key] = res
            return res

        # 🥇 Regla: Legajo explícito primero (Hardened)
        legajo_data = self._extract_legajo_explicit(raw_grid, global_grid, start_row, used_coords)
        if legajo_data:
            data["legajo"] = legajo_data["value"]
            # Only track used coords if it was INSIDE the block (relative r_idx in extract_legajo)
            # Actually, extract_legajo returns global coords now.
            # But here we are inside _extract_segment where raw_grid is a SLICE.
            # So used_coords must be relative to the slice.
            # I'll just avoid updating used_coords for legajo if it was found ABOVE.

        # PASS 1: Canonical Mapping
        for r_idx, row in enumerate(raw_grid):
            if check_timeout: check_timeout()
            for c_idx, cell in enumerate(row[:MAX_FORM_SCAN_COLS]):
                if cell is None or (r_idx, c_idx) in used_coords: continue

                label_path, confidence = get_label(cell)
                if not label_path or confidence <= 70: continue

                clean_key = label_path.split(".")[-1]
                used_coords.add((r_idx, c_idx))

                # Extract Value
                best_val = self._find_value_for_label(raw_grid, r_idx, c_idx, label_path, used_coords)
                if best_val:
                    data[clean_key] = best_val

        # Post-Process specific to segment
        if "full_name" in data: data = self._resolve_full_name(data)
        data = self._normalize_numeric_values(data)
        data = self._semantic_validate_record(data)

        return data

    def _find_value_for_label(self, grid, r, c, label_path, used_coords):
        """Scans adjacent and row-wide cells for the best candidate value."""
        best_val = None
        best_score = -1

        candidates = self._get_candidates(grid, r, c)
        for cand_r, cand_c, cand_val in candidates:
            if cand_val is None or cand_val == "" or (cand_r, cand_c) in used_coords: continue
            
            # Avoid labels acting as values
            if self._is_label_like(cand_val): continue

            val_score = self._score_value_candidate(label_path, cand_val)
            pos_score = self._score_candidate_position(r, c, cand_r, cand_c)
            
            # Row-wide penalty
            if cand_r == r and abs(cand_c - c) > 35: pos_score -= 15
            
            total = val_score + pos_score
            if total > best_score:
                best_score = total
                best_val = (cand_r, cand_c, cand_val)

        if best_val and best_score >= 50:
            cr, cc, cv = best_val
            used_coords.add((cr, cc))
            return cv
        return None

    def _get_candidates(self, grid, r, c):
        candidates = []
        # Right (Stretched)
        for dc in range(1, 36):
            if c + dc < len(grid[r]): candidates.append((r, c + dc, grid[r][c + dc]))
        # Below
        for dr in range(1, 4):
            if r + dr < len(grid):
                for dc in range(-2, 10):
                    if 0 <= c + dc < len(grid[r + dr]): candidates.append((r + dr, c + dc, grid[r + dr][c + dc]))
        return candidates

    def _score_value_candidate(self, label_path, val) -> int:
        clean = str(val).strip()
        if not clean: return 0
        
        if "dni" in label_path or "document_number" in label_path:
            digits = self._normalize_digits(val)
            return 90 if 7 <= len(digits) <= 9 else 0
        if "cuil" in label_path:
            digits = self._normalize_digits(val)
            return 100 if len(digits) == 11 else 0
        if "full_name" in label_path:
            return 80 if self._looks_like_person_name(clean) else 10
        if "date" in label_path:
            # Score dates higher to avoid picking up random numbers
            return 95 if self._looks_like_date_text(val) else 0
        if "account_number" in label_path:
            digits = self._normalize_digits(val)
            return 90 if 1 <= len(digits) <= 20 else 0
        if "bank_alias" in label_path:
            clean_alias = str(val).strip()
            return 90 if len(clean_alias) >= 3 and not clean_alias.isdigit() else 0
        if "union_number" in label_path or "health_insurance_number" in label_path:
            digits = self._normalize_digits(val)
            return 90 if 1 <= len(digits) <= 15 else 0
        return 50

    def _score_candidate_position(self, lr, lc, cr, cc) -> int:
        if cr == lr: return 40 # Inline
        if cr == lr + 1: return 20 # Below
        return 5

    # ---------------------------------------------------------------------
    # LEGAJO DETECTION
    # ---------------------------------------------------------------------
    def _extract_legajo_explicit(self, block_grid: List[List[Any]], global_grid: List[List[Any]], start_row: int, used_coords: set) -> Optional[Dict[str, Any]]:
        LEG_LABELS = ["LEGAJO", "N° LEGAJO", "NRO LEGAJO", "N° LEG.", "NRO. LEG.", "LEGO.", "LEG."]
        
        # 1. Search INSIDE the block
        res = self._search_legajo_in_grid(block_grid, used_coords)
        if res: return res
        
        # 2. Bounded Upward Fallback (max 10 rows above start)
        lookback = min(10, start_row)
        if lookback > 0:
            above_grid = global_grid[start_row - lookback : start_row]
            res = self._search_legajo_in_grid(above_grid, used_coords, offset_r=(start_row - lookback))
            if res:
                logger.info(f"{self._ctx} LEGAJO_FALLBACK: Found Legajo {res['value']} in upward scan (-{lookback} rows)")
                return res
        return None

    def _search_legajo_in_grid(self, grid: List[List[Any]], used_coords: set, offset_r: int = 0) -> Optional[Dict[str, Any]]:
        LEG_LABELS = ["LEGAJO", "N° LEGAJO", "NRO LEGAJO", "N° LEG.", "NRO. LEG.", "LEGO.", "LEG."]
        for r_idx, row in enumerate(grid):
            for c_idx, cell in enumerate(row[:MAX_FORM_SCAN_COLS]):
                if not isinstance(cell, str): continue
                cell_upper = cell.upper()
                if any(lbl in cell_upper for lbl in LEG_LABELS):
                    # Inline?
                    if ":" in cell:
                        val = self._normalize_digits(cell.split(":", 1)[1])
                        if 1 <= len(val) <= 10: return {"value": val, "coords": {(r_idx + offset_r, c_idx)}}
                    # Adjacent (Increase range for wide forms)
                    for dc in range(1, 36):
                        if c_idx + dc < len(row):
                            val = self._normalize_digits(row[c_idx + dc])
                            if 1 <= len(val) <= 10: return {"value": val, "coords": {(r_idx + offset_r, c_idx), (r_idx + offset_r, c_idx + dc)}}
        return None

    # ---------------------------------------------------------------------
    # PUBLIC API
    # ---------------------------------------------------------------------
    def extract(self, raw_grid: List[List[Any]], job_id: str = None) -> List[Dict[str, Any]]:
        if job_id:
            self.job_id = job_id
            self._ctx = f"[IMPORT {self.job_id}]"

        block_starts = self._detect_blocks(raw_grid)
        logger.info(f"{self._ctx} BLOCK_SCAN: Detected {len(block_starts)} employee blocks.")

        if not block_starts:
            logger.error(f"{self._ctx} BLOCK_SCAN: Fatal error - No 'Nombre Empleado' markers found.")
            return []

        records = []
        for i, start_row in enumerate(block_starts):
            end_row = block_starts[i+1] if i+1 < len(block_starts) else len(raw_grid)
            if end_row - start_row > MAX_SEGMENT_ROWS: end_row = start_row + MAX_SEGMENT_ROWS

            logger.info(f"{self._ctx} BLOCK_DETECTED: Rows {start_row}-{end_row}")

            # ❗ Reset Context
            current_employee = {
                "full_name": None,
                "cuil": None,
                "dni": None,
                "legajo": None,
                "document_number": None,
                "account_number": None,
                "bank_alias": None,
                "union_number": "NO",
                "health_insurance_number": "NO",
                "_parser_status": "valid"
            }
            
            try:
                block_grid = raw_grid[start_row:end_row]
                record_data = self._extract_segment(block_grid, raw_grid, start_row)
                current_employee.update(record_data)
            except Exception as e:
                logger.error(f"{self._ctx} BLOCK_ERROR: Row {start_row} - {e}")
                continue

            # Build a canonical full_name when only first/last were extracted
            if not current_employee.get("full_name"):
                first_name = current_employee.get("first_name")
                last_name = current_employee.get("last_name")
                if first_name and last_name:
                    current_employee["full_name"] = f"{first_name} {last_name}".strip()

            # Validation AFTER extraction
            name = str(current_employee.get("full_name") or "").strip()
            dni = current_employee.get("dni")
            cuil = current_employee.get("cuil")
            legajo = current_employee.get("legajo")

            if not name or not self._looks_like_person_name(name):
                logger.error(f"{self._ctx} BLOCK_INVALID: Row {start_row} - Missing or Invalid Name.")
                current_employee["_parser_status"] = "invalid"
                current_employee["error"] = "Nombre inválido o faltante"
                records.append(current_employee)
                continue

            if not dni and not cuil:
                logger.error(f"{self._ctx} BLOCK_INVALID: Row {start_row} - Missing Identity (DNI/CUIL).")
                current_employee["_parser_status"] = "invalid"
                current_employee["error"] = "DNI y CUIL faltantes"
                records.append(current_employee)
                continue

            # Field Missing Logs
            if not legajo:
                logger.warning(f"{self._ctx} FIELD_MISSING: 'legajo' at Row {start_row} for {name}")
            if not dni:
                logger.warning(f"{self._ctx} FIELD_MISSING: 'dni' at Row {start_row} for {name}")
            if not cuil:
                logger.warning(f"{self._ctx} FIELD_MISSING: 'cuil' at Row {start_row} for {name}")

            records.append(current_employee)
            logger.info(f"{self._ctx} BLOCK_VALID: {name} (CUIL: {cuil or 'N/A'}, Legajo: {legajo or 'N/A'})")

        return self._final_hardening(records)

    def parse(self, file_path: str = None, raw_rows: List[List[Any]] = None, job_id: str = None, sheet_name: str = None, **kwargs) -> List[Dict[str, Any]]:
        """Compatibility alias for FormParser.extract().

        If raw_rows are provided, it extracts from them directly.
        Otherwise it reads the first sheet from the given file_path.
        """
        if job_id:
            self.job_id = job_id
            self._ctx = f"[IMPORT {self.job_id}]"

        if raw_rows is None:
            if not file_path:
                raise ValueError("FormParser.parse requiere raw_rows o file_path")
            from .parsers import ParserFactory
            parser = ParserFactory.get_parser(file_path)
            sheets = parser.get_raw_sheets(file_path)
            if sheet_name:
                if sheet_name not in sheets:
                    raise ValueError(f"Sheet '{sheet_name}' no encontrada en {file_path}")
                raw_rows = sheets[sheet_name]
            else:
                raw_rows = next(iter(sheets.values()))

        return self.extract(raw_rows, job_id=job_id)

    # ---------------------------------------------------------------------
    # REFINEMENT & HARDENING
    # ---------------------------------------------------------------------
    def _resolve_full_name(self, data: Dict[str, Any]) -> Dict[str, Any]:
        fn = data.get("full_name")
        if not fn or not isinstance(fn, str): return data
        if "," in fn:
            parts = fn.split(",", 1)
            data["last_name"] = parts[0].strip()
            data["first_name"] = parts[1].strip()
        else:
            parts = fn.rsplit(None, 1)
            if len(parts) > 1:
                data["first_name"] = parts[0].strip()
                data["last_name"] = parts[1].strip()
        return data

    def _normalize_numeric_values(self, data: Dict[str, Any]) -> Dict[str, Any]:
        for k in ["dni", "cuil", "legajo", "postal_code", "cbu", "account_number", "ieric_number", "union_number", "health_insurance_number", "document_number"]:
            if k in data and data[k] != "NO" and data[k] is not None:
                data[k] = self._normalize_digits(data[k])
        return data

    def _semantic_validate_record(self, data: Dict[str, Any]) -> Dict[str, Any]:
        if data.get("dni") and not (7 <= len(data["dni"]) <= 9): data.pop("dni", None)
        if data.get("cuil") and len(data["cuil"]) != 11: data.pop("cuil", None)

        # Autocomplete DNI <-> document_number
        dni_val = data.get("dni")
        doc_num_val = data.get("document_number")
        if dni_val and not doc_num_val:
            data["document_number"] = dni_val
        elif doc_num_val and not dni_val:
            data["dni"] = doc_num_val
        elif dni_val and doc_num_val:
            data["document_number"] = dni_val

        # Nro Afiliado rule: if has a number, set it; otherwise, default to "NO"
        for k in ["union_number", "health_insurance_number"]:
            val = str(data.get(k) or "").strip()
            digits = self._normalize_digits(val)
            if digits:
                data[k] = digits
            else:
                data[k] = "NO"

        return data

    def _normalize_date_text(self, val: Any) -> Optional[str]:
        if not val: return None
        s = str(val).lower().strip()
        
        # Spanish month mapping
        months = {
            "enero": "01", "febrero": "02", "marzo": "03", "abril": "04",
            "mayo": "05", "junio": "06", "julio": "07", "agosto": "08",
            "septiembre": "09", "octubre": "10", "noviembre": "11", "diciembre": "12",
            "setiembre": "09" # common variant
        }
        
        # Handle "DD-mes-YYYY" or "DD/mes/YYYY"
        for m_name, m_num in months.items():
            if m_name in s:
                s = s.replace(m_name, m_num)
        
        # Clean non-digits for standard formatting
        s = re.sub(r"[^0-9/.\-]", " ", s).strip()
        parts = re.split(r"[\s/.\-]+", s)
        
        if len(parts) == 3:
            d, m, y = parts
            # Ensure 4-digit year
            if len(y) == 2: y = "20" + y if int(y) < 50 else "19" + y
            if len(d) == 1: d = "0" + d
            if len(m) == 1: m = "0" + m
            return f"{y}-{m}-{d}"
            
        return None

    def _final_hardening(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Garantiza que las fechas y nombres estén normalizados antes de salir del parser.
        """
        for r in records:
            # Normalización de Fechas
            for key in ("birth_date", "hire_date"):
                if key in r:
                    val = r[key]
                    if hasattr(val, "strftime"):
                        r[key] = val.strftime("%Y-%m-%d")
                    else:
                        norm = self._normalize_date_text(val)
                        if norm:
                            r[key] = norm
                        else:
                            r.pop(key, None)
        return records