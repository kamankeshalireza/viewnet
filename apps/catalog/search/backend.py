"""Search abstraction. The portable backend works on any DB; a PostgreSQL FTS/trigram backend
can be dropped in later via settings.SEARCH_BACKEND without touching views."""
from __future__ import annotations

from django.conf import settings
from django.db.models import Case, IntegerField, Q, QuerySet, Value, When
from django.utils.module_loading import import_string

from apps.core.text import normalize_fa, to_ascii_digits


def normalize_query(q: str | None) -> list[str]:
    q = to_ascii_digits(normalize_fa(q or "", zwnj="space")).lower()
    return [t for t in q.split(" ") if t][:8]


class SearchBackend:
    def apply(self, qs: QuerySet, q: str) -> QuerySet:  # pragma: no cover - interface
        raise NotImplementedError


class SimpleSearchBackend(SearchBackend):
    """All tokens must appear in the normalized `search_text` (substring match). Title hits rank first."""

    def apply(self, qs, q):
        tokens = normalize_query(q)
        if not tokens:
            return qs.none()
        for t in tokens:
            qs = qs.filter(search_text__icontains=t)
        in_title = Q()
        for t in tokens:
            in_title &= Q(title__icontains=t)
        return qs.annotate(search_rank=Case(When(in_title, then=Value(0)), default=Value(1), output_field=IntegerField()))


def get_backend() -> SearchBackend:
    return import_string(getattr(settings, "SEARCH_BACKEND", "apps.catalog.search.backend.SimpleSearchBackend"))()
