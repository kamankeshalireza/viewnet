import pytest
from django.core.management import call_command

from apps.catalog.models import Brand, Category, DeviceModel, Product

pytestmark = pytest.mark.django_db


def test_seed_is_idempotent_and_has_users_categories(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    call_command("seed_catalog", "--demo", verbosity=0)
    counts = (Category.objects.count(), Brand.objects.count(), DeviceModel.objects.count(), Product.objects.count())
    call_command("seed_catalog", "--demo", verbosity=0)
    assert counts == (Category.objects.count(), Brand.objects.count(), DeviceModel.objects.count(), Product.objects.count())
    assert set(Category.objects.values_list("name", flat=True)) == {"قاب گوشی", "گلس", "کابل", "شارژر", "ایرپاد", "فندکی ماشین", "پاوربانک", "اپل آیدی"}
    assert Product.objects.filter(product_type="digital", title__contains="اپل آیدی").exists()
    case = Product.objects.get(title__startswith="قاب سیلیکونی")
    assert case.variants.count() == 4 and case.primary_image.renditions
