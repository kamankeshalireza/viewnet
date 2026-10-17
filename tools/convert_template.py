"""One-shot template converter (dev tool, not part of the runtime app).

Splits src_template/index.html into Django templates:
  templates/includes/header.html, footer.html, catalog/home.html
and rewrites asset paths to {% static %} and *.html links to planned URLs.
Run:  python tools/convert_template.py
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src_template" / "index.html"

# Planned URLs (architecture doc §2.4). Replaced by {% url %} as views are implemented.
LINKS = {
    "index.html": "/", "category.html": "/category/", "search-results.html": "/search/",
    "product-details.html": "/category/", "cart.html": "/cart/", "checkout.html": "/checkout/",
    "order-confirmation.html": "/checkout/result/", "account.html": "/account/orders/",
    "login.html": "/account/login/", "register.html": "/account/login/",
    "payment-methods.html": "/payment-methods/", "paymnt-methods.html": "/payment-methods/",
    "shiping-info.html": "/shipping/", "shipping-info.html": "/shipping/",
    "return-policy.html": "/return-policy/", "retun-policy.html": "/return-policy/",
    "privacy.html": "/privacy/", "tos.html": "/terms/", "about.html": "/about/",
    "faq.html": "/faq/", "contact.html": "/contact/", "support.html": "/support/",
    "404.html": "/404/", "starter-page.html": "#",
}


def rewrite(html: str) -> str:
    html = re.sub(r"assets/([^\"')\s]+)", r"{% static '\1' %}", html)
    def link(m):
        name, frag = m.group(1), m.group(2) or ""
        return f'href="{LINKS.get(name, "#")}{frag}"'
    html = re.sub(r'href="([a-z0-9-]+\.html)(#[^"]*)?"', link, html)
    return html


def between(text, start, end):
    s = text.index(start)
    e = text.index(end, s) + len(end)
    return text[s:e]


def main():
    src = SRC.read_text(encoding="utf8")
    header = between(src, '<header id="header"', "</header>")
    main = between(src, '<main class="main">', "</main>")
    footer = between(src, '<footer id="footer"', "</footer>")

    (ROOT / "templates/includes").mkdir(parents=True, exist_ok=True)
    (ROOT / "apps/catalog/templates/catalog").mkdir(parents=True, exist_ok=True)
    (ROOT / "templates/includes/header.html").write_text("{% load static %}\n" + rewrite(header) + "\n", encoding="utf8")
    (ROOT / "templates/includes/footer.html").write_text("{% load static %}\n" + rewrite(footer) + "\n", encoding="utf8")
    body = rewrite(main)
    # inside <main> keep only the inner content; base.html provides <main>
    inner = body[len('<main class="main">'):-len("</main>")]
    page = ('{% extends "base.html" %}\n{% load static %}\n'
            '{% block title %}ویونت | لوازم جانبی موبایل{% endblock %}\n'
            '{% block body_class %}index-page{% endblock %}\n'
            '{% block content %}' + inner + '{% endblock %}\n')
    (ROOT / "apps/catalog/templates/catalog/home.html").write_text(page, encoding="utf8")
    print("header", len(header), "footer", len(footer), "main", len(main))


if __name__ == "__main__":
    main()
