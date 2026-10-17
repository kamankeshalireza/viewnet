from django.db import transaction

from ..models import Address


def set_default_address(address: Address) -> None:
    with transaction.atomic():
        Address.objects.filter(user=address.user, is_default=True).exclude(pk=address.pk).update(is_default=False)
        if not address.is_default:
            address.is_default = True
            address.save(update_fields=["is_default", "updated_at"])
