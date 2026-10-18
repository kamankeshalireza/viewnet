"""Product image pipeline: validate → strip metadata → re-encode to WebP renditions."""
from __future__ import annotations

import io
import logging

from celery import shared_task
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from PIL import Image, ImageOps

from .validators import MAX_PIXELS

log = logging.getLogger("catalog.images")
SIZES = {"thumb": 160, "card": 480, "detail": 900, "zoom": 1600}  # max width in px
WEBP_QUALITY = 82


def build_renditions(image_id: int) -> dict[str, str]:
    from .models import ProductImage

    obj = ProductImage.objects.select_related("product").get(pk=image_id)
    with obj.image.open("rb") as fh:
        img = Image.open(fh)
        if img.width * img.height > MAX_PIXELS:
            raise ValueError("image too large")
        img = ImageOps.exif_transpose(img)  # bake in rotation, then drop all metadata on re-encode
        img.load()
    mode = "RGBA" if img.mode in ("RGBA", "LA", "P") and "transparency" in img.info or img.mode == "RGBA" else "RGB"
    img = img.convert(mode)
    names: dict[str, str] = {}
    for key, max_w in SIZES.items():
        im = img.copy()
        if im.width > max_w:
            im = im.resize((max_w, round(im.height * max_w / im.width)), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "WEBP", quality=WEBP_QUALITY, method=4)
        target = f"products/renditions/{obj.product_id}/{obj.pk}-{key}.webp"
        if default_storage.exists(target):
            default_storage.delete(target)
        names[key] = default_storage.save(target, ContentFile(buf.getvalue()))
    ProductImage.objects.filter(pk=obj.pk).update(renditions=names, width=img.width, height=img.height)
    return names


@shared_task(queue="images", ignore_result=True, max_retries=2, default_retry_delay=10, bind=True)
def process_product_image(self, image_id: int):
    from .models import ProductImage

    if not ProductImage.objects.filter(pk=image_id).exists():
        return
    try:
        build_renditions(image_id)
    except (OSError, ValueError):
        log.exception("image processing failed id=%s", image_id)
        raise self.retry() from None
