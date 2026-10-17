from django.db import models


class Province(models.Model):
    name = models.CharField("نام", max_length=60, unique=True)
    slug = models.SlugField("اسلاگ", allow_unicode=True, unique=True)

    class Meta:
        verbose_name, verbose_name_plural, ordering = "استان", "استان‌ها", ["name"]

    def __str__(self):
        return self.name


class City(models.Model):
    province = models.ForeignKey(Province, on_delete=models.PROTECT, related_name="cities")
    name = models.CharField("نام", max_length=80)
    slug = models.SlugField("اسلاگ", allow_unicode=True)
    is_active = models.BooleanField("فعال", default=True)

    class Meta:
        verbose_name, verbose_name_plural, ordering = "شهر", "شهرها", ["name"]
        constraints = [models.UniqueConstraint(fields=["province", "name"], name="uniq_city_per_province")]
        indexes = [models.Index(fields=["province", "is_active"])]

    def __str__(self):
        return f"{self.name}، {self.province.name}"
