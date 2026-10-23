from django.db import models


class ShippingMethod(models.Model):
    """Today every method is a flat price (the shop ships free). Zone/weight rates can be added later
    behind `services.quote()` without touching checkout."""

    code = models.SlugField("کد", unique=True)
    name = models.CharField("نام", max_length=80)
    description = models.CharField("توضیح", max_length=200, blank=True)
    price_rial = models.PositiveBigIntegerField("هزینه (ریال)", default=0)
    eta_min_days = models.PositiveSmallIntegerField("حداقل روز تحویل", default=1)
    eta_max_days = models.PositiveSmallIntegerField("حداکثر روز تحویل", default=4)
    is_active = models.BooleanField("فعال", default=True)
    position = models.PositiveIntegerField("ترتیب", default=0)

    class Meta:
        verbose_name, verbose_name_plural, ordering = "روش ارسال", "روش‌های ارسال", ["position", "pk"]

    def __str__(self):
        return self.name

    @property
    def eta_text(self) -> str:
        return f"{self.eta_min_days} تا {self.eta_max_days} روز کاری"
