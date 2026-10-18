from __future__ import annotations

from apps.core.text import search_variants, to_ascii_digits


def build_search_text(product) -> str:
    """Everything a shopper might type: title, brand (+aliases), category path, SKUs, phone models, options."""
    parts: list[str] = [product.title]
    if product.brand_id:
        b = product.brand
        parts += [b.name, b.name_en, b.search_aliases]
    parts += [c.name for c in product.category.ancestors()] + [product.category.name]
    for v in product.variants.all():
        parts.append(v.sku)
        if v.device_model_id:
            d = v.device_model
            parts += [d.name, d.series, d.search_aliases, d.brand.name, d.brand.name_en, d.brand.search_aliases]
        parts += [o.label for o in v.options.all()]
    parts += [o.label for o in product.attribute_options.all()]
    text = " ".join(p for p in parts if p)
    return to_ascii_digits(search_variants(text)).lower()
