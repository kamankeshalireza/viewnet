from django import forms
from django.contrib import admin, messages
from django.db import transaction

from apps.core.money import rial_to_toman, toman_to_rial

from . import services
from .images import process_product_image
from .models import (
    AttributeDefinition,
    AttributeOption,
    Brand,
    Category,
    DeviceModel,
    Product,
    ProductAttributeValue,
    ProductImage,
    ProductSpecification,
    ProductVariant,
    WishlistItem,
)


class VariantForm(forms.ModelForm):
    """Admins type prices in Toman; the model stores Rial (architecture §6.0)."""

    price_toman = forms.IntegerField(label="قیمت (تومان)", min_value=0)
    compare_at_toman = forms.IntegerField(label="قیمت قبل از تخفیف (تومان)", min_value=0, required=False)

    class Meta:
        model = ProductVariant
        exclude = ("price_rial", "compare_at_price_rial")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["price_toman"].initial = rial_to_toman(self.instance.price_rial)
            if self.instance.compare_at_price_rial:
                self.fields["compare_at_toman"].initial = rial_to_toman(self.instance.compare_at_price_rial)

    def clean(self):
        data = super().clean()
        price, compare = data.get("price_toman"), data.get("compare_at_toman")
        if price is not None and compare and compare <= price:
            self.add_error("compare_at_toman", "قیمت قبل از تخفیف باید بیشتر از قیمت فروش باشد.")
        return data

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.price_rial = toman_to_rial(self.cleaned_data["price_toman"])
        compare = self.cleaned_data.get("compare_at_toman")
        obj.compare_at_price_rial = toman_to_rial(compare) if compare else None
        if commit:
            obj.save()
            self.save_m2m()
        return obj


class VariantInline(admin.TabularInline):
    model = ProductVariant
    form = VariantForm
    extra = 0
    fields = ("sku", "device_model", "options", "price_toman", "compare_at_toman", "weight_g", "is_default", "is_active", "position")
    autocomplete_fields = ("device_model",)
    filter_horizontal = ("options",)


class ImageInline(admin.TabularInline):
    model = ProductImage
    extra = 0
    fields = ("image", "alt", "position", "is_primary")


class SpecInline(admin.TabularInline):
    model = ProductSpecification
    extra = 0


class AttrValueInline(admin.TabularInline):
    model = ProductAttributeValue
    extra = 0


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "brand", "product_type", "price_range", "in_stock", "is_active", "is_featured")
    list_filter = ("is_active", "is_featured", "product_type", "category", "brand")
    search_fields = ("title", "variants__sku")
    list_select_related = ("category", "brand")
    autocomplete_fields = ("brand",)
    prepopulated_fields = {}
    inlines = [VariantInline, ImageInline, SpecInline, AttrValueInline]
    actions = ["activate", "deactivate", "reindex"]
    fieldsets = (
        (None, {"fields": ("title", "slug", "product_type", "category", "brand", "short_description", "description")}),
        ("نمایش", {"fields": ("is_active", "is_featured", "published_at")}),
        ("سئو", {"classes": ("collapse",), "fields": ("seo_title", "seo_description", "seo_noindex")}),
    )

    @admin.display(description="بازهٔ قیمت")
    def price_range(self, obj):
        if not obj.min_price_rial:
            return "—"
        lo = f"{rial_to_toman(obj.min_price_rial):,}"
        return lo if not obj.has_price_range else f"{lo} – {rial_to_toman(obj.max_price_rial):,}"

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        product = form.instance
        services.recalc_product(product.pk)  # variants/options are saved now
        for img in product.images.filter(renditions={}):
            transaction.on_commit(lambda i=img.pk: process_product_image.delay(i))

    @admin.action(description="فعال کردن")
    def activate(self, request, qs):
        self.message_user(request, f"{qs.update(is_active=True)} محصول فعال شد.")

    @admin.action(description="غیرفعال کردن")
    def deactivate(self, request, qs):
        self.message_user(request, f"{qs.update(is_active=False)} محصول غیرفعال شد.")

    @admin.action(description="بازسازی قیمت/جستجو")
    def reindex(self, request, qs):
        n = services.recalc_products(list(qs.values_list("pk", flat=True)))
        self.message_user(request, f"{n} محصول بازسازی شد.", messages.SUCCESS)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("indented_name", "slug_path", "position", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)
    ordering = ("path",)
    fields = ("parent", "name", "slug", "position", "image", "description", "is_active", "seo_title", "seo_description", "seo_noindex")

    @admin.display(description="نام")
    def indented_name(self, obj):
        return str(obj)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if change:
            services.reindex_for(category=obj)


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ("name", "name_en", "is_phone_brand", "is_active")
    list_filter = ("is_phone_brand", "is_active")
    search_fields = ("name", "name_en")

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if change:
            services.reindex_for(brand=obj)


@admin.register(DeviceModel)
class DeviceModelAdmin(admin.ModelAdmin):
    list_display = ("name", "brand", "series", "release_year", "is_active")
    list_filter = ("brand", "is_active")
    search_fields = ("name", "series", "search_aliases")

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if change:
            services.reindex_for(device_model=obj)


class OptionInline(admin.TabularInline):
    model = AttributeOption
    extra = 1


@admin.register(AttributeDefinition)
class AttributeDefinitionAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "kind", "is_variant_axis", "is_filterable")
    inlines = [OptionInline]


@admin.register(WishlistItem)
class WishlistItemAdmin(admin.ModelAdmin):
    list_display = ("user", "product", "created_at")
    raw_id_fields = ("user", "product")
