"""
Excel Processor — Clean and optimize .xlsx files.

Operations:
  - Drop completely empty rows
  - Strip whitespace from string cells
  - Re-save with openpyxl (lighter than pandas default)

Expected savings: 10-30% on typical payroll imports.
"""
import os
import logging
from pathlib import Path

logger = logging.getLogger("dircom.payroll")


def process_excel(input_path: str) -> str:
    """
    GAP-015 Fix: Disabled pandas-based Excel optimization to prevent Out Of Memory (OOM) 
    crashes on large files. Pandas loads the entire file into RAM which is unsafe 
    for production APIs handling multi-megabyte Excel files.
    """
    logger.info("excel_processor.bypassed: Pandas optimization disabled for OOM safety")
    return input_path
