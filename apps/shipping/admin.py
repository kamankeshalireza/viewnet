from django import forms
from django.contrib import admin

from apps.core.money import rial_to_toman, toman_to_rial

from .models import ShippingMethod


class ShippingMethodForm(forms.ModelForm):
    price_toman = forms.IntegerField(label="هزینه (تومان)", min_value=0, initial=0)

    class Meta:
        model = ShippingMethod
        exclude = ("price_rial",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["price_toman"].initial = rial_to_toman(self.instance.price_rial)

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.price_rial = toman_to_rial(self.cleaned_data["price_toman"])
        if commit:
            obj.save()
        return obj


@admin.register(ShippingMethod)
class ShippingMethodAdmin(admin.ModelAdmin):
    form = ShippingMethodForm
    list_display = ("name", "code", "is_active", "position")
