from .services import item_count
from .stores import get_store


def cart_summary(request):
    if not hasattr(request, "session"):
        return {"cart_count": 0}
    try:
        return {"cart_count": item_count(get_store(request))}
    except Exception:  # never break a page because the cart badge failed
        return {"cart_count": 0}
