"""Cart rules (architecture §10). The cart stores only variant+quantity; price/stock are always live."""
from __future__ import annotations

from dataclasses import dataclass, field

from django.conf import settings
from django.db import transaction

from apps.catalog.models import ProductVariant
from apps.inventory import services as inventory

from .domain import LineInput, Totals, cart_totals
from .models import Cart
from .stores import CartStore, DbStore


class CartError(Exception):
    """Message is user-facing (Persian)."""


class VariantNotFound(CartError):
    pass


class OutOfStock(CartError):
    pass


@dataclass(frozen=True)
class CartChange:
    variant_id: int
    quantity: int
    requested: int
    reason: str | None = None  # None | "max_qty" | "stock"

    @property
    def adjusted(self) -> bool:
        return self.reason is not None


@dataclass
class CartLine:
    variant: ProductVariant
    quantity: int
    unit_price_rial: int
    available: int | None  # None = unlimited (digital)

    @property
    def product(self):
        return self.variant.product

    @property
    def total_rial(self) -> int:
        return self.unit_price_rial * self.quantity


@dataclass
class CartView:
    lines: list[CartLine] = field(default_factory=list)
    totals: Totals = field(default_factory=lambda: Totals(0, 0))
    issues: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.lines


def _load_variants(ids) -> dict[int, ProductVariant]:
    qs = (ProductVariant.objects.filter(pk__in=list(ids), is_active=True, product__is_active=True, product__category__is_active=True)
          .select_related("product__category", "device_model").prefetch_related("options", "product__images"))
    return {v.pk: v for v in qs}


def _cap(variant: ProductVariant, wanted: int, available: int | None) -> tuple[int, str | None]:
    """Largest quantity we can honour and why we reduced it."""
    limit, reason = wanted, None
    if limit > settings.CART_MAX_QTY_PER_ITEM:
        limit, reason = settings.CART_MAX_QTY_PER_ITEM, "max_qty"
    if available is not None and limit > available:
        limit, reason = max(available, 0), "stock"
    return limit, reason


def add_item(store: CartStore, variant_id: int, qty: int = 1) -> CartChange:
    if qty < 1:
        raise CartError("تعداد نامعتبر است.")
    variant = _load_variants([variant_id]).get(variant_id)
    if variant is None:
        raise VariantNotFound("این کالا در دسترس نیست.")
    available = inventory.availability([variant_id])[variant_id]
    if available is not None and available <= 0:
        raise OutOfStock("این کالا موجود نیست.")
    current = store.items().get(variant_id, 0)
    final, reason = _cap(variant, current + qty, available)
    store.set_qty(variant_id, final)
    return CartChange(variant_id, final, current + qty, reason)


def set_quantity(store: CartStore, variant_id: int, qty: int) -> CartChange:
    if qty <= 0:
        store.set_qty(variant_id, 0)
        return CartChange(variant_id, 0, qty)
    variant = _load_variants([variant_id]).get(variant_id)
    if variant is None:
        store.set_qty(variant_id, 0)
        raise VariantNotFound("این کالا دیگر در دسترس نیست و از سبد حذف شد.")
    available = inventory.availability([variant_id])[variant_id]
    final, reason = _cap(variant, qty, available)
    store.set_qty(variant_id, final)
    return CartChange(variant_id, final, qty, reason)


def remove_item(store: CartStore, variant_id: int) -> None:
    store.set_qty(variant_id, 0)


def build_cart(store: CartStore, *, fix: bool = True) -> CartView:
    """Priced view of the cart. With fix=True the cart heals itself (drops dead items, trims quantities)."""
    items = store.items()
    view = CartView()
    if not items:
        return view
    variants = _load_variants(items)
    stock = inventory.availability(variants)
    for vid, qty in items.items():
        variant = variants.get(vid)
        if variant is None:
            view.issues.append("یکی از کالاهای سبد دیگر در دسترس نبود و حذف شد.")
            if fix:
                store.set_qty(vid, 0)
            continue
        available = stock.get(vid)
        final, reason = _cap(variant, qty, available)
        if final <= 0:
            view.issues.append(f"«{variant.product.title}» موجود نیست و از سبد حذف شد.")
            if fix:
                store.set_qty(vid, 0)
            continue
        if final != qty:
            view.issues.append(f"تعداد «{variant.product.title}» به {final} عدد کاهش یافت"
                               + (" (موجودی کافی نیست)." if reason == "stock" else " (سقف تعداد مجاز)."))
            if fix:
                store.set_qty(vid, final)
        view.lines.append(CartLine(variant, final, variant.price_rial, available))
    view.totals = cart_totals([LineInput(line.unit_price_rial, line.quantity) for line in view.lines])
    return view


def merge_guest_into_user(user, guest_items: dict[int, int]) -> int:
    """Sum guest + user quantities, capped by stock/max. Returns how many lines had to be adjusted/dropped.
    Idempotent from the caller's side: the guest cart is cleared right after, so a retry merges nothing."""
    if not guest_items:
        return 0
    adjusted = 0
    with transaction.atomic():
        Cart.objects.select_for_update().get_or_create(user=user)
        store = DbStore(user)
        current = store.items()
        variants = _load_variants(guest_items)
        stock = inventory.availability(variants)
        for vid, qty in guest_items.items():
            variant = variants.get(vid)
            if variant is None:
                adjusted += 1
                continue
            target = current.get(vid, 0) + qty
            final, _ = _cap(variant, target, stock.get(vid))
            if final <= 0:
                adjusted += 1
                continue
            adjusted += final != target
            store.set_qty(vid, final)
    return adjusted


def item_count(store: CartStore) -> int:
    return sum(store.items().values())
