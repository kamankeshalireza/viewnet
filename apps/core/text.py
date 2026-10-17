"""Persian text normalization (search, phone numbers, coupon codes)."""
from __future__ import annotations

import re
import unicodedata

ZWNJ = "\u200c"
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_CHAR_MAP = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک", "ة": "ه", "ۀ": "ه", "أ": "ا", "إ": "ا", "ٱ": "ا"})
_STRIP = re.compile("[\u0640\u064b-\u065f\u0670]")  # tatweel + harakat
_SPACES = re.compile(r"\s+")


def to_ascii_digits(text: str) -> str:
    return text.translate(_DIGITS)


def normalize_fa(text: str | None, *, zwnj: str = "keep") -> str:
    """Canonicalize Persian text. zwnj: 'keep' | 'space' | 'remove'."""
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text).translate(_CHAR_MAP)
    text = _STRIP.sub("", text)
    if zwnj == "space":
        text = text.replace(ZWNJ, " ")
    elif zwnj == "remove":
        text = text.replace(ZWNJ, "")
    return _SPACES.sub(" ", text).strip()


def search_variants(text: str) -> str:
    """Index text containing both ZWNJ-as-space and ZWNJ-removed forms."""
    a, b = normalize_fa(text, zwnj="space"), normalize_fa(text, zwnj="remove")
    return a if a == b else f"{a} {b}"


_PHONE_RE = re.compile(r"^09\d{9}$")


def normalize_phone(raw: str | None) -> str | None:
    """Return 09XXXXXXXXX or None. Accepts 0912…, 912…, +98912…, 0098912…, Persian digits."""
    if not raw:
        return None
    s = to_ascii_digits(raw)
    s = re.sub(r"[\s\-()]", "", s)
    if s.startswith("+98"):
        s = "0" + s[3:]
    elif s.startswith("0098"):
        s = "0" + s[4:]
    elif s.startswith("98") and len(s) == 12:
        s = "0" + s[2:]
    elif s.startswith("9") and len(s) == 10:
        s = "0" + s
    return s if _PHONE_RE.match(s) else None


def mask_phone(phone: str) -> str:
    return f"{phone[:4]}***{phone[-3:]}" if len(phone) >= 8 else "***"
