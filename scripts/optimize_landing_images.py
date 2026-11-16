from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    "hero": ROOT / "ui/IVMMRH/resource_8MPyrSyYQQ37qJAhRh3_JT.png",
    "evidence": ROOT / "ui/IVMMRH/resource_aFFXnvDIdP02Z9Rc60f4Q8.png",
}
WIDTHS = (480, 768, 1080)
OUTPUT_DIR = ROOT / "ui/assets/landing"


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, source in SOURCES.items():
        with Image.open(source) as image:
            image = image.convert("RGB")
            for width in WIDTHS:
                if width > image.width:
                    continue
                height = round(image.height * width / image.width)
                resized = image.resize((width, height), Image.Resampling.LANCZOS)
                output = OUTPUT_DIR / f"{name}-{width}.webp"
                resized.save(output, "WEBP", quality=80, method=6)
                print(f"Generated {output.relative_to(ROOT)} ({output.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
