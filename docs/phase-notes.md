# Phase notes (deviations from docs/architecture.md)

## Phase 3 — Catalog
- **Search (§6.8):** MVP uses `SimpleSearchBackend` (normalized `search_text` + token AND substring match), portable and tested on SQLite.
  PostgreSQL FTS + `pg_trgm` is the planned upgrade behind `settings.SEARCH_BACKEND` (no view changes).
- **Compatibility table dropped:** because stock is tracked per phone model, `DeviceModel` is a *variant axis* (`ProductVariant.device_model`);
  `ProductCompatibility` would duplicate it. Add it back only for universal accessories that must list compatible models.
- **Digital products:** `Product.product_type=digital` (e.g. Apple ID) → `requires_shipping=False`; Phase 4/5 must skip stock and shipping for them.
- **Stock:** `Product.in_stock` currently means "has an active variant"; Phase 4 replaces it with real inventory.
- **Images:** originals are kept as uploaded (may contain EXIF); only the re-encoded WebP renditions (EXIF stripped) are served.
- **Not yet done from the roadmap:** CSV import, JSON-LD/sitemap (Phase 10), reviews (Phase 9), add-to-cart (Phase 4).
