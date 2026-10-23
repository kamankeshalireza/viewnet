import pytest
from django.core.management import call_command

from apps.locations.models import City, Province

pytestmark = pytest.mark.django_db


def test_seed_locations_is_idempotent_and_covers_every_province():
    call_command("seed_locations", verbosity=0)
    counts = (Province.objects.count(), City.objects.count())
    call_command("seed_locations", verbosity=0)
    assert counts == (Province.objects.count(), City.objects.count()) and counts[0] == 31 and counts[1] >= 80
    assert not Province.objects.filter(cities__isnull=True).exists()  # every province has at least its capital
    assert City.objects.filter(name="تهران", province__name="تهران").exists()
