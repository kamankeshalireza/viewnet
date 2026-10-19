import io

import pytest
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from PIL import Image

from apps.accounts.models import User
from apps.catalog.admin import VariantForm
from apps.catalog.images import build_renditions
from apps.catalog.models import Product, ProductImage, ProductVariant, WishlistItem
from apps.catalog.validators import validate_product_image
from apps.core.sanitize import clean_html

from .helpers import make_category, make_product

pytestmark = pytest.mark.django_db


def png_bytes(size=(2400, 1200), color=(200, 30, 30), fmt="PNG"):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, fmt)
    return buf.getvalue()


@pytest.fixture
def media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


def test_validator_accepts_real_image_rejects_fake_and_oversized():
    validate_product_image(SimpleUploadedFile("a.png", png_bytes((100, 100))))
    with pytest.raises(ValidationError):
        validate_product_image(SimpleUploadedFile("a.png", b"<?php echo 1; ?>"))
    with pytest.raises(ValidationError):
        validate_product_image(SimpleUploadedFile("a.gif", png_bytes((10, 10), fmt="GIF")))
    with pytest.raises(ValidationError):
        validate_product_image(SimpleUploadedFile("big.png", b"0" * (5 * 1024 * 1024 + 1)))


def test_renditions_are_webp_resized_and_recorded(media):
    p = make_product("x")
    img = ProductImage(product=p, is_primary=True)
    img.image.save("big.png", ContentFile(png_bytes()), save=True)
    names = build_renditions(img.pk)
    img.refresh_from_db()
    assert set(names) == {"thumb", "card", "detail", "zoom"} and (img.width, img.height) == (2400, 1200)
    widths = {k: Image.open(media / v) for k, v in names.items()}
    assert {k: im.format for k, im in widths.items()} == dict.fromkeys(names, "WEBP")
    assert [widths[k].width for k in ("thumb", "card", "detail", "zoom")] == [160, 480, 900, 1600]
    assert img.url_card.endswith("-card.webp") and "/products/renditions/" in img.url_zoom


def test_small_image_is_not_upscaled_and_exif_is_stripped(media):
    buf = io.BytesIO()
    im = Image.new("RGB", (300, 200), "blue")
    exif = Image.Exif()
    exif[0x010F] = "SecretCamera"
    im.save(buf, "JPEG", exif=exif)
    p = make_product("x")
    img = ProductImage(product=p)
    img.image.save("s.jpg", ContentFile(buf.getvalue()), save=True)
    names = build_renditions(img.pk)
    out = Image.open(media / names["zoom"])
    assert out.width == 300 and not out.getexif()


def test_image_falls_back_to_original_until_processed(media):
    img = ProductImage(product=make_product("x"))
    img.image.save("a.png", ContentFile(png_bytes((50, 50))), save=True)
    assert img.url_card == img.image.url
    assert ProductImage().url_card.endswith("no-image.svg")


def test_sanitizer_and_product_save():
    dirty = '<p onclick="x()">a</p><script>alert(1)</script><a href="javascript:alert(1)">l</a><img src="x" onerror="y()"><strong>b</strong>'
    out = clean_html(dirty)
    assert "<script" not in out and "onclick" not in out and "javascript:" not in out and "onerror" not in out
    assert "<strong>b</strong>" in out
    p = make_product("x", description=dirty)
    assert "<script" not in Product.objects.get(pk=p.pk).description


def test_db_constraints():
    p = make_product("x", variants=[(100_000, None, None)])
    with pytest.raises(IntegrityError), transaction.atomic():  # compare must exceed price
        ProductVariant.objects.create(product=p, sku="BAD1", price_rial=1000, compare_at_price_rial=500)
    with pytest.raises(IntegrityError), transaction.atomic():  # one default variant
        ProductVariant.objects.create(product=p, sku="BAD2", price_rial=1000, is_default=True)
    with pytest.raises(IntegrityError), transaction.atomic():  # unique SKU
        ProductVariant.objects.create(product=p, sku=p.variants.first().sku, price_rial=1000)
    with pytest.raises(IntegrityError), transaction.atomic():
        Product.objects.filter(pk=p.pk).update(min_price_rial=10, max_price_rial=5)


def test_one_primary_image_and_unique_wishlist(media):
    p = make_product("x")
    ProductImage.objects.create(product=p, image="a.png", is_primary=True)
    with pytest.raises(IntegrityError), transaction.atomic():
        ProductImage.objects.create(product=p, image="b.png", is_primary=True)
    u = User.objects.create_user("09123456789")
    WishlistItem.objects.create(user=u, product=p)
    with pytest.raises(IntegrityError), transaction.atomic():
        WishlistItem.objects.create(user=u, product=p)


def test_variant_form_converts_toman_to_rial_and_validates_compare():
    p = make_product("x")
    base = {"product": p.pk, "sku": "NEW-1", "weight_g": 10, "position": 0, "price_toman": "190000", "compare_at_toman": "250000", "is_active": "on"}
    form = VariantForm(data=base)
    assert form.is_valid(), form.errors
    v = form.save()
    assert (v.price_rial, v.compare_at_price_rial) == (1_900_000, 2_500_000)
    assert VariantForm(instance=v).fields["price_toman"].initial == 190_000
    bad = VariantForm(data={**base, "sku": "NEW-2", "compare_at_toman": "100000"})
    assert not bad.is_valid() and "compare_at_toman" in bad.errors
    no_compare = VariantForm(data={**base, "sku": "NEW-3", "compare_at_toman": ""})
    assert no_compare.is_valid() and no_compare.save().compare_at_price_rial is None


def test_admin_pages_load_and_product_save_recalcs(client, settings, media):
    su = User.objects.create_superuser("09121112244", "s3cret-Passw0rd")
    client.force_login(su)
    prefix = f"/{settings.ADMIN_URL_PREFIX}/catalog"
    for m in ("product", "category", "brand", "devicemodel", "attributedefinition", "wishlistitem"):
        assert client.get(f"{prefix}/{m}/").status_code == 200, m
        assert client.get(f"{prefix}/{m}/add/").status_code == 200, m
    cat = make_category("قاب")
    data = {
        "title": "قاب تست", "slug": "", "product_type": "physical", "category": cat.pk, "short_description": "", "description": "<p>x</p>",
        "is_active": "on", "published_at_0": "2026-10-01", "published_at_1": "10:00:00",
        "variants-TOTAL_FORMS": "1", "variants-INITIAL_FORMS": "0", "variants-MIN_NUM_FORMS": "0", "variants-MAX_NUM_FORMS": "1000",
        "variants-0-sku": "ADM-1", "variants-0-price_toman": "120000", "variants-0-weight_g": "0", "variants-0-position": "0",
        "variants-0-is_active": "on", "variants-0-is_default": "on",
        **{f"{n}-{k}": v for n in ("images", "specifications", "attribute_values")
           for k, v in (("TOTAL_FORMS", "0"), ("INITIAL_FORMS", "0"), ("MIN_NUM_FORMS", "0"), ("MAX_NUM_FORMS", "1000"))},
    }
    r = client.post(f"{prefix}/product/add/", data)
    assert r.status_code == 302, getattr(r, "context", None) and r.context["adminform"].form.errors
    p = Product.objects.get(title="قاب تست")
    assert (p.min_price_rial, p.in_stock) == (1_200_000, False)  # no stock entered yet and "adm-1" in p.search_text
