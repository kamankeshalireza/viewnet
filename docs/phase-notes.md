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

## Review fixes & design pass (after reviewing the pushed repo)
- `config/__init__.py` must import the Celery app (an empty file silently falls back to Celery's AMQP default → OTP/image tasks fail). Regression tests added.
- Development runs Celery tasks inline (`CELERY_EAGER`, default on) so the OTP code prints to the console without a worker.
- **Why the site looked weak:** the template only styles `.product-card` inside `.category-product-list`; all product grids are now wrapped in it.
  The home page was redesigned (phone-model finder, perks, category tiles with icons, brand-colour buttons). Demo products no longer ship the
  template's fashion/furniture photos — add real product photos in the admin.
- Added `.gitattributes` (LF) to stop CRLF noise on Windows.

## Phase 5 — Checkout, addresses, coupons, orders
- **Free shipping for everyone** (one `ShippingMethod` "free", price 0, created by a data migration). `shipping.quote()` is the single place to add rates later.
- Digital-only carts (Apple ID) skip address/shipping/stock entirely. Mixed carts need an address.
- `place_order` is one atomic step: order + items (snapshot prices/titles/address) + stock reservation + coupon reservation. Same `checkout_token` → same order (double-click safe).
  Failure of any part (stock, coupon limit) rolls back everything and leaves the cart intact.
- Order lifecycle lives in `orders.services.orders` (state table in `orders.domain.state_machine`). `mark_paid()` (for Phase 6) consumes stock, redeems the coupon, bumps `sales_count`, is idempotent,
  and raises `ReservationLost` if the stock hold already expired (caller flags `needs_review`). Cancelling a *paid* order is intentionally unsupported until refunds exist (Phase 7).
- Unpaid orders expire after `ORDER_PAYMENT_TIMEOUT_MINUTES` (30): by the stock-expiry event and by the `expire_unpaid_orders` Beat task (both idempotent).
- Coupons: whole-order scope (percent/fixed, cap, min order, dates, total & per-user limits). Usage is *reserved* at checkout, *redeemed* on payment, *released* on cancel/expiry.
  Jalali date pickers in the admin are not done yet (⚠️ V13).
- Cities: `seed_locations` loads 31 provinces + 82 starter cities (capitals/big cities) — **not** the official full list; add the rest in the admin (⚠️ V20).
- The "Pay online" button is a placeholder until Phase 6 (payment gateway).
