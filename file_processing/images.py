"""
Image Processor — Resize + compress images by asset type.

Supports: signatures, logos, DNI photos.
Output format: JPEG (optimized quality per type).

Expected savings: 60-90% on typical uploads.
"""
import os
import logging
from pathlib import Path

logger = logging.getLogger("dircom.payroll")

# ─── Per-type configuration ───
CONFIG = {
    "signature": {
        "size": (400, 400),
        "quality": 70,
        "description": "Firma digital",
    },
    "logo": {
        "size": (600, 600),
        "quality": 80,
        "description": "Logo empresarial",
    },
    "dni": {
        "size": (1000, 1000),
        "quality": 85,
        "description": "Documento de identidad",
    },
}

# Max resolution allowed (security: prevent memory bombs)
MAX_PIXELS = 4096 * 4096  # ~16 MP


def process_image(input_path: str, image_type: str) -> str:
    """
    Resizes and compresses an image based on its asset type.

    - Converts RGBA/P modes to RGB for JPEG compatibility
    - Applies thumbnail (preserves aspect ratio)
    - Outputs optimized JPEG
    - Deletes original on success

    Args:
        input_path: Path to the uploaded image
        image_type: One of "signature", "logo", "dni"

    Returns:
        Path to the optimized image
    """
    try:
        from PIL import Image
    except ImportError:
        logger.warning("image_processor.pillow_not_installed: skipping optimization")
        return input_path

    config = CONFIG.get(image_type)
    if not config:
        logger.warning(f"image_processor.unknown_type: {image_type}")
        return input_path

    try:
        img = Image.open(input_path)

        # Security: check for decompression bombs
        w, h = img.size
        if w * h > MAX_PIXELS:
            logger.warning(
                f"image_processor.resolution_exceeded: "
                f"{w}x{h} exceeds {MAX_PIXELS} pixels"
            )
            # Resize to max safe resolution instead of rejecting
            img.thumbnail((4096, 4096))

        # Convert for JPEG compatibility (Skip for signatures to preserve Alpha)
        if image_type != "signature":
            if img.mode in ("RGBA", "P", "LA"):
                # Create white background for transparency
                background = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "P":
                    img = img.convert("RGBA")
                background.paste(img, mask=img.split()[-1] if "A" in img.mode else None)
                img = background
            elif img.mode != "RGB":
                img = img.convert("RGB")

        # Resize preserving aspect ratio
        img.thumbnail(config["size"])

        # Build output path (Phase 1 Fix: Signatures MUST be PNG to preserve Alpha)
        input_p = Path(input_path)
        is_signature = image_type == "signature"
        ext = ".png" if is_signature else ".jpg"
        output_path = str(input_p.parent / f"{input_p.stem}_opt{ext}")

        # Save optimized
        if is_signature:
            img.save(
                output_path,
                format="PNG",
                optimize=True
            )
        else:
            img.save(
                output_path,
                format="JPEG",
                quality=config["quality"],
                optimize=True,
            )

        # Verify output
        original_size = os.path.getsize(input_path)
        new_size = os.path.getsize(output_path)

        # Delete original
        if input_path != output_path:
            os.remove(input_path)

        logger.info(
            f"image_processor.optimized: type={image_type} "
            f"{original_size}B -> {new_size}B "
            f"({((original_size - new_size) / max(original_size, 1) * 100):.1f}% saved) "
            f"final_size={img.size[0]}x{img.size[1]}"
        )

        return output_path

    except Exception as e:
        logger.error(f"image_processor.error: type={image_type} error={e}")
        return input_path
