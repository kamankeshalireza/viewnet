"""Idempotent starter data: the shop's real top-level categories, phone brands/models, colours.
`--demo` also creates a few clearly-marked sample products so the storefront can be explored."""
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.catalog import services
from apps.catalog.images import build_renditions
from apps.catalog.models import (
    AttributeDefinition,
    AttributeOption,
    Brand,
    Category,
    DeviceModel,
    Product,
    ProductImage,
    ProductSpecification,
    ProductVariant,
)
from apps.core.money import toman_to_rial

CATEGORIES = ["قاب گوشی", "گلس", "کابل", "شارژر", "ایرپاد", "فندکی ماشین", "پاوربانک", "اپل آیدی"]
BRANDS = [("اپل", "Apple", "اپل apple آیفون iphone", True), ("سامسونگ", "Samsung", "سامسونگ samsung گلکسی galaxy", True),
          ("شیائومی", "Xiaomi", "شیائومی xiaomi redmi ردمی", True)]
MODELS = [("اپل", "iPhone 15", "ایفون ۱۵ آیفون 15 iphone15"), ("اپل", "iPhone 15 Pro", "آیفون ۱۵ پرو"),
          ("اپل", "iPhone 14", "آیفون ۱۴"), ("اپل", "iPhone 13", "آیفون ۱۳"),
          ("سامسونگ", "Galaxy S24", "گلکسی اس ۲۴ s24"), ("سامسونگ", "Galaxy A54", "گلکسی ای ۵۴ a54"),
          ("شیائومی", "Redmi Note 13", "ردمی نوت ۱۳")]
COLORS = [("black", "مشکی", "#111111"), ("white", "سفید", "#ffffff"), ("blue", "آبی", "#2f6fed"), ("red", "قرمز", "#d63031")]


class Command(BaseCommand):
    help = "Seed categories, brands, phone models and colours (idempotent). Use --demo for sample products."

    def add_arguments(self, parser):
        parser.add_argument("--demo", action="store_true", help="also create sample products (marked 'نمونه')")

    @transaction.atomic
    def handle(self, *args, **opts):
        for i, name in enumerate(CATEGORIES):
            Category.objects.get_or_create(name=name, parent=None, defaults={"position": i})
        brands = {}
        for fa, en, aliases, phone in BRANDS:
            brands[fa], _ = Brand.objects.get_or_create(name=fa, defaults={"name_en": en, "search_aliases": aliases, "is_phone_brand": phone})
        for brand, name, aliases in MODELS:
            DeviceModel.objects.get_or_create(brand=brands[brand], name=name, defaults={"search_aliases": aliases})
        color, _ = AttributeDefinition.objects.get_or_create(code="color", defaults={"name": "رنگ", "kind": "color", "is_variant_axis": True})
        for i, (v, label, hexv) in enumerate(COLORS):
            AttributeOption.objects.get_or_create(definition=color, value=v, defaults={"label": label, "hex": hexv, "position": i})
        self.stdout.write(self.style.SUCCESS("Categories, brands, phone models, colours: OK"))
        if opts["demo"]:
            self.demo(brands, color)

    def _image(self, product, filename, primary):
        src = Path(settings.BASE_DIR) / "static" / "img" / "product" / filename
        if not src.exists():
            return
        img = ProductImage(product=product, alt=product.title, is_primary=primary)
        img.image.save(filename, ContentFile(src.read_bytes()), save=True)
        build_renditions(img.pk)

    def demo(self, brands, color):
        cat = {c.name: c for c in Category.objects.filter(parent=None)}
        black, white = (AttributeOption.objects.get(definition=color, value=v) for v in ("black", "white"))
        models = list(DeviceModel.objects.filter(brand=brands["اپل"], name__in=["iPhone 15", "iPhone 14"]))

        def make(title, category, brand, variants, ptype=Product.Type.PHYSICAL, image=None, specs=()):
            p, created = Product.objects.get_or_create(title=title, defaults={"category": cat[category], "brand": brand, "product_type": ptype,
                                                       "short_description": "محصول نمونه برای آزمایش فروشگاه", "is_featured": True,
                                                       "description": "<p>این یک محصول <strong>نمونه</strong> است.</p>"})
            if created:
                for n, (sku, dm, opts, price, compare) in enumerate(variants):
                    v = ProductVariant.objects.create(product=p, sku=sku, device_model=dm, price_rial=toman_to_rial(price),
                                                      compare_at_price_rial=toman_to_rial(compare) if compare else None,
                                                      weight_g=40, is_default=(n == 0), position=n)
                    v.options.set(opts)
                for k, val in specs:
                    ProductSpecification.objects.create(product=p, key=k, value=val)
                if image:
                    self._image(p, image, True)
                services.recalc_product(p.pk)

        make("قاب سیلیکونی (نمونه)", "قاب گوشی", None,
             [(f"DEMO-CASE-{m.pk}-{o.value}", m, [o], 190_000, 250_000 if o is black else None) for m in models for o in (black, white)], specs=[("جنس", "سیلیکون")])
        make("گلس تمام‌صفحه (نمونه)", "گلس", None, [(f"DEMO-GLASS-{m.pk}", m, [], 90_000, None) for m in models])
        make("کابل شارژ USB-C (نمونه)", "کابل", None, [("DEMO-CABLE-1M", None, [], 120_000, None), ("DEMO-CABLE-2M", None, [], 160_000, None)])
        make("پاوربانک ۱۰۰۰۰ (نمونه)", "پاوربانک", None, [("DEMO-PB-10K", None, [black], 780_000, 890_000)], specs=[("ظرفیت", "۱۰۰۰۰ میلی‌آمپرساعت")])
        make("ساخت اپل آیدی (نمونه)", "اپل آیدی", brands["اپل"], [("DEMO-APPLEID", None, [], 300_000, None)], ptype=Product.Type.DIGITAL)
        self.stdout.write(self.style.SUCCESS("Demo products: OK (titles end with «نمونه»). Now run: python manage.py seed_demo_stock"))
