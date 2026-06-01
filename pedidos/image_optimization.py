from pathlib import Path

from django.conf import settings
from PIL import Image, ImageOps


MENU_IMAGE_MAX_SIZE = (960, 720)
MENU_IMAGE_QUALITY = 78
OPTIMIZED_MEDIA_DIR = "optimized/menu"


def _source_signature(path):
    stat = path.stat()
    return f"{int(stat.st_mtime)}-{stat.st_size}"


def optimized_menu_image_path(image_field, *, max_size=MENU_IMAGE_MAX_SIZE, quality=MENU_IMAGE_QUALITY, generate=True):
    if not image_field:
        return None

    try:
        source_path = Path(image_field.path)
    except (NotImplementedError, ValueError):
        return None

    if not source_path.exists() or not source_path.is_file():
        return None

    relative_source = Path(image_field.name)
    source_stem = relative_source.with_suffix("")
    signature = _source_signature(source_path)
    output_relative = Path(OPTIMIZED_MEDIA_DIR) / source_stem.parent / f"{source_stem.name}-{signature}.webp"
    output_path = Path(settings.MEDIA_ROOT) / output_relative

    if output_path.exists():
        return output_path
    if not generate:
        return None

    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with Image.open(source_path) as image:
            image = ImageOps.exif_transpose(image)
            if image.mode not in ("RGB", "RGBA"):
                image = image.convert("RGB")
            image.thumbnail(max_size, Image.Resampling.LANCZOS)
            image.save(output_path, "WEBP", quality=quality, method=6)
    except Exception:
        if output_path.exists():
            output_path.unlink(missing_ok=True)
        return None

    return output_path


def optimized_menu_image_url(image_field, fallback_url="", **kwargs):
    output_path = optimized_menu_image_path(image_field, generate=False, **kwargs)
    if not output_path:
        return fallback_url

    try:
        relative_path = output_path.relative_to(settings.MEDIA_ROOT).as_posix()
    except ValueError:
        return fallback_url
    return f"{settings.MEDIA_URL}{relative_path}"
