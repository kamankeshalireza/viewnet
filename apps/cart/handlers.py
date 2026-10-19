import logging

from django.contrib import messages

from apps.core.constants import GUEST_CART_SESSION_KEY
from apps.core.events import UserLoggedIn

from . import services

log = logging.getLogger("cart")


def on_user_logged_in(event: UserLoggedIn) -> None:
    """Fold the guest cart (captured before login) into the user's saved cart."""
    guest = {}
    for k, v in (event.guest_cart or {}).items():
        try:
            guest[int(k)] = int(v)
        except (TypeError, ValueError):
            continue
    try:
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.get(pk=event.user_id)
        adjusted = services.merge_guest_into_user(user, guest)
    except Exception:
        log.exception("cart merge failed user=%s", event.user_id)
        return
    event.request.session.pop(GUEST_CART_SESSION_KEY, None)
    if adjusted:
        messages.info(event.request, "سبد خرید قبلی شما با سبد فعلی ادغام شد؛ تعداد برخی کالاها بر اساس موجودی اصلاح شد.")
