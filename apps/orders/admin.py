from django.contrib import admin, messages

from apps.core.money import rial_to_toman

from .models import Order, OrderItem, OrderStatusHistory
from .services import orders as order_service


class ItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    can_delete = False
    fields = ("product_title", "variant_title", "sku", "unit_price_rial", "quantity", "discount_rial", "line_total_rial")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


class HistoryInline(admin.TabularInline):
    model = OrderStatusHistory
    extra = 0
    can_delete = False
    fields = ("created_at", "from_status", "to_status", "actor", "reason")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


def _advance(to):
    def action(modeladmin, request, queryset):
        done = failed = 0
        for order in queryset:
            try:
                order_service.transition(order.pk, to, actor=request.user, reason="تغییر توسط مدیر")
                done += 1
            except order_service.OrderError as exc:
                failed += 1
                modeladmin.message_user(request, f"{order.number}: {exc}", messages.WARNING)
        modeladmin.message_user(request, f"{done} سفارش به‌روز شد" + (f"، {failed} مورد ناموفق" if failed else ""))
    action.short_description = f"تغییر وضعیت به «{Order.Status(to).label}»"
    action.__name__ = f"to_{to}"
    return action


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("number", "user", "status", "payment_status", "total_toman", "placed_at", "needs_review")
    list_filter = ("status", "payment_status", "needs_review", "requires_shipping")
    search_fields = ("number", "user__phone", "receiver_name", "receiver_phone")
    date_hierarchy = "placed_at"
    inlines = [ItemInline, HistoryInline]
    actions = [_advance("processing"), _advance("packed"), _advance("shipped"), _advance("delivered"), _advance("cancelled")]
    list_select_related = ("user",)

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in Order._meta.fields]  # orders are read-only; change status via the actions

    @admin.display(description="مبلغ (تومان)")
    def total_toman(self, obj):
        return f"{rial_to_toman(obj.total_rial):,}"

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
