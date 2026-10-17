from django.conf import settings


def get_client_ip(request) -> str:
    """Client IP behind N trusted reverse proxies (NUM_PROXIES). Never trust the leftmost XFF entry:
    clients can forge it. With 0 proxies only REMOTE_ADDR is used."""
    n = settings.NUM_PROXIES
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if n > 0 and xff:
        parts = [p.strip() for p in xff.split(",") if p.strip()]
        if len(parts) >= n:
            return parts[-n]
    return request.META.get("REMOTE_ADDR", "") or "unknown"
