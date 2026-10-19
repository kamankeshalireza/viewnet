from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_POST

from apps.core.text import to_ascii_digits

from . import services
from .stores import get_store


def _int(value, default=0) -> int:
    try:
        return int(to_ascii_digits(str(value)).strip())
    except (TypeError, ValueError):
        return default


def _next(request, fallback):
    nxt = request.POST.get("next", "")
    ok = nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}, require_https=request.is_secure())
    return nxt if ok else fallback


@require_GET
def cart_detail(request):
    store = get_store(request)
    cart = services.build_cart(store)
    for issue in cart.issues:
        messages.warning(request, issue)
    return render(request, "cart/cart.html", {"cart": cart})


@require_POST
def cart_add(request):
    try:
        change = services.add_item(get_store(request), _int(request.POST.get("variant_id")), max(_int(request.POST.get("qty"), 1), 1))
    except services.CartError as exc:
        messages.error(request, str(exc))
        return redirect(_next(request, "/cart/"))
    if change.reason == "stock":
        messages.warning(request, f"فقط {change.quantity} عدد از این کالا موجود است؛ همان تعداد به سبد اضافه شد.")
    elif change.reason == "max_qty":
        messages.warning(request, f"حداکثر تعداد مجاز برای هر کالا {change.quantity} عدد است.")
    else:
        messages.success(request, "به سبد خرید اضافه شد.")
    return redirect("/cart/")


@require_POST
def cart_update(request, variant_id):
    try:
        change = services.set_quantity(get_store(request), variant_id, _int(request.POST.get("qty"), 1))
    except services.CartError as exc:
        messages.error(request, str(exc))
    else:
        if change.reason == "stock":
            messages.warning(request, f"فقط {change.quantity} عدد موجود است.")
        elif change.reason == "max_qty":
            messages.warning(request, f"حداکثر تعداد مجاز {change.quantity} عدد است.")
    return redirect("/cart/")


@require_POST
def cart_remove(request, variant_id):
    services.remove_item(get_store(request), variant_id)
    messages.info(request, "از سبد خرید حذف شد.")
    return redirect("/cart/")
