"""
ZIP Utilities — On-demand ZIP generation for exports.

CRITICAL RULES:
  - ZIPs are NEVER stored. They are generated on-the-fly.
  - In-memory for small files, temp file for large ones.
  - Caller is responsible for cleanup of temp files.
"""
import os
import zipfile
import tempfile
import logging
from io import BytesIO
from pathlib import Path
from typing import List

logger = logging.getLogger("dircom.payroll")

# Threshold: if total input size exceeds this, use temp file instead of memory
MEMORY_THRESHOLD = 50 * 1024 * 1024  # 50 MB


def generate_zip_stream(file_paths: List[str]) -> BytesIO:
    """
    Generates a ZIP archive in memory.
    Best for small to medium exports (<50MB total).

    Args:
        file_paths: List of absolute file paths to include

    Returns:
        BytesIO stream positioned at start, ready to send
    """
    memory_file = BytesIO()

    with zipfile.ZipFile(memory_file, "w", zipfile.ZIP_DEFLATED) as z:
        for file_path in file_paths:
            if os.path.exists(file_path):
                z.write(file_path, arcname=os.path.basename(file_path))
            else:
                logger.warning(f"zip_utils.file_missing: {file_path}")

    memory_file.seek(0)

    total = sum(os.path.getsize(f) for f in file_paths if os.path.exists(f))
    logger.info(
        f"zip_utils.stream_generated: "
        f"files={len(file_paths)} input_size={total}B zip_size={memory_file.getbuffer().nbytes}B"
    )

    return memory_file


def generate_zip_temp(file_paths: List[str]) -> str:
    """
    Generates a ZIP archive as a temporary file on disk.
    Best for large exports (>50MB total).

    Args:
        file_paths: List of absolute file paths to include

    Returns:
        Path to the temporary ZIP file.
        
        CRITICAL: The caller MUST ensure this file is deleted.
        In FastAPI, use BackgroundTasks:
        
        @router.get("/download")
        async def download(background_tasks: BackgroundTasks):
            path = generate_zip_temp(...)
            background_tasks.add_task(os.remove, path)
            return FileResponse(path)
    """
    temp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip", prefix="payroll_export_")

    with zipfile.ZipFile(temp.name, "w", zipfile.ZIP_DEFLATED) as z:
        for file_path in file_paths:
            if os.path.exists(file_path):
                z.write(file_path, arcname=os.path.basename(file_path))
            else:
                logger.warning(f"zip_utils.file_missing: {file_path}")

    total = sum(os.path.getsize(f) for f in file_paths if os.path.exists(f))
    zip_size = os.path.getsize(temp.name)
    logger.info(
        f"zip_utils.temp_generated: "
        f"files={len(file_paths)} input_size={total}B zip_size={zip_size}B "
        f"path={temp.name}"
    )

    return temp.name


def generate_zip_auto(file_paths: List[str]):
    """
    Automatically chooses between in-memory and temp file.

    Returns:
        tuple: (BytesIO or str, is_temp_file: bool)
    """
    total = sum(os.path.getsize(f) for f in file_paths if os.path.exists(f))

    if total > MEMORY_THRESHOLD:
        return generate_zip_temp(file_paths), True
    else:
        return generate_zip_stream(file_paths), False
