from __future__ import annotations

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import F, Q
from django.templatetags.static import static
from django.utils import timezone

from apps.core.models import TimeStampedModel
from apps.core.sanitize import clean_html
from apps.core.text import make_slug

from .validators import validate_product_image

CATEGORY_TREE_CACHE_KEY = "catalog:category_tree:v1"


class SEOFields(models.Model):
    seo_title = models.CharField("عنوان سئو", max_length=70, blank=True)
    seo_description = models.CharField("توضیحات سئو", max_length=170, blank=True)
    seo_noindex = models.BooleanField("noindex", default=False)

    class Meta:
        abstract = True


class Brand(TimeStampedModel, SEOFields):
    name = models.CharField("نام (فارسی)", max_length=80)
    name_en = models.CharField("نام (انگلیسی)", max_length=80, blank=True)
    slug = models.SlugField("اسلاگ", allow_unicode=True, unique=True, max_length=100, blank=True)
    logo = models.ImageField("لوگو", upload_to="brands/", blank=True, validators=[validate_product_image])
    search_aliases = models.CharField("معادل‌های جستجو", max_length=200, blank=True,
                                      help_text="مثلاً: iphone ایفون — با فاصله جدا کنید")
    is_phone_brand = models.BooleanField("برند سازندهٔ گوشی", default=False)
    is_active = models.BooleanField("فعال", default=True)

    class Meta:
        verbose_name, verbose_name_plural, ordering = "برند", "برندها", ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = make_slug(self.name_en or self.name)
        super().save(*args, **kwargs)


class Category(TimeStampedModel, SEOFields):
    """Tree via materialized path. `path` ('/1/5/') for subtree queries; `slug_path` for URLs."""

    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT,
                               related_name="children", verbose_name="دستهٔ والد")
    name = models.CharField("نام", max_length=100)
    slug = models.SlugField("اسلاگ", allow_unicode=True, max_length=100, blank=True)
    path = models.CharField(max_length=255, blank=True, default="", editable=False, db_index=True)
    slug_path = models.CharField(max_length=500, blank=True, default="", editable=False)
    depth = models.PositiveSmallIntegerField(default=0, editable=False)
    position = models.PositiveIntegerField("ترتیب", default=0)
    image = models.ImageField("تصویر", upload_to="categories/", blank=True, validators=[validate_product_image])
    description = models.TextField("توضیحات", blank=True)
    is_active = models.BooleanField("فعال", default=True)

    class Meta:
        verbose_name, verbose_name_plural, ordering = "دسته‌بندی", "دسته‌بندی‌ها", ["path"]
        constraints = [models.UniqueConstraint(fields=["slug_path"], condition=~Q(slug_path=""),
                                               name="uniq_category_slug_path")]

    def __str__(self):
        return ("— " * self.depth) + self.name

    def clean(self):
        if self.pk and self.parent_id:
            if self.parent_id == self.pk or (self.path and self.parent.path.startswith(self.path)):
                raise ValidationError({"parent": "دستهٔ والد نمی‌تواند خود دسته یا زیرمجموعهٔ آن باشد."})

    def save(self, *args, **kwargs):
        """Maintains path/slug_path/depth (needed so the admin stays correct). Moves re-path the subtree."""
        if not self.slug:
            self.slug = make_slug(self.name)
        with transaction.atomic():
            super().save(*args, **kwargs)
            parent = self.parent
            path = f"{parent.path}{self.pk}/" if parent else f"/{self.pk}/"
            slug_path = f"{parent.slug_path}/{self.slug}" if parent else self.slug
            depth = parent.depth + 1 if parent else 0
            if (path, slug_path, depth) != (self.path, self.slug_path, self.depth):
                self.path, self.slug_path, self.depth = path, slug_path, depth
                Category.objects.filter(pk=self.pk).update(path=path, slug_path=slug_path, depth=depth)
                for child in self.children.all():  # re-path descendants (rare: only on move/rename)
                    child.save()
        cache.delete(CATEGORY_TREE_CACHE_KEY)

    def delete(self, *args, **kwargs):
        out = super().delete(*args, **kwargs)
        cache.delete(CATEGORY_TREE_CACHE_KEY)
        return out

    def get_absolute_url(self):
        return f"/category/{self.slug_path}/"

    def ancestors(self):
        ids = [int(i) for i in self.path.strip("/").split("/") if i][:-1]
        found = {c.pk: c for c in Category.objects.filter(pk__in=ids)}
        return [found[i] for i in ids if i in found]

    def subtree_ids(self) -> list[int]:
        return list(Category.objects.filter(path__startswith=self.path).values_list("pk", flat=True))


class DeviceModel(TimeStampedModel):
    """A phone model (iPhone 15 Pro). It is a *variant axis* for cases/glass: stock is tracked per model."""

    brand = models.ForeignKey(Brand, on_delete=models.PROTECT, related_name="device_models",
                              limit_choices_to={"is_phone_brand": True}, verbose_name="برند")
    series = models.CharField("سری", max_length=60, blank=True)
    name = models.CharField("نام مدل", max_length=80)
    slug = models.SlugField("اسلاگ", allow_unicode=True, unique=True, max_length=100, blank=True)
    search_aliases = models.CharField("معادل‌های جستجو", max_length=200, blank=True)
    release_year = models.PositiveSmallIntegerField("سال عرضه", null=True, blank=True)
    position = models.PositiveIntegerField("ترتیب", default=0)
    is_active = models.BooleanField("فعال", default=True)

    class Meta:
        verbose_name, verbose_name_plural, ordering = "مدل گوشی", "مدل‌های گوشی", ["brand", "-release_year", "name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = make_slug(f"{self.brand.name_en or self.brand.name} {self.name}")
        super().save(*args, **kwargs)


class AttributeDefinition(models.Model):
    class Kind(models.TextChoices):
        CHOICE = "choice", "انتخابی"
        COLOR = "color", "رنگ"

    code = models.SlugField("کد", unique=True)
    name = models.CharField("نام", max_length=60)
    kind = models.CharField("نوع", max_length=10, choices=Kind.choices, default=Kind.CHOICE)
    is_variant_axis = models.BooleanField("محور تنوع (Variant)", default=False)
    is_filterable = models.BooleanField("قابل فیلتر", default=True)
    position = models.PositiveIntegerField("ترتیب", default=0)

    class Meta:
        verbose_name, verbose_name_plural, ordering = "ویژگی", "ویژگی‌ها", ["position", "name"]

    def __str__(self):
        return self.name


class AttributeOption(models.Model):
    definition = models.ForeignKey(AttributeDefinition, on_delete=models.CASCADE, related_name="options")
    value = models.SlugField("مقدار (کد)", allow_unicode=True)
    label = models.CharField("برچسب", max_length=60)
    hex = models.CharField("کد رنگ", max_length=7, blank=True, help_text="مثلاً #000000 (فقط برای رنگ)")
    position = models.PositiveIntegerField("ترتیب", default=0)

    class Meta:
        verbose_name, verbose_name_plural, ordering = "گزینهٔ ویژگی", "گزینه‌های ویژگی", ["definition", "position", "label"]
        constraints = [models.UniqueConstraint(fields=["definition", "value"], name="uniq_option_per_definition")]

    def __str__(self):
        return f"{self.definition.name}: {self.label}"


class Product(TimeStampedModel, SEOFields):
    class Type(models.TextChoices):
        PHYSICAL = "physical", "کالای فیزیکی"
        DIGITAL = "digital", "دیجیتال / خدمت (بدون ارسال)"

    product_type = models.CharField("نوع", max_length=10, choices=Type.choices, default=Type.PHYSICAL)
    title = models.CharField("عنوان", max_length=200)
    slug = models.SlugField("اسلاگ", allow_unicode=True, max_length=200, blank=True)
    brand = models.ForeignKey(Brand, null=True, blank=True, on_delete=models.PROTECT, related_name="products",
                              verbose_name="برند")
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products", verbose_name="دسته")
    short_description = models.CharField("توضیح کوتاه", max_length=300, blank=True)
    description = models.TextField("توضیحات", blank=True)
    is_active = models.BooleanField("فعال", default=True)
    is_featured = models.BooleanField("ویژه", default=False)
    published_at = models.DateTimeField("زمان انتشار", default=timezone.now)

    attribute_options = models.ManyToManyField(AttributeOption, through="ProductAttributeValue",
                                               related_name="products", blank=True)

    # Denormalized (maintained by catalog.services.recalc_product; never edit by hand)
    min_price_rial = models.PositiveBigIntegerField(default=0, editable=False)
    max_price_rial = models.PositiveBigIntegerField(default=0, editable=False)
    compare_at_min_rial = models.PositiveBigIntegerField(default=0, editable=False)
    in_stock = models.BooleanField(default=False, editable=False)
    rating_avg_x10 = models.PositiveSmallIntegerField(default=0, editable=False)
    rating_count = models.PositiveIntegerField(default=0, editable=False)
    sales_count = models.PositiveIntegerField(default=0, editable=False)
    search_text = models.TextField(blank=True, default="", editable=False)

    class Meta:
        verbose_name, verbose_name_plural, ordering = "محصول", "محصولات", ["-published_at", "-pk"]
        constraints = [models.CheckConstraint(condition=Q(min_price_rial__lte=F("max_price_rial")),
                                              name="product_min_price_lte_max")]
        indexes = [
            models.Index(fields=["is_active", "category", "-published_at"], name="prod_cat_new_idx"),
            models.Index(fields=["is_active", "min_price_rial"], name="prod_price_idx"),
            models.Index(fields=["is_active", "-sales_count"], name="prod_sales_idx"),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = make_slug(self.title)
        self.description = clean_html(self.description)
        super().save(*args, **kwargs)

    @property
    def requires_shipping(self) -> bool:
        return self.product_type == self.Type.PHYSICAL

    @property
    def is_new(self) -> bool:
        return (timezone.now() - self.published_at).days < 14

    @property
    def discount_percent(self) -> int:
        if self.compare_at_min_rial and self.min_price_rial and self.compare_at_min_rial > self.min_price_rial:
            return 100 - (self.min_price_rial * 100) // self.compare_at_min_rial
        return 0

    @property
    def has_price_range(self) -> bool:
        return self.min_price_rial != self.max_price_rial

    @property
    def primary_image(self):
        images = getattr(self, "prefetched_images", None)
        if images is None:
            images = list(self.images.all())
        return next((i for i in images if i.is_primary), images[0] if images else None)

    @property
    def hover_image(self):
        images = getattr(self, "prefetched_images", None)
        if images is None:
            images = list(self.images.all())
        primary = self.primary_image
        return next((i for i in images if i is not primary), None)

    def get_absolute_url(self):
        return f"/product/{self.pk}/{self.slug}/"


class ProductVariant(TimeStampedModel):
    """One sellable SKU. Stock (Phase 4) is tracked per variant → per phone model."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    sku = models.CharField("SKU", max_length=50, unique=True)
    barcode = models.CharField("بارکد", max_length=50, blank=True)
    device_model = models.ForeignKey(DeviceModel, null=True, blank=True, on_delete=models.PROTECT,
                                     related_name="variants", verbose_name="مدل گوشی")
    options = models.ManyToManyField(AttributeOption, blank=True, related_name="variants", verbose_name="ویژگی‌ها (رنگ و…)")
    price_rial = models.PositiveBigIntegerField("قیمت (ریال)")
    compare_at_price_rial = models.PositiveBigIntegerField("قیمت قبل از تخفیف (ریال)", null=True, blank=True)
    weight_g = models.PositiveIntegerField("وزن (گرم)", default=0)
    is_default = models.BooleanField("پیش‌فرض", default=False)
    is_active = models.BooleanField("فعال", default=True)
    position = models.PositiveIntegerField("ترتیب", default=0)

    class Meta:
        verbose_name, verbose_name_plural, ordering = "تنوع کالا", "تنوع‌های کالا", ["position", "pk"]
        constraints = [
            models.CheckConstraint(condition=Q(compare_at_price_rial__isnull=True) | Q(compare_at_price_rial__gt=F("price_rial")),
                                   name="variant_compare_gt_price"),
            models.UniqueConstraint(fields=["product"], condition=Q(is_default=True), name="one_default_variant_per_product"),
        ]

    def __str__(self):
        return f"{self.product.title} — {self.label}" if self.label else self.product.title

    @property
    def label(self) -> str:
        parts = []
        if self.device_model_id:
            parts.append(self.device_model.name)
        parts += [o.label for o in self.options.all()]
        return " / ".join(parts)


class ProductAttributeValue(models.Model):
    """Filterable attribute at product level (e.g. connector type, material)."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="attribute_values")
    option = models.ForeignKey(AttributeOption, on_delete=models.CASCADE, related_name="product_values")

    class Meta:
        verbose_name, verbose_name_plural = "ویژگی محصول", "ویژگی‌های محصول"
        constraints = [models.UniqueConstraint(fields=["product", "option"], name="uniq_product_option")]


class ProductSpecification(models.Model):
    """Display-only technical specs (not filterable)."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="specifications")
    group = models.CharField("گروه", max_length=60, blank=True)
    key = models.CharField("عنوان", max_length=80)
    value = models.CharField("مقدار", max_length=200)
    position = models.PositiveIntegerField("ترتیب", default=0)

    class Meta:
        verbose_name, verbose_name_plural, ordering = "مشخصه فنی", "مشخصات فنی", ["position", "pk"]


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField("تصویر", upload_to="products/%Y/%m/", validators=[validate_product_image])
    alt = models.CharField("متن جایگزین", max_length=150, blank=True)
    position = models.PositiveIntegerField("ترتیب", default=0)
    is_primary = models.BooleanField("تصویر اصلی", default=False)
    width = models.PositiveIntegerField(null=True, blank=True, editable=False)
    height = models.PositiveIntegerField(null=True, blank=True, editable=False)
    renditions = models.JSONField(default=dict, blank=True, editable=False)

    class Meta:
        verbose_name, verbose_name_plural, ordering = "تصویر محصول", "تصاویر محصول", ["position", "pk"]
        constraints = [models.UniqueConstraint(fields=["product"], condition=Q(is_primary=True),
                                               name="one_primary_image_per_product")]

    def _url(self, size: str) -> str:
        from django.core.files.storage import default_storage

        name = self.renditions.get(size)
        if name:
            return default_storage.url(name)
        return self.image.url if self.image else static("img/no-image.svg")  # fallback while processing

    url_thumb = property(lambda self: self._url("thumb"))
    url_card = property(lambda self: self._url("card"))
    url_detail = property(lambda self: self._url("detail"))
    url_zoom = property(lambda self: self._url("zoom"))


class WishlistItem(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="wishlist_items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="wishlisted_by")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name, verbose_name_plural, ordering = "علاقه‌مندی", "علاقه‌مندی‌ها", ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["user", "product"], name="uniq_wishlist_item")]
