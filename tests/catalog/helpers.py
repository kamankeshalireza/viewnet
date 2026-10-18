from apps.catalog import services
from apps.catalog.models import (
    AttributeDefinition,
    AttributeOption,
    Brand,
    Category,
    DeviceModel,
    Product,
    ProductVariant,
)
from apps.core.money import toman_to_rial

_n = {"i": 0}


def uid() -> int:
    _n["i"] += 1
    return _n["i"]


def make_category(name="قاب گوشی", parent=None, **kw):
    return Category.objects.create(name=name, parent=parent, **kw)


def make_brand(name="اپل", name_en="Apple", phone=True, aliases="", **kw):
    return Brand.objects.create(name=name, name_en=name_en, is_phone_brand=phone, search_aliases=aliases, **kw)


def make_device(brand, name="iPhone 15", aliases="", **kw):
    return DeviceModel.objects.create(brand=brand, name=name, search_aliases=aliases, **kw)


def make_color(value="black", label="مشکی", hexv="#000000"):
    d, _ = AttributeDefinition.objects.get_or_create(code="color", defaults={"name": "رنگ", "kind": "color", "is_variant_axis": True})
    o, _ = AttributeOption.objects.get_or_create(definition=d, value=value, defaults={"label": label, "hex": hexv})
    return o


def make_product(title="قاب سیلیکونی", category=None, brand=None, variants=((100_000, None, None),), active=True, **kw):
    """variants: iterable of (price_toman, device_model|None, [options]|None, compare_toman|None)."""
    category = category or make_category(name=f"دسته {uid()}")
    p = Product.objects.create(title=title, category=category, brand=brand, is_active=active, **kw)
    for n, spec in enumerate(variants):
        price, dm, opts, *rest = (*spec, None, None)[:4] if len(spec) < 4 else spec
        compare = rest[0] if rest else None
        v = ProductVariant.objects.create(product=p, sku=f"SKU-{uid()}", device_model=dm, price_rial=toman_to_rial(price),
                                          compare_at_price_rial=toman_to_rial(compare) if compare else None, is_default=(n == 0))
        if opts:
            v.options.set(opts)
    services.recalc_product(p.pk)
    p.refresh_from_db()
    return p
