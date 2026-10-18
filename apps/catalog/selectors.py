"""Read-side catalog queries."""
from __future__ import annotations

from dataclasses import dataclass, field

from django.core.cache import cache
from django.db.models import Count, Max, Min, Prefetch, Q, QuerySet

from apps.core.money import toman_to_rial
from apps.core.text import to_ascii_digits

from .models import (
    CATEGORY_TREE_CACHE_KEY,
    AttributeOption,
    Brand,
    Category,
    DeviceModel,
    Product,
    ProductImage,
)
from .search.backend import get_backend

SORTS = {
    "newest": ("جدیدترین", ("-published_at", "-pk")),
    "cheapest": ("ارزان‌ترین", ("min_price_rial", "-pk")),
    "expensive": ("گران‌ترین", ("-min_price_rial", "-pk")),
    "bestseller": ("پرفروش‌ترین", ("-sales_count", "-pk")),
}
PAGE_SIZE = 12


def _ints(values) -> list[int]:
    out = []
    for v in values:
        v = to_ascii_digits(str(v)).strip()
        if v.isdigit():
            out.append(int(v))
    return out


@dataclass
class ListingParams:
    q: str = ""
    brands: list[str] = field(default_factory=list)
    devices: list[str] = field(default_factory=list)
    options: list[int] = field(default_factory=list)
    min_toman: int | None = None
    max_toman: int | None = None
    in_stock: bool = False
    sort: str = "newest"
    page: int = 1

    @classmethod
    def from_request(cls, GET) -> ListingParams:
        def num(key):
            v = _ints([GET.get(key, "")])
            return v[0] if v else None

        sort = GET.get("sort", "")
        return cls(
            q=(GET.get("q") or "").strip()[:100],
            brands=[b for b in GET.getlist("brand") if b][:10],
            devices=[d for d in GET.getlist("device") if d][:10],
            options=_ints(GET.getlist("opt"))[:20],
            min_toman=num("min_price"), max_toman=num("max_price"),
            in_stock=GET.get("in_stock") == "1",
            sort=sort if sort in SORTS else ("relevance" if (GET.get("q") or "").strip() else "newest"),
            page=max(num("page") or 1, 1),
        )


def published_products() -> QuerySet[Product]:
    return Product.objects.filter(is_active=True, category__is_active=True)


def with_card_data(qs: QuerySet[Product]) -> QuerySet[Product]:
    return qs.select_related("brand", "category").prefetch_related(
        Prefetch("images", queryset=ProductImage.objects.order_by("-is_primary", "position", "pk"), to_attr="prefetched_images")
    )


def listing_queryset(params: ListingParams, category: Category | None = None) -> QuerySet[Product]:
    qs = published_products()
    if category is not None:
        qs = qs.filter(category__path__startswith=category.path)
    if params.q:
        qs = get_backend().apply(qs, params.q)
    if params.brands:
        qs = qs.filter(brand__slug__in=params.brands)
    if params.devices:
        qs = qs.filter(variants__device_model__slug__in=params.devices, variants__is_active=True)
    if params.options:
        qs = qs.filter(Q(attribute_values__option_id__in=params.options) | Q(variants__options__in=params.options))
    if params.min_toman is not None:
        qs = qs.filter(min_price_rial__gte=toman_to_rial(params.min_toman))
    if params.max_toman is not None:
        qs = qs.filter(min_price_rial__lte=toman_to_rial(params.max_toman))
    if params.in_stock:
        qs = qs.filter(in_stock=True)
    qs = qs.distinct()
    if params.sort == "relevance" and params.q:
        order = ("search_rank", "-sales_count", "-pk")
    else:
        order = SORTS.get(params.sort, SORTS["newest"])[1]
    return with_card_data(qs.order_by(*order))


def listing_facets(category: Category | None) -> dict:
    """Filter choices for the sidebar, scoped to the category (not to other active filters)."""
    scope = published_products()
    if category is not None:
        scope = scope.filter(category__path__startswith=category.path)
    ids = scope.values("pk")
    brands = (Brand.objects.filter(is_active=True, products__in=ids)
              .annotate(n=Count("products", distinct=True)).order_by("name"))
    devices = (DeviceModel.objects.filter(is_active=True, variants__product__in=ids, variants__is_active=True)
               .select_related("brand").annotate(n=Count("variants__product", distinct=True)))
    by_variant = (AttributeOption.objects.filter(definition__is_filterable=True, variants__product__in=ids)
                  .annotate(n=Count("variants__product", distinct=True)))
    by_product = (AttributeOption.objects.filter(definition__is_filterable=True, product_values__product__in=ids)
                  .annotate(n=Count("product_values__product", distinct=True)))
    options: dict[int, AttributeOption] = {}
    for o in list(by_variant) + list(by_product):
        if o.pk not in options or o.n > options[o.pk].n:
            options[o.pk] = o
    groups: dict[str, dict] = {}
    for o in sorted(options.values(), key=lambda o: (o.definition.position, o.position, o.label)):
        g = groups.setdefault(o.definition.code, {"definition": o.definition, "options": []})
        g["options"].append(o)
    price = scope.filter(min_price_rial__gt=0).aggregate(lo=Min("min_price_rial"), hi=Max("min_price_rial"))
    return {"brands": brands, "devices": devices, "option_groups": list(groups.values()), "price": price}


def get_category_tree() -> list[dict]:
    """Nested active categories, cached until any Category changes."""
    tree = cache.get(CATEGORY_TREE_CACHE_KEY)
    if tree is not None:
        return tree
    nodes = {}
    roots: list[dict] = []
    for c in Category.objects.filter(is_active=True).order_by("path"):
        node = {"id": c.pk, "name": c.name, "url": c.get_absolute_url(), "slug_path": c.slug_path,
                "depth": c.depth, "image": c.image.url if c.image else "", "children": []}
        nodes[c.pk] = node
        parent_id = c.parent_id
        (nodes[parent_id]["children"] if parent_id in nodes else roots).append(node)
    cache.set(CATEGORY_TREE_CACHE_KEY, roots, 3600)
    return roots


def get_product_for_detail(pk: int) -> Product | None:
    return (published_products().select_related("brand", "category")
            .prefetch_related("images", "specifications", "variants__device_model__brand", "variants__options__definition",
                              "attribute_values__option__definition")
            .filter(pk=pk).first())


def home_sections(limit: int = 8) -> dict:
    base = with_card_data(published_products())
    return {
        "new_products": list(base.order_by("-published_at", "-pk")[:limit]),
        "featured_products": list(base.filter(is_featured=True).order_by("-published_at")[:limit]),
        "bestsellers": list(base.filter(sales_count__gt=0).order_by("-sales_count")[:limit]),
        "categories": get_category_tree(),
    }
