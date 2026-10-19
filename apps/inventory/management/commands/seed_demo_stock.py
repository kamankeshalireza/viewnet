"""Give the demo products stock so the storefront can be tried end-to-end (idempotent).
The 2nd variant of each demo product is left sold-out on purpose to exercise the sold-out UI."""
from django.core.management.base import BaseCommand

from apps.catalog.models import Product, ProductVariant
from apps.inventory import services
from apps.inventory.models import InventoryItem


class Command(BaseCommand):
    help = "Add demo stock to variants of products whose title ends with «(نمونه)»."

    def handle(self, *args, **opts):
        added = 0
        for product in Product.objects.filter(title__endswith="(نمونه)", product_type=Product.Type.PHYSICAL):
            for n, v in enumerate(ProductVariant.objects.filter(product=product).order_by("position", "pk")):
                if n == 1 or InventoryItem.objects.filter(variant=v).exists():
                    continue
                services.receive_purchase(v.pk, 8, note="موجودی نمونه")
                added += 1
        self.stdout.write(self.style.SUCCESS(f"Demo stock added to {added} variants"))
