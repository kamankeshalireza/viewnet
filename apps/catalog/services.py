"""Write-side catalog logic: denormalized columns + search index (architecture §6.4, §6.8)."""
from __future__ import annotations

from django.db.models import Q

from .models import Product
from .search.indexing import build_search_text


def recalc_product(product_id: int) -> None:
    """Recompute price range, stock flag and search text from the product's active variants."""
    product = (Product.objects.select_related("brand", "category")
               .prefetch_related("variants__device_model__brand", "variants__options", "attribute_options")
               .get(pk=product_id))
    active = [v for v in product.variants.all() if v.is_active]
    prices = [v.price_rial for v in active]
    compare = [v.compare_at_price_rial for v in active if v.compare_at_price_rial and v.compare_at_price_rial > v.price_rial]
    Product.objects.filter(pk=product_id).update(
        min_price_rial=min(prices, default=0),
        max_price_rial=max(prices, default=0),
        compare_at_min_rial=min(compare, default=0),
        # Phase 4 replaces this with real stock (digital products are always available).
        in_stock=bool(active),
        search_text=build_search_text(product),
    )


def recalc_products(product_ids) -> int:
    n = 0
    for pid in product_ids:
        recalc_product(pid)
        n += 1
    return n


def reindex_for(*, brand=None, category=None, device_model=None) -> int:
    """After renaming a brand/category/phone model, refresh the products that mention it."""
    q = Q()
    if brand is not None:
        q |= Q(brand=brand) | Q(variants__device_model__brand=brand)
    if category is not None:
        q |= Q(category__path__startswith=category.path)
    if device_model is not None:
        q |= Q(variants__device_model=device_model)
    if not q:
        return 0
    return recalc_products(set(Product.objects.filter(q).values_list("pk", flat=True)))


def recalc_all() -> int:
    return recalc_products(list(Product.objects.values_list("pk", flat=True)))


__all__ = ["recalc_product", "recalc_products", "reindex_for", "recalc_all"]
