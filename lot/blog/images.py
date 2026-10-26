from io import BytesIO
from pathlib import PurePath
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.utils import timezone
from PIL import Image, ImageOps, UnidentifiedImageError

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "GIF"}
PRIVATE_INFO_KEYS = ("exif", "xmp", "XML:com.adobe.xmp", "comment", "photoshop")


def _open(file):
    file.seek(0)
    try:
        img = Image.open(file)
        img.load()
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError) as exc:
        raise ValidationError("That file isn't a readable image.") from exc
    if img.format not in ALLOWED_FORMATS:
        raise ValidationError("Upload a JPEG, PNG, WebP, or GIF image.")
    return img


def validate_image_upload(file):
    """Field validator: size limit and a real, supported image (not just a renamed file)."""
    limit_mb = settings.BLOG_MAX_UPLOAD_MB
    if file.size and file.size > limit_mb * 1024 * 1024:
        raise ValidationError(f"Images must be under {limit_mb} MB.")
    if getattr(file, "_committed", True):
        return
    _open(file)
    file.seek(0)


def upload_to(instance, filename):
    """Random file names: nothing leaks from the original name, and draft image URLs aren't guessable."""
    ext = PurePath(filename).suffix.lower().lstrip(".") or "jpg"
    return f"blog/{timezone.now():%Y/%m}/{uuid4().hex[:16]}.{ext}"


def optimize(file, max_px):
    """Return (ContentFile, ext, width, height): orientation fixed, location/camera metadata dropped, downscaled."""
    img = _open(file)
    if img.format == "GIF" and getattr(img, "is_animated", False):
        file.seek(0)
        return ContentFile(file.read()), "gif", img.width, img.height

    img = ImageOps.exif_transpose(img)
    for key in PRIVATE_INFO_KEYS:
        img.info.pop(key, None)
    img.thumbnail((max_px, max_px), Image.LANCZOS)

    has_alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)
    buf = BytesIO()
    if has_alpha:
        img.save(buf, "PNG", optimize=True)
        ext = "png"
    else:
        img.convert("RGB").save(buf, "JPEG", quality=85, optimize=True, progressive=True)
        ext = "jpg"
    return ContentFile(buf.getvalue()), ext, img.width, img.height


def store_optimized(field_file, max_px, thumb_field=None, thumb_px=960):
    """Replace a freshly uploaded file with an optimized copy (and optionally a smaller thumbnail)."""
    content, ext, width, height = optimize(field_file.file, max_px)
    field_file.save(f"image.{ext}", content, save=False)
    if thumb_field is not None:
        content.seek(0)
        thumb, thumb_ext, _, _ = optimize(content, thumb_px)
        thumb_field.save(f"thumb.{thumb_ext}", thumb, save=False)
    return width, height
