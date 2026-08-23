"""
Secure temporary file management for sensitive payroll operations.

Provides a dedicated, permission-restricted temporary directory for plaintext
files that exist transiently during encryption/decryption and PDF signing.

Production Linux: uses /dev/shm (tmpfs, RAM-backed) if available.
Fallback: uses <STORAGE_PATH>/.tmp_secure/ with 0o700 permissions.

Orphaned temp files are cleaned up at application startup and can be swept
periodically via cleanup_orphaned_temps().
"""

from __future__ import annotations

import logging
import os
import platform
import tempfile
import time
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger("dircom.payroll.secure_temp")

_TMPFS_BASE = "/dev/shm"
_TMPFS_APP_DIR = "mymanagerh_secure_tmp"
_FALLBACK_DIR_NAME = ".tmp_secure"

# Prefixes used by the system for sensitive temp files
_KNOWN_TEMP_PREFIXES = (
    "yc_decrypted_",
    "tmp_visual_",
    ".receipt_",
    ".signed_",
)

_secure_dir: Optional[Path] = None


def get_secure_temp_dir() -> Path:
    """
    Returns the secure temporary directory, creating it if necessary.

    Priority:
    1. /dev/shm/mymanagerh_secure_tmp (tmpfs, RAM-only, Linux production)
    2. <STORAGE_PATH>/.tmp_secure/ (cross-platform fallback)

    Both are created with 0o700 permissions (owner-only access).
    """
    global _secure_dir
    if _secure_dir is not None and _secure_dir.exists():
        return _secure_dir

    from payroll_core import ALLOWED_STORAGE_DIR

    # Attempt tmpfs (Linux production)
    if platform.system() == "Linux" and Path(_TMPFS_BASE).is_dir():
        tmpfs_dir = Path(_TMPFS_BASE) / _TMPFS_APP_DIR
        try:
            tmpfs_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
            # Verify we can write
            test_file = tmpfs_dir / ".probe"
            test_file.write_bytes(b"ok")
            test_file.unlink()
            _secure_dir = tmpfs_dir
            logger.info(
                "secure_temp.using_tmpfs",
                extra={"path": str(tmpfs_dir)},
            )
            return _secure_dir
        except Exception as exc:
            logger.warning(
                "secure_temp.tmpfs_unavailable fallback=storage",
                extra={"error": str(exc)},
            )

    # Fallback to storage-based secure dir
    fallback_dir = Path(ALLOWED_STORAGE_DIR).resolve() / _FALLBACK_DIR_NAME
    fallback_dir.mkdir(parents=True, exist_ok=True)

    # Set restrictive permissions on Unix-like systems
    try:
        os.chmod(str(fallback_dir), 0o700)
    except (OSError, NotImplementedError):
        pass  # Windows: permissions handled differently

    _secure_dir = fallback_dir
    logger.info(
        "secure_temp.using_fallback",
        extra={"path": str(fallback_dir)},
    )
    return _secure_dir


def secure_mkstemp(
    prefix: str = "yc_secure_",
    suffix: str = "",
) -> Tuple[int, str]:
    """
    Creates a temporary file inside the secure temp directory.

    Returns (fd, path) like tempfile.mkstemp().
    The caller is responsible for closing fd and deleting the file.
    """
    secure_dir = get_secure_temp_dir()
    return tempfile.mkstemp(prefix=prefix, suffix=suffix, dir=str(secure_dir))


def cleanup_orphaned_temps(max_age_seconds: int = 300) -> int:
    """
    Removes orphaned temporary files older than max_age_seconds.

    Scans the secure temp directory for files matching known prefixes.
    Returns the number of files removed.

    Safe to call at startup and periodically from a background task.
    """
    try:
        secure_dir = get_secure_temp_dir()
    except Exception:
        return 0

    removed = 0
    now = time.time()
    cutoff = now - max_age_seconds

    try:
        for entry in secure_dir.iterdir():
            if not entry.is_file():
                continue
            # Only touch files with known prefixes or .enc.tmp suffix
            name = entry.name
            is_known = any(name.startswith(p) for p in _KNOWN_TEMP_PREFIXES)
            is_enc_tmp = name.endswith(".enc.tmp")
            if not is_known and not is_enc_tmp:
                continue
            try:
                mtime = entry.stat().st_mtime
                if mtime < cutoff:
                    entry.unlink(missing_ok=True)
                    removed += 1
                    logger.info(
                        "secure_temp.orphan_removed",
                        extra={
                            "file": name,
                            "age_seconds": int(now - mtime),
                        },
                    )
            except Exception:
                pass  # File may have been cleaned by another process
    except Exception as exc:
        logger.warning(
            "secure_temp.cleanup_scan_error",
            extra={"error": str(exc)},
        )

    if removed > 0:
        logger.info(
            "secure_temp.cleanup_complete",
            extra={"removed": removed, "max_age_seconds": max_age_seconds},
        )
    return removed
