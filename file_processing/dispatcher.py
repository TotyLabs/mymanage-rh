"""
File Processing Dispatcher — Central routing for file optimization.

All uploaded files MUST pass through process_file() before being stored.
This ensures consistent optimization, validation, and security.
"""
import os
import shutil
import logging
import mimetypes
from pathlib import Path
from typing import Optional, Dict, Any

from file_processing.pdf import process_pdf
from file_processing.images import process_image
from file_processing.excel import process_excel
from file_processing.security import encrypt_file

logger = logging.getLogger("dircom.payroll")

# ─── Size Limits (bytes) ───
MAX_SIZE = {
    "pdf":       50 * 1024 * 1024,   # 50 MB
    "signature":  2 * 1024 * 1024,   #  2 MB
    "logo":       5 * 1024 * 1024,   #  5 MB
    "dni":       10 * 1024 * 1024,   # 10 MB
    "excel":     20 * 1024 * 1024,   # 20 MB
    "default":   25 * 1024 * 1024,   # 25 MB
}

# ─── MIME Validation ───
ALLOWED_MIMES = {
    "pdf":       {"application/pdf"},
    "signature": {"image/png", "image/jpeg", "image/webp"},
    "logo":      {"image/png", "image/jpeg", "image/webp"},
    "dni":       {"image/png", "image/jpeg", "image/webp"},
    "excel":     {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel",
        "application/octet-stream",  # fallback for .xls/.xlsx
    },
}

# ─── Storage Subdirectories ───
STORAGE_DIRS = {
    "pdf":       "receipts",
    "signature": "signatures",
    "logo":      "branding/logos",
    "dni":       "identity",
    "excel":     "imports",
}


class FileProcessingError(Exception):
    """Raised when file validation or processing fails."""
    pass


def validate_file(file_path: str, file_type: str) -> None:
    """
    Validates file size and MIME type before processing.
    Raises FileProcessingError on failure.
    """
    path = Path(file_path)

    if not path.exists():
        raise FileProcessingError(f"File not found: {file_path}")

    # Size check
    size = path.stat().st_size
    max_allowed = MAX_SIZE.get(file_type, MAX_SIZE["default"])
    if size > max_allowed:
        size_mb = size / (1024 * 1024)
        max_mb = max_allowed / (1024 * 1024)
        raise FileProcessingError(
            f"File too large: {size_mb:.1f}MB exceeds {max_mb:.0f}MB limit for type '{file_type}'"
        )

    # MIME check (best-effort, not a hard block for unknown types)
    allowed = ALLOWED_MIMES.get(file_type)
    if allowed:
        mime, _ = mimetypes.guess_type(str(path))
        if mime and mime not in allowed:
            logger.warning(
                f"file_processing.mime_mismatch: expected={allowed} got={mime} path={path.name}"
            )
            # Don't block — some systems return wrong MIME for valid files


def process_file(
    file_path: str,
    file_type: str,
    metadata: Optional[Dict[str, Any]] = None
) -> str:
    """
    Central entry point. Every file passes through here.

    Args:
        file_path: Absolute path to the uploaded file
        file_type: One of "pdf", "signature", "logo", "dni", "excel"
        metadata: Optional dict with extra context

    Returns:
        Path to the optimized file (original is deleted)

    Raises:
        FileProcessingError on validation failure
    """
    original_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0

    # 1. Validate
    validate_file(file_path, file_type)

    # 2. Process by type
    try:
        if file_type == "pdf":
            result_path = process_pdf(file_path)

        elif file_type in ("signature", "logo", "dni"):
            result_path = process_image(file_path, file_type)

        elif file_type == "excel":
            result_path = process_excel(file_path)

        else:
            # Unknown type — pass through without optimization
            logger.info(f"file_processing.passthrough: type={file_type}")
            result_path = file_path

    except FileProcessingError:
        raise
    except Exception as e:
        logger.error(f"file_processing.error: type={file_type} error={e}")
        # On processing failure, keep the original file
        return file_path

    # 3. Security: encrypt DNI files
    if file_type == "dni":
        result_path = encrypt_file(result_path)

    # 4. Log savings
    if os.path.exists(result_path):
        new_size = os.path.getsize(result_path)
        if original_size > 0:
            savings = ((original_size - new_size) / original_size) * 100
            logger.info(
                f"file_processing.optimized: type={file_type} "
                f"original={original_size}B optimized={new_size}B "
                f"savings={savings:.1f}%"
            )

    return result_path


def get_storage_subdir(file_type: str) -> str:
    """Returns the storage subdirectory for a given file type."""
    return STORAGE_DIRS.get(file_type, "uploads")


def move_to_storage(
    optimized_path: str,
    file_type: str,
    storage_root: Optional[str] = None
) -> str:
    """
    Moves the optimized file to its final storage location.

    Args:
        optimized_path: Path to the optimized file
        file_type: Type for determining subdirectory
        storage_root: Root storage directory (defaults to config)

    Returns:
        Final relative path in storage
    """
    if storage_root is None:
        import config
        storage_root = config.ALLOWED_STORAGE_DIR

    subdir = get_storage_subdir(file_type)
    dest_dir = os.path.join(storage_root, subdir)
    os.makedirs(dest_dir, exist_ok=True)

    filename = os.path.basename(optimized_path)
    final_path = os.path.join(dest_dir, filename)

    # Avoid duplicates
    if os.path.exists(final_path) and final_path != optimized_path:
        base, ext = os.path.splitext(filename)
        import uuid
        final_path = os.path.join(dest_dir, f"{base}_{uuid.uuid4().hex[:8]}{ext}")

    if optimized_path != final_path:
        shutil.move(optimized_path, final_path)

    # Return relative path for DB storage
    return os.path.relpath(final_path, storage_root)


def handle_upload(
    file_path: str,
    file_type: str,
    metadata: Optional[Dict[str, Any]] = None,
    storage_root: Optional[str] = None,
) -> str:
    """
    Full pipeline: validate → optimize → move to storage.

    Returns:
        Relative path in storage (for DB)
    """
    optimized_path = process_file(file_path, file_type, metadata)
    final_path = move_to_storage(optimized_path, file_type, storage_root)
    return final_path
