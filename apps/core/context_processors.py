from django.conf import settings
from django.core.cache import cache

from .models import SiteSetting


def site(request):
    """Store-wide settings, cached briefly to avoid a query on every request."""
    setting = cache.get("site_setting")
    if setting is None:
        try:
            setting = SiteSetting.load()
        except Exception:  # DB not migrated yet (first boot / CI)
            setting = SiteSetting()
        cache.set("site_setting", setting, 60)
    return {"site": setting, "SITE_URL": settings.SITE_URL.rstrip("/")}
