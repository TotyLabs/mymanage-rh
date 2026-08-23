"""
PDF Processor — Ghostscript compression + pikepdf structural cleanup.

Pipeline:
  1. Ghostscript: downsample images to 150dpi, apply /ebook preset
  2. pikepdf: remove unreferenced resources, compress streams
  3. Clean up intermediary and original files

Expected savings: 40-70% on typical payroll PDFs.
"""
import os
import shutil
import subprocess
import logging
from pathlib import Path

logger = logging.getLogger("dircom.payroll")

# Ghostscript binary name (platform-dependent)
GS_BINARY = "gswin64c" if os.name == "nt" else "gs"


def _find_ghostscript() -> str:
    """Finds the Ghostscript binary, checking common Windows paths."""
    # Try system PATH first
    if shutil.which(GS_BINARY):
        return GS_BINARY

    # Windows: try alternate name
    if os.name == "nt":
        for alt in ("gswin64c", "gswin32c", "gs"):
            if shutil.which(alt):
                return alt

        # Common install paths
        for prog_dir in (os.environ.get("ProgramFiles", ""), os.environ.get("ProgramFiles(x86)", "")):
            if not prog_dir:
                continue
            for gs_folder in ("gs", "GPLGS"):
                gs_dir = Path(prog_dir) / gs_folder
                if gs_dir.exists():
                    for bin_path in gs_dir.rglob("gswin64c.exe"):
                        return str(bin_path)
                    for bin_path in gs_dir.rglob("gswin32c.exe"):
                        return str(bin_path)

    return GS_BINARY  # fallback, will fail with clear error


def _ghostscript_compress(input_path: str, output_path: str) -> bool:
    """
    Phase 1: Ghostscript compression.
    Returns True on success, False if GS not available.
    """
    gs_bin = _find_ghostscript()

    cmd = [
        gs_bin,
        "-sDEVICE=pdfwrite",
        "-dCompatibilityLevel=1.4",
        "-dPDFSETTINGS=/ebook",
        "-dNOPAUSE",
        "-dQUIET",
        "-dBATCH",
        "-dDownsampleColorImages=true",
        "-dColorImageResolution=150",
        "-dGrayImageResolution=150",
        "-dMonoImageResolution=300",
        f"-sOutputFile={output_path}",
        input_path,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,  # 2 minute timeout for large PDFs
        )

        if result.returncode != 0:
            logger.warning(
                f"pdf_processor.gs_warning: returncode={result.returncode} "
                f"stderr={result.stderr[:200] if result.stderr else 'none'}"
            )
            return False

        # Verify output exists and is valid
        if not os.path.exists(output_path) or os.path.getsize(output_path) < 100:
            logger.warning("pdf_processor.gs_output_invalid")
            return False

        return True

    except FileNotFoundError:
        logger.warning(
            f"pdf_processor.gs_not_found: Ghostscript not installed. "
            f"Install it for PDF optimization. Tried: {gs_bin}"
        )
        return False

    except subprocess.TimeoutExpired:
        logger.error("pdf_processor.gs_timeout: PDF too large or complex")
        return False

    except Exception as e:
        logger.error(f"pdf_processor.gs_error: {e}")
        return False


def _pikepdf_cleanup(input_path: str, output_path: str) -> bool:
    """
    Phase 2: pikepdf structural cleanup.
    Removes unreferenced resources, compresses streams.
    Returns True on success.
    """
    try:
        import pikepdf

        with pikepdf.open(input_path) as pdf:
            pdf.remove_unreferenced_resources()
            pdf.save(output_path, compress_streams=True)

        return True

    except ImportError:
        logger.warning("pdf_processor.pikepdf_not_installed: skipping structural cleanup")
        return False

    except Exception as e:
        logger.error(f"pdf_processor.pikepdf_error: {e}")
        return False


def process_pdf(input_path: str) -> str:
    """
    Full PDF optimization pipeline.

    Strategy:
      1. Try Ghostscript → pikepdf (best compression)
      2. If GS unavailable, try pikepdf only (moderate compression)
      3. If nothing works, return original (no data loss)

    The original file is ALWAYS deleted on success.
    Returns path to optimized file.
    """
    input_p = Path(input_path)
    stem = input_p.stem
    parent = input_p.parent

    gs_path = str(parent / f"{stem}_gs.pdf")
    final_path = str(parent / f"{stem}_opt.pdf")

    original_size = os.path.getsize(input_path)

    # Phase 1: Ghostscript
    gs_success = _ghostscript_compress(input_path, gs_path)

    if gs_success:
        # Phase 2: pikepdf on GS output
        pike_success = _pikepdf_cleanup(gs_path, final_path)

        if pike_success:
            # Full pipeline succeeded
            os.remove(gs_path)

            # Safety: only delete original if optimized is smaller or same
            opt_size = os.path.getsize(final_path)
            if opt_size <= original_size * 1.05:  # allow 5% margin
                os.remove(input_path)
                logger.info(
                    f"pdf_processor.full_pipeline: "
                    f"{original_size}B -> {opt_size}B "
                    f"({((original_size - opt_size) / original_size * 100):.1f}% saved)"
                )
                return final_path
            else:
                # Optimized is bigger — keep original
                logger.info("pdf_processor.optimized_larger: keeping original")
                os.remove(final_path)
                return input_path
        else:
            # pikepdf failed — use GS output directly
            opt_size = os.path.getsize(gs_path)
            if opt_size <= original_size * 1.05:
                os.remove(input_path)
                os.rename(gs_path, final_path)
                return final_path
            else:
                os.remove(gs_path)
                return input_path
    else:
        # GS not available — try pikepdf only
        pike_success = _pikepdf_cleanup(input_path, final_path)

        if pike_success:
            opt_size = os.path.getsize(final_path)
            if opt_size <= original_size * 1.05:
                os.remove(input_path)
                return final_path
            else:
                os.remove(final_path)
                return input_path
        else:
            # Nothing worked — return original
            logger.info("pdf_processor.no_optimization: no tools available")
            return input_path
