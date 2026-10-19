from django.apps import AppConfig


class CartConfig(AppConfig):
    name = "apps.cart"
    verbose_name = "سبد خرید"

    def ready(self):
        from apps.core.events import UserLoggedIn, subscribe

        from .handlers import on_user_logged_in

        subscribe(UserLoggedIn, on_user_logged_in)
