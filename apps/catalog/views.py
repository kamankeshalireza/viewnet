from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponsePermanentRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_POST

from apps.core.templatetags.core_tags import toman

from . import selectors
from .models import Category, Product, WishlistItem


def home(request):
    return render(request, "catalog/home.html", selectors.home_sections())


def _listing(request, *, title, category=None, crumbs=(), noindex=False, empty_query=False):
    params = selectors.ListingParams.from_request(request.GET)
    qs = selectors.listing_queryset(params, category) if not empty_query else Product.objects.none()
    page = Paginator(qs, selectors.PAGE_SIZE).get_page(params.page)
    facets = selectors.listing_facets(category)
    has_filters = bool(params.brands or params.devices or params.options or params.min_toman is not None
                       or params.max_toman is not None or params.in_stock)
    ctx = {
        "title": title, "category": category, "crumbs": crumbs, "params": params, "page_obj": page,
        "facets": facets, "sorts": selectors.SORTS, "noindex": noindex or has_filters or bool(request.GET.get("sort")),
        "subcategories": list(category.children.filter(is_active=True)) if category else [],
        "selected_options": set(params.options), "selected_brands": set(params.brands),
        "selected_devices": set(params.devices),
        "has_filters": has_filters,
    }
    return render(request, "catalog/listing.html", ctx)


def all_products(request):
    return _listing(request, title="همهٔ محصولات", crumbs=[("همهٔ محصولات", None)])


def category_detail(request, slug_path):
    category = get_object_or_404(Category, slug_path=slug_path.strip("/"), is_active=True)
    crumbs = [(c.name, c.get_absolute_url()) for c in category.ancestors()] + [(category.name, None)]
    return _listing(request, title=category.name, category=category, crumbs=crumbs)


@require_GET
def search(request):
    q = request.GET.get("q", "").strip()
    return _listing(request, title=f"نتایج جستجو برای «{q}»" if q else "جستجو", crumbs=[("جستجو", None)],
                    noindex=True, empty_query=not q)


def _variant_payload(product):
    """Variants + axes for the client-side picker. Prices are pre-formatted by the server."""
    variants = [v for v in product.variants.all() if v.is_active]
    axes = []
    if any(v.device_model_id for v in variants):
        choices = {}
        for v in variants:
            if v.device_model_id:
                choices[v.device_model_id] = {"id": v.device_model_id, "label": v.device_model.name}
        axes.append({"key": "device", "label": "مدل گوشی", "kind": "device", "choices": list(choices.values())})
    defs = {}
    for v in variants:
        for o in v.options.all():
            d = defs.setdefault(o.definition_id, {"key": f"attr{o.definition_id}", "label": o.definition.name,
                                                  "kind": o.definition.kind, "choices": {}})
            d["choices"][o.pk] = {"id": o.pk, "label": o.label, "hex": o.hex}
    for d in defs.values():
        d["choices"] = list(d["choices"].values())
        axes.append(d)
    items = []
    for v in variants:
        ax = {}
        if v.device_model_id:
            ax["device"] = v.device_model_id
        for o in v.options.all():
            ax[f"attr{o.definition_id}"] = o.pk
        items.append({"id": v.pk, "sku": v.sku, "price": toman(v.price_rial), "default": v.is_default, "axes": ax,
                      "compare": toman(v.compare_at_price_rial) if v.compare_at_price_rial else ""})
    default = next((i for i in items if i["default"]), items[0] if items else None)
    return {"axes": axes, "variants": items}, default


def product_detail(request, pk, slug=None):
    product = selectors.get_product_for_detail(pk)
    if product is None:
        return render(request, "errors/404.html", status=404)
    if slug != product.slug:  # canonical URL (title/slug may have changed)
        return HttpResponsePermanentRedirect(product.get_absolute_url())
    payload, default = _variant_payload(product)
    for ax in payload["axes"]:
        key = ax["key"]
        ax["selected"] = default["axes"].get(key) if default else None
    crumbs = [(c.name, c.get_absolute_url()) for c in product.category.ancestors()]
    crumbs += [(product.category.name, product.category.get_absolute_url()), (product.title, None)]
    related = selectors.with_card_data(
        selectors.published_products().filter(category=product.category).exclude(pk=product.pk)
    ).order_by("-sales_count", "-pk")[:4]
    in_wishlist = request.user.is_authenticated and WishlistItem.objects.filter(user=request.user, product=product).exists()
    return render(request, "catalog/product_detail.html", {
        "product": product, "variants_payload": payload, "default_variant": default, "crumbs": crumbs,
        "images": list(product.images.all()), "specs": list(product.specifications.all()),
        "related": list(related), "in_wishlist": in_wishlist,
        "attribute_values": list(product.attribute_values.all()),
    })


def _safe_next(request, fallback="/"):
    nxt = request.POST.get("next") or request.META.get("HTTP_REFERER") or ""
    ok = nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}, require_https=request.is_secure())
    return nxt if ok else fallback


@require_POST
def wishlist_toggle(request, pk):
    if not request.user.is_authenticated:
        messages.info(request, "برای افزودن به علاقه‌مندی‌ها ابتدا وارد شوید.")
        return redirect(f"/account/login/?next={_safe_next(request)}")
    product = get_object_or_404(Product, pk=pk, is_active=True)
    item, created = WishlistItem.objects.get_or_create(user=request.user, product=product)
    if not created:
        item.delete()
    messages.success(request, "به علاقه‌مندی‌ها اضافه شد." if created else "از علاقه‌مندی‌ها حذف شد.")
    return redirect(_safe_next(request))


@login_required
def wishlist_list(request):
    ids = list(WishlistItem.objects.filter(user=request.user).values_list("product_id", flat=True))
    products = list(selectors.with_card_data(selectors.published_products().filter(pk__in=ids)))
    return render(request, "catalog/wishlist.html", {"products": products})
