from django import forms
from django.contrib import admin

from apps.core.money import rial_to_toman, toman_to_rial

from .models import Coupon, CouponRedemption


class CouponForm(forms.ModelForm):
    """Money fields are typed in Toman; stored in Rial."""

    amount_toman = forms.IntegerField(label="مبلغ تخفیف (تومان)", min_value=0, required=False)
    max_discount_toman = forms.IntegerField(label="سقف تخفیف (تومان)", min_value=0, required=False)
    min_order_toman = forms.IntegerField(label="حداقل مبلغ سفارش (تومان)", min_value=0, required=False, initial=0)

    class Meta:
        model = Coupon
        exclude = ("amount_rial", "max_discount_rial", "min_order_rial")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        i = self.instance
        if i.pk:
            self.fields["amount_toman"].initial = rial_to_toman(i.amount_rial) if i.amount_rial else None
            self.fields["max_discount_toman"].initial = rial_to_toman(i.max_discount_rial) if i.max_discount_rial else None
            self.fields["min_order_toman"].initial = rial_to_toman(i.min_order_rial)

    def clean(self):
        data = super().clean()
        if data.get("kind") == "percent" and not (data.get("percent") and 1 <= data["percent"] <= 100):
            self.add_error("percent", "برای کد درصدی، عددی بین ۱ تا ۱۰۰ وارد کنید.")
        if data.get("kind") == "fixed" and not data.get("amount_toman"):
            self.add_error("amount_toman", "برای کد مبلغ ثابت، مبلغ را وارد کنید.")
        return data

    def save(self, commit=True):
        obj = super().save(commit=False)
        c = self.cleaned_data
        obj.amount_rial = toman_to_rial(c["amount_toman"]) if c.get("amount_toman") else None
        obj.max_discount_rial = toman_to_rial(c["max_discount_toman"]) if c.get("max_discount_toman") else None
        obj.min_order_rial = toman_to_rial(c.get("min_order_toman") or 0)
        if obj.kind == "percent":
            obj.amount_rial = None
        else:
            obj.percent = None
        if commit:
            obj.save()
        return obj


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    form = CouponForm
    list_display = ("code", "kind", "percent", "is_active", "starts_at", "ends_at", "max_uses_total", "used")
    list_filter = ("kind", "is_active")
    search_fields = ("code", "note")

    @admin.display(description="استفاده")
    def used(self, obj):
        return obj.redemptions.filter(status__in=["reserved", "redeemed"]).count()


@admin.register(CouponRedemption)
class CouponRedemptionAdmin(admin.ModelAdmin):
    list_display = ("coupon", "user", "order_ref", "status", "discount_rial", "created_at")
    list_filter = ("status",)
    search_fields = ("order_ref", "coupon__code", "user__phone")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
