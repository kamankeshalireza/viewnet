"""Template filters, auto-loaded as builtins (see TEMPLATES.OPTIONS.builtins)."""
from __future__ import annotations

from datetime import datetime

import jdatetime
from django import template
from django.utils import timezone

from apps.core.money import rial_to_toman

register = template.Library()
_FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


@register.filter
def fa_digits(value):
    return str(value).translate(_FA_DIGITS)


@register.filter
def toman(rial, with_unit=True):
    """Rial (int) -> '۱٬۲۵۰٬۰۰۰ تومان'."""
    if rial is None or rial == "":
        return ""
    text = f"{rial_to_toman(int(rial)):,}".replace(",", "٬").translate(_FA_DIGITS)
    return f"{text} تومان" if with_unit else text


@register.filter
def jalali(value, fmt="%Y/%m/%d"):
    """Aware/naive datetime (UTC in DB) -> Jalali string in Asia/Tehran."""
    if not value:
        return ""
    if isinstance(value, datetime) and timezone.is_aware(value):
        value = timezone.localtime(value)
    jd = jdatetime.datetime.fromgregorian(datetime=value) if isinstance(value, datetime) \
        else jdatetime.date.fromgregorian(date=value)
    return jd.strftime(fmt).translate(_FA_DIGITS)
