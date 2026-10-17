# NiceShop — سند طراحی معماری (Architecture Design Document)

> **پروژه:** فروشگاه اینترنتی فارسی لوازم جانبی موبایل (Django + قالب NiceShop)
> **وضعیت:** پیش‌نویس v0.1 — مرحلهٔ طراحی، قبل از کدنویسی
> **تاریخ:** 2026-10-10
> **ADRها:** در فایل جداگانهٔ `NiceShop-ADRs.md`

## راهنمای علامت‌ها

| علامت | معنا |
|---|---|
| ✅ | تصمیم پیشنهادی (Recommended) |
| ⚠️ `[Vxx]` | مورد وابسته به اطلاعات بیرونی (API سرویس‌دهنده، قیمت، قانون، نسخهٔ کتابخانه) که **نباید به‌عنوان فرض قطعی** پذیرفته شود و باید هنگام پیاده‌سازی بررسی شود. فهرست کامل در «پیوست ج — Verification Register» |
| 🔹 | جایگزین بررسی‌شده که انتخاب نشد |

## فهرست

1. Executive Summary
2. بررسی قالب NiceShop
3. Architecture Diagram
4. Django Apps
5. Database ERD
6. Models
7. Service Layer
8. Payment Architecture
9. OTP Architecture
10. Cart Architecture
11. Inventory Architecture (+ ماتریس Concurrency)
12. Shipping Architecture
13. SEO
14. Security
15. Infrastructure (ایران)
16. Docker Architecture
17. Environment Variables
18. Backup & Disaster Recovery
19. Logging & Monitoring
20. Testing Strategy
21. Project Directory
22. Development Roadmap
23. Recommended Final Architecture
- پیوست الف — Checklist راه‌اندازی در ایران
- پیوست ب — ADRها (فایل جدا)
- پیوست ج — Verification Register

---

# بخش 1 — Executive Summary

**معماری پیشنهادی:** یک **Modular Monolith** با Django (۱۳ اپ با قوانین وابستگی یک‌طرفه)، با رندر سمت سرور (Django Templates + Bootstrap RTL + HTMX/Vanilla JS) و یک لایهٔ DRF نسخه‌دار برای آینده (اپ موبایل / PWA). دیتابیس اصلی PostgreSQL، Redis برای Cache/Session/Rate-limit/Broker، Celery برای کارهای پس‌زمینه، و Nginx + Gunicorn در Docker Compose روی VPS/سرور ایرانی.

**پنج تصمیم کلیدی که بقیهٔ طراحی روی آن‌ها بنا شده:**

1. **پول = Integer ریال.** تمام مبالغ `BigIntegerField` به ریال؛ تومان فقط در لایهٔ Presentation (و ورودی فرم‌های Admin) و در صورت نیاز در Adapter درگاه. هیچ `float`/`Decimal` در مسیر پول وجود ندارد.
2. **Payment ≠ Order.** دو State Machine مستقل. Order فقط از طریق `PaymentService` و رویداد «پرداخت موفق» به `PAID` می‌رود. هر پول‌حرکتی در یک جدول **Transaction** (append-only) ثبت می‌شود.
3. **Adapter Layer برای هر سرویس ایرانی** (`integrations/payments|sms|shipping`). Business Logic هرگز مستقیماً با API ZarinPal/Kavenegar/Tipax صحبت نمی‌کند؛ هر Adapter «Capability Flag» دارد (مثلاً `supports_refund`)، چون همهٔ درگاه‌ها قابلیت‌های یکسان ندارند ⚠️`[V2][V3][V5]`.
4. **Inventory مبتنی بر دفتر کل (Ledger) + Reservation** با قفل ردیفی/به‌روزرسانی شرطی در PostgreSQL؛ رزرو در لحظهٔ ثبت سفارش و آزادسازی خودکار با Celery Beat.
5. **همه چیز Idempotent:** ثبت سفارش (checkout token)، ساخت پرداخت (partial unique index)، Callback درگاه (قفل روی Attempt + وضعیت پایانی)، Merge سبد، رزرو/آزادسازی موجودی (Unique روی ledger).

**یافتهٔ مهم دربارهٔ قالب:** قالب ۲۱ صفحهٔ HTML دارد، Header و Footer در همهٔ صفحات یکسان‌اند (کاندید `base.html`)، Bootstrap 5.3.7 با فایل RTL آماده همراه است، ولی `main.css` (~309KB) با ~۲۰۰ تعریف جهت‌دار (`left/right/margin-left/...`) برای RTL نیاز به تبدیل دارد، و صفحهٔ Checkout شامل فیلدهای کارت بانکی/PayPal/Apple Pay است که **باید کاملاً حذف شود** (در ایران پرداخت از طریق ریدایرکت به درگاه انجام می‌شود، نه دریافت اطلاعات کارت در سایت).

**چیزهایی که عمداً در MVP نیست (Overengineering Guard):** Microservices، Elasticsearch، Kubernetes، Repository Pattern عمومی، CQRS/Event Sourcing، React/Vue، Wallet/کیف پول (در پیوست الف دلیل آمده).

---

# بخش 2 — بررسی قالب NiceShop

## 2.1 آنچه در `NiceShop.zip` پیدا شد

| مورد | یافته |
|---|---|
| تعداد صفحه | **۲۱** فایل HTML (۲۰ صفحهٔ فهرست شده + `starter-page.html` که اسکلت خالی است) |
| فریم‌ورک CSS | Bootstrap **5.3.7** + `bootstrap.rtl.min.css` موجود در vendor ✅ |
| آیکن | Bootstrap Icons |
| کتابخانه‌های JS | Swiper، AOS، GLightbox، Drift-Zoom، PureCounter، `php-email-form/validate.js` |
| CSS سفارشی | `assets/css/main.css` ≈ 309KB؛ متغیرهای رنگ/فونت در `:root` (`--default-font`, `--heading-font`, `--nav-font`, `--accent-color`, …) → تغییر برند و فونت از یک نقطه ممکن است |
| JS سفارشی | `assets/js/main.js` ≈ ۸۱۰ خط؛ **هیچ اسکریپت Inline اجرایی در HTML نیست** (فقط بلوک‌های `type="application/json"` برای Swiper) → برای CSP مناسب است |
| Header | یکسان در هر ۲۱ صفحه (بعد از حذف کلاس `active`)؛ حدود **۳۶KB** HTML به‌خاطر Mega Menu |
| Footer | یکسان در هر ۲۱ صفحه (~۵.۷KB) |
| وابستگی بیرونی | Google Fonts (Roboto/Montserrat/Poppins) در تک‌تک صفحات؛ iframe نقشهٔ Google در `contact.html`؛ ~۸۶ لینک به `bootstrapmade.com` (دمو/Credit) |
| Breadcrumb | در همهٔ صفحات به‌جز `index` و `search-results` |
| فرم‌ها | جستجو/خبرنامه در همهٔ صفحات؛ `contact.php` (وابسته به کتابخانهٔ پولی PHP Email Form) |

## 2.2 مشکلات و ریسک‌های قالب برای بازار ایران

| # | مشکل | راهکار |
|---|---|---|
| 1 | `lang="en"` و LTR | `lang="fa" dir="rtl"` در `base.html` |
| 2 | Google Fonts (احتمال کندی/قطعی در ایران، و نقض اصل «بدون وابستگی خارجی») | Self-host فونت فارسی (پیشنهاد Vazirmatn، نسخهٔ Variable woff2) ⚠️`[V14]`؛ فقط با override کردن سه متغیر فونت در `:root` |
| 3 | `main.css`: ~79× `left:`، ~46× `right:`، ~21× `margin-left`، ~32× `margin-right`، ~11× `padding-left`، ~6× `padding-right`، چند `text-align` | یک‌بار تبدیل با ابزار RTL (مثلاً `rtlcss` به‌صورت One-time، نه در Production) → خروجی را Commit و دستی بازبینی می‌کنیم؛ بعد از آن دیگر Node در مسیر Build لازم نیست |
| 4 | آیکن‌های جهت‌دار (`bi-arrow-left` برای «قبلی»، `bi-chevron-right` در Breadcrumb/Dropdown) | معکوس‌سازی در Template؛ برای Paginationِ سفارشی قالب (`<ul>` سفارشی، نه `.pagination` بوتستراپ) باید «قبلی» → فلش راست باشد |
| 5 | Swiper، اسلایدر قیمت (Price Range)، Countdown، Drift-Zoom | Swiper با `dir="rtl"`؛ اسلایدر قیمت دو‌دسته‌ای (min/max range) باید برای RTL تست و احتمالاً اصلاح شود؛ Drift-Zoom پنجرهٔ Zoom (`paneContainer`) را در RTL تست کنید |
| 6 | Checkout: فیلدهای `card-number/expiry/cvv/card-name` + PayPal + Apple Pay | **حذف کامل.** جایگزین: انتخاب درگاه (در صورت چند درگاه) → ریدایرکت. هرگز اطلاعات کارت روی سرور ما نیاید |
| 7 | Checkout: `state/zip/country/apartment` | `Province/City` (Select وابسته)، `Postal Code` ده‌رقمی، `Plaque`، `Unit`، نام و موبایل گیرنده؛ فیلد Country حذف |
| 8 | Checkout: `email` اجباری | موبایل اصلی‌ترین شناسه است؛ ایمیل اختیاری |
| 9 | Account: تب‌های `orders / wishlist / wallet / reviews / addresses / settings` که با JS سمت کلاینت جابه‌جا می‌شوند | تبدیل به **URLهای جدا** (هر تب یک View/Query/Pagination سمت سرور) |
| 10 | `login.html` و `register.html` جدا | ادغام به یک جریان **Phone-first**: شماره → OTP → (کاربر جدید) تکمیل پروفایل. صفحهٔ Register به همان Flow Redirect می‌شود (جلوگیری از User Enumeration — بخش 9) |
| 11 | منطق دمو در `main.js`: کد تخفیف ثابت `DISCOUNT20`، محاسبهٔ مجموع سبد و تعداد در کلاینت | حذف. **سرور تنها منبع حقیقت** برای قیمت/تخفیف/موجودی؛ کلاینت فقط درخواست می‌فرستد (HTMX) |
| 12 | رنگ‌ها با `style="background:..."` Inline (مثلاً Color Chip) | برای CSP سخت‌گیرانه: `data-hex` + تنظیم از طریق CSSOM یا کلاس‌های تولیدشده؛ یا `style-src 'unsafe-inline'` فقط برای style (نه script) ⚠️`[V24]` |
| 13 | محتوای دمو (تصاویر مد/لباس، متن Lorem، Women/Men/Kids در Mega Menu) | جایگزینی با دادهٔ واقعی؛ Mega Menu باید از درخت دسته‌بندی ساخته شود |
| 14 | Credit/لایسنس BootstrapMade | نسخهٔ رایگان معمولاً نیازمند حفظ لینک Credit است ⚠️`[V18]` |
| 15 | نام‌گذاری غلط‌املایی: `shiping-info`, `paymnt-methods`, `retun-policy` | در Django نام‌های درست و استاندارد: `shipping`, `payment-methods`, `return-policy` |
| 16 | هدر ۳۶KB تکراری در هر صفحه | Mega Menu را از Fragment Cache (Redis) رندر کنیم؛ کاهش HTML هر صفحه |

## 2.3 استراتژی تبدیل به Django Templates

**قاعده:** کپی مستقیم HTML → شکستن به Layout/Include/Component → حذف Duplication → اتصال داده. ✅ بدون React/Vue؛ تعامل‌های پویا با **HTMX** (Vendor شده، بدون CDN) و Vanilla JS.

یک اسکریپت یک‌بارمصرف (`tools/convert_template.py`، **خارج از اپلیکیشن Production**) کارهای مکانیکی را انجام می‌دهد: استخراج Header/Footer، بازنویسی مسیر `assets/...` به `{% static %}`، حذف Google Fonts، جایگزینی `bootstrap.min.css` با `bootstrap.rtl.min.css`، تعویض `lang/dir`. پس از آن، بازبینی دستی صفحه‌به‌صفحه.

### ساختار Template پیشنهادی

```text
templates/                         # فقط چیزهای مشترک (Global)
├── base.html                      # <html lang="fa" dir="rtl">, blocks: title, meta, content, extra_css, extra_js
├── layouts/
│   ├── page_simple.html           # از starter-page.html: Breadcrumb header + container (CMS/Static)
│   ├── account.html               # Sidebar تب‌های حساب + {% block account_content %}
│   ├── auth.html                  # Login/OTP (بدون Mega Menu)
│   └── checkout.html              # هدر مینیمال (کاهش Abandonment)
├── includes/
│   ├── header.html  (top_bar, main_header, navbar, mobile_nav)   # Mega Menu ← {% cache %}
│   ├── footer.html
│   ├── breadcrumb.html            # + BreadcrumbList JSON-LD هم‌زمان
│   ├── pagination.html            # URL-based, حفظ Query String
│   ├── messages.html              # django.messages → Toast/Alert
│   ├── seo_meta.html              # title/description/canonical/OG/robots
│   └── jsonld/{product,organization,website,breadcrumb}.html
├── components/
│   ├── product_card.html          # پارامتر variant="compact|listing"
│   ├── category_card.html
│   ├── price.html                 # تومان + قیمت خط‌خورده + Badge درصد تخفیف
│   ├── rating_stars.html
│   ├── quantity_input.html        # HTMX
│   ├── color_chip.html
│   ├── filter_sidebar.html  sort_bar.html  active_filters.html
│   ├── banner_slider.html   countdown.html  empty_state.html  modal.html
│   ├── cart_mini.html  cart_item_row.html  order_summary.html
│   ├── address_card.html  address_form.html
│   ├── order_status_badge.html    # Status → برچسب فارسی + رنگ
│   └── payment_method_list.html
└── errors/{403,404,429,500}.html

apps/<app>/templates/<app>/        # Template صفحات هر اپ کنار خود اپ (Cohesion)
```

> 🔹 جایگزین: همهٔ Templateها در `templates/` مرکزی. رد شد چون در Modular Monolith می‌خواهیم هر اپ مستقل و قابل فهم باشد؛ فقط Base/Layout/Component در Global می‌ماند.

### دو شکل کارت محصول در قالب
- **Compact** (تصویر + عنوان + قیمت + «مشاهده») — داخل تب‌های Mega Menu.
- **Listing** (`.product-overlay` با اکشن‌ها، دسته، عنوان، قیمت، امتیاز) — در `category` و `search-results`.

هر دو در یک Component با پارامتر `variant`؛ ورودی Component یک **DTO/Dict ساده** (نه Queryset خام) است تا Query اضافه از داخل Template اجرا نشود.

## 2.4 نگاشت صفحه‌به‌صفحه (۲۱ صفحه)

| صفحهٔ قالب | Template در Django | URL | اپ / View | منبع داده | نکات |
|---|---|---|---|---|---|
| `index.html` | `catalog/home.html` | `/` | `catalog.HomeView` | Banner، Bestseller، Featured، New، Discount (Countdown) | Sectionهای `hero / promo-cards / best-sellers / cards / call-to-action` → Block/Include؛ Fragment Cache ۲–۵ دقیقه |
| `category.html` | `catalog/category.html` | `/category/<path>/` | `catalog.CategoryView` | Product (فیلتر+مرتب‌سازی)، Brand، Attribute | Sidebar فیلتر: قیمت/رنگ/برند/(مدل گوشی) ← HTMX برای Swap لیست؛ Active-filter tags؛ Pagination |
| `search-results.html` | `catalog/search.html` | `/search/?q=` | `catalog.SearchView` | Search (بخش 6.8) | هم‌خانوادهٔ category (Partial مشترک)؛ `noindex` |
| `product-details.html` | `catalog/product_detail.html` | `/product/<id>/<slug>/` | `catalog.ProductDetailView` | Product, Variant, Images, Specs, Reviews | Gallery (GLightbox+Drift)؛ Color Chip → Variant؛ **افزودن انتخاب «مدل گوشی»**؛ تب‌ها: توضیحات/مشخصات/نظرات؛ JSON-LD Product |
| `cart.html` | `cart/cart.html` | `/cart/` | `cart.CartView` | CartService | HTMX برای تغییر تعداد/حذف؛ پیام تغییر قیمت/موجودی |
| `checkout.html` | `checkout/checkout.html` | `/checkout/` | `orders.CheckoutView` | Address، ShippingMethod، Coupon | قالب دو حالت (Multi-step / One-page) دارد؛ **پیشنهاد: One-page** (ساده‌تر برای MVP/موبایل)؛ کارت/PayPal/Apple Pay حذف |
| `order-confirmation.html` | `checkout/result.html` (Success/Failed/Pending) | `/checkout/result/<order_no>/` | `payments.PaymentResultView` | Order+Payment | هم موفق هم ناموفق؛ فقط پس از Redirect داخلی نمایش (نه مستقیم از Callback) |
| `account.html` | `accounts/dashboard/*.html` روی `layouts/account.html` | `/account/orders/` , `/account/orders/<no>/`, `/account/wishlist/`, `/account/addresses/`, `/account/reviews/`, `/account/profile/` | `accounts.*` | — | تب `wallet` در MVP **حذف** (پیوست الف) |
| `login.html` | `accounts/login.html` | `/account/login/` | `accounts.PhoneLoginView` | OTPService | مراحل: شماره → کد → (پروفایل) ؛ تب «ورود با رمز» اختیاری |
| `register.html` | — | `/account/register/` → 302 به login | — | — | ادغام (ضد Enumeration) |
| `payment-methods.html` | `cms/page.html` + بلوک پویا | `/payment-methods/` | `cms.PageView` | CMS + `PaymentGatewayConfig` | متن ثابت + لیست درگاه‌های فعال |
| `shiping-info.html` | `cms/page.html` + بلوک پویا | `/shipping/` | `cms.PageView` | CMS + `ShippingMethod` | هزینه/زمان از دیتابیس |
| `return-policy.html` | `cms/page.html` | `/return-policy/` | `cms.PageView` | CMS | |
| `privacy.html` | `cms/page.html` | `/privacy/` | `cms.PageView` | CMS | ⚠️`[V12]` |
| `tos.html` | `cms/page.html` | `/terms/` | `cms.PageView` | CMS | ⚠️`[V12]` |
| `about.html` | `cms/about.html` | `/about/` | `cms.PageView` | CMS + آمار | `stats` (PureCounter) و `testimonials` را یا از CMS بگیرید یا حذف کنید (دادهٔ جعلی نگذارید) |
| `faq.html` | `cms/faq.html` | `/faq/` | `cms.FAQView` | `FAQCategory/FAQItem` | |
| `contact.html` | `cms/contact.html` | `/contact/` | `cms.ContactView` | `ContactMessage` | جایگزین `contact.php`؛ Rate-limit + Honeypot؛ نقشهٔ Google حذف/جایگزین ⚠️`[V16]` |
| `support.html` | `cms/support.html` | `/support/` | `cms.PageView` | CMS | MVP: صفحهٔ ثابت + فرم تماس. سیستم تیکت = Phase بعدی |
| `404.html` | `errors/404.html` | handler404 | — | — | + `403/429/500` |
| `starter-page.html` | `layouts/page_simple.html` | — | — | — | الگوی Layout؛ به‌عنوان صفحه حذف می‌شود |

## 2.5 تصمیم دربارهٔ Vendorها

| کتابخانه | تصمیم | دلیل |
|---|---|---|
| Bootstrap 5.3.7 (RTL build) | ✅ نگه‌داشتن | پایه‌ٔ قالب؛ فایل RTL موجود است |
| Bootstrap Icons | ✅ | فقط فونت‌های لازم؛ آیکن‌های جهت‌دار اصلاح شود |
| Swiper | ✅ | با `dir="rtl"`؛ فقط در صفحات نیازمند (`extra_js`) |
| GLightbox + Drift-Zoom | ✅ فقط صفحهٔ محصول | |
| AOS | 🔹 پیشنهاد حذف یا غیرفعال در موبایل | تزئینی؛ هزینهٔ Performance؛ احترام به `prefers-reduced-motion` |
| PureCounter | ✅ فقط صفحهٔ About (اگر آمار واقعی داریم) | |
| php-email-form `validate.js` + `contact.php` | ❌ حذف | PHP نداریم؛ Django Form + HTMX |
| `main.js` | ✂️ شکستن به ماژول‌ها | `ui.js` (nav/scroll/swiper-init)، `price-range.js`، `product-gallery.js`؛ منطق Cart/Checkout/Promo دمو **حذف** و با HTMX سمت سرور جایگزین می‌شود |
| HTMX | ➕ اضافه (Vendor محلی) | سبد، فیلتر، OTP-step، Coupon، Wishlist؛ پیکربندی سازگار با CSP ⚠️`[V24]` |

---

# بخش 3 — Architecture Diagram

## 3.1 نمای کلی Runtime

```text
                         Internet (کاربران ایران)
                                  │
                       ┌──────────▼──────────┐
                       │  DNS (.ir / intl)   │
                       └──────────┬──────────┘
                                  │ 443 (TLS 1.2/1.3)
                          ┌───────▼────────┐
                          │     Nginx      │  TLS termination, HSTS, gzip/brotli,
                          │ (reverse proxy)│  limit_req (coarse), static+media cache,
                          └───┬────────┬───┘  security headers
                 /static,/media│        │ /  (proxy_pass, unix socket / network)
                  (read-only)  │        ▼
                  ┌────────────▼┐  ┌──────────────────────────────────────────┐
                  │ Static vol. │  │        Gunicorn  (gthread workers)       │
                  │ Media store │  │  ┌────────────────────────────────────┐  │
                  │ (Local/MinIO│  │  │            Django (WSGI)           │  │
                  │ /S3-compat) │  │  │                                    │  │
                  └─────────────┘  │  │  Presentation:                     │  │
                                   │  │   • Django Templates (+HTMX)       │  │
                                   │  │   • DRF  /api/v1/  (versioned)     │  │
                                   │  │   • Django Admin (staff only)      │  │
                                   │  │  ───────────────────────────────── │  │
                                   │  │  Application: Services + Selectors │  │
                                   │  │  Domain: pure pricing/state rules  │  │
                                   │  │  ───────────────────────────────── │  │
                                   │  │  Infrastructure: ORM, integrations │  │
                                   │  └────────────────────────────────────┘  │
                                   └───────┬──────────────┬──────────┬────────┘
                                           │              │          │
                              ┌────────────▼───┐   ┌──────▼─────┐   │ HTTPS (outbound, timeouts)
                              │  PostgreSQL    │   │   Redis    │   │
                              │ (source of     │   │ cache      │   ▼
                              │  truth: orders,│   │ session    │ ┌─────────────────────────────┐
                              │  payments,     │   │ rate-limit │ │ Iranian external services   │
                              │  inventory)    │   │ celery brk │ │  PSP  : ZarinPal / IDPay …  │
                              └───────▲────────┘   └──────┬─────┘ │  SMS  : Kavenegar/SMS.ir …  │
                                      │                   │       │  Ship : Post / Tipax / Peyk │
                                      │            ┌──────▼─────┐ └──────────────▲──────────────┘
                                      │            │   Celery   │                │
                                      └────────────┤ worker(s)  ├────────────────┘
                                                   │ + Beat     │  (SMS, email, image renditions,
                                                   └────────────┘   payment reconcile, stock release,
                                                                     OTP cleanup, reports)
        Backups: pgBackRest/pg_dump ─► local ─► off-site (second DC/provider)   Media ─► restic/rclone
        Observability: Prometheus + Grafana + Loki(optional) + GlitchTip/Sentry(optional)
```

## 3.2 لایه‌بندی داخل Django

```text
 HTTP (Template View / DRF View / Admin action / Celery task / Mgmt command)
                   │   ← فقط parse، auth، validation فرم، فراخوانی سرویس، رندر
                   ▼
 ┌─────────────────────────────  services.py  (Write / Use-cases)  ─────────────────────────┐
 │ transaction.atomic، قفل‌ها، Idempotency، انتشار Event (on_commit)                          │
 └─────────┬───────────────────────────────┬────────────────────────────┬───────────────────┘
           ▼                               ▼                            ▼
   selectors.py (Read-only queries)   domain/ (pure Python:        integrations/ (Adapters)
   select_related/prefetch/annotate   pricing, state-machine,      payments · sms · shipping · storage
                                      money, validators)           ← فقط از طریق Interface
           ▼
        Models (ORM) + DB Constraints (CHECK / UNIQUE / partial indexes)
```

**قاعده‌ها:** View و Template فاقد Business Logic‌اند؛ Model فقط داده + Constraint + متدهای ساده (بدون Side-effect)؛ `save()` سفارشی برای منطق کسب‌وکار ممنوع؛ Signalهای ORM برای منطق مهم ممنوع (Event صریح به‌جای آن).

## 3.3 وابستگی بین اپ‌ها (فقط به سمت پایین)

```text
                    notifications        cms
                         ▲  (subscribe to events)   (مستقل)
                         │
   reviews ─────────────►│
      │                  │
   payments ───► orders ─┴─► shipping ─► locations
                   │  ▲
                   │  └──────────────┐
                   ▼                 │
                  cart ──► discounts ──► catalog ◄── inventory
                   │                      │
                   └──────────► accounts ◄┘
                                   │
                                  core   (BaseModel, Money, events, rate-limit, utils)
```

- `payments → orders` (نه برعکس): `PaymentService` از `OrderService.mark_paid()` استفاده می‌کند.
- `orders` Orchestrator چک‌اوت است (`CheckoutService`): از cart/inventory/discounts/shipping استفاده می‌کند.
- `notifications` فقط Event می‌گیرد؛ هیچ اپی `notifications` را import نمی‌کند (جهت: Event ← Handler).
- اجرا با **`import-linter`** در CI (قرارداد لایه‌ای) ⚠️`[V13]`.

---

# بخش 4 — Django Apps

## 4.1 فهرست اپ‌ها

| اپ | مسئولیت | مدل‌های اصلی | وابستگی |
|---|---|---|---|
| `core` | BaseModel، Money، Rate-limiter، Event dispatcher، فیلترهای Jalali/تومان، Middleware (RequestID)، نرمال‌سازی فارسی، `ProviderCallLog`، `SiteSetting` | `SiteSetting`, `ProviderCallLog` | — |
| `locations` | استان/شهر (دادهٔ مرجع) | `Province`, `City` | core |
| `accounts` | کاربر (موبایل‌محور)، OTP، نشانی‌ها، علاقه‌مندی‌ها، پروفایل | `User`, `OTPChallenge`, `Address`, `WishlistItem` | core, locations |
| `catalog` | محصول، دسته‌بندی (درخت)، برند، Variant/SKU، تصاویر، ویژگی‌ها، سازگاری با مدل گوشی، **Search** | `Product`, `ProductVariant`, `Category`, `Brand`, `ProductImage`, `AttributeDefinition`, `AttributeOption`, `ProductAttributeValue`, `ProductSpecification`, `DeviceModel`, `ProductCompatibility` | core |
| `inventory` | موجودی، دفتر تراکنش، رزرو | `InventoryItem`, `InventoryTransaction`, `StockReservation` | catalog |
| `discounts` | کوپن، قیمت‌گذاری ویژه/حراج، محدودیت‌های مصرف | `Coupon`, `CouponRedemption`, `PriceRule` | catalog |
| `cart` | سبد مهمان (Session) و کاربر (DB)، Merge | `Cart`, `CartItem` | catalog, inventory(خواندن), discounts(خواندن) |
| `shipping` | روش/نرخ ارسال، محاسبهٔ هزینه، Shipment، Providerها | `ShippingMethod`, `ShippingRate`, `Shipment`, `ShipmentItem`, `ShipmentEvent` | locations, catalog(وزن) |
| `orders` | چک‌اوت، سفارش، Statusها، مرجوعی | `Order`, `OrderItem`, `OrderStatusHistory`, `ReturnRequest` | cart, inventory, discounts, shipping, accounts |
| `payments` | Payment/Attempt/Transaction/Refund، Callback، Reconcile | `Payment`, `PaymentAttempt`, `Transaction`, `Refund`, `PaymentGatewayConfig` | orders |
| `reviews` | نظرات و امتیاز (با Moderation) | `ProductReview` | catalog, orders (خرید تأییدشده) |
| `notifications` | SMS/Email/In-app، قالب پیام، Log ارسال | `Notification`, `NotificationTemplate`, `NotificationLog` | core (Event) |
| `cms` | صفحات ثابت، FAQ، Banner، پیام تماس | `Page`, `FAQCategory`, `FAQItem`, `Banner`, `ContactMessage` | core |

## 4.2 تفاوت با ساختار پیشنهادی شما و دلیل

| تغییر | دلیل |
|---|---|
| `categories` ادغام در `catalog` | Category فقط برای Catalog معنا دارد؛ جدا کردن آن Circular dependency و Overhead ایجاد می‌کند |
| افزودن `locations` | استان/شهر دادهٔ مرجع مشترک بین Address و Shipping است؛ وابستگی چرخه‌ای را حذف می‌کند |
| `Address` در `accounts` | مالک آن کاربر است؛ Snapshot آن در Order کپی می‌شود (تغییر بعدی آدرس نباید سفارش قدیمی را عوض کند) |
| `reviews` جدا از `catalog` | وابسته به `orders` (خرید تأییدشده) است؛ اگر داخل `catalog` باشد جهت وابستگی معکوس می‌شود |
| `integrations/` به‌صورت پکیج سطح بالا (نه Django app) | Adapterها مدل ندارند؛ لاگ آن‌ها در `core.ProviderCallLog` است |
| پوشهٔ `search` وجود ندارد | Search در `catalog/search/` است (ماژول، نه اپ) تا اپ اضافه نسازیم |
| `wallet` ندارد | پیوست الف |
| Templateهای صفحات داخل هر اپ | Cohesion؛ فقط Layout/Component مشترک در `templates/` |

---

# بخش 5 — Database ERD

> Mermaid (در GitHub/GitLab/VSCode رندر می‌شود). کلیدها: PK=BigInt؛ `public_id`=UUID برای شناسهٔ بیرونی.

```mermaid
erDiagram
    PROVINCE ||--o{ CITY : has
    USER ||--o{ ADDRESS : owns
    USER ||--o{ OTP_CHALLENGE : requests
    USER ||--o{ WISHLIST_ITEM : saves
    CITY ||--o{ ADDRESS : located_in

    BRAND ||--o{ PRODUCT : makes
    CATEGORY ||--o{ CATEGORY : parent_of
    CATEGORY ||--o{ PRODUCT : classifies
    PRODUCT ||--|{ PRODUCT_VARIANT : has
    PRODUCT ||--o{ PRODUCT_IMAGE : has
    PRODUCT ||--o{ PRODUCT_SPECIFICATION : describes
    PRODUCT ||--o{ PRODUCT_ATTRIBUTE_VALUE : filterable_by
    ATTRIBUTE_DEFINITION ||--o{ ATTRIBUTE_OPTION : offers
    ATTRIBUTE_OPTION ||--o{ PRODUCT_ATTRIBUTE_VALUE : used_in
    PRODUCT_VARIANT }o--o{ ATTRIBUTE_OPTION : variant_axes
    DEVICE_MODEL ||--o{ PRODUCT_COMPATIBILITY : supported
    PRODUCT ||--o{ PRODUCT_COMPATIBILITY : fits
    BRAND ||--o{ DEVICE_MODEL : phone_brand
    PRODUCT ||--o{ WISHLIST_ITEM : saved_in

    PRODUCT_VARIANT ||--|| INVENTORY_ITEM : stock_of
    INVENTORY_ITEM ||--o{ INVENTORY_TRANSACTION : ledger
    PRODUCT_VARIANT ||--o{ STOCK_RESERVATION : reserved
    ORDER ||--o{ STOCK_RESERVATION : holds

    USER ||--o| CART : has
    CART ||--o{ CART_ITEM : contains
    PRODUCT_VARIANT ||--o{ CART_ITEM : refers

    COUPON ||--o{ COUPON_REDEMPTION : used
    ORDER ||--o| COUPON_REDEMPTION : applies
    PRICE_RULE }o--o{ PRODUCT : targets
    PRICE_RULE }o--o{ CATEGORY : targets

    USER ||--o{ ORDER : places
    ORDER ||--|{ ORDER_ITEM : has
    PRODUCT_VARIANT ||--o{ ORDER_ITEM : snapshot_of
    ORDER ||--o{ ORDER_STATUS_HISTORY : audit
    ORDER ||--o{ RETURN_REQUEST : may_have
    SHIPPING_METHOD ||--o{ ORDER : chosen
    SHIPPING_METHOD ||--o{ SHIPPING_RATE : priced_by

    ORDER ||--o{ PAYMENT : paid_by
    PAYMENT ||--o{ PAYMENT_ATTEMPT : tries
    PAYMENT ||--o{ TRANSACTION : ledger
    PAYMENT_ATTEMPT ||--o{ TRANSACTION : produces
    PAYMENT ||--o{ REFUND : refunded_by
    RETURN_REQUEST ||--o{ REFUND : triggers

    ORDER ||--o{ SHIPMENT : fulfilled_by
    SHIPMENT ||--o{ SHIPMENT_ITEM : packs
    ORDER_ITEM ||--o{ SHIPMENT_ITEM : shipped_as
    SHIPMENT ||--o{ SHIPMENT_EVENT : tracking

    USER ||--o{ PRODUCT_REVIEW : writes
    PRODUCT ||--o{ PRODUCT_REVIEW : receives
    ORDER_ITEM ||--o| PRODUCT_REVIEW : verifies

    USER ||--o{ NOTIFICATION : receives
    NOTIFICATION ||--o{ NOTIFICATION_LOG : delivery
```

---

# بخش 6 — Models

## 6.0 قواعد عمومی دیتابیس

| قاعده | جزئیات |
|---|---|
| PK | `BigAutoField` برای همه. شناسهٔ بیرونی (URL/API/Gateway) = `public_id` (UUID4) یا شمارهٔ سفارش غیرقابل‌حدس؛ هرگز PK خام در URL حساس |
| زمان | `created_at/updated_at` = `timestamptz` (UTC). `USE_TZ=True`، `TIME_ZONE="Asia/Tehran"` فقط برای تفسیر ورودی/نمایش. ایران از ۱۴۰۱ ساعت تابستانی ندارد؛ اطمینان از به‌روز بودن `tzdata` سیستم/کانتینر ⚠️`[V19]` |
| پول | `BigIntegerField` به **ریال** + `CheckConstraint(>= 0)`. نام ستون با پسوند `_rial` (`price_rial`, `total_rial`) تا ابهام ریال/تومان غیرممکن شود |
| درصد | `PositiveSmallIntegerField` به **basis point** (۱۰۰۰ = ۱۰٪) یا درصد صحیح؛ سقف تخفیف `max_discount_rial`. گرد کردن: همیشه رو به پایین (floor) و نتیجه مضرب ۱۰ ریال (=۱ تومان) |
| Enumها | `TextChoices` + `CheckConstraint(status IN (...))` در DB |
| Soft delete | فقط برای Product/Category/Brand (`is_active` + `deleted_at`)؛ سفارش‌ها و پرداخت‌ها **هرگز حذف نمی‌شوند** (`on_delete=PROTECT`) |
| Snapshot | `OrderItem` عنوان، SKU، قیمت واحد، تخفیف، وزن را کپی می‌کند؛ سفارش به تغییر کاتالوگ وابسته نیست |
| Audit | `OrderStatusHistory` و `Transaction` تغییرناپذیر (append-only؛ Admin فقط‌خواندنی) |
| Index | روی هر FK (Django خودکار)، به‌علاوهٔ Composite/Partial مشخص شده زیر |
| تراکنش | `ATOMIC_REQUESTS=False`؛ تراکنش صریح در Service؛ **هیچ قفل DB نباید حین تماس HTTP بلند‌مدت نگه داشته شود** (استثنای کنترل‌شده در Verify پرداخت — بخش 8.6) |

### نقطهٔ تبدیل ریال ↔ تومان (دقیقاً کجا؟)

```text
 ورودی انسانی (Admin، فرم قیمت)  ──(×10)──►  Rial  ──► Services / Domain / DB  (همیشه Rial)
                                               │
                    ┌──────────────────────────┼───────────────────────────┐
                    ▼                          ▼                           ▼
        Presentation: فیلتر template     Adapter درگاه:               JSON-LD / API
        {{ x|toman }} → x÷10 +           فقط اگر درگاه تومان          priceCurrency="IRR"
        جداکننده هزارگان + «تومان»       می‌خواهد ⚠️[V2][V3]          مقدار ریال (استاندارد ISO 4217)
```

سه نقطهٔ مجاز تبدیل: (۱) فرم‌ها/Admin (`TomanField` → ریال)، (۲) Template filter `toman`، (۳) داخل Adapter درگاه (و **فقط** همان‌جا). در Service/Model/DB هرگز.

### نمایش تاریخ شمسی

✅ DB: UTC/میلادی. نمایش: Template filter `|jalali:"Y/m/d H:i"` بر پایهٔ `jdatetime` (یا `persiantools`) ⚠️`[V13]`، با تبدیل به `Asia/Tehran` قبل از فرمت. Admin: ویجت/نمایش شمسی با `django-jalali-date` یا `@admin.display` سفارشی ⚠️`[V13]`. API: ISO‑8601 UTC و فرمت‌کردن در کلاینت. گزارش‌های ماهانهٔ شمسی: محاسبهٔ مرز ماه شمسی در Python و Query با بازهٔ میلادی (یا جدول `DimDate` با ستون‌های jalali_year/month) — نه تبدیل در SQL. ورودی تاریخ در Admin (شروع/پایان کوپن) → تبدیل به میلادی قبل از ذخیره. شروع هفته: شنبه (در UI).

### نرمال‌سازی ورودی فارسی (`core.text`)

`normalize_fa(text)`: Unicode NFKC محتاطانه → `ي→ی`, `ك→ک`, `ة→ه`، حذف کشیده (ـ) و اعراب، ارقام فارسی/عربی → ASCII (فقط برای فیلدهای عددی/موبایل/کد)، فاصله‌های اضافه، **نیم‌فاصله (U+200C)**: برای Search هر دو شکل (با فاصله و بدون) Index می‌شود؛ برای نمایش دست‌نخورده می‌ماند. به‌صورت `NormalizedCharField`/Mixin روی فرم‌ها.

## 6.1 core

| مدل | فیلدها / قیود |
|---|---|
| `SiteSetting` (Singleton) | نام فروشگاه، تلفن، ایمیل، نشانی، شبکه‌های اجتماعی، متن Announcement Bar، لوگو، فعال‌بودن ثبت‌نام/خرید (Kill-switch)، `min_order_rial`، `payment_timeout_minutes`، `reservation_ttl_minutes` |
| `ProviderCallLog` | `provider`(payments/sms/shipping), `operation`, `request_masked` JSON, `response_masked` JSON, `http_status`, `duration_ms`, `ok`, `correlation_id`, `created_at`. Index `(provider, created_at)`. **Retention** ۹۰–۱۸۰ روز (Celery) |

## 6.2 locations

| مدل | فیلدها |
|---|---|
| `Province` | `name`, `slug`, `code`؛ Unique(`name`) |
| `City` | `province FK`, `name`, `slug`, `is_active`؛ Unique(`province`,`name`)؛ Index(`province`,`is_active`) |

دادهٔ مرجع از فایل Fixture/Migration با منبع رسمی ⚠️`[V20]`. شهرستان/محله در MVP نیست (`neighborhood` متنی اختیاری در Address).

## 6.3 accounts

**`User`** (`AbstractBaseUser` + `PermissionsMixin`، `USERNAME_FIELD="phone"`):
`phone` (نرمال‌شده `09XXXXXXXXX`، Unique، CheckConstraint regex)، `first_name`, `last_name`, `email` (اختیاری، Unique partial where not null), `national_id` (اختیاری ⚠️`[V12][V20]`)، `is_active`, `is_staff`, `phone_verified_at`, `date_joined`, `last_login`; رمز عبور **اختیاری** (`set_unusable_password()` برای کاربران فقط‌OTP).

**`OTPChallenge`**: `phone`, `purpose`(LOGIN/…)، `code_hash` (HMAC‑SHA256 با pepper)، `salt`, `expires_at`, `attempts`, `max_attempts`, `consumed_at`, `ip`, `user_agent_hash`, `provider`, `provider_message_id`, `created_at`.
Index `(phone, created_at DESC)`، Partial index روی `consumed_at IS NULL AND expires_at > now`‑معادل (با `expires_at`) برای جستجوی Challenge فعال.

**`Address`**: `user FK`, `province FK`, `city FK`, `address_line`, `plaque`, `unit`, `postal_code` (CharField؛ ۱۰ رقم)، `receiver_name`, `receiver_phone`, `latitude/longitude` (اختیاری ⚠️`[V16]`), `is_default`, `is_deleted`؛ Partial Unique: یک `is_default=True` برای هر کاربر.
**`WishlistItem`**: `user`, `product`؛ Unique(`user`,`product`).

## 6.4 catalog

**`Brand`**: `name`, `name_en`, `slug` (unicode), `logo`, `search_aliases` (آیفون/iphone…), `is_phone_brand` (برای `DeviceModel`), SEO fields, `is_active`.

**`Category`** (درخت — بخش 6.9): `parent FK(self)`, `name`, `slug`, `path` (Materialized Path)، `depth`, `position`, `image`, `description`, SEO fields, `is_active`.
Unique(`parent`,`slug`)؛ Unique(`path`).

**`Product`** (SPU): `title`, `slug`, `brand FK`, `category FK` (دستهٔ اصلی), `short_description`, `description` (HTML پاک‌سازی‌شده)، `is_active`, `is_featured`, `is_new` (یا محاسبه از `published_at`)، `published_at`, `search_text` + `search_vector` (بخش 6.8), **ستون‌های Denormalized برای لیست‌گیری سریع:** `min_price_rial`, `max_price_rial`, `compare_at_min_rial`, `in_stock`, `rating_avg` (Decimal یا ×۱۰ Integer)، `rating_count`, `sales_count`؛ SEO fields.
Index: `(is_active, category, -published_at)`، `(is_active, min_price_rial)`، `(is_active, -sales_count)`، GIN(`search_vector`)، GIN trigram(`search_text`).

**`ProductVariant`** (= **SKU**): `product FK`, `sku` (Unique), `barcode` (Unique partial), `title_suffix` (مثلاً «مشکی / USB‑C»)، `price_rial`, `compare_at_price_rial` (null)، `weight_g`, `length_mm/width_mm/height_mm`, `is_default`, `is_active`, `position`.
CHECK: `price_rial >= 0`, `compare_at_price_rial IS NULL OR compare_at_price_rial > price_rial`. Partial Unique: یک `is_default` برای هر Product. **هر محصول حداقل یک Variant دارد** (محصول ساده = یک Variant پیش‌فرض) → سبد/موجودی/سفارش همه به Variant اشاره می‌کنند و استثنا ندارند.

> 🔹 `ProductSKU` به‌صورت جدا طراحی **نمی‌شود**: SKU همان Variant است؛ جدول جدا فقط Join بی‌فایده می‌سازد.

**ویژگی‌ها (Attributes) — EAV سبک فقط برای چیزهای فیلترپذیر:**
- `AttributeDefinition`: `code` (color, connector, wattage, capacity_mah, length_cm, material…), `name`, `kind` (`COLOR/CHOICE/NUMBER/TEXT`), `is_variant_axis`, `is_filterable`, `position`.
- `AttributeOption`: `definition FK`, `value`, `label`, `hex` (برای رنگ)، `position`؛ Unique(`definition`,`value`).
- `ProductAttributeValue`: `product FK`, `option FK` (Unique(`product`,`option`)) → ویژگی‌های فیلترپذیر سطح محصول.
- `ProductVariant.options` ← M2M به `AttributeOption` (محورهای Variant مثل رنگ/ظرفیت). Constraint سطح Service: یک Variant برای هر Definition-axis حداکثر یک Option.
- `ProductSpecification`: `product FK`, `group`, `key`, `value`, `position` — **متن نمایشی** «مشخصات فنی» (تب Technical Details)، غیرقابل فیلتر. (جداسازی «نمایش» از «فیلتر» از Overengineering جلوگیری می‌کند.)

**سازگاری با مدل گوشی (پیشنهاد افزوده‌شده — تفاوت اصلی فروشگاه لوازم جانبی با فروشگاه عمومی):**
- `DeviceModel`: `brand FK` (Apple/Samsung/Xiaomi)، `series`, `name` (iPhone 15 Pro)، `slug`, `search_aliases`, `release_year`, `is_active`.
- `ProductCompatibility`: `product FK`, `device_model FK`؛ Unique(`product`,`device_model`) — این جدول فیلتر «مناسب برای گوشی …» و Search «قاب ایفون ۱۵» را ممکن می‌کند و در ادامه می‌تواند جایگزین ایجاد ده‌ها Variant برای قاب هر مدل شود. ✅ (اگر هر قاب برای هر مدل SKU جدا دارد، `device_model` به‌صورت Variant-axis مدل‌سازی شود؛ تصمیم نهایی با ساختار انبار شما.)

**`ProductImage`**: `product FK`, `variant FK (null)`, `image`, `alt`, `position`, `is_primary` (Partial Unique per product)، `width/height`, `renditions` JSON (مسیر اندازه‌های تولیدشده).

## 6.5 inventory (بخش 11 جزئیات)

| مدل | فیلدها / قیود |
|---|---|
| `InventoryItem` | `variant OneToOne`, `on_hand`, `reserved`, `low_stock_threshold`, `backorder_allowed`(پیش‌فرض False)؛ CHECK: `on_hand >= 0`, `reserved >= 0`, `reserved <= on_hand` (مگر backorder)؛ `available = on_hand − reserved` (Property/Annotation) |
| `InventoryTransaction` | **Append‑only**: `item FK`, `type` ∈ {PURCHASE, SALE, RETURN, ADJUSTMENT, RESERVATION, RELEASE}، `quantity_delta` (علامت‌دار)، `reserved_delta`, `on_hand_after`, `reserved_after`, `reference_type`, `reference_id`, `actor FK(null)`, `note`, `created_at`. **Unique(`type`,`reference_type`,`reference_id`,`item`)** برای Idempotency |
| `StockReservation` | `order FK`, `variant FK`, `quantity`, `status` ∈ {ACTIVE, CONSUMED, RELEASED, EXPIRED}، `expires_at`؛ Unique(`order`,`variant`)؛ Partial index(`expires_at`) WHERE `status='ACTIVE'` |

## 6.6 discounts / cart

| مدل | فیلدها / قیود |
|---|---|
| `Coupon` | `code` (Unique، case‑insensitive: ذخیره Upper)، `kind` ∈ {PERCENT, FIXED}، `value`, `max_discount_rial`, `min_order_rial`, `scope` ∈ {ORDER, PRODUCTS, CATEGORIES, BRANDS} + M2Mهای Target، `exclude_discounted_items`, `starts_at`, `ends_at`, `max_uses_total`, `max_uses_per_user`, `is_active`؛ CHECK: `starts_at < ends_at`, مقدار معتبر برای kind |
| `CouponRedemption` | `coupon`, `user`, `order`, `status` ∈ {RESERVED, REDEEMED, RELEASED}, `discount_rial`؛ Unique(`coupon`,`order`)؛ Index(`coupon`,`user`,`status`) |
| `PriceRule` (تخفیف محصول/دسته، حراج زمان‌دار) | `name`, `kind`, `value`, `targets` (M2M Product/Category/Brand), `starts_at`, `ends_at`, `priority`, `is_active` — خروجی: قیمت نهایی Variant + `compare_at` برای نمایش «۲۰٪ تخفیف» و Countdown صفحهٔ اصلی |
| `Cart` | `user OneToOne(null)` (فقط کاربر واردشده)، `updated_at`، `expires_at` |
| `CartItem` | `cart FK`, `variant FK`, `quantity`؛ Unique(`cart`,`variant`)؛ CHECK(`quantity BETWEEN 1 AND N`). **قیمت ذخیره نمی‌شود** (همیشه Live محاسبه) |

## 6.7 orders / payments / shipping / reviews / notifications / cms

**`Order`**: `number` (Unique، غیرقابل‌حدس، مثلاً ۹ رقم تصادفی + چک)، `user FK(PROTECT)`, `status`, `payment_status` (Denormalized، فقط توسط `PaymentService` به‌روز می‌شود), `checkout_token` (UUID Unique → Idempotency ثبت)، Snapshot آدرس: `ship_province`, `ship_city`, `ship_address`, `ship_plaque`, `ship_unit`, `ship_postal_code`, `receiver_name`, `receiver_phone`, `shipping_method FK`, مبالغ: `subtotal_rial`, `item_discount_rial`, `coupon_discount_rial`, `shipping_rial`, `tax_rial`, `total_rial`, `coupon_code`, `customer_note`, `placed_at`, `paid_at`, `cancelled_at`, `expires_at`, `needs_review` (برای پرداخت دیرهنگام).
CHECK: `total_rial = subtotal − item_discount − coupon_discount + shipping + tax` و همه ≥ ۰. Index: `(user, -placed_at)`, `(status, placed_at)`, `(status, expires_at)` (Partial برای `AWAITING_PAYMENT`).
**`OrderItem`**: `order FK`, `variant FK(PROTECT, null)`, Snapshot (`product_title`, `variant_title`, `sku`, `image`, `weight_g`), `unit_price_rial`, `unit_discount_rial`, `quantity`, `line_total_rial`؛ CHECK: `line_total = (unit_price − unit_discount) × quantity`.
**`OrderStatusHistory`**: `order`, `from_status`, `to_status`, `actor`(User/system), `reason`, `created_at`.
**`ReturnRequest`**: `order`, `items` (JSON/through با تعداد)، `reason`, `status`, `admin_note`.

**payments:** `Payment`، `PaymentAttempt`، `Transaction`، `Refund`، `PaymentGatewayConfig` — جزئیات و قیود در بخش 8.3.

**shipping:** `ShippingMethod` (`code`, `name`, `provider_code`, `is_active`, `eta_min_days/max_days`, `max_weight_g`, `requires_postal_code`), `ShippingRate` (روش + محدودهٔ استان/شهر + بازهٔ وزن + `price_rial` + `free_over_rial`), `Shipment` (`order`, `method`, `provider_code`, `tracking_code`, `status` ∈ {PENDING, PACKED, HANDED_OVER, IN_TRANSIT, DELIVERED, FAILED, RETURNED}، `shipped_at`, `delivered_at`, `cost_rial`, `provider_ref`)، `ShipmentItem`، `ShipmentEvent` (Tracking).

**reviews:** `ProductReview`: `product`, `user`, `order_item (null)`, `rating (1..5 CHECK)`, `title`, `body`, `pros/cons` (اختیاری), `status` ∈ {PENDING, APPROVED, REJECTED}, `is_verified_purchase`; **Unique(`user`,`product`)**؛ میانگین/تعداد در `Product` توسط Service/Celery به‌روز می‌شود.

**notifications:** `NotificationTemplate` (`event`, `channel`, `body` با متغیر)، `Notification` (In‑app: `user`, `title`, `body`, `read_at`, `url`)، `NotificationLog` (`event`, `channel`, `recipient_masked`, `entity_type/id`, `status`, `provider_ref`, `attempts`؛ **Unique(`event`,`channel`,`entity_type`,`entity_id`)** برای جلوگیری از ارسال تکراری).

**cms:** `Page` (`slug`, `title`, `body` HTML sanitize‌شده با `nh3`, `seo_*`, `is_published`, `show_in_footer`, `position`) ⚠️`[V13]`، `FAQCategory/FAQItem`، `Banner` (`placement` ∈ {HOME_HERO, HOME_PROMO, CATEGORY_TOP, …}, `image`, `mobile_image`, `alt`, `url`, `starts_at`, `ends_at`, `position`, `is_active`)، `ContactMessage` (`name`, `phone`, `email`, `subject`, `message`, `ip_hash`, `status`).

## 6.8 Search (PostgreSQL، MVP)

**هدف:** نام، SKU، برند، دسته، ویژگی‌ها، مدل گوشی، تحمل غلط‌املایی، فارسی/انگلیسی/ارقام.

```text
 index time (Celery task بعد از تغییر Product/Variant/Brand/Category، یا signal→on_commit→task):
   search_text   = normalize_fa(  title  + brand(fa+en+aliases) + category path
                                 + variant SKUs + attribute labels + compatible DeviceModel names/aliases )
                   + نسخهٔ بدون نیم‌فاصله + نسخهٔ transliterate شده (آیفون ⇄ iphone از جدول aliases)
   search_vector = setweight(to_tsvector('simple', title_norm),'A')
                 || setweight(to_tsvector('simple', sku || brand_norm),'B')
                 || setweight(to_tsvector('simple', category_norm || device_norm),'C')
                 || setweight(to_tsvector('simple', attrs_norm),'D')

 query time:
   q → normalize_fa(q) → tokens
   1) FTS:  search_vector @@ to_tsquery('simple', 'tok1:* & tok2:*')  → ts_rank_cd
   2) Fuzzy fallback (اگر نتیجه کم/صفر): search_text % q  (pg_trgm similarity)  → ORDER BY similarity
   3) SKU/Barcode دقیق: اگر q شبیه SKU → Exact match اول
   + فیلترها (brand/category/price/attributes/stock) روی همان Queryset
```

- **چرا `simple`؟** برای فارسی دیکشنری/Stemmer بومی در PostgreSQL استاندارد نداریم؛ `simple` + نرمال‌سازی قوی در Python + Prefix matching (`:*`) برای MVP کافی و قابل‌پیش‌بینی است ⚠️`[V21]`.
- Extensionها: `pg_trgm` (و در صورت نیاز `unaccent` فقط برای لاتین). نیازمند دسترسی Superuser/Allowlist در Postgres میزبان.
- **Autocomplete:** Endpoint سبک روی Trigram/Prefix (۸ نتیجه)، Cache کوتاه در Redis.
- **مرحلهٔ بعد (Scale-up):** OpenSearch/Elasticsearch با Analyzer فارسی، وقتی: >~۵۰–۱۰۰ هزار SKU، نیاز به Facet Count سنگین/Synonym پیشرفته/Learning‑to‑rank، یا Latency قابل‌قبول نباشد ⚠️`[V21]`. چون Search پشت `catalog.search.SearchBackend` (Interface: `search(query, filters, page)`) است، تعویض بدون تغییر View انجام می‌شود.

## 6.9 Category Tree

| گزینه | مزیت | عیب |
|---|---|---|
| Adjacency (parent FK) ساده | ساده | Query زیرشاخه‌ها بازگشتی (CTE) |
| **Materialized Path** (`path='/12/45/'`) ✅ | همهٔ زیرشاخه‌ها با `path LIKE '/12/%'` (Index با `text_pattern_ops`)؛ Breadcrumb بدون Query؛ ساده | جابه‌جایی شاخه نیازمند به‌روزرسانی Pathِ زیرشاخه‌ها (نادر) |
| Nested Set | خواندن سریع | نوشتن/جابه‌جایی سنگین و پیچیده |
| `django-mptt` / `django-treebeard` | آماده | وابستگی؛ وضعیت نگهداری/سازگاری باید بررسی شود ⚠️`[V13]` |

✅ **پیشنهاد:** `django-treebeard` با `MP_Node` (Materialized Path آماده + پشتیبانی Admin) **یا** پیاده‌سازی Path دست‌نویس ~۴۰ خط (اگر Library بررسی ⚠️`[V13]` نشد). **کل درخت (چند صد گره) در Redis/Local-memory Cache** با Invalidation هنگام تغییر؛ Mega Menu و Breadcrumb از همین Cache ساخته می‌شوند. اسلاگ فارسی (`allow_unicode`) + Unique(`parent`,`slug`).

**نمونه:**
```text
لوازم جانبی موبایل
├── قاب موبایل ── قاب آیفون / قاب سامسونگ / قاب شیائومی
├── گلس ── کابل ── شارژر (+آداپتور) ── پاوربانک ── هندزفری/هدفون ── هولدر
```
> برند/مدل گوشی را **هم** می‌توان درخت دسته (قاب آیفون) و **هم** ویژگی/سازگاری (`DeviceModel`) مدل کرد. پیشنهاد: دستهٔ «قاب آیفون» برای ناوبری/SEO (Landing) و `ProductCompatibility` برای فیلتر دقیق مدل؛ هر دو از یک منبع دادهٔ سازگاری قابل Sync‌اند.

---

# بخش 7 — Service Layer

## 7.1 قرارداد

- **Write = `services.py`**، **Read = `selectors.py`**. View فقط: اعتبارسنجی ورودی → فراخوانی Service/Selector → رندر/Redirect.
- Service‌ها تابع/کلاس بدون حالت (Stateless)اند؛ ورودی = مقادیر ساده/DTO؛ خروجی = Entity یا DTO؛ خطا = استثنای دامنه‌ای (`OutOfStock`, `CouponInvalid`, `InvalidTransition`, `GatewayError`…) که View به پیام فارسی نگاشت می‌کند.
- **محاسبات خالص** (قیمت‌گذاری، توزیع تخفیف، State machine) در `domain/` به‌صورت توابع Pure بدون ORM → تست سریع و بدون DB.
- **Repository Pattern استفاده نمی‌شود** (ORM خودش Repository است). تنها «جایی که ارزش دارد»: رابط‌های `SearchBackend` و `StorageBackend` و Adapterهای `integrations/` — چون واقعاً چند پیاده‌سازی قابل تعویض دارند.
- Eventها: Dataclassهای ساده در `core.events` + `publish(event)` که Handlerها را در `AppConfig.ready()` ثبت‌شده فراخوانی می‌کند؛ Handlerها فقط Task Celery را با `transaction.on_commit` صف می‌کنند (هرگز ارسال SMS داخل تراکنش DB).

## 7.2 فهرست سرویس‌ها

| سرویس | متدهای کلیدی | قفل/تراکنش/Idempotency |
|---|---|---|
| `OTPService` | `request_otp(phone, ip, purpose)`, `verify_otp(phone, code, ip)` | Redis counters؛ `OTPChallenge` با `select_for_update` هنگام Verify؛ پاسخ یکسان برای شمارهٔ ناشناخته |
| `AuthService` | `login_or_register(phone)`, `set_password`, `login_with_password` | ایجاد کاربر با `get_or_create` روی Unique(phone)؛ Merge سبد بعد از Login |
| `CatalogService` | `publish_product`, `recalc_product_denormalized(product_id)`, `reindex_product` | Celery |
| `PricingService` (+ `domain/pricing.py`) | `price_variant(variant, at)`, `price_cart(lines, coupon, shipping, tax)` → `Totals` | Pure؛ همان تابع در Cart نمایشی و Checkout نهایی استفاده می‌شود (تا اختلاف قیمت صفر شود) |
| `DiscountService` | `validate_coupon(code, user, lines)`, `reserve_coupon(order)`, `release_coupon(order)`, `redeem_coupon(order)` | `select_for_update` روی `Coupon` هنگام شمارش مصرف؛ Unique(`coupon`,`order`) |
| `CartService` | `get_cart(request)`, `add`, `set_quantity`, `remove`, `merge_guest_into_user`, `validate_for_checkout` | Merge Idempotent (بخش 10) |
| `InventoryService` | `reserve(order, lines)`, `release(order)`, `consume(order)`, `adjust(variant, delta, reason)`, `receive_purchase(...)`, `restock_return(...)` | قفل/Update شرطی + Unique در Ledger (بخش 11) |
| `ShippingService` | `quote(address, lines) → [Quote]`, `create_shipment(order)`, `sync_tracking(shipment)` | Adapter؛ Retry در Celery |
| `CheckoutService` (در `orders`) | `place_order(user, cart, address_id, shipping_code, coupon, checkout_token)` | **یک تراکنش:** Lock/Validate → Price → Create Order+Items → Reserve stock → Reserve coupon؛ `checkout_token` Unique ⇒ ثبت دوباره همان سفارش را برمی‌گرداند |
| `OrderService` | `transition(order, to, actor, reason)`, `mark_paid(order, payment)`, `cancel(order, reason)`, `request_return`, `expire_unpaid()` | State machine جدولی + `select_for_update(order)` + `OrderStatusHistory` |
| `PaymentService` | `start_payment(order, gateway_code)`, `handle_callback(gateway_code, request)`, `verify(attempt)`, `reconcile_pending()`, `request_refund(payment, amount, reason)` | بخش 8 |
| `ReviewService` | `submit`, `moderate`, `recalc_rating(product)` | Unique(user, product) |
| `NotificationService` | `send(event, recipient, context)` | `NotificationLog` Unique ⇒ ارسال تکراری ممکن نیست |
| `CMSService` | `get_page(slug)` (Cache) | |

## 7.3 Notification Architecture

```text
 Service ──publish(Event)──► core.events registry ──► notifications.handlers
                                                         │  transaction.on_commit
                                                         ▼
                                                  Celery: send_notification(event, entity_id)
                                                         │ Template (DB) + context
                              ┌──────────────────────────┼───────────────────────────┐
                              ▼                          ▼                           ▼
                        SMSChannel                  EmailChannel               InAppChannel
                  (SMSProvider adapter)            (SMTP/Anymail)             (Notification row)
                              └──── NotificationLog (Unique event+channel+entity) ────┘
```

| Event | SMS | Email | In‑app | یادداشت |
|---|:--:|:--:|:--:|---|
| `USER_REGISTERED` | – | ایمیل اختیاری | ✔ | خوش‌آمد |
| `OTP_REQUESTED` | ✔ (مسیر ویژه، اولویت بالا، بدون Retry طولانی) | – | – | صف مجزا `otp` |
| `ORDER_CREATED` | ✔ | ✔ | ✔ | |
| `PAYMENT_SUCCESSFUL` | ✔ | ✔ | ✔ | رسید + شمارهٔ پیگیری درگاه |
| `PAYMENT_FAILED` | ✔ (اختیاری) | – | ✔ | لینک تلاش مجدد |
| `ORDER_PROCESSING` | – | – | ✔ | |
| `ORDER_SHIPPED` | ✔ | ✔ | ✔ | کد رهگیری |
| `ORDER_DELIVERED` | – | ✔ | ✔ | درخواست نظر |
| `ORDER_CANCELLED` | ✔ | ✔ | ✔ | |
| `REFUND_CREATED` | ✔ | ✔ | ✔ | |

صف‌های Celery: `otp` (حساس به تأخیر)، `default`، `payments` (Reconcile)، `images` (CPU)، `reports` (کم‌اولویت) — تا ارسال گزارش سنگین OTP را کند نکند.

---

# بخش 8 — Payment Architecture

## 8.1 اصول

1. **درگاه فقط Adapter است.** هسته (`payments`) فقط با Interface `PaymentGateway` کار می‌کند؛ Pattern: **Strategy + Adapter + Registry (Factory)**.
2. **مبلغ و وضعیت را فقط از Verify سمت‌سرور باور می‌کنیم.** پارامتر Callback (مثلاً `Status=OK`) به‌تنهایی «پرداخت موفق» نیست.
3. **Payment (قصد پرداخت برای سفارش) ≠ PaymentAttempt (هر Session درگاه) ≠ Transaction (حرکت پول).**
4. Callback نباید به Session/Cookie وابسته باشد (برگشت از درگاه ممکن است Cross‑site POST باشد و `SameSite=Lax` کوکی را نفرستد). شناسایی فقط با `attempt.public_id`/`authority` ذخیره‌شدهٔ خودمان؛ پس از Verify، به صفحهٔ نتیجهٔ داخلی **303 Redirect** می‌دهیم (ناوبری Top‑level GET ⇒ کوکی ارسال می‌شود).
5. هیچ اطلاعات کارت روی سرور ما دریافت/ذخیره نمی‌شود؛ فقط شمارهٔ ماسک‌شدهٔ کارت (`6037‑99**‑****‑1234`) در صورت ارائهٔ درگاه.

## 8.2 Interface (طراحی، نه پیاده‌سازی کامل)

```python
# integrations/payments/base.py
@dataclass(frozen=True)
class PaymentRequest:           # ورودی Gateway-agnostic (همه ریال)
    attempt_ref: str            # public_id مربوط به Attempt
    amount_rial: int
    callback_url: str
    description: str
    payer_phone: str | None
    metadata: dict

@dataclass(frozen=True)
class PaymentSession:
    authority: str              # توکن/Authority درگاه
    redirect_url: str           # یا form_post: {url, fields}
    redirect_method: Literal["GET", "POST"]
    expires_at: datetime | None
    raw: dict                   # برای ProviderCallLog (ماسک‌شده)

@dataclass(frozen=True)
class CallbackData:             # خروجی parse_callback
    authority: str
    gateway_status: str | None  # خام، فقط اطلاعاتی
    raw: dict

@dataclass(frozen=True)
class VerifyResult:
    outcome: Literal["SUCCESS", "FAILED", "PENDING", "ALREADY_VERIFIED"]
    gateway_ref: str | None     # شمارهٔ مرجع/ref_id
    paid_amount_rial: int | None
    card_pan_masked: str | None
    fee_rial: int | None
    raw: dict

class PaymentGateway(ABC):
    code: str
    capabilities: GatewayCapabilities    # supports_inquiry, supports_refund, post_callback, unit="RIAL"|"TOMAN"

    def create_payment(self, req: PaymentRequest) -> PaymentSession: ...
    def parse_callback(self, request) -> CallbackData: ...      # GET/POST را خود Adapter می‌فهمد
    def verify(self, authority: str, expected_amount_rial: int) -> VerifyResult: ...
    def inquire(self, authority: str) -> VerifyResult: ...      # اختیاری (برای Reconcile)
    def refund(self, gateway_ref: str, amount_rial: int, reason: str) -> RefundResult: ...  # اختیاری
```

- **واحد پول:** `capabilities.unit` تعیین می‌کند Adapter مبلغ را ریال یا تومان بفرستد؛ هسته همیشه ریال می‌دهد ⚠️`[V2][V3][V4]`.
- **خطاها:** Adapter همهٔ خطاهای HTTP/JSON/کد درگاه را به سلسله‌مراتب داخلی نگاشت می‌کند: `GatewayUnavailable` (Retry-able)، `GatewayTimeout`، `GatewayRejected` (دائمی)، `GatewayProtocolError`.
- **HTTP:** `timeout=(connect 3s, read 10s)`؛ Retry خودکار فقط برای عملیات Idempotent (inquire/verify نه create)؛ همهٔ تماس‌ها در `ProviderCallLog` (ماسک‌شده).
- **Registry:** `PAYMENT_GATEWAYS` در Settings (کلاس + پارامترها از Env) + `PaymentGatewayConfig` در DB (فعال/غیرفعال، اولویت، حداقل/حداکثر مبلغ، عنوان/لوگو) → Admin می‌تواند درگاه را بدون Deploy خاموش/روشن کند. **Secretها هرگز در DB نیستند.**
- **Sandbox/Mock:** `FakeGateway` (Deterministic، قابل‌برنامه‌ریزی برای SUCCESS/FAILED/TIMEOUT) برای Test و Dev؛ Adapterهای واقعی با Sandbox رسمی هر PSP در صورت وجود ⚠️`[V2][V3]`.

## 8.3 مدل‌ها و قیود

| مدل | فیلدها | قیود مهم |
|---|---|---|
| `Payment` | `public_id`, `order FK(PROTECT)`, `amount_rial`, `status`, `idempotency_key`, `gateway_code` (آخرین)، `paid_at` | Unique(`idempotency_key`)؛ CHECK(`amount_rial > 0`)؛ Partial Unique: **حداکثر یک Payment با `status IN (INITIATED, PENDING, PAID)` برای هر Order** |
| `PaymentAttempt` | `public_id`, `payment FK`, `gateway_code`, `authority`, `amount_rial`, `status`, `redirect_url`, `expires_at`, `callback_received_at`, `verified_at`, `failure_code`, `failure_message`, `ip`, `created_at` | **Unique(`gateway_code`,`authority`)** (WHERE authority≠'')؛ **Partial Unique(`payment`) WHERE `status IN (CREATED, REDIRECTED, VERIFYING)`** ⇒ «یک Attempt فعال برای هر Payment» (کلیک چندباره = همان Attempt) |
| `Transaction` (Ledger، Append‑only) | `payment FK`, `attempt FK(null)`, `type` ∈ {CHARGE, REFUND}, `status` ∈ {SUCCEEDED, FAILED}, `amount_rial`, `gateway_ref` (شمارهٔ مرجع درگاه)، `internal_id` (UUID)، `card_pan_masked`, `fee_rial`, `occurred_at`, `raw_ref` → ProviderCallLog | **Partial Unique(`payment`) WHERE `type='CHARGE' AND status='SUCCEEDED'`**؛ Unique(`gateway_code`,`gateway_ref`) WHERE not null؛ CHECK(`amount_rial > 0`) |
| `Refund` | `public_id`, `payment`, `return_request (null)`, `amount_rial`, `reason`, `method` ∈ {GATEWAY, MANUAL_BANK_TRANSFER}, `status` ∈ {REQUESTED, APPROVED, PROCESSING, COMPLETED, FAILED}, `requested_by`, `approved_by`, `bank_reference` | CHECK(`amount_rial > 0`)؛ **مجموع Refundهای غیرِ‌FAILED ≤ مبلغ پرداخت‌شده** (در Service با قفل Payment + CHECK سطح Aggregate در Service) |

## 8.4 Flow کامل

```text
[User] Place order
   │ CheckoutService.place_order()  (1 atomic txn)
   │   → Order(PENDING→AWAITING_PAYMENT), items snapshot, stock RESERVED (TTL), coupon RESERVED
   ▼
PaymentService.start_payment(order, gateway)
   ├─ txn A: get_or_create Payment (idempotency_key = f"order:{id}:pay")
   │         + (reuse active Attempt  یا  create Attempt[CREATED])                      ──commit
   ├─ HTTP : gateway.create_payment(...)    (بدون قفل DB؛ timeout)
   └─ txn B: Attempt.authority=..., status=REDIRECTED, expires_at                        ──commit
   ▼
302/auto‑POST → Gateway page (کاربر پرداخت می‌کند)
   ▼
Gateway ──► /payments/callback/<gateway_code>/   (GET یا POST، csrf_exempt، بدون وابستگی به Session)
   │  parse_callback → authority → Attempt بر اساس (gateway, authority)  (ناشناخته → 404/لاگ امنیتی)
   │  PaymentService.verify(attempt)   ← بخش 8.6
   ▼
 303 Redirect → /checkout/result/<order_no>/    (صفحهٔ نمایش؛ فقط وضعیت DB را می‌خواند)

Background (Celery Beat, هر ۱–۲ دقیقه):
   reconcile_pending(): Attemptهای REDIRECTED/VERIFYING قدیمی‌تر از N دقیقه → gateway.inquire() (اگر پشتیبانی شود) → همان مسیر verify
   expire_unpaid_orders(): Orderهای AWAITING_PAYMENT منقضی → cancel + release stock/coupon
```

## 8.5 State Machineها

**PaymentAttempt**
```text
CREATED ─► REDIRECTED ─► VERIFYING ─► SUCCEEDED
   │           │  │           └──────► FAILED
   │           │  └─(user cancel)────► CANCELLED
   └───────────┴─(expires_at)────────► EXPIRED          ← حالات پایانی: SUCCEEDED/FAILED/CANCELLED/EXPIRED
```
**Payment:** `INITIATED → PENDING → PAID`؛ `PENDING → FAILED/CANCELLED/EXPIRED` (بعد می‌تواند Attempt جدید بسازد → دوباره `PENDING`)؛ `PAID → PARTIALLY_REFUNDED → REFUNDED`.

**Order** (جدا از Payment — جدول مجاز انتقال‌ها؛ `OrderService.transition` فقط همین را می‌پذیرد):

| از → به | محرک | Side‑effects |
|---|---|---|
| `PENDING → AWAITING_PAYMENT` | شروع پرداخت | — |
| `AWAITING_PAYMENT → PAID` | `PaymentSucceeded` (فقط `PaymentService`) | Reservation→CONSUMED + `SALE` در Ledger؛ Coupon→REDEEMED؛ Event |
| `AWAITING_PAYMENT → CANCELLED` | انصراف/انقضا | Release stock؛ Release coupon |
| `PAID → PROCESSING` | Admin/خودکار | — |
| `PROCESSING → PACKED` | Admin | — |
| `PACKED → SHIPPED` | ثبت `tracking_code` | `Shipment` + Event |
| `SHIPPED → DELIVERED` | Admin/Tracking | امکان ثبت نظر |
| `PAID/PROCESSING/PACKED → CANCELLED` | Admin (قبل از ارسال) | **Refund** ایجاد؛ بازگشت موجودی (`RETURN`/`ADJUSTMENT`) |
| `DELIVERED → RETURN_REQUESTED → RETURNED` | مشتری/Admin | بازرسی کالا |
| `RETURNED → REFUNDED` | پایان Refund | Order به `REFUNDED` فقط وقتی Refund کامل **COMPLETED** شد |

> یادداشت: برای «لغو بعد از پرداخت» وضعیت Order = `CANCELLED` و `payment_status` = `REFUNDED/REFUND_PENDING`؛ وضعیت `REFUNDED` در Order مخصوص «بازگشت کالا + عودت وجه» است. با این کار دو محور جدا و بدون ابهام می‌مانند.

## 8.6 الگوریتم `PaymentService.verify(attempt)`

```text
1. with transaction.atomic():
2.    attempt = PaymentAttempt.objects.select_for_update().get(pk=...)      # قفل فقط همین ردیف
3.    if attempt.status in TERMINAL:  return stored_result(attempt)           # Idempotent: Callback تکراری/Replay
4.    attempt.status = VERIFYING; attempt.callback_received_at = now
5.    result = gateway.verify(attempt.authority, expected_amount_rial=attempt.amount_rial)   # HTTP، timeout ≤10s
6.        └ خطای شبکه/Timeout → وضعیت VERIFYING می‌ماند (commit)، Celery reconcile ادامه می‌دهد؛ پاسخ به کاربر: «در حال بررسی»
7.    if result.outcome in (SUCCESS, ALREADY_VERIFIED):
8.        validate: result.paid_amount_rial == attempt.amount_rial  AND  attempt.amount_rial == payment.amount_rial == order.total_rial
9.        mismatch → Attempt=FAILED(reason=AMOUNT_MISMATCH) + هشدار امنیتی + نیاز به بررسی دستی (پول ممکن است کسر شده باشد!)
10.       insert Transaction(CHARGE, SUCCEEDED, gateway_ref=...)   # Unique(payment, CHARGE+SUCCEEDED) جلوی دوبار ثبت را می‌گیرد
11.       Attempt=SUCCEEDED; Payment=PAID; OrderService.mark_paid(order)   # در همان تراکنش
12.       transaction.on_commit → publish(PaymentSucceeded)
13.    else (FAILED): Attempt=FAILED; Payment=FAILED(یا PENDING اگر Attempt دیگری امکان دارد)؛ publish(PaymentFailed)
```

> **استثنای آگاهانه:** در گام 5 قفل ردیفیِ *همان Attempt* نگه داشته می‌شود. دلیل: ساده‌ترین راه جلوگیری از Verify دوبل هم‌زمان؛ هزینه: یک Connection تا ≤۱۰ ثانیه. در مقیاس MVP قابل‌قبول است. 🔹 جایگزین مقیاس‌پذیرتر (Claim‑pattern): Commit کردن `VERIFYING` → تماس HTTP بدون قفل → قفل مجدد و اعمال نتیجه، با Reconcile برای ردیف‌های گیرکرده.

## 8.7 سناریوهای خطا و پاسخ

| سناریو | رفتار |
|---|---|
| Callback دوبار برسد / Replay | Attempt پایانی است ⇒ نتیجهٔ ذخیره‌شده؛ Transaction جدید ساخته نمی‌شود (Unique) |
| Callback جعلی (authority ناشناخته یا مبلغ متفاوت) | 404/۴۰۰ + `security` log؛ هیچ تغییر وضعیتی. تنها Verify سمت‌سرور مبنای تصمیم است |
| مبلغ Verify ≠ مبلغ سفارش | `FAILED(AMOUNT_MISMATCH)` + Alert فوری + `order.needs_review`؛ بدون Mark Paid |
| کاربر چندبار «پرداخت» بزند | Partial Unique ⇒ همان Attempt فعال (تا `expires_at`) بازگردانده می‌شود |
| Callback هرگز نرسید (بستن مرورگر بعد از پرداخت) | `reconcile_pending` با `inquire` (در صورت پشتیبانی)؛ در غیر این‌صورت لیست «نیازمند بررسی» در Admin ⚠️`[V2][V3]` |
| پرداخت موفق، ولی Order قبلاً منقضی/لغو شد (Late payment) | Verify انجام می‌شود (پول نباید گم شود)؛ اگر موجودی هنوز هست ⇒ Re‑reserve و `PAID`؛ وگرنه Order به `needs_review` و Refund پیشنهادی؛ هرگز بی‌صدا نادیده گرفته نمی‌شود |
| انصراف کاربر در درگاه | `CANCELLED`؛ سفارش تا انقضا قابل «پرداخت مجدد» |
| دو Worker روی یک سفارش | قفل `select_for_update(order)` در `OrderService.transition`؛ Transition دوباره ⇒ `InvalidTransition` بی‌ضرر |
| خطای 5xx درگاه در `create_payment` | Attempt در `CREATED` می‌ماند و بعد از Timeout به `EXPIRED`؛ پیام «موقتاً در دسترس نیست» + امکان درگاه دیگر |

## 8.8 Refund

- Interface: `refund()` اختیاری است (`capabilities.supports_refund`). بسیاری از Flowها در ایران عملاً **عودت دستی/بانکی** هستند ⚠️`[V2][V3][V4]` ⇒ `Refund.method = MANUAL_BANK_TRANSFER` با فیلدهای `bank_reference` و Workflow: `REQUESTED → APPROVED → PROCESSING → COMPLETED`.
- Admin Action «ثبت عودت»؛ هر Refund یک `Transaction(type=REFUND)` تولید می‌کند و Event `REFUND_CREATED`.
- مجموع Refundها هرگز از مبلغ شارژ بیشتر نمی‌شود (قفل `Payment` در `request_refund`).

## 8.9 Logging پرداخت
`payments` logger مجزا: JSON، شامل `attempt_ref`, `order_no`, `gateway`, `event`, `outcome`, `amount_rial`, `duration_ms`. **ممنوع:** Merchant ID/Token/PAN کامل. Retention طولانی‌تر (حسابداری/اختلاف) — با تأیید ⚠️`[V12]`.

---

# بخش 9 — OTP Architecture

## 9.1 Flow (Phone‑first، ضد Enumeration)

```text
POST /account/login/phone/  {phone}
   │ normalize_phone()  (۰۹۱۲… / +98912… / 0098… / ارقام فارسی → 09XXXXXXXXX؛ نامعتبر → خطای فرم)
   │ RateLimiter: ip / phone / global-budget  (جدول 9.3)
   │ پاسخ **همیشه یکسان**: «اگر شماره صحیح باشد، کد ارسال شد»  (چه کاربر موجود باشد چه نه)
   ▼
 OTPService.request_otp():  (cooldown فعال؟ → همان پاسخ + زمان باقی‌مانده)
   code = secrets.randbelow(10**6) → ۶ رقم
   challenge = OTPChallenge(code_hash=HMAC(pepper, phone|purpose|code|salt), expires_at=now+120s, attempts=0)
   publish(OtpRequested) → Celery(queue=otp) → SMSProvider.send_otp(phone, code)
   ▼
POST /account/login/verify/ {phone, code}
   │ RateLimiter(verify attempts)
   │ challenge = آخرین Challenge فعال (select_for_update)
   │ attempts += 1  (همیشه، حتی اگر اشتباه)  | attempts > max → Challenge باطل + Cooldown
   │ compare_digest(HMAC(...), challenge.code_hash)  و  expires_at > now  و  consumed_at is NULL
   ▼ موفق: consumed_at=now → AuthService.login_or_register(phone) → merge cart → session cycle_key → 302
```

## 9.2 Abstraction SMS

```python
# integrations/sms/base.py
class SMSProvider(ABC):
    code: str
    def send_otp(self, phone: str, code: str, *, ttl_seconds: int) -> SMSResult: ...
    def send_text(self, phone: str, text: str, *, template: str | None = None) -> SMSResult: ...
    def get_status(self, provider_message_id: str) -> DeliveryStatus | None: ...   # اختیاری

class SMSResult:  ok: bool; provider_message_id: str|None; error_code: str|None; retryable: bool
```
- Providerها: `kavenegar.py`, `sms_ir.py`, `farazsms.py`, `console.py` (Dev: چاپ در Log)، `fake.py` (Test: ذخیره در حافظه).
- **Failover:** `SMS_PROVIDER` (اصلی) و `SMS_FALLBACK_PROVIDER`؛ در `retryable=False` یا ۲ بار خطا → Provider دوم. تأخیر OTP برای کاربر حیاتی است.
- بسیاری از Providerهای ایرانی برای OTP **قالب از پیش‌تأییدشده/خط خدماتی** می‌خواهند؛ هر Adapter نگاشت `send_otp → template/lookup` را خودش انجام می‌دهد ⚠️`[V5][V6]`.

## 9.3 محافظت‌ها

| تهدید | کنترل |
|---|---|
| Brute‑force کد | `max_attempts=5` به‌ازای Challenge؛ بعد از آن Challenge باطل و Cooldown ۱۵ دقیقه؛ شمارندهٔ Verify به‌ازای phone و IP در Redis |
| Spam/SMS Pumping (هزینهٔ SMS) | سقف **ارسال** به‌ازای phone (مثلاً ۵/ساعت، ۱۰/روز)، به‌ازای IP (مثلاً ۲۰/ساعت)، به‌ازای IP‑subnet، و **بودجهٔ سراسری** (Circuit‑breaker: اگر ارسال/دقیقه از آستانه گذشت، درخواست‌های جدید با تأخیر/Captcha) |
| Resend abuse | Cooldown ۱۲۰ ثانیه بین دو ارسال (سمت سرور، نه فقط تایمر UI) |
| Enumeration | پاسخ یکسان + زمان پاسخ تقریباً یکسان؛ Register/Login یکی |
| Replay/استفادهٔ مجدد | `consumed_at` + بسته شدن Challenge‌های قبلی هنگام صدور جدید |
| لو رفتن دیتابیس | فقط `code_hash` (HMAC با Pepper از Env)؛ کد خام هرگز ذخیره/Log نمی‌شود (در Production) |
| Timing attack | `hmac.compare_digest` |
| Bot‑farm | Honeypot + در صورت نیاز Captcha (گزینه‌های قابل‌استفاده در ایران ⚠️`[V15]`؛ احتمالاً Captcha خودمیزبان) |
| Session Fixation | `request.session.cycle_key()` بعد از ورود |

مقادیر (۶ رقم/۱۲۰ ثانیه/۵ تلاش…) پیش‌فرضِ پیشنهادی‌اند و از `SiteSetting`/Env قابل تنظیم‌اند.
**Rate limiter** در `core` (Redis `INCR`+`EXPIRE` یا Lua برای اتمیک بودن؛ یا Token‑bucket) و مشترک با DRF Throttle؛ کلیدها: `rl:otp:send:phone:{hash}`، `rl:otp:send:ip:{ip}`، `rl:otp:verify:phone:{hash}`. شمارهٔ موبایل در کلید/Log **هش یا ماسک** می‌شود.

**Logging (`otp` logger):** درخواست/ارسال/موفق/ناموفق/Throttle با `phone_masked`, `ip`, `challenge_id`, `provider`, `latency` — بدون کد.

**ورود با رمز (اختیاری) و Admin:** تب «ورود با رمز» برای کاربرانی که رمز تعیین کرده‌اند، با Throttle مشابه. **کاربران Staff با OTP وارد Admin نمی‌شوند**؛ Admin ورود جدا (آدرس غیرپیش‌فرض)، رمز قوی + TOTP (2FA) ⚠️`[V13]`.

---

# بخش 10 — Cart Architecture

| نوع | ذخیره‌سازی | مشخصات |
|---|---|---|
| **مهمان** | Session (`{variant_id: qty}`) | Session Backend: `cached_db` (Redis + Write‑through به DB) تا با Restart/Evict Redis سبد گم نشود؛ TTL ۳۰ روز |
| **کاربر** | `Cart`/`CartItem` در PostgreSQL | OneToOne به User؛ بین دستگاه‌ها همگام |

`CartService.get_cart(request)` یک **Interface یکسان** (`CartLike`) برمی‌گرداند؛ بقیهٔ کد نمی‌داند مهمان است یا کاربر.

**اصل قیمت:** سبد فقط `variant_id` و `quantity` را ذخیره می‌کند؛ قیمت/تخفیف/موجودی همیشه Live از `PricingService`/`InventoryService` محاسبه می‌شود. در Checkout، اگر قیمت نسبت به لحظهٔ نمایش سبد تغییر کرده باشد، پیام صریح نشان داده می‌شود و ثبت سفارش با تأیید کاربر ادامه می‌یابد.

## Merge هنگام Login

```text
 Login موفق (OTP)
   ▼
 1) guest_items = session cart را **قبل از** `login()` بخوان
    (django.contrib.auth.login ممکن است Session را flush کند اگر کاربر دیگری در همان Session بوده)
   ▼
 2) user_cart = Cart.get_or_create(user)                         ─┐ یک تراکنش atomic
 3) برای هر variant: qty = guest.qty + user.qty (جمع)            │ قفل: select_for_update(user_cart)
 4) Resolve duplicates:  qty = min(qty, available_stock, max_per_item)  │
 5) Variant غیرفعال/ناموجود → حذف + پیام                         │
 6) ذخیره User Cart  ─────────────────────────────────────────────┘
 7) Session cart را پاک کن (مرحلهٔ آخر ⇒ اگر خطا بخورد، دوباره قابل Merge است = Idempotent)
 8) پیام به کاربر: «n مورد اصلاح شد»
```
قاعدهٔ پیشنهادی ادغام = **جمع تعداد با سقف** (و نه «max»). 🔹 جایگزین: «سبد کاربر برنده» — ساده‌تر ولی کالاهای مهمان گم می‌شود.

**HTMX:** `POST /cart/add/` ، `PATCH /cart/items/<variant>/` ، `DELETE …` پاسخ = Partial سبد (`cart_item_row` + `order_summary` + شمارندهٔ هدر). **سبد خالی/منقضی**: Task Celery برای پاکسازی سبد کاربران ناپدید‌شده (>۹۰ روز).

---

# بخش 11 — Inventory Architecture

## 11.1 مدل

- **Source of truth:** `InventoryItem(on_hand, reserved)` + دفتر کل **`InventoryTransaction`** (Append‑only). مقدار `on_hand/reserved` یک Cache قابل بازسازی از Ledger است؛ تست «Reconcile» (جمع Ledger = مقدار فعلی) به‌صورت Job شبانه + Alert.
- `available = on_hand − reserved`. فروش فقط از `available`.
- مستقل از Product: `InventoryItem` به `ProductVariant` وصل است (نه Product)؛ Product فقط `in_stock` را Denormalize می‌کند (Celery).

| نوع Ledger | on_hand Δ | reserved Δ | کِی |
|---|:-:|:-:|---|
| `PURCHASE` | + | 0 | ورود کالا از تأمین‌کننده |
| `RESERVATION` | 0 | + | ثبت سفارش (قبل از پرداخت) |
| `RELEASE` | 0 | − | لغو/انقضا/شکست پرداخت |
| `SALE` | − | − | پرداخت موفق (Reservation → مصرف) |
| `RETURN` | + | 0 | بازگشت کالا (سالم) |
| `ADJUSTMENT` | ± | 0 | شمارش انبار/خرابی (Admin، با دلیل) |

## 11.2 زمان رزرو

رزرو در **ثبت سفارش** (دکمهٔ «پرداخت»)، نه در «افزودن به سبد». TTL = `payment_timeout_minutes` (پیش‌فرض ۲۰–۳۰ دقیقه، قابل تنظیم). 🔹 رزرو در سبد: موجودی را با سبدهای رهاشده قفل می‌کند و برای MVP مضر است.
در **نمایش** سبد/چک‌اوت، موجودی فقط **اعتبارسنجی** می‌شود (بدون رزرو).

## 11.3 الگوریتم Reserve (Race‑safe)

دو روش معتبر:

| روش | شرح | انتخاب |
|---|---|---|
| **A. Update شرطی اتمیک** | `UPDATE inventory SET reserved = reserved + :q WHERE variant_id=:v AND (on_hand - reserved) >= :q` → اگر ۰ ردیف: `OutOfStock` | ✅ برای MVP: ساده، بدون Deadlock، Lock کوتاه |
| B. `select_for_update` | قفل ردیف → چک در Python → Update | زمانی که منطق پیچیده‌تر (Backorder، قوانین چندمرحله‌ای) داریم |

```text
reserve(order, lines):
  with atomic():
     for line in sorted(lines, key=variant_id):          # ترتیب ثابت ⇒ بدون Deadlock
         rows = InventoryItem.filter(variant=line.v, on_hand - reserved >= line.q).update(reserved = F('reserved') + line.q)
         if rows == 0: raise OutOfStock(variant)         # کل تراکنش Rollback
         StockReservation(order, variant, q, ACTIVE, expires_at)    # Unique(order, variant)
         InventoryTransaction(RESERVATION, ref=('order', order.id))  # Unique ⇒ Idempotent
```
- **CHECK در DB** (`reserved <= on_hand`, `>= 0`) آخرین خط دفاع است.
- **Release/Consume** نیز Idempotent‌اند (Reservation در حالت پایانی ⇒ Skip).
- **انقضا:** Celery Beat هر دقیقه `StockReservation.status=ACTIVE AND expires_at < now` را Release می‌کند (و سفارش `AWAITING_PAYMENT` متناظر را لغو).

## 11.4 ماتریس Concurrency (بخش 34 درخواست شما)

| سناریو | مکانیزم |
|---|---|
| دو کاربر هم‌زمان آخرین کالا را بخرند | Update شرطی اتمیک (یا `select_for_update`) + CHECK ⇒ دقیقاً یکی موفق؛ دیگری `OutOfStock` با پیام فارسی |
| Gateway دوبار Callback بفرستد | قفل ردیف `PaymentAttempt` + وضعیت پایانی + Unique(`CHARGE`,`SUCCEEDED`) |
| کاربر چندبار «پرداخت» بزند | Partial Unique یک‑Attempt‑فعال؛ `checkout_token` Unique برای ثبت سفارش |
| دو Worker یک سفارش را پردازش کنند | `select_for_update(order)` در `OrderService.transition` + جدول انتقال مجاز |
| دو درخواست هم‌زمان استفادهٔ آخرین سهمیهٔ کوپن | `select_for_update(coupon)` هنگام شمارش + Unique(`coupon`,`order`) |
| Merge هم‌زمان سبد (دو تب Login) | قفل `Cart` + Merge Idempotent |
| دو Admin هم‌زمان موجودی را تغییر دهند | `ADJUSTMENT` همیشه `F()` Delta (نه مقدار مطلق) + Ledger |
| Celery تسک را دوبار اجرا کند (`acks_late`) | همهٔ Taskها Idempotent (کلیدهای Unique، چک وضعیت) |

---

# بخش 12 — Shipping Architecture

## 12.1 Abstraction

```python
# integrations/shipping/base.py
class ShippingProvider(ABC):
    code: str
    capabilities: ShippingCapabilities       # live_quote, create_shipment_api, tracking_api, cod
    def quote(self, origin, destination, parcel: Parcel) -> list[ShippingQuote]: ...      # اختیاری
    def create_shipment(self, shipment_payload) -> ProviderShipment: ...                  # اختیاری
    def track(self, tracking_code: str) -> list[TrackingEvent]: ...                       # اختیاری
    def cancel(self, provider_ref: str) -> bool: ...                                      # اختیاری
```
Providerها: `post.py` (پست)، `tipax.py`، `courier.py` (پیک شهری)، `manual.py` ⚠️`[V7]`.

## 12.2 رویکرد مرحله‌ای (Overengineering Guard)

| مرحله | رفتار |
|---|---|
| **MVP** ✅ | **نرخ Static** در DB (`ShippingRate`: روش × منطقه (استان/شهر) × بازهٔ وزن + آستانهٔ ارسال رایگان) + **ثبت دستی کد رهگیری** در Admin (Provider = `manual`). هیچ API خارجی لازم نیست؛ همان Interface رعایت می‌شود |
| بعد | اتصال API (Quote زنده/ایجاد مرسوله/رهگیری خودکار) Adapter به Adapter |

**محاسبه:** `ShippingService.quote(address, lines)` → وزن کل = Σ `weight_g × qty` (+ وزن بسته‌بندی ثابت) → انتخاب `ShippingRate` منطبق → `price_rial` (۰ اگر مجموع سفارش ≥ `free_over_rial`). پیک شهری فقط برای شهرهای فعال (مثلاً تهران). خروجی چند «گزینهٔ ارسال» با ETA برای انتخاب در Checkout. `Order.shipping_rial` در لحظهٔ ثبت **Snapshot** می‌شود.

## 12.3 Shipment
`Shipment` پس از `PACKED` ساخته می‌شود؛ `tracking_code` ← `SHIPPED` + Event + SMS. جدول `ShipmentItem` اجازهٔ ارسال چندقسمتی را در Schema می‌دهد؛ **MVP: یک Shipment برای هر Order**. Task Celery برای Sync وضعیت رهگیری (وقتی Provider API دارد).

## 12.4 Address ایران
`Province/City` جدا و Select وابسته (HTMX: انتخاب استان → بارگذاری شهرها)، `postal_code` ده‌رقمی (اعتبارسنجی فرمت؛ قوانین دقیق‌تر ⚠️`[V20]`)، `plaque`, `unit`, `receiver_name`, `receiver_phone` (پیش‌فرض موبایل کاربر؛ قابل‌تغییر برای هدیه)، `address_line`. مختصات اختیاری (نقشه ⚠️`[V16]`). در Checkout آدرس Snapshot روی Order کپی می‌شود.

---

# بخش 13 — SEO فارسی

## 13.1 ساختار URL

| صفحه | الگو | نمونه | یادداشت |
|---|---|---|---|
| خانه | `/` | | |
| دسته | `/category/<path-slug>/` | `/category/قاب-موبایل/قاب-آیفون/` | اسلاگ یونیکد فارسی (خوانا در نتایج و Breadcrumb) |
| محصول | `/product/<id>/<slug>/` | `/product/1234/قاب-سیلیکونی-آیفون-15/` | **شناسهٔ عددی مرجع است**؛ اگر `slug` متفاوت بود ⇒ 301 به Slug درست (تغییر عنوان، لینک را نمی‌شکند) |
| برند | `/brand/<slug>/` | | Landing برای SEO |
| مدل گوشی | `/device/<slug>/` | `/device/iphone-15-pro/` | Landing «لوازم جانبی iPhone 15 Pro» ← پرارزش برای جستجوی خرید |
| جستجو | `/search/?q=` | | `noindex,follow` |
| سبد/چک‌اوت/حساب | `/cart/`, `/checkout/`, `/account/…` | | `noindex` + `Disallow` |
| CMS | `/about/`, `/faq/`, `/privacy/`, … | | |

> 🔹 اسلاگ ASCII (انگلیسی) ساده‌تر برای اشتراک‌گذاری است ولی نیازمند نگهداری ترجمه. ✅ فارسی + شناسه (ID‑first) بهترین توازن «SEO فارسی بدون شکستن لینک‌ها» است. اسلاگ با `slugify(allow_unicode=True)` و نرمال‌سازی ی/ک.

## 13.2 Meta و Open Graph
- هر `Product/Category/Brand/Page` فیلدهای `seo_title`, `seo_description`, `seo_noindex`, `canonical_override` دارد؛ در نبود مقدار، **قالب پیش‌فرض** (مثلاً «خرید {title} | قیمت {x} تومان | {site}») ساخته می‌شود؛ طول عنوان ≤ ~۶۰ و توضیح ≤ ~۱۶۰ کاراکتر (Admin هشدار می‌دهد).
- `<html lang="fa" dir="rtl">`, `og:locale="fa_IR"`, `og:type=product/website`, `og:image` (Rendition ۱۲۰۰×۶۳۰)، `twitter:card`.
- **Canonical:** صفحهٔ دسته با پارامترهای فیلتر/مرتب‌سازی ⇒ Canonical به نسخهٔ بدون پارامتر؛ ترکیب‌های فیلتر عمیق و `?sort=` ⇒ `noindex,follow`؛ فیلترهای ارزشمند (برند/مدل گوشی) صفحهٔ Landing مستقل دارند (`/brand/…`, `/device/…`). صفحات Pagination Canonical به خودشان (`rel=prev/next` منسوخ است).

## 13.3 Sitemap و Robots
- `django.contrib.sitemaps` به‌صورت **Sitemap Index** (محصولات، دسته‌ها، برندها، مدل‌ها، CMS) با حداکثر ۵۰هزار URL در هر فایل؛ `lastmod` میلادی (ISO)؛ محصولات غیرفعال/ناموجود دائمی حذف یا 410.
- `robots.txt` از Template: Allow همه؛ Disallow: `/admin…/`, `/cart/`, `/checkout/`, `/account/`, `/search/`, `/api/`, `*?sort=`, `*?page=…&filter…`؛ آدرس Sitemap.

## 13.4 Structured Data (JSON‑LD، Partial Template)
| نوع | جایگاه | نکات |
|---|---|---|
| `Organization` + `WebSite` + `SearchAction` | همهٔ صفحات/خانه | `target = /search/?q={search_term_string}` |
| `BreadcrumbList` | همهٔ صفحات دارای Breadcrumb | از همان Breadcrumb Component |
| `Product` + `Offer` | صفحهٔ محصول | `price` به **ریال** با `priceCurrency="IRR"` (کد ISO 4217؛ «تومان» ISO نیست)، `availability` (InStock/OutOfStock)، `sku`, `brand`, `image`؛ `AggregateRating/Review` **فقط** با نظرات واقعی تأییدشده (جعل = ریسک جریمهٔ Google) |
| `ItemList` | صفحات دسته (اختیاری) | |

## 13.5 فنی/Performance (اثر مستقیم روی SEO)
تصاویر `webp` با `width/height` صریح (جلوگیری از CLS) و `loading="lazy"` (به‌جز LCP)، فونت `woff2` Self‑host با `font-display: swap`، Gzip/Brotli، Cache‑Control طولانی برای Static هش‌دار، HTML پاسخ‌های بی‌حالت (Anonymous) با Fragment Cache، حذف AOS/CSS/JS استفاده‌نشده. هدف: LCP < 2.5s روی موبایل ایران (اینترنت همراه). Google Search Console/Bing و Yandex؛ ابزارهای Analytics داخلی/خودمیزبان ممکن است لازم باشد (وابستگی به سرویس‌های خارجی اختیاری) ⚠️`[V17]`.

---

# بخش 14 — Security Architecture

## 14.1 ماتریس کنترل‌ها

| حوزه | کنترل |
|---|---|
| **CSRF** | `CsrfViewMiddleware`؛ HTMX با هدر `X-CSRFToken` (از کوکی/`hx-headers`)؛ فقط Callback درگاه `csrf_exempt` (و جایگزین: شناسایی با authority + Verify سمت‌سرور) |
| **XSS** | Auto‑escape قالب‌ها؛ محتوای HTML (CMS/توضیحات محصول) فقط از Admin و **Sanitize با `nh3`** هنگام ذخیره؛ `|safe` فقط روی خروجی Sanitize‌شده؛ نظرات کاربران: Plain‑text؛ CSP |
| **CSP** | `django-csp` ⚠️`[V13]`: `default-src 'self'`; `script-src 'self' 'nonce-…'` (قالب اسکریپت Inline اجرایی ندارد ✔)؛ `style-src 'self' 'unsafe-inline'` تا زمانی که `style=` Inline قالب حذف شود ⚠️`[V24]`؛ `img-src 'self' data: <media/CDN>`؛ `frame-ancestors 'none'`؛ `form-action 'self' <آدرس درگاه‌ها>` (چون POST به درگاه) ؛ ابتدا **Report‑Only** |
| **SQL Injection** | فقط ORM/Parameterized؛ ممنوعیت `raw()`/f‑string در SQL (Lint)؛ Search از `to_tsquery` با ورودی پاک‌سازی‌شده (`plainto/websearch` یا Escape توکن‌ها) |
| **Session/Cookie** | `SESSION_COOKIE_SECURE/HTTPONLY=True`, `SameSite=Lax` (به‌دلیل بازگشت از درگاه)، `CSRF_COOKIE_SECURE`, `cycle_key` بعد از Login، انقضای مطلق ۳۰ روز / Idle طولانی برای مهمان؛ Session Staff کوتاه‌تر |
| **HTTPS/HSTS** | `SECURE_SSL_REDIRECT`, `SECURE_PROXY_SSL_HEADER`, HSTS (شروع ۱ روز → ۶ ماه → `preload` فقط پس از اطمینان)؛ TLS 1.2/1.3 |
| **هدرها** | `X-Content-Type-Options`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy`, `Cross-Origin-Opener-Policy` |
| **CORS** | `django-cors-headers` فقط برای `/api/` و Originهای صریح؛ پیش‌فرض بسته |
| **Rate limiting** | لایهٔ ۱ Nginx `limit_req` (IP، درشت)؛ لایهٔ ۲ اپ (Redis): OTP، Login رمز، Contact، Search/Autocomplete، Add‑to‑cart، Coupon (جلوگیری از Brute‑force کد تخفیف)، API (DRF Throttle) |
| **Brute force** | Login رمز: Throttle به‌ازای phone+IP با Backoff؛ قفل موقت؛ پاسخ یکسان |
| **Admin** | آدرس غیرپیش‌فرض (`ADMIN_URL_PREFIX` از Env)، 2FA (TOTP) ⚠️`[V13]`، فقط Staff، (اختیاری) IP Allowlist/VPN در Nginx، Session کوتاه، لاگ همهٔ تغییرات (`LogEntry` + History)، مدل‌های مالی (`Transaction`, `OrderStatusHistory`) **Read‑only** |
| **Permissions** | Groupها: `Catalog Manager`, `Content Editor`, `Order Operator`, `Finance`, `Support`, `Superadmin`. Refund/ثبت دستی پرداخت فقط `Finance`. Object‑level برای API/Account: کاربر فقط سفارش/آدرس خودش (`get_object_or_404(user=request.user)`، **IDOR**: شناسهٔ عمومی غیرقابل‌حدس) |
| **Upload** | بخش 14.2 |
| **Secrets** | Env/Docker secrets؛ هرگز در Git؛ `.env` با مجوز 600؛ چرخش دوره‌ای؛ Pepper OTP و `SECRET_KEY` جدا؛ اسکن Git برای Secret (pre‑commit: `gitleaks`/`detect-secrets`) |
| **Dependency** | `pip-audit`/`safety` در CI، Pin کامل نسخه (`requirements/*.txt` با Hash)، Dependabot‑مشابه (در صورت نبود GitHub: Renovate/Script دوره‌ای) ⚠️`[V9]` |
| **PII/حریم خصوصی** | حداقل‌سازی داده؛ شمارهٔ موبایل در Log ماسک؛ دسترسی Support به تلفن/آدرس Audit می‌شود؛ سیاست نگهداری/حذف (OTP > ۷ روز پاک، ContactMessage قدیمی…) ⚠️`[V12]` |
| **Business Logic** | محدودیت تعداد/مبلغ، اعتبارسنجی Server‑side همهٔ مبالغ، عدم اعتماد به فیلد پنهان؛ جلوگیری از Price Tampering (قیمت هرگز از کلاینت نمی‌آید)؛ Enumeration کوپن/سفارش |
| **Clickjacking** | `X-Frame-Options: DENY` / `frame-ancestors` |
| **Open Redirect** | پارامتر `next=` با `url_has_allowed_host_and_scheme` |

## 14.2 Upload تصویر
Allowlist پسوند/MIME + **بررسی Magic Bytes** و `Pillow.verify()`؛ سقف حجم (مثلاً ۵MB) و ابعاد (decompression‑bomb: `MAX_IMAGE_PIXELS`)؛ **Re‑encode** به WebP (حذف EXIF/متادیتا/Payload پنهان)؛ نام فایل تصادفی (UUID)؛ بدون اجرای هرگز (Nginx برای `/media/` فقط Static، `autoindex off`، `add_header Content-Disposition`/ `X-Content-Type-Options: nosniff`)؛ SVG آپلود **ممنوع** (یا Sanitize)؛ پردازش در Celery با Resource limit.

## 14.3 Checklist Django Deploy
`manage.py check --deploy` در CI باید پاک باشد؛ `DEBUG=False`, `ALLOWED_HOSTS` صریح، `CSRF_TRUSTED_ORIGINS`، `SECURE_*`، Admin جدا، پاک‌سازی Stack‑trace در 500 (Sentry/GlitchTip داخلی)، `handler403/404/429/500` سفارشی.

---

# بخش 15 — Infrastructure و Deployment در ایران

## 15.1 ملاحظات ویژهٔ محیط ایران (باید با میزبان انتخابی راستی‌آزمایی شود)

| موضوع | اثر طراحی |
|---|---|
| دسترسی از داخل ایران به Registryهای خارجی (Docker Hub، PyPI، npm، GitHub، apt) ممکن است محدود/ناپایدار باشد ⚠️`[V9]` | **Build را خارج از سرور تولید** (CI/لپ‌تاپ) یا از Mirror داخلی؛ Image نهایی را به **Registry خصوصی** (خودمیزبان مثلاً Harbor/`registry:2` یا Registry میزبان) Push کنید و روی سرور فقط `docker pull` از همان؛ Wheelهای Python را Vendor/Cache کنید؛ هیچ `pip install` از اینترنت در زمان Deploy |
| سرویس‌های SaaS خارجی (Sentry.io، Google Fonts/Analytics/reCAPTCHA/Maps، CDNهای خارجی، FCM) | وابستگی اجباری ندارند؛ جایگزین Self‑host (GlitchTip/Sentry، Prometheus/Grafana، فونت محلی، Captcha خودمیزبان، نقشهٔ داخلی) ⚠️`[V15][V16][V17]` |
| ارتباط با PSP/SMS/Shipping داخلی | Outbound از DC ایران؛ IP ثابت سرور برای Whitelist در پنل برخی سرویس‌ها لازم است ⚠️`[V2][V5]` |
| DDoS/WAF | بسیاری از میزبان‌ها سرویس دارند ⚠️`[V9]`؛ حداقل: Nginx `limit_req/limit_conn`, `fail2ban`, محدودسازی پورت‌ها |
| ایمیل | تحویل‌پذیری SMTP از ایران ⚠️`[V22]`؛ SMS کانال اصلی، ایمیل ثانویه |
| زمان | NTP داخلی، `tzdata` به‌روز ⚠️`[V19]` |

## 15.2 معماری استقرار

**MVP (Single Node — همه روی یک VPS، Docker Compose):**
```text
 Internet ─► Nginx ─► Gunicorn/Django ─► PostgreSQL (روی دیسک جدا/Volume)
                          │              Redis (یک نمونه، volatile-lru + AOF)
                          └► Celery worker + beat
 Backup: pg_dump شبانه + rsync/restic به Off-site       Media: Volume/MinIO
```
**Production (رشد):**
```text
            ┌── Nginx/LB (HA اختیاری، keepalived) ──┐
            ▼                                        ▼
       App node 1 (web)                         App node 2 (web)      ← Stateless
            └───────────────┬────────────────────────┘
        ┌───────────────────┼────────────────────────────┐
        ▼                   ▼                            ▼
  PostgreSQL primary ─► replica (Streaming)     Redis cache  +  Redis queue/state (AOF)
   (pgBackRest/WAL‑G → Off‑site)                 (دو نمونهٔ جدا)
        Worker node(s) (Celery) + Beat (یک نمونه)     MinIO / Iranian Object Storage (+CDN)
        Monitoring node (Prometheus/Grafana/Loki/GlitchTip)
```
اپ **Stateless** است (Session در Redis/DB، Media در Storage مشترک) ⇒ افزودن گره وب بدون تغییر کد. Celery Beat **فقط یک** نمونه.

## 15.3 منابع پیشنهادی (نقطهٔ شروع تخمینی؛ با Load‑test و ترافیک واقعی اصلاح شود)

| مؤلفه | MVP (تا ~۵–۱۰ هزار بازدید/روز) | Production (~۵۰–۲۰۰ هزار بازدید/روز) |
|---|---|---|
| CPU | ۴ vCPU کل | Web: 2×(۴ vCPU)، DB: ۸ vCPU، Worker: ۴ vCPU |
| RAM | ۸ GB کل (Postgres ~۲–۳ GB، Redis ~۰.۵–۱ GB، Django/Gunicorn ~۲ GB، Celery ~۱ GB) | Web: ۸ GB هرکدام؛ DB: ۱۶–۳۲ GB؛ Redis: ۲–۴ GB؛ Worker: ۸ GB |
| SSD/NVMe | ۸۰–۱۰۰ GB (OS+Docker 30، DB 20–30، رشد) | DB: ۲۰۰–۵۰۰ GB NVMe (+WAL جدا)؛ Web: ۴۰ GB |
| PostgreSQL Storage | ~۵–۲۰ GB سال اول (بدون Media) | ۵۰–۲۰۰ GB + WAL archive |
| Media | ۲۰–۵۰ GB (Local Volume) | ۲۰۰ GB+ Object Storage + CDN |
| Bandwidth | ۱–۳ TB/ماه (تصاویر غالب‌اند؛ CDN/Cache بار را کم می‌کند) | ۱۰ TB+/ماه یا ترافیک‌ نامحدود/CDN |
| Backup Storage | ≥ ۳× حجم DB فشرده + Media (نسخهٔ Off‑site جدا) | ≥ ۵× (WAL + Base + Media versions) |
| سرویس‌ها | ۱ VPS | ۴–۶ سرور/VM (web×2, db, db‑replica, worker, monitoring) |

## 15.4 Hosting‑agnostic
هیچ وابستگی به API یک میزبان خاص نیست: Docker + Compose + Nginx + Postgres روی هر VPS/اختصاصی/Cloud ایرانی اجراشدنی است. تنها لایه‌های جایگزین‌پذیر: Storage (S3‑compat)، SMTP، DNS، Registry، Object‑Storage ⚠️`[V8][V9]`.

## 15.5 دامنه و SSL

| موضوع | پیشنهاد |
|---|---|
| دامنهٔ اصلی | **`.ir`** (اعتماد کاربر ایرانی و معمولاً ملزومات اینماد/PSP) ⚠️`[V11]` + دامنهٔ بین‌المللی به‌عنوان Alias/Redirect |
| Canonical | یک Host واحد (مثلاً `https://shop.ir`)؛ بقیه 301 (از جمله `www` یا دامنهٔ بین‌المللی) برای جلوگیری از Duplicate Content |
| گواهی TLS | Let's Encrypt (ACME با `certbot`/`acme.sh`) به شرط دسترسی ACME از DC و پشتیبانی برای TLD؛ در غیر این‌صورت CA تجاری/جایگزین ⚠️`[V10]` |
| Nginx | SSL Termination، TLS 1.2+/1.3، Cipher مدرن، HTTP/2، تمدید خودکار + Reload بدون Downtime، Redirect 80→443، HSTS پس از تثبیت |
| DNS | TTL پایین قبل از Cutover؛ NS داخلی/بین‌المللی با اتکا به یک ارائه‌دهنده نباشد؛ بررسی CDN/Proxy خارجی از نظر دسترسی/تأخیر در ایران ⚠️`[V9]` |
| ایمیل دامنه | SPF/DKIM/DMARC برای ایمیل‌های تراکنشی ⚠️`[V22]` |

## 15.6 CI/CD (ساده)
`git push` → CI (GitLab CI/Gitea Actions/GitHub Actions ⚠️`[V9]`: Lint، Test، `check --deploy`، Security scan) → Build Image (Tag = commit SHA) → Push به Registry خصوصی → Deploy: `docker compose pull && docker compose up -d` با Healthcheck + اجرای `migrate` به‌صورت One‑shot **قبل** از جایگزینی `web` (مهاجرت‌ها Backward‑compatible: Expand → Migrate → Contract) → Smoke Test → Rollback = Tag قبلی.

---

# بخش 16 — Docker Architecture

## 16.1 Dockerfile (Multi‑stage — طرح)
1. **builder:** `python:<3.x>-slim` (نسخه ⚠️`[V1]`)، نصب Build‑deps، ساخت Wheelها از `requirements/production.txt` (با Hash).
2. **runtime:** `python:<3.x>-slim`، فقط Runtime libs (`libpq5`, `libjpeg`, `libwebp`)، نصب Wheelها، کپی کد، کاربر **non‑root**، `PYTHONDONTWRITEBYTECODE=1`, `PYTHONUNBUFFERED=1`، `collectstatic` در زمان Build، `HEALTHCHECK`، `ENTRYPOINT` برای Wait‑for‑DB (اختیاری).
3. یک Image واحد برای `web`, `worker`, `beat`, `migrate` (فقط `command` متفاوت) ⇒ یکنواختی نسخه.

## 16.2 سرویس‌های Compose

| سرویس | Image | Command | Port | Volume | یادداشت |
|---|---|---|---|---|---|
| `nginx` | `nginx:stable‑alpine` | — | **80/443** (تنها پورت منتشرشده) | `static:ro`, `media:ro`, `certs`, `conf` | TLS، Static/Media، `limit_req`، Gzip/Brotli |
| `web` | App image | `gunicorn config.wsgi -w N -k gthread --threads 4 --timeout 30 --max-requests 1000 --max-requests-jitter 100` | داخلی 8000 | `media` (rw اگر Local) | `N≈2×CPU+1`؛ Healthcheck `/healthz/` |
| `worker` | App image | `celery -A config worker -Q default,otp,payments,images -c 4 --max-tasks-per-child=200 --without-gossip` | — | `media` | OTP صف مجزا (اولویت)؛ جداسازی Worker `images` در Production |
| `beat` | App image | `celery -A config beat` | — | — | **یک نمونه** |
| `migrate` | App image | `python manage.py migrate --noinput` | — | — | One‑shot (`restart: "no"`) قبل از `web` |
| `postgres` | `postgres:<ver>` ⚠️`[V1]` | — | **منتشر نمی‌شود** | `pgdata` (دیسک جدا)، `wal-archive` | `shared_buffers`≈25٪ RAM؛ `pg_trgm` |
| `redis` | `redis:<ver>` ⚠️`[V1]` | `--appendonly yes --maxmemory-policy volatile-lru` (MVP) | — | `redisdata` | Production: دو نمونه: Cache (`allkeys-lru`، بدون AOF) و Queue/State (`noeviction`+AOF) |
| `minio` (اختیاری) | `minio/minio` | `server /data` | داخلی | `minio-data` | وقتی Storage خودمیزبان |
| `backup` | App/`pgbackrest` | Cron/Beat | — | `backup` | بخش 18 |
| `prometheus/grafana/loki/node‑exporter` (Profile `monitoring`) | — | — | داخلی/پشت Nginx با Auth | | بخش 19 |
| `certbot` | `certbot/certbot` | تمدید دوره‌ای | — | `certs` | یا `acme.sh` روی میزبان |

**شبکه‌ها:** `edge` (nginx↔web) و `internal` (web/worker/beat↔postgres/redis/minio) با `internal: true`؛ Postgres/Redis هرگز روی `0.0.0.0` منتشر نمی‌شوند. **Limitها:** `mem_limit`, `cpus`, `restart: unless-stopped`، `logging: json-file` با `max-size/max-file`، `healthcheck` برای همهٔ سرویس‌ها و `depends_on: condition: service_healthy`.

## 16.3 اسکلت Compose (برای نمایش ساختار)

```yaml
# docker/compose.prod.yml  (طرح، نه فایل نهایی)
name: niceshop
x-app: &app
  image: registry.example.ir/niceshop/app:${APP_TAG}
  env_file: [.env]                 # Secretها؛ در Git نیست
  depends_on: { postgres: { condition: service_healthy }, redis: { condition: service_healthy } }
  networks: [internal]
services:
  nginx:   { image: nginx:stable-alpine, ports: ["80:80","443:443"], networks: [edge], depends_on: [web] }
  web:     { <<: *app, command: gunicorn config.wsgi:application -w 5 -k gthread --threads 4, networks: [edge, internal] }
  worker:  { <<: *app, command: celery -A config worker -Q default,otp,payments,images }
  beat:    { <<: *app, command: celery -A config beat }
  migrate: { <<: *app, command: python manage.py migrate --noinput, restart: "no" }
  postgres:{ image: postgres:XX, volumes: [pgdata:/var/lib/postgresql/data], networks: [internal] }
  redis:   { image: redis:X, command: redis-server --appendonly yes --maxmemory-policy volatile-lru, networks: [internal] }
networks: { edge: {}, internal: { internal: true } }
volumes:  { pgdata: {}, redisdata: {}, static: {}, media: {} }
```

## 16.4 Static/Media
`collectstatic` با `ManifestStaticFilesStorage` (نام فایل هش‌دار ⇒ Cache طولانی `immutable`)؛ در Build داخل Image، هنگام Deploy به Volume مشترک با Nginx کپی. Media: بخش 15/18 و ADR‑010 (`STORAGES["default"]` قابل‌تعویض Local ⇄ S3).

---

# بخش 17 — Environment Variables

> همه از Env خوانده می‌شوند (کتابخانه: `django-environ` یا `pydantic-settings`). فایل `.env.example` در Git (بدون مقدار حساس)، `.env` واقعی خارج از Git.

| گروه | متغیر | Secret؟ | توضیح |
|---|---|:-:|---|
| Core | `DJANGO_SETTINGS_MODULE` | – | `config.settings.production` |
| | `SECRET_KEY` | ✔ | حداقل ۵۰ کاراکتر تصادفی |
| | `DEBUG` | – | `False` در Production |
| | `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `SITE_URL` | – | |
| | `ADMIN_URL_PREFIX` | ✔(نیمه) | مسیر Admin |
| | `TIME_ZONE` (`Asia/Tehran`), `LANGUAGE_CODE` (`fa-ir`) | – | |
| DB | `DATABASE_URL` | ✔ | `postgres://user:pass@postgres:5432/niceshop` |
| | `DB_CONN_MAX_AGE`, `DB_POOL_*` | – | |
| Redis | `REDIS_CACHE_URL`, `REDIS_QUEUE_URL` | ✔ | DBهای جدا |
| | `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` | ✔ | |
| Security | `SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` | – | |
| | `CSP_REPORT_ONLY`, `CSP_REPORT_URI` | – | |
| | `ADMIN_IP_ALLOWLIST` | – | اختیاری |
| Payment | `PAYMENT_GATEWAY` (پیش‌فرض)، `PAYMENT_ENABLED_GATEWAYS` | – | |
| | `ZARINPAL_MERCHANT_ID`, `ZARINPAL_SANDBOX` | ✔ | ⚠️`[V2]` |
| | `IDPAY_API_KEY`, `IDPAY_SANDBOX` | ✔ | ⚠️`[V3]` |
| | `PAYMENT_CALLBACK_BASE_URL` | – | |
| SMS | `SMS_PROVIDER`, `SMS_FALLBACK_PROVIDER` | – | |
| | `SMS_API_KEY` یا `KAVENEGAR_API_KEY`, `SMS_IR_API_KEY`, `FARAZSMS_*`, `SMS_SENDER_LINE`, `SMS_OTP_TEMPLATE` | ✔ | ⚠️`[V5]` |
| OTP | `OTP_HMAC_PEPPER` | ✔ | جدا از `SECRET_KEY` |
| | `OTP_TTL_SECONDS`, `OTP_MAX_ATTEMPTS`, `OTP_RESEND_COOLDOWN`, `OTP_SEND_LIMIT_PHONE_HOURLY`, `OTP_SEND_LIMIT_IP_HOURLY`, `OTP_GLOBAL_PER_MINUTE` | – | |
| Order | `ORDER_PAYMENT_TIMEOUT_MINUTES`, `STOCK_RESERVATION_TTL_MINUTES`, `CART_MAX_QTY_PER_ITEM` | – | |
| Shipping | `SHIPPING_PROVIDER_*` (کلیدهای Provider در آینده) | ✔ | ⚠️`[V7]` |
| Email | `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USER`, `EMAIL_PASSWORD`, `EMAIL_USE_TLS`, `DEFAULT_FROM_EMAIL` | ✔ | |
| Storage | `STORAGE_BACKEND` (`local`/`s3`)، `S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET_MEDIA`, `MEDIA_BASE_URL` | ✔ | |
| Observability | `SENTRY_DSN` (اختیاری)، `LOG_LEVEL`, `LOG_FORMAT=json` | ✔(DSN) | |
| Runtime | `WEB_CONCURRENCY`, `GUNICORN_THREADS`, `CELERY_CONCURRENCY` | – | |
| Backup | `BACKUP_ENCRYPTION_KEY` (age/GPG)، `BACKUP_REMOTE_URL`, `BACKUP_REMOTE_KEY` | ✔ | |

---

# بخش 18 — Backup و Disaster Recovery

## 18.1 اهداف (پیشنهاد، با کسب‌وکار نهایی شود)
| | MVP | Production |
|---|---|---|
| RPO (حداکثر از‑دست‌رفتن داده) | ≤ ۲۴ ساعت | ≤ ۵–۱۵ دقیقه (WAL archiving / PITR) |
| RTO (زمان بازگشت) | ≤ ۴–۸ ساعت | ≤ ۱–۲ ساعت |

## 18.2 PostgreSQL
| سطح | روش | زمان‌بندی | Retention پیشنهادی |
|---|---|---|---|
| روزانه | `pg_dump -Fc` (MVP) یا Base backup افزایشی `pgBackRest`/`WAL‑G` | هر شب (خارج از اوج) | ۱۴ روز |
| هفتگی | Full | یک‌شنبه/جمعه | ۸ هفته |
| ماهانه | Full | اول ماه | ۶–۱۲ ماه |
| پیوسته (Production) | **WAL Archiving** (PITR) | مداوم | ۷–۱۴ روز |
| **Off‑site** | کپی رمزنگاری‌شده (`age`/GPG) به **دیتاسنتر/ارائه‌دهندهٔ دوم** (قانون 3‑2‑1) | پس از هر Backup | همان Retention |
اصول: Backup روی همان دیسک/سرور Primary **کافی نیست**؛ کلید رمز در جایی جدا از Backup؛ مانیتورینگ «سن آخرین Backup موفق» با Alert.

## 18.3 Media
Local: `restic`/`rclone`/`rsync` افزایشی به Off‑site، با Versioning/Retention؛ MinIO: Versioning + Replication/`mc mirror`؛ Object Storage ایرانی: قابلیت Versioning/Replication ⚠️`[V8]`. تصاویر Renditionها قابل بازتولیدند؛ **Originalها** اولویت Backup دارند.

## 18.4 Redis
دادهٔ Redis بازسازی‌پذیر است (Cache). Queue/State (AOF) → در Backup روزانه RDB snapshot کافی؛ Session کاربران در `cached_db` به DB هم نوشته می‌شود. Celery Taskهای از‑دست‌رفته توسط Reconcile (پرداخت/موجودی/اعلان) جبران می‌شوند.

## 18.5 Restore Procedure (Runbook)
1. اعلام Incident؛ فعال‌سازی صفحهٔ Maintenance (Nginx) و توقف `web/worker/beat` (جلوگیری از نوشتن هم‌زمان).
2. انتخاب نقطهٔ بازیابی (آخرین Backup سالم یا PITR تا زمان مشخص).
3. بازسازی Postgres روی Volume جدید/سرور جایگزین (`pg_restore` یا `pgbackrest restore --type=time`).
4. بازیابی Media (در صورت نیاز) و Secretها (`.env`) از Vault/Backup جداگانه.
5. اجرای `migrate --check` (باید No‑op باشد)، `manage.py check`.
6. راه‌اندازی `web` → Smoke Test (صفحهٔ اصلی، ورود OTP تستی، سبد، Admin).
7. اجرای **Reconcile**: `reconcile_pending_payments` + تطبیق سفارش‌های `AWAITING_PAYMENT`/`PAID` با گزارش درگاه (به‌خصوص پرداخت‌های بین نقطهٔ بازیابی و Incident) + Reconcile موجودی از Ledger.
8. راه‌اندازی `worker/beat`، رفع Maintenance، Postmortem.

**تمرین:** Restore Drill ماهانه روی محیط جدا و ثبت زمان واقعی RTO؛ Backup‑ی که Restore نشده، Backup محسوب نمی‌شود.

---

# بخش 19 — Logging و Monitoring

## 19.1 Logging
فرمت **JSON ساختاریافته** (stdout کانتینر → Driver `json-file` با Rotation → Loki/Promtail یا فایل + `logrotate`). فیلدهای مشترک: `ts(UTC)`, `level`, `logger`, `request_id`, `user_id`, `ip`, `path`, `duration_ms`. `RequestIDMiddleware` هدر `X-Request-ID` را به Logها و Celery Taskها منتقل می‌کند.

| Logger | محتوا | Retention پیشنهادی | یادداشت |
|---|---|---|---|
| `app` | رویدادهای عمومی | ۳۰ روز | |
| `error` | استثناها/Traceback (+Sentry/GlitchTip) | ۹۰ روز | |
| `access` | Nginx Access (فرمت JSON) | ۳۰–۹۰ روز | نگهداری مطابق الزامات ⚠️`[V12]` |
| `payments` | هر Create/Callback/Verify/Refund | ≥ ۱–۲ سال | بدون Secret/PAN؛ برای اختلاف‌ها |
| `otp` | درخواست/ارسال/Verify/Throttle | ۹۰ روز | بدون کد؛ شماره ماسک |
| `security` | Login Admin، Throttle، CSRF/Callback مشکوک، AMOUNT_MISMATCH، تغییر Permission | ≥ ۱ سال | Alert‌پذیر |
| `orders` | تغییر Status (علاوه بر `OrderStatusHistory`) | ۱ سال | |
| `integrations` | `ProviderCallLog` (DB) | ۹۰–۱۸۰ روز | |

**PII:** هرگز OTP، Token درگاه، کلید API، PAN کامل، رمز عبور در Log.

## 19.2 Monitoring (بدون وابستگی اجباری به سرویس خارجی)
- **Metrics:** `django-prometheus` ⚠️`[V13]`، `celery` exporter، `postgres_exporter`، `redis_exporter`، `node_exporter`، `nginx` metrics، `cAdvisor`؛ **Grafana** (Dashboardهای: درخواست/تأخیر، نرخ خطا، صف Celery، Postgres، Redis، موجودی‌های کم، نرخ موفقیت پرداخت/OTP).
- **Error tracking:** Sentry SaaS ممکن است در دسترس نباشد ⇒ **GlitchTip/Sentry self‑hosted** یا Log‑only ⚠️`[V17]`؛ `SENTRY_DSN` اختیاری.
- **Uptime:** Blackbox exporter + یک Monitor بیرونی (Uptime Kuma خودمیزبان روی سرور دیگر) برای `/healthz/` و صفحهٔ اصلی و Endpoint پرداخت.
- **Health:** `/healthz/` (Liveness) و `/readyz/` (DB+Redis).

**Alertهای کلیدی:** نرخ شکست Verify پرداخت > آستانه؛ `AMOUNT_MISMATCH` (هر وقوع)؛ Attemptهای `VERIFYING` گیرکرده؛ نرخ خطای 5xx؛ عمق صف `otp`/`default`؛ شکست ارسال SMS و Failover؛ سقف هزینهٔ SMS؛ فضای دیسک/WAL؛ تأخیر Replica؛ **سن آخرین Backup**؛ انقضای TLS (<۱۴ روز)؛ ناهمخوانی Ledger موجودی؛ تعداد `needs_review`. کانال هشدار: ایمیل/SMS/پیام‌رسان داخلی؛ دسترسی به پیام‌رسان‌های خارجی ممکن است متغیر باشد ⚠️`[V17]`.

---

# بخش 20 — Testing Strategy

## 20.1 هرم تست

```text
            ▲  E2E (Playwright)            ~5–10%   مسیرهای حیاتی: OTP login → سبد → چک‌اوت → پرداخت (FakeGateway) → سفارش
           ╱ ╲ API / Integration           ~20%     View/DRF با DB واقعی، Celery eager، Adapterها با HTTP Mock
          ╱   ╲ Service / Domain / Model   ~70%     منطق، قیود DB، State machine، قیمت‌گذاری (Pure)
```
ابزار: `pytest` + `pytest-django`، `factory_boy`، `freezegun`، `responses`/`respx` (Mock HTTP)، `pytest-xdist`، `coverage`. DB تست = **PostgreSQL واقعی** (نه SQLite) چون Partial Index/`select_for_update`/FTS/Trigram/CHECK بخشی از طراحی‌اند. Playwright ⚠️`[V23]` (دانلود مرورگر از داخل ایران → Mirror/Cache در CI).

## 20.2 برنامهٔ تست به‌تفکیک حوزه

| حوزه | چه چیزی تست می‌شود | نوع |
|---|---|---|
| **Money/Domain** | هرگز float؛ گرد کردن؛ توزیع تخفیف سفارش بین اقلام (Largest‑remainder)؛ `total = Σ…` | Unit + Property‑based (`hypothesis`) |
| **Model/DB** | همهٔ CHECK/UNIQUE/Partial Unique (مثلاً دو `CHARGE SUCCEEDED` برای یک Payment غیرممکن است) | Model |
| **OTP** | انقضا، حداکثر تلاش، Cooldown، Throttle phone/IP، پاسخ یکسان برای شمارهٔ ناشناخته، Replay، عدم ذخیرهٔ کد خام، فرمت‌های موبایل | Service + API |
| **SMS Adapterها** | Contract Test با Payload ضبط‌شده/Mock؛ Failover Provider | Integration |
| **Cart** | مهمان، کاربر، Merge (جمع/سقف/ناموجود)، Idempotent بودن Merge، قیمت Live | Service |
| **Inventory** | Reserve/Release/Consume؛ Idempotency؛ انقضا؛ **تست هم‌زمانی** (`django_db(transaction=True)` + چند Thread/Process روی آخرین واحد) | Service/Concurrency |
| **Checkout/Order** | ثبت سفارش اتمیک؛ `checkout_token` تکراری؛ تغییر قیمت؛ State machine (همهٔ انتقال‌های مجاز/غیرمجاز) | Service |
| **Payment** | `FakeGateway`: SUCCESS/FAILED/TIMEOUT/CANCEL؛ Callback تکراری؛ Replay؛ مبلغ نامتناسب؛ Late payment؛ Reconcile؛ Refund جزئی/کامل؛ دو Callback هم‌زمان | Service + Concurrency + API |
| **Gateway Adapterها** | Contract Tests با Sandbox رسمی (اگر هست) یا Fixtureهای ضبط‌شده؛ نگاشت خطا؛ واحد ریال/تومان ⚠️`[V2][V3]` | Integration |
| **Shipping** | نرخ‌ها، وزن، آستانهٔ ارسال رایگان، شهرهای فعال | Service |
| **Search** | نرمال‌سازی (ی/ک/ارقام/نیم‌فاصله)، Prefix، Trigram، SKU دقیق، مترادف آیفون⇄iphone | Integration |
| **SEO** | Canonical، `noindex`، Sitemap، JSON‑LD معتبر (`IRR`)، Redirect Slug | Integration |
| **Security** | IDOR (کاربر A سفارش B را نبیند)، CSRF، Rate‑limit، Upload مخرب، XSS در نظر/CMS، هدرها، `check --deploy`، Admin ورود | Security |
| **API** | Versioning، Permission، Throttle، Schema (OpenAPI) | API |
| **Template/RTL** | Snapshot HTML کلیدی؛ بررسی `dir=rtl`، عدم وجود `$`/متن انگلیسی دمو | Template |
| **E2E** | مسیر خرید کامل + Guest→Login Merge + شکست پرداخت + انقضای سفارش (با Freeze زمان) | E2E |

## 20.3 Payment Gateway Mock/Sandbox Architecture

```text
 settings.test:  PAYMENT_GATEWAYS = {"fake": FakeGateway, ...};  SMS_PROVIDER="fake"
 FakeGateway:  برنامه‌پذیر  (gateway.script_next(authority, outcome=SUCCESS|FAILED|PENDING|TIMEOUT, amount=...))
               ← حالت‌های Replay/Amount mismatch/Callback دوباره را بدون شبکه شبیه می‌سازد
 Adapter واقعی:  تست با `responses` روی Payloadهای ضبط‌شده  +  (اختیاری، خارج از CI اصلی) Sandbox واقعی
 Celery:  CELERY_TASK_ALWAYS_EAGER=True  برای تست ساده؛ برای تست on_commit از `django_capture_on_commit_callbacks`
```

## 20.4 CI Gate
Lint (`ruff`)، Type‑check (`mypy` تدریجی روی services/domain)، Test با Coverage: **≥ ۹۰٪ روی `payments/inventory/orders/accounts(OTP)/domain`**، ≥ ۷۵٪ کل؛ `bandit`، `pip-audit`، `makemigrations --check`، `import-linter`، `check --deploy`، Secret‑scan.

---

# بخش 21 — Project Directory

```text
niceshop/
├── config/
│   ├── settings/{base,development,production,test}.py     # Env-driven
│   ├── urls.py   asgi.py   wsgi.py   celery.py
│   └── api_urls.py                                          # /api/v1/ router جمع‌کننده
├── apps/
│   ├── core/            {models, events.py, ratelimit.py, money.py, text.py (normalize_fa), jalali.py,
│   │                     middleware.py, templatetags/(toman,jalali,fa_digits), storage.py, health.py}
│   ├── locations/       {models, fixtures/provinces_cities.json}
│   ├── accounts/        {models, services/(otp.py, auth.py), selectors.py, forms.py, views/, api/, admin.py, templates/accounts/}
│   ├── catalog/         {models/, services.py, selectors.py, search/(backend.py, pg.py, normalize.py), views/, api/, admin.py,
│   │                     sitemaps.py, templatetags/, templates/catalog/}
│   ├── inventory/       {models, services.py, tasks.py (expire/reconcile), admin.py}
│   ├── discounts/       {models, services.py, domain/rules.py, admin.py}
│   ├── cart/            {models, services.py, context_processors.py, views/, api/, templates/cart/}
│   ├── shipping/        {models, services.py, tasks.py, admin.py}
│   ├── orders/          {models, domain/(state_machine.py, pricing.py), services/(checkout.py, orders.py), tasks.py, views/, api/, admin.py, templates/(checkout|orders)/}
│   ├── payments/        {models, services.py, callbacks.py, tasks.py (reconcile), views/, api/, admin.py}
│   ├── reviews/         {models, services.py, views/, api/, admin.py}
│   ├── notifications/   {models, handlers.py, channels/, tasks.py, templates (پیام‌ها)}
│   └── cms/             {models, views/, admin.py, sitemaps.py, templates/cms/}
├── integrations/                      # ← Adapterها، بدون مدل Django
│   ├── payments/  {base.py, registry.py, fake.py, zarinpal.py, idpay.py, nextpay.py}
│   ├── sms/       {base.py, registry.py, fake.py, console.py, kavenegar.py, sms_ir.py, farazsms.py}
│   ├── shipping/  {base.py, registry.py, manual.py, post.py, tipax.py, courier.py}
│   ├── storage/   {local/s3 helpers}
│   └── http.py                         # کلاینت HTTP مشترک: timeout، retry، لاگ ماسک‌شده
├── templates/                          # base, layouts, includes, components, errors   (بخش 2)
├── static/
│   ├── vendor/{bootstrap(rtl), bootstrap-icons, swiper, glightbox, drift-zoom, htmx, purecounter}
│   ├── css/{main.rtl.css, site.css (override ما)}   fonts/(vazirmatn woff2)   img/   js/{ui.js, price-range.js, product-gallery.js, app.js}
├── media/                              # فقط Dev (Production: Volume/MinIO)
├── locale/fa/LC_MESSAGES/              # ترجمهٔ Django (برچسب‌ها/پیام‌ها)
├── tests/{unit, integration, api, concurrency, security, e2e, factories, fakes}
├── requirements/{base,development,production,test}.txt
├── docker/{Dockerfile, compose.dev.yml, compose.prod.yml, nginx/(conf.d, snippets), postgres/, redis/, prometheus/, grafana/, scripts/}
├── docs/{architecture.md, adr/, runbooks/(restore.md, incident-payment.md), onboarding.md}
├── tools/{convert_template.py, rtl_convert.sh, import_provinces.py}
├── .env.example   .gitignore   .pre-commit-config.yaml   pyproject.toml (ruff, mypy, import-linter, pytest)   Makefile
└── manage.py
```

---

# بخش 22 — Development Roadmap

> تخمین‌ها «تقریبی» و برای **یک توسعه‌دهندهٔ تمام‌وقت** با فرض آشنایی با Django‌اند؛ مجموع ≈ ۱۸–۲۶ هفته تا Launch. **Definition of Done هر Phase:** تست‌های همان Phase سبز، Admin مربوطه ساخته، بررسی امنیتی مختصر، Migration Backward‑compatible، به‌روزرسانی `docs/`.
> **تغییر نسبت به فهرست شما:** Admin/Security/Testing «Phase پایانی» نیستند و در هر Phase اجرا می‌شوند؛ Phase‌های 9/11/12 فقط **تکمیل/سخت‌سازی** هستند. هزینهٔ ارسال Static در Phase 5 لازم است (نه Phase 8).

### Phase 1 — Project Foundation (~۱٫۵–۲ هفته)
- **هدف:** اسکلت قابل‌اجرا + Pipeline.
- **Taskها:** Repo/Settings چندمحیطی، Docker Compose Dev (Postgres/Redis)، `core` (BaseModel/Money/Events/RateLimiter/normalize_fa/templatetags)، تبدیل قالب → `base.html`+Layout+Include+Component (RTL، فونت محلی، حذف Google)، CI، pre‑commit، `import-linter`، `locations` + Fixture.
- **Dependency:** —
- **تحویل:** صفحهٔ اصلی استاتیک RTL با Layout نهایی، `docker compose up` کار می‌کند.
- **تست:** Unit (money/normalize)، Smoke، `check`، رندر Template.

### Phase 2 — Authentication (~۲ هفته)
- **Taskها:** `User`، `OTPChallenge`، `OTPService`، `SMSProvider` + `console/fake/یک Provider واقعی`، Rate‑limit، صفحهٔ Login Phone‑first، پروفایل، Address (با Province/City HTMX)، Admin Login امن + 2FA.
- **Dependency:** P1
- **تحویل:** ورود/ثبت‌نام با OTP کامل.
- **تست:** OTP (کامل بخش 20)، Security (Enumeration/Throttle)، API Auth.

### Phase 3 — Catalog (~۳ هفته)
- **Taskها:** Brand/Category(Tree)/Product/Variant/Image/Attribute/Spec/DeviceModel، Pipeline تصویر (Celery)، Selectors، صفحات Home/Category/Product/Search، فیلتر/مرتب‌سازی/Pagination با HTMX، Search PG، Cache درخت دسته/Mega Menu، Admin کامل (Inline Variant/Image، Autocomplete)، Wishlist، ورود دادهٔ اولیه (Import CSV).
- **Dependency:** P1
- **تحویل:** کاتالوگ قابل‌مرور و جستجوپذیر.
- **تست:** Search، Query‑count (`assertNumQueries`)، Model constraints، Template.

### Phase 4 — Cart & Inventory (~۲ هفته)
- **Taskها:** `InventoryItem/Transaction/Reservation` + Service، Admin انبار (ورود کالا/Adjustment)، Cart مهمان/کاربر/Merge، `PricingService` + `PriceRule` (حراج)، صفحهٔ سبد (HTMX).
- **Dependency:** P2، P3
- **تحویل:** سبد صحیح با موجودی/قیمت Live.
- **تست:** Cart، Inventory، **Concurrency**.

### Phase 5 — Checkout (~۲ هفته)
- **Taskها:** `CheckoutService.place_order` (اتمیک)، انتخاب آدرس/ارسال (نرخ Static)، `Coupon` کامل + رزرو/آزادسازی، رزرو موجودی با TTL، `Order/OrderItem/History`، Expire Task، صفحهٔ Checkout (One‑page).
- **Dependency:** P4، `shipping` (مدل‌ها و نرخ Static)
- **تحویل:** ثبت سفارش `AWAITING_PAYMENT` با رزرو.
- **تست:** Checkout، Coupon، Idempotency (`checkout_token`)، انقضا.

### Phase 6 — Payment (~۲–۳ هفته)
- **Taskها:** مدل‌ها/Constraints، Interface + `FakeGateway` + **اولین Adapter واقعی** (مثلاً ZarinPal ⚠️`[V2]`)، `start_payment`، Callback/Verify، Reconcile، Late‑payment، Refund دستی، لاگ پرداخت، صفحهٔ نتیجه، Admin مالی (Read‑only).
- **Dependency:** P5
- **تحویل:** پرداخت موفق/ناموفق/لغو/منقضی با Sandbox.
- **تست:** Payment (کل ماتریس)، Concurrency، Contract Adapter.

### Phase 7 — Order Lifecycle & Notifications (~۲ هفته)
- **Taskها:** State machine کامل، Admin عملیات سفارش (Action‌های وضعیت)، Cancel/Return/Refund Workflow، `notifications` (SMS/Email/In‑app + قالب‌ها)، حساب کاربری: سفارش‌ها/جزئیات.
- **Dependency:** P6
- **تحویل:** چرخهٔ کامل سفارش + اعلان‌ها.
- **تست:** Transition matrix، Notification idempotency، IDOR.

### Phase 8 — Shipping Integration (~۱–۲ هفته؛ اختیاری برای Launch)
- **Taskها:** `Shipment`، ثبت کد رهگیری، Provider Adapters واقعی (در صورت API) ⚠️`[V7]`، Sync رهگیری.
- **Dependency:** P7
- **تحویل:** رهگیری در حساب کاربری.
- **تست:** Shipping، Adapter Contract.

### Phase 9 — Admin Polish, CMS & Reviews (~۲ هفته)
- **Taskها:** CMS (Page/FAQ/Banner/Contact)، Reviews + Moderation، گزارش‌های پایه (فروش، موجودی کم)، Bulk Actions/Export، Dashboard، Jalali Admin، مجوزها/Groupها.
- **Dependency:** P3، P7
- **تحویل:** پنل مدیریت عملیاتی.
- **تست:** Permission، Admin Smoke.

### Phase 10 — SEO (~۱ هفته)
- **Taskها:** Meta/OG/Canonical، Sitemap Index، robots، JSON‑LD، Redirect Slug، Landing برند/مدل، Performance (Lazy، Cache)، Core Web Vitals.
- **Dependency:** P3، P9
- **تحویل:** گزارش Lighthouse/Search Console.
- **تست:** SEO Integration.

### Phase 11 — Security Hardening (~۱–۲ هفته)
- **Taskها:** CSP (Report‑Only→Enforce)، HSTS، حذف `style=` Inline ⚠️`[V24]`، Pen‑test داخلی (OWASP ZAP baseline)، بررسی Rate‑limit، Audit لاگ‌ها/PII، `pip-audit`، بازبینی Permission.
- **Dependency:** همهٔ قبلی
- **تحویل:** گزارش امنیتی + رفع یافته‌ها.
- **تست:** Security Suite.

### Phase 12 — Testing & Stabilization (~۱–۲ هفته)
- **Taskها:** تکمیل E2E، Load‑test (Locust/k6: Checkout/Callback/Search)، Fix، Coverage Gate، Chaos ساده (قطع Redis/Gateway/SMS).
- **Dependency:** P11
- **تحویل:** Release Candidate با معیارهای عملکرد.
- **تست:** E2E، Load، Failure‑injection.

### Phase 13 — Production Deployment (~۱–۲ هفته)
- **Taskها:** انتخاب میزبان/ارتباط ⚠️`[V9]`، Registry خصوصی، Nginx/TLS ⚠️`[V10]`، Compose Prod، Backup+Restore Drill، Monitoring/Alert، Runbookها، Cutover DNS، اینماد/درگاه Production ⚠️`[V11]`، Launch Checklist (پیوست الف).
- **Dependency:** P12 (+ موازی از P8 به بعد برای کار اداری درگاه/اینماد که زمان‌بر است)
- **تحویل:** سایت زنده + Runbook.
- **تست:** Smoke Prod، Restore Drill، تست پرداخت واقعی مبلغ کم.

> **نکتهٔ مسیر بحرانی:** مجوز/درگاه پرداخت/اینماد/خط SMS معمولاً **زمان اداری** می‌برد؛ همین حالا (موازی با Phase 1) شروع شود.

---

# بخش 23 — Recommended Final Architecture

**انتخاب برای شروع توسعه:**

| لایه | انتخاب | چرا |
|---|---|---|
| ساختار | **Django Modular Monolith** — ۱۳ اپ (`core, locations, accounts, catalog, inventory, discounts, cart, shipping, orders, payments, reviews, notifications, cms`) + پکیج `integrations/` | یک Deploy، یک تراکنش DB برای عملیات حیاتی (سفارش/موجودی/پرداخت)، قابل‌تفکیک بعدی |
| Frontend | Django Templates + Bootstrap 5.3 RTL + HTMX + Vanilla JS (قالب NiceShop حفظ و Component‌شده) | بدون SPA؛ SEO عالی؛ کمترین پیچیدگی |
| Backend | Services/Selectors/Domain؛ Events صریح؛ DRF `/api/v1/` برای آینده | Business Logic خارج از View/Model؛ قابل تست |
| داده | PostgreSQL (CHECK/Partial Unique/FTS/Trigram)؛ پول Integer ریال؛ UTC | Integrity پرداخت/سفارش |
| Redis | Cache + Session(`cached_db`) + Rate‑limit + Broker (MVP: یک نمونه `volatile-lru`+AOF؛ Prod: دو نمونه) | سادگی → رشد |
| Async | Celery + Beat (صف‌های `otp/default/payments/images`) | SMS/Reconcile/Release/Images |
| یکپارچگی‌ها | Adapter + Registry برای Payment/SMS/Shipping/Storage + Capability flags | عدم وابستگی به Vendor |
| Search | PostgreSQL FTS(`simple`)+`pg_trgm`+نرمال‌سازی فارسی؛ OpenSearch در آینده | کافی برای MVP، بدون سرویس اضافه |
| استقرار | Docker Compose روی VPS/سرور ایرانی؛ Nginx+Gunicorn؛ Registry خصوصی؛ Prometheus/Grafana self‑hosted | Hosting‑agnostic، مستقل از اینترنت جهانی |
| Storage | MVP: Volume مدیریت‌شده (جدا از Container) پشت `STORAGES` Abstraction → MinIO/S3 ایرانی در رشد | تعویض با تغییر Config |

**دلیل کلی:** کم‌ترین پیچیدگی که الزامات حساس (پول، موجودی، OTP، ایران) را **درست** پوشش دهد؛ هر مرز (Gateway/SMS/Shipping/Search/Storage) پشت Interface است تا رشد یا تعویض Vendor نیازمند بازنویسی Business Logic نباشد. Microservices/Elasticsearch/Kubernetes/CQRS **عمداً** کنار گذاشته شده‌اند و معیار بازنگری در ADRها ثبت شده است.

**ریسک‌های اصلی و کاهش:**
1. وابستگی زمانی به مجوز/درگاه/اینماد/SMS → شروع موازی از Day‑1.
2. ناپایداری شبکهٔ بین‌الملل در Build/Deploy → Registry/Mirror خصوصی.
3. تفاوت واقعی APIهای درگاه/SMS با فرض‌ها → Phase 6 با Sandbox + Capability flags + همهٔ موارد ⚠️.
4. تبدیل RTL قالب (جزئیات ظاهری) → Phase 1 با بازبینی دستی صفحه‌به‌صفحه.
5. Late/lost payment callbacks → Reconcile + `needs_review` + هشدار.

---

# پیوست الف — Checklist راه‌اندازی فروشگاه در ایران

> وضعیت‌ها: **[ ] نیازمند بررسی/اقدام**. هیچ‌یک از موارد حقوقی/مالیاتی در این سند «قطعی» نیست؛ همه باید با وکیل/حسابدار/مرجع رسمی تأیید شود ⚠️`[V11][V12]`.

| # | مورد | توضیح | وضعیت |
|---|---|---|---|
| 1 | دامنه `.ir` (+ بین‌المللی) | ثبت به نام صاحب کسب‌وکار؛ مالکیت برای اینماد/PSP اهمیت دارد | [ ] ⚠️`[V11]` |
| 2 | SSL/TLS | HTTPS اجباری؛ روش صدور بخش 15.5 | [ ] ⚠️`[V10]` |
| 3 | پروانه/مجوز کسب‌وکار و هویت حقوقی/حقیقی | الزامات PSP و اینماد متفاوت است | [ ] ⚠️`[V11][V12]` |
| 4 | **نماد اعتماد الکترونیکی (اینماد)** | معمولاً پیش‌نیاز درگاه پرداخت؛ شرایط/دسته‌بندی کالا/مدارک | [ ] ⚠️`[V11]` |
| 5 | درگاه پرداخت (PSP) | شرایط اتصال، IP/Domain Whitelist، تسویه، کارمزد، Sandbox، قابلیت Refund/Inquiry | [ ] ⚠️`[V2][V3][V4]` |
| 6 | خط/Provider SMS | خط خدماتی/قالب OTP، هزینه، سقف ارسال، ساعات مجاز | [ ] ⚠️`[V5][V6]` |
| 7 | روش‌های ارسال | قرارداد/API پست، تیپاکس، پیک؛ بسته‌بندی؛ بیمه | [ ] ⚠️`[V7]` |
| 8 | احراز هویت موبایل | شمارهٔ موبایل متعلق به کاربر (OTP)؛ سیاست Re‑verify | [ ] |
| 9 | کد پستی/آدرس | اعتبارسنجی؛ ضرورت کد پستی برای ارسال | [ ] ⚠️`[V20]` |
| 10 | فاکتور / صورت‌حساب | قالب فاکتور فروش؛ شماره‌گذاری؛ اطلاعات فروشنده/خریدار | [ ] ⚠️`[V12]` |
| 11 | مالیات بر ارزش افزوده / سامانهٔ مودیان / صدور صورت‌حساب الکترونیکی | ضرورت، نرخ، نحوهٔ نمایش (با/بدون مالیات) | [ ] ⚠️`[V12]` — فیلد `tax_rial` در Schema آماده است |
| 12 | قوانین مرجوعی | شرایط بازگشت کالا، مهلت، هزینهٔ ارسال بازگشت (صفحهٔ Return Policy) | [ ] ⚠️`[V12]` |
| 13 | حریم خصوصی | چه داده‌ای، چرا، تا کی، با چه کسی؛ رضایت؛ نگهداری لاگ‌ها | [ ] ⚠️`[V12]` |
| 14 | شرایط استفاده | قراردادهای کاربر | [ ] ⚠️`[V12]` |
| 15 | الزامات قانونی فروشگاه اینترنتی (تجارت الکترونیکی/حمایت از مصرف‌کننده) | اطلاعات الزامی نمایش در سایت، حق انصراف، ضمانت، اطلاعات تماس | [ ] ⚠️`[V12]` |
| 16 | نمایش اطلاعات تماس/نشانی/ثبت | صفحهٔ تماس و Footer | [ ] |
| 17 | گارانتی/اصالت کالا | سیاست نمایش و ثبت | [ ] ⚠️`[V12]` |
| 18 | کیف پول/اعتبار | **خارج از MVP**: نگهداری وجه کاربر می‌تواند الزامات مالی/مجوزی داشته باشد | [ ] ⚠️`[V12]` |
| 19 | پرداخت در محل (COD) | تصمیم کسب‌وکار؛ ریسک و Workflow متفاوت | [ ] |
| 20 | Backup/DR، Monitoring | بخش‌های 18–19 | [ ] |

---

# پیوست ب — ADRها
فایل جدا: **`NiceShop-ADRs.md`** (ADR‑001 تا ADR‑010).

---

# پیوست ج — Verification Register (موارد باید هنگام پیاده‌سازی راستی‌آزمایی شوند)

| شناسه | موضوع | چه چیزی باید بررسی شود | وابستگی در طراحی |
|---|---|---|---|
| V1 | نسخه‌ها | Python، Django (LTS فعلی)، PostgreSQL، Redis/Valkey، Celery، Nginx — سازگاری با هم و پشتیبانی امنیتی | Dockerfile/Compose/Settings |
| V2 | ZarinPal | نسخهٔ API، Endpointها، **واحد مبلغ (ریال/تومان)**، Sandbox، Inquiry، Refund، Callback (GET/POST)، محدودیت‌ها | Adapter، `capabilities` |
| V3 | IDPay | همان موارد V2 | Adapter |
| V4 | NextPay/سایر PSP و شاپرک | شرایط اتصال، تسویه، IP Whitelist، الزامات فنی | Adapter، Checklist |
| V5 | SMS Providerها (Kavenegar، SMS.ir، FarazSMS) | API فعلی، **قالب/Lookup OTP**، خط، Delivery Report، Rate‑limit، احراز | Adapter OTP |
| V6 | قیمت/محدودیت SMS | هزینه، ساعت مجاز ارسال، سقف، لیست سیاه | سقف‌های Throttle |
| V7 | حمل‌ونقل | وجود/شرایط API پست، تیپاکس، پیک؛ قرارداد؛ Tracking | `ShippingProvider` |
| V8 | Object Storage/CDN ایرانی | سازگاری S3، قیمت، SLA، Versioning، CDN | `STORAGES`، Backup |
| V9 | میزبان/شبکه | منابع، پهنای باند، DDoS/WAF، **دسترسی به Docker Hub/PyPI/npm/GitHub از DC**، Mirrorها، IP ثابت، CI در دسترس | Registry، CI/CD، Sizing |
| V10 | TLS | امکان ACME/Let's Encrypt از DC و برای `.ir`، گزینهٔ CA تجاری/جایگزین | Nginx/Certbot |
| V11 | اینماد/مجوزها/دامنه | الزامات، مدارک، مدت، ارتباط با PSP | Roadmap Phase 13، پیوست الف |
| V12 | حقوقی/مالیاتی/حریم خصوصی | قوانین جاری تجارت الکترونیک، حمایت مصرف‌کننده، فاکتور، VAT/مودیان، نگهداری لاگ/داده، مرجوعی | CMS، Schema `tax_rial`، Retention |
| V13 | کتابخانه‌ها | وضعیت نگهداری/سازگاری: `django-treebeard`/`mptt`, `django-jalali-date`/`jdatetime`/`persiantools`, `django-csp`, `django-otp`, `nh3`, TinyMCE/ویرایشگر، `drf-spectacular`, `simplejwt`, `import-linter`, `django-prometheus` | انتخاب‌های Library |
| V14 | فونت فارسی | مجوز (مثلاً Vazirmatn) و Self‑host | `static/fonts` |
| V15 | Captcha | سرویس قابل‌استفاده در ایران یا خودمیزبان | OTP anti‑bot |
| V16 | نقشه | Provider داخلی، شرایط API (در صورت انتخاب نقشه برای آدرس) | Address lat/lng |
| V17 | Monitoring/Analytics | دسترسی Sentry.io؛ GlitchTip؛ کانال Alert؛ ابزار Analytics | Observability |
| V18 | لایسنس قالب | شرط Credit/حذف لینک BootstrapMade | Footer |
| V19 | Time zone | `tzdata` به‌روز؛ بدون DST در ایران | settings |
| V20 | دادهٔ مرجع | منبع رسمی استان/شهر؛ قواعد دقیق کد پستی/کد ملی | `locations`، Address |
| V21 | Search | کفایت `simple`+`pg_trgm` روی دادهٔ واقعی؛ آستانهٔ رفتن به OpenSearch؛ Analyzer فارسی | `SearchBackend` |
| V22 | ایمیل | SMTP/تحویل‌پذیری از ایران | Notification |
| V23 | E2E tooling | دانلود مرورگر Playwright/Mirror در CI | Testing |
| V24 | CSP و Vendorها | سازگاری CSP با HTMX/Swiper/Drift/GLightbox و `style=` Inline | بخش 14 |
