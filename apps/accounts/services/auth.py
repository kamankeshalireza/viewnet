from django.db import IntegrityError, transaction
from django.utils import timezone

from ..models import User


def login_or_register(phone: str) -> tuple[User, bool]:
    """Phone-first auth: one flow for both login and sign-up."""
    created = False
    try:
        user = User.objects.get(phone=phone)
    except User.DoesNotExist:
        try:
            with transaction.atomic():
                user = User.objects.create_user(phone)
            created = True
        except IntegrityError:  # concurrent first login: someone else just created it
            user = User.objects.get(phone=phone)
    if not user.phone_verified_at:
        user.phone_verified_at = timezone.now()
        user.save(update_fields=["phone_verified_at"])
    return user, created
