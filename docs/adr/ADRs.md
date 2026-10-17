# NiceShop — Architecture Decision Records (ADR)

> وضعیت همهٔ ADRها: **Proposed** (تا تأیید نهایی). قالب: Context → Decision → Alternatives → Consequences.
> موارد ⚠️`[Vxx]` به «Verification Register» در `NiceShop-Architecture.md` ارجاع می‌دهند.

---

## ADR-001 — Django Modular Monolith

**Context.** پروژه توسط تیم کوچک (احتمالاً یک نفر) ساخته می‌شود؛ عملیات حیاتی (ثبت سفارش + رزرو موجودی + کوپن، تأیید پرداخت + تغییر وضعیت سفارش) به **تراکنش اتمیک روی یک دیتابیس** نیاز دارد. زیرساخت ایران پیچیدگی عملیاتی اضافه می‌کند (شبکه، Registry، مانیتورینگ).

**Decision.** یک Django Monolith با ۱۳ اپ و مرزهای صریح: لایه‌بندی `Service/Selector/Domain`، وابستگی فقط به سمت پایین (اجرا با `import-linter`)، ارتباط بین اپ‌ها از طریق Service عمومی و Eventهای صریح. DRF برای API نسخه‌دار، بدون Microservice.

**Alternatives.**
- Microservices (Catalog/Order/Payment جدا): تراکنش توزیع‌شده/Saga، هزینهٔ DevOps، Latency شبکه؛ برای این مقیاس غیرموجه.
- Monolith بدون مرز (Django معمول): سریع‌ترین شروع ولی Coupling و «Fat views/models» در ۶ ماه.
- Django + SPA جدا (React/Vue): دو Deploy، SEO پیچیده‌تر، بازنویسی قالب.

**Consequences.** (+) ساده، تراکنشی، تست‌پذیر، یک Deploy. (+) قابل استخراج اپ‌ها در آینده چون وابستگی‌ها کنترل شده‌اند. (−) نیاز به انضباط معماری (Lint قرارداد وابستگی). (−) مقیاس‌پذیری افقی فقط روی لایهٔ Stateless (کافی). **معیار بازنگری:** یک دامنه (مثلاً Search یا Notification) با نیاز مقیاس/تیم کاملاً متفاوت.

---

## ADR-002 — PostgreSQL به‌عنوان Database اصلی

**Context.** Order/Payment/Inventory به Integrity قوی نیاز دارند: CHECK، Partial Unique، قفل ردیفی، تراکنش‌های ACID؛ Search فارسی MVP بدون سرویس جدا؛ ذخیرهٔ JSONB برای Payload/Spec.

**Decision.** PostgreSQL (نسخهٔ پایدار پشتیبانی‌شده ⚠️`[V1]`) تنها منبع حقیقت. استفاده از `CHECK`, `UNIQUE`, Partial Unique/Index، `select_for_update`، `timestamptz`، FTS (`simple`) + `pg_trgm`، `BigInteger` برای پول.

**Alternatives.** MySQL/MariaDB (Partial Index/CHECK/FTS ضعیف‌تر برای این طراحی)؛ SQLite (Production نامناسب)؛ MongoDB (تراکنش/قیود رابطه‌ای ضعیف برای پول).

**Consequences.** (+) Integrity در سطح DB (آخرین خط دفاع در برابر باگ اپ)، Search بدون زیرساخت اضافه. (−) نیاز به مدیریت Postgres (Backup/WAL/Replica) توسط ما یا میزبان؛ نیاز به Extension `pg_trgm` (دسترسی در میزبان) ⚠️`[V9]`. (−) تست‌ها باید روی Postgres واقعی اجرا شوند.

---

## ADR-003 — Redis (Cache، Session، Rate‑limit، Celery Broker)

**Context.** نیاز به Cache سریع (درخت دسته/Mega Menu)، Rate‑limiting اتمیک (OTP/Login/Coupon)، Broker برای Celery و Session. تفاوت حیاتی: Cache قابل‌حذف است، ولی Broker/Rate‑limit نباید «Evict» شوند.

**Decision.** MVP: **یک نمونه** Redis با `appendonly yes` و `maxmemory-policy volatile-lru` (همهٔ کلیدهای Cache با TTL؛ کلیدهای Broker بدون TTL ⇒ Evict نمی‌شوند). Production: **دو نمونه** (Cache: `allkeys-lru` بدون AOF؛ Queue/State: `noeviction` + AOF). Session = `cached_db` (Redis + Write‑through به DB) تا سبد مهمان با از‑دست‌رفتن Redis گم نشود. Redis هرگز به‌عنوان منبع حقیقت برای پول/موجودی استفاده نمی‌شود.

**Alternatives.** Memcached (فاقد Broker/Rate‑limit اتمیک)؛ RabbitMQ (قابل‌اتکاتر برای Queue ولی سرویس اضافه)؛ Cache در DB (کندتر)؛ Valkey (فورک سازگار ⚠️`[V1]`).

**Consequences.** (+) سادگی و عملکرد. (−) باید Taskها Idempotent باشند (`acks_late`، Redelivery)؛ تفاوت سیاست Evict را در Config مستند و تست کنیم. **معیار بازنگری:** حجم/اهمیت Queue که Redis AOF را ناکافی کند ⇒ RabbitMQ.

---

## ADR-004 — Django Templates (+ Bootstrap RTL + HTMX) به‌جای SPA

**Context.** قالب NiceShop آمادهٔ HTML/Bootstrap است؛ SEO فارسی اولویت دارد؛ تیم کوچک؛ تعامل‌های لازم محدود (سبد، فیلتر، OTP، Coupon).

**Decision.** Server‑side rendering با Django Templates، قالب به Layout/Include/Component شکسته می‌شود؛ Bootstrap 5.3 (build RTL)؛ HTMX برای Partial updateها؛ Vanilla JS حداقلی؛ بدون Build Chain Node در Production. لایهٔ DRF آماده‌ برای آینده (موبایل/PWA).

**Alternatives.** React/Next.js/Vue (SEO/Deploy/زمان بیشتر، بدون نیاز واقعی)؛ Alpine.js (قابل‌ترکیب با HTMX؛ فعلاً لازم نیست)؛ Django + Turbo (مشابه HTMX).

**Consequences.** (+) سرعت توسعه، SEO ذاتی، Deploy ساده، حفظ قالب. (−) تعاملات بسیار غنی (در آینده) سخت‌تر؛ **معیار بازنگری:** نیاز به اپ موبایل/Dashboard پیچیده ⇒ API موجود + کلاینت جدا. (−) تبدیل RTL و CSP نیازمند کار دستی (بخش 2 و 14).

---

## ADR-005 — Payment Gateway Abstraction

**Context.** درگاه‌های ایرانی (ZarinPal/IDPay/NextPay/…) API، واحد پول، قابلیت Refund/Inquiry و شکل Callback متفاوت دارند و ممکن است تغییر کنند یا Down شوند ⚠️`[V2][V3][V4]`. پرداخت حساس‌ترین بخش سیستم است.

**Decision.** Interface `PaymentGateway` (`create_payment`, `parse_callback`, `verify`, `inquire?`, `refund?`) + `GatewayCapabilities` + Registry (Strategy/Adapter/Factory). هستهٔ `payments` فقط ریال می‌شناسد؛ Adapter واحد را تبدیل می‌کند. سه موجودیت جدا: **Payment / PaymentAttempt / Transaction (Ledger)**؛ Idempotency با Unique/Partial Unique؛ Verify فقط سمت‌سرور با تطبیق مبلغ؛ Callback بدون وابستگی به Session؛ Reconcile دوره‌ای؛ `FakeGateway` برای Test.

**Alternatives.** اتصال مستقیم به یک درگاه در Service (Lock‑in)؛ Library شخص ثالث Multi‑gateway (وضعیت نگهداری/کنترل ⚠️`[V13]`)؛ Payment Model یکتا (فاقد Audit تلاش‌ها).

**Consequences.** (+) تعویض/افزودن درگاه = یک Adapter؛ تست‌پذیری؛ Audit کامل؛ مقاومت در برابر Callback تکراری/جعلی. (−) مدل‌ها و کد بیشتر از «ساده‌ترین» پیاده‌سازی؛ پذیرفته‌شده چون هزینهٔ باگ پرداخت بسیار بالاست. (−) Refund خودکار تنها برای درگاه‌های دارای قابلیت؛ بقیه Workflow دستی.

---

## ADR-006 — SMS/OTP Provider Abstraction

**Context.** OTP کانال اصلی ورود است؛ Providerها (Kavenegar/SMS.ir/FarazSMS/…) API، الزام قالب/خط و قیمت متفاوتی دارند ⚠️`[V5][V6]`. تهدید «SMS Pumping» هزینهٔ مستقیم دارد.

**Decision.** Interface `SMSProvider` (`send_otp`, `send_text`, `get_status?`) + Registry + Provider اصلی/Fallback با Failover؛ `Console` (Dev) و `Fake` (Test). OTP: ۶ رقم، ذخیره **HMAC** با Pepper، TTL کوتاه، حداکثر تلاش، Cooldown، سقف‌ها به‌ازای phone/IP/سراسری، پاسخ یکسان (ضد Enumeration)، ارسال از صف اختصاصی `otp` پس از Commit.

**Alternatives.** SDK Provider در Service؛ OTP بدون Hash (ریسک نشت)؛ ورود فقط با رمز (UX ضعیف‌تر در ایران)؛ Provider واحد بدون Fallback (SPOF).

**Consequences.** (+) تعویض Provider بدون تغییر Business Logic؛ کنترل هزینه و سوءاستفاده؛ تست‌پذیری. (−) لایهٔ Mapping قالب‌ها برای هر Provider؛ نیاز به Redis برای Rate‑limit (Fail‑closed برای OTP).

---

## ADR-007 — Inventory Architecture (Ledger + Reservation)

**Context.** خرید هم‌زمان آخرین کالا، رهاشدن پرداخت، لغو/مرجوعی، و نیاز به ردیابی علت تغییرات موجودی؛ باید Concurrency‑safe و قابل Audit باشد.

**Decision.** `InventoryItem(on_hand, reserved)` به ازای **Variant** (مستقل از Product) + دفتر Append‑only `InventoryTransaction` با نوع‌های `PURCHASE/SALE/RETURN/ADJUSTMENT/RESERVATION/RELEASE` و Unique روی (`type`,`reference`,`item`) برای Idempotency. رزرو در **ثبت سفارش** با TTL، با **Update شرطی اتمیک** (`WHERE on_hand-reserved >= q`) و ترتیب ثابت قفل‌ها؛ CHECK در DB؛ آزادسازی خودکار با Celery Beat؛ `SALE` هنگام پرداخت موفق؛ تطبیق شبانهٔ Ledger با مقدار فعلی.

**Alternatives.** فقط ستون `stock` در Product (Race، بدون Audit)؛ رزرو در سبد (قفل موجودی توسط سبدهای رها)؛ `select_for_update` همه‌جا (قفل بلندتر/Deadlock‑prone)؛ Event Sourcing کامل (Overengineering).

**Consequences.** (+) بدون Oversell، Audit کامل، Idempotent. (−) پیچیدگی بیشتر از ستون ساده؛ نیاز به Reconcile و تست هم‌زمانی؛ TTL باید با مهلت پرداخت هم‌خوان باشد.

---

## ADR-008 — جداسازی Order State و Payment State

**Context.** وضعیت پرداخت (INITIATED/PENDING/PAID/REFUNDED…) و چرخهٔ تکمیل سفارش (PROCESSING/PACKED/SHIPPED…) دو محور مستقل با سرعت و عوامل تغییر متفاوت‌اند؛ ادغام آن‌ها به Stateهای انفجاری و باگ‌های Race می‌انجامد.

**Decision.** دو State Machine مستقل. `Order.status` با جدول انتقال مجاز و `OrderStatusHistory`؛ `Payment.status` و `PaymentAttempt.status` جدا. تنها `PaymentService` اجازه دارد `OrderService.mark_paid()` را فراخواند؛ `Order.payment_status` Denormalized فقط‌خواندنی برای UI. Order `REFUNDED` فقط پس از «بازگشت کالا + عودت کامل»؛ لغو بعد از پرداخت = `CANCELLED` + Refund در محور Payment. کتابخانهٔ FSM لازم نیست (جدول ساده + قفل).

**Alternatives.** یک Status واحد (ابهام و Stateهای ترکیبی)؛ `django-fsm` (وضعیت نگهداری ⚠️`[V13]`، پنهان‌سازی منطق در Model)؛ Workflow Engine (Overengineering).

**Consequences.** (+) شفافیت، تست‌پذیری، کاهش Race. (−) دو وضعیت برای نمایش در UI باید به یک برچسب کاربرپسند نگاشت شود (Template Tag/Component).

---

## ADR-009 — Iranian Deployment Architecture

**Context.** استقرار روی VPS/اختصاصی/Cloud ایرانی؛ احتمال محدودیت دسترسی به Registryهای خارجی ⚠️`[V9]`؛ نیاز به عدم وابستگی به SaaS خارجی؛ تیم کوچک.

**Decision.** Docker Compose روی یک VPS برای MVP (Nginx → Gunicorn/Django → PostgreSQL/Redis + Celery Worker/Beat) و مسیر رشد به چند Node (Web×۲، DB+Replica، Worker، Monitoring) بدون تغییر کد (App Stateless). **Build خارج از سرور** و Push به Registry خصوصی؛ بدون `pip install` در Deploy. TLS در Nginx؛ Backup رمزنگاری‌شده Off‑site به ارائه‌دهندهٔ دوم؛ Monitoring خودمیزبان (Prometheus/Grafana، GlitchTip اختیاری). میزبان‑آگنوستیک.

**Alternatives.** Kubernetes (Overengineering)؛ PaaS خارجی (دسترسی/تحریم/تأخیر)؛ Bare‑metal بدون Docker (تکرارپذیری کمتر)؛ SaaS Observability (دسترسی نامطمئن).

**Consequences.** (+) تکرارپذیر، قابل‌انتقال بین میزبان‌ها، مستقل از اینترنت جهانی. (−) مسئولیت عملیات (Backup/Patch/Monitoring) با ماست؛ HA کامل در MVP نیست (RTO چندساعته)؛ نیاز به Registry/Mirror. **معیار بازنگری:** SLA بالاتر یا ترافیک ⇒ HA/Replica/LB.

---

## ADR-010 — Storage Architecture (Media)

**Context.** تصاویر محصول نباید به‌صورت غیرقابل‌مدیریت داخل Container بمانند؛ باید قابل Backup، قابل‌اشتراک بین گره‌های Web و قابل‌تعویض بین Local/MinIO/Object Storage ایرانی/CDN باشند ⚠️`[V8]`.

**Decision.** Django `STORAGES["default"]` + `django-storages` (S3‑compatible) پشت `STORAGE_BACKEND`: **MVP = Volume مستقل/دیسک جدا با سرو مستقیم Nginx** (بدون نگهداری در Layer کانتینر)؛ **رشد = MinIO خودمیزبان یا Object Storage ایرانی S3‑compat** + **CDN داخلی** در جلو. مسیر URL تصاویر با `MEDIA_BASE_URL` تنظیم می‌شود. پردازش تصویر (اعتبارسنجی، حذف EXIF، Re‑encode WebP، Renditionهای ثابت) در Celery؛ Originalها در Backup اولویت دارند.

**Alternatives.** Local ثابت روی VPS (ساده ولی SPOF و غیرقابل‌اشتراک)؛ MinIO از روز اول (سرویس اضافه)؛ Object Storage ایرانی از روز اول (وابستگی/هزینه/ناشناخته ⚠️`[V8]`)؛ ذخیرهٔ تصاویر در DB (نامناسب).

**Consequences.** (+) مهاجرت Storage با تغییر Config؛ مدیریت/Backup روشن؛ آمادگی چند‌گره. (−) در MVP با Local، Web چندگانه نیاز به Storage مشترک دارد (در همان زمان به MinIO/S3 می‌رویم)؛ مدیریت آدرس CDN و Cache‑busting.
