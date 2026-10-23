import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.models import Address
from apps.cart.stores import DbStore
from apps.core.text import to_ascii_digits
from apps.discounts import services as coupons

from .models import Order
from .services import checkout, orders

COUPON_SESSION_KEY = "checkout_coupon"


def _int(value):
    v = to_ascii_digits(str(value or "")).strip()
    return int(v) if v.isdigit() else None


@login_required
@require_GET
def checkout_page(request):
    store = DbStore(request.user)
    try:
        quote = checkout.build_quote(request.user, store, coupon_code=request.session.get(COUPON_SESSION_KEY, ""),
                                     shipping_code=request.GET.get("shipping", ""))
    except checkout.CheckoutError as exc:
        messages.warning(request, str(exc))
        return redirect("cart:detail")
    if quote.coupon_error:
        messages.warning(request, quote.coupon_error)
        request.session.pop(COUPON_SESSION_KEY, None)
    addresses = list(Address.objects.filter(user=request.user, is_deleted=False).select_related("province", "city")
                     .order_by("-is_default", "-pk"))
    return render(request, "checkout/checkout.html", {
        "quote": quote, "addresses": addresses, "token": uuid.uuid4(),
        "coupon_code": quote.coupon.coupon.code if quote.coupon else "",
    })


@login_required
@require_POST
def coupon_apply(request):
    if request.POST.get("remove"):
        request.session.pop(COUPON_SESSION_KEY, None)
        messages.info(request, "کد تخفیف حذف شد.")
        return redirect("orders:checkout")
    code = coupons.normalize_code(request.POST.get("code", ""))
    if not code:
        messages.error(request, "کد تخفیف را وارد کنید.")
        return redirect("orders:checkout")
    try:
        quote = checkout.build_quote(request.user, DbStore(request.user), coupon_code=code)
    except checkout.CheckoutError as exc:
        messages.warning(request, str(exc))
        return redirect("cart:detail")
    if quote.coupon:
        request.session[COUPON_SESSION_KEY] = code
        messages.success(request, "کد تخفیف اعمال شد.")
    else:
        messages.error(request, quote.coupon_error)
    return redirect("orders:checkout")


@login_required
@require_POST
def place_order(request):
    token = request.POST.get("token", "")
    try:
        token = uuid.UUID(token)
    except ValueError:
        messages.error(request, "درخواست نامعتبر بود؛ دوباره تلاش کنید.")
        return redirect("orders:checkout")
    if not request.POST.get("accept_terms"):
        messages.error(request, "برای ثبت سفارش باید قوانین و مقررات را بپذیرید.")
        return redirect("orders:checkout")
    try:
        order, _created = checkout.place_order(
            request.user, DbStore(request.user), address_id=_int(request.POST.get("address_id")),
            shipping_code=request.POST.get("shipping_code", ""), coupon_code=request.session.get(COUPON_SESSION_KEY, ""),
            note=request.POST.get("note", ""), checkout_token=token)
    except checkout.CheckoutError as exc:
        messages.error(request, str(exc))
        return redirect("orders:checkout")
    request.session.pop(COUPON_SESSION_KEY, None)
    return redirect(order.get_absolute_url())


def _own_order(request, number):
    return get_object_or_404(Order.objects.prefetch_related("items", "history"), number=number, user=request.user)


@login_required
@require_GET
def order_detail(request, number):
    return render(request, "orders/order_detail.html", {"order": _own_order(request, number)})


@login_required
@require_GET
def order_list(request):
    page = Paginator(Order.objects.filter(user=request.user).order_by("-placed_at"), 10).get_page(request.GET.get("page"))
    return render(request, "orders/order_list.html", {"page_obj": page})


@login_required
@require_POST
def order_cancel(request, number):
    order = _own_order(request, number)
    try:
        orders.cancel_by_customer(order, request.user)
        messages.success(request, "سفارش لغو شد.")
    except orders.OrderError as exc:
        messages.error(request, str(exc) if "فاز" in str(exc) else "این سفارش قابل لغو نیست.")
    return redirect(order.get_absolute_url())
