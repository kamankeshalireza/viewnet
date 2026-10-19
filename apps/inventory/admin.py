from django import forms
from django.contrib import admin, messages

from . import services
from .models import InventoryItem, InventoryTransaction, StockReservation


class InventoryItemForm(forms.ModelForm):
    """Stock is never edited directly: every change goes through the service so the ledger stays true."""

    delta = forms.IntegerField(label="تغییر موجودی (±)", required=False, help_text="مثلاً 10 برای ورود کالا یا -2 برای کسری")
    note = forms.CharField(label="دلیل / توضیح", required=False, max_length=200)

    class Meta:
        model = InventoryItem
        fields = ("variant", "low_stock_threshold")

    def clean(self):
        data = super().clean()
        if data.get("delta") and not (data.get("note") or "").strip():
            self.add_error("note", "برای تغییر موجودی، دلیل را بنویسید.")
        return data


@admin.register(InventoryItem)
class InventoryItemAdmin(admin.ModelAdmin):
    form = InventoryItemForm
    list_display = ("sku", "product", "variant_label", "on_hand", "reserved", "available_display", "low")
    list_filter = ("variant__product__category",)
    search_fields = ("variant__sku", "variant__product__title")
    list_select_related = ("variant__product", "variant__device_model")
    readonly_fields = ("on_hand", "reserved")
    autocomplete_fields = ()
    raw_id_fields = ("variant",)
    actions = None

    @admin.display(description="SKU")
    def sku(self, obj):
        return obj.variant.sku

    @admin.display(description="محصول")
    def product(self, obj):
        return obj.variant.product.title

    @admin.display(description="مدل/رنگ")
    def variant_label(self, obj):
        return obj.variant.label

    @admin.display(description="قابل فروش")
    def available_display(self, obj):
        return obj.available

    @admin.display(description="کمبود", boolean=True)
    def low(self, obj):
        return obj.available <= obj.low_stock_threshold

    def save_model(self, request, obj, form, change):
        delta, note = form.cleaned_data.get("delta") or 0, form.cleaned_data.get("note") or ""
        if not change:
            obj.save()
        else:
            obj.save(update_fields=["low_stock_threshold"])
        try:
            if delta > 0:
                services.receive_purchase(obj.variant_id, delta, actor=request.user, note=note)
            elif delta < 0:
                services.adjust(obj.variant_id, delta, note=note, actor=request.user)
        except services.InsufficientStock:
            messages.error(request, "موجودی کمتر از مقدار رزروشده/درخواستی است؛ تغییری اعمال نشد.")
        obj.refresh_from_db()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(InventoryTransaction)
class InventoryTransactionAdmin(admin.ModelAdmin):
    list_display = ("created_at", "item", "type", "on_hand_delta", "reserved_delta", "on_hand_after", "reserved_after", "reference_id", "actor")
    list_filter = ("type",)
    search_fields = ("item__variant__sku", "reference_id")
    list_select_related = ("item__variant", "actor")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(StockReservation)
class StockReservationAdmin(admin.ModelAdmin):
    list_display = ("ref", "variant", "quantity", "status", "expires_at")
    list_filter = ("status",)
    search_fields = ("ref", "variant__sku")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
