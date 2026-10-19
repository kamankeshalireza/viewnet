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

## Phase 4 — Inventory & Cart
- **Policy decisions (defaults, change if needed):** no backorders (sold-out = unavailable); max 10 per item in a cart (`CART_MAX_QTY_PER_ITEM`);
  reservation TTL = `STOCK_RESERVATION_TTL_MINUTES` (30). Digital products (Apple ID) are never stocked or reserved.
- **Stock model:** `InventoryItem(on_hand, reserved)` per variant + append-only `InventoryTransaction` ledger + `StockReservation(ref, variant)`.
  Reserve = conditional `UPDATE ... WHERE on_hand - reserved >= qty` (no oversell), all-or-nothing, idempotent per `(ref, variant)`.
  Phase 5 will call `reserve("order:<no>", lines)` at checkout, `consume()` on payment, `release()` on cancel; `expire_stock_reservations`
  (every 60 s via Celery Beat) releases overdue holds and publishes `ReservationsExpired`.
- **Stock changes only via services** (admin form has "تغییر موجودی ±" + mandatory reason); `on_hand`/`reserved` are read-only in admin.
- `ProductVariant.is_in_stock` is maintained by inventory so catalog never imports inventory (layer rule). New physical variants are
  *out of stock until stock is received*.
- **Cart:** guests = session, users = DB (`Cart`/`CartItem`, quantity only). The cart heals itself on every view. On login the
  guest cart is captured *before* `login()` and merged (sum, capped by stock/max) via the `UserLoggedIn` event.
- **Worker command:** `celery -A config worker -Q default,otp,images -l info` and `celery -A config beat -l info`.
- **Postgres-only test:** `test_concurrent_buyers_never_oversell_last_unit` is skipped on SQLite; run the suite on PostgreSQL in CI.
- Demo data: `seed_catalog --demo` then `seed_demo_stock`.
