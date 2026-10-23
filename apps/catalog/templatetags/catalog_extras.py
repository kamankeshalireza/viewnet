from django import template

register = template.Library()

_ICONS = (("قاب", "bi-phone"), ("گلس", "bi-shield-check"), ("محافظ", "bi-shield-check"), ("کابل", "bi-usb-plug"),
          ("شارژر", "bi-lightning-charge"), ("ایرپاد", "bi-earbuds"), ("هندزفری", "bi-earbuds"), ("هدفون", "bi-headset"),
          ("فندک", "bi-car-front"), ("پاوربانک", "bi-battery-charging"), ("اپل", "bi-apple"))


@register.filter
def category_icon(name: str) -> str:
    """Bootstrap-Icons class for a category, picked by a keyword in its name (falls back to a grid icon)."""
    name = name or ""
    return next((icon for key, icon in _ICONS if key in name), "bi-grid")
