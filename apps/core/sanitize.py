"""HTML sanitizer for admin-authored rich text (product descriptions, CMS pages)."""
import nh3

ALLOWED_TAGS = {
    "p", "br", "hr", "strong", "b", "em", "i", "u", "ul", "ol", "li", "h2", "h3", "h4", "blockquote",
    "a", "img", "table", "thead", "tbody", "tr", "th", "td", "span", "div",
}
ALLOWED_ATTRIBUTES = {
    "a": {"href", "title"},
    "img": {"src", "alt", "width", "height"},
    "*": {"dir"},
}


def clean_html(html: str | None) -> str:
    return nh3.clean(
        html or "",
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        url_schemes={"http", "https", "mailto", "tel"},
        link_rel="noopener noreferrer nofollow",
    )
