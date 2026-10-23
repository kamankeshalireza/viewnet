from django.db import migrations


def create_default(apps, schema_editor):
    ShippingMethod = apps.get_model("shipping", "ShippingMethod")
    ShippingMethod.objects.get_or_create(
        code="free",
        defaults={"name": "ارسال رایگان", "description": "ارسال رایگان برای همهٔ سفارش‌ها", "price_rial": 0,
                  "eta_min_days": 1, "eta_max_days": 4, "is_active": True, "position": 0},
    )


class Migration(migrations.Migration):
    dependencies = [("shipping", "0001_initial")]
    operations = [migrations.RunPython(create_default, migrations.RunPython.noop)]
