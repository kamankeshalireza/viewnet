"""Load provinces + a STARTER list of cities (province capitals and big cities). Idempotent.
This is not the official full list — add/import the rest from the admin (⚠️ V20 in the architecture doc)."""
import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.core.text import make_slug
from apps.locations.models import City, Province

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


class Command(BaseCommand):
    help = "Seed provinces and a starter list of cities (idempotent)."

    @transaction.atomic
    def handle(self, *args, **opts):
        for row in json.loads((FIXTURES / "provinces.json").read_text(encoding="utf8")):
            f = row["fields"]
            Province.objects.get_or_create(name=f["name"], defaults={"slug": f["slug"]})
        created = 0
        for prov_name, names in json.loads((FIXTURES / "cities_seed.json").read_text(encoding="utf8")).items():
            province = Province.objects.get(name=prov_name)
            for name in names:
                _, new = City.objects.get_or_create(province=province, name=name, defaults={"slug": make_slug(name)})
                created += new
        self.stdout.write(self.style.SUCCESS(f"Provinces: {Province.objects.count()}, cities: {City.objects.count()} (+{created})"))
