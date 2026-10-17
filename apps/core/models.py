from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField("تاریخ ایجاد", auto_now_add=True)
    updated_at = models.DateTimeField("آخرین ویرایش", auto_now=True)

    class Meta:
        abstract = True


class SiteSetting(TimeStampedModel):
    """Singleton: store-wide settings editable from the admin."""

    store_name = models.CharField("نام فروشگاه", max_length=100, default="ویونت")
    tagline = models.CharField("شعار", max_length=150, default="لوازم جانبی موبایل")
    phone = models.CharField("تلفن", max_length=20, blank=True)
    email = models.EmailField("ایمیل", blank=True)
    address = models.TextField("نشانی", blank=True)
    announcement = models.CharField("پیام نوار بالا", max_length=200, blank=True)
    purchases_enabled = models.BooleanField("امکان خرید فعال است", default=True)
    min_order_rial = models.PositiveBigIntegerField("حداقل مبلغ سفارش (ریال)", default=0)

    class Meta:
        verbose_name = "تنظیمات سایت"
        verbose_name_plural = "تنظیمات سایت"

    def __str__(self):
        return self.store_name

    def save(self, *args, **kwargs):
        self.pk = 1  # enforce singleton
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
