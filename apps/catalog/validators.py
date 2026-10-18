from django.core.exceptions import ValidationError
from PIL import Image, UnidentifiedImageError

MAX_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 40_000_000
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}


def validate_product_image(file) -> None:
    """Real content check (not just the extension): size, format, pixel bomb."""
    if file.size > MAX_BYTES:
        raise ValidationError("حجم تصویر نباید بیشتر از ۵ مگابایت باشد.")
    try:
        file.seek(0)
        img = Image.open(file)
        img.verify()
        fmt = img.format
        file.seek(0)
        w, h = Image.open(file).size
    except (UnidentifiedImageError, OSError, SyntaxError) as exc:
        raise ValidationError("فایل انتخاب‌شده یک تصویر معتبر نیست.") from exc
    finally:
        file.seek(0)
    if fmt not in ALLOWED_FORMATS:
        raise ValidationError("فقط تصاویر JPEG، PNG و WebP مجاز است.")
    if w * h > MAX_PIXELS:
        raise ValidationError("ابعاد تصویر بیش از حد بزرگ است.")
