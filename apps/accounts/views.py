from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_POST

from apps.core.constants import GUEST_CART_SESSION_KEY
from apps.core.events import UserLoggedIn, publish
from apps.core.http import get_client_ip

from .forms import AddressForm, CodeForm, PhoneForm, ProfileForm
from .models import Address
from .services.addresses import set_default_address
from .services.auth import login_or_register
from .services.otp import request_otp, verify_otp

BACKEND = "django.contrib.auth.backends.ModelBackend"
VERIFY_ERRORS = {
    "invalid": "کد وارد‌شده صحیح نیست.",
    "expired": "کد منقضی شده است. دوباره درخواست کد کنید.",
    "locked": "تعداد تلاش‌های ناموفق زیاد بود. دوباره درخواست کد کنید.",
    "throttled": "تعداد تلاش‌ها زیاد است. کمی بعد دوباره امتحان کنید.",
    "unavailable": "سرویس موقتاً در دسترس نیست. کمی بعد دوباره تلاش کنید.",
}


def _safe_next(request, value) -> str:
    ok = value and url_has_allowed_host_and_scheme(value, allowed_hosts={request.get_host()},
                                                   require_https=request.is_secure())
    return value if ok else "/"


def _notify(request, result):
    """Same wording for known/unknown numbers — nothing here reveals whether an account exists."""
    if result.reason == "sent":
        messages.success(request, "کد تأیید به شمارهٔ شما پیامک شد.")
    elif result.reason == "cooldown":
        messages.info(request, f"کد قبلاً ارسال شده است. {result.retry_after} ثانیهٔ دیگر می‌توانید دوباره درخواست دهید.")
    elif result.reason == "throttled":
        messages.error(request, "تعداد درخواست‌ها زیاد است. کمی بعد دوباره تلاش کنید.")
    else:
        messages.error(request, "سرویس موقتاً در دسترس نیست. کمی بعد دوباره تلاش کنید.")


@require_http_methods(["GET", "POST"])
def login_phone(request):
    nxt = _safe_next(request, request.POST.get("next") or request.GET.get("next"))
    if request.user.is_authenticated:
        return redirect(nxt)
    form = PhoneForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        phone = form.cleaned_data["phone"]
        result = request_otp(phone, get_client_ip(request))
        _notify(request, result)
        if result.reason in ("sent", "cooldown"):
            request.session["otp_phone"] = phone
            request.session["otp_next"] = nxt
            return redirect("accounts:verify")
    return render(request, "accounts/login.html", {"form": form, "next": nxt})


@require_http_methods(["GET", "POST"])
def login_verify(request):
    phone = request.session.get("otp_phone")
    if not phone:
        return redirect("accounts:login")
    form = CodeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        result = verify_otp(phone, form.cleaned_data["code"], get_client_ip(request))
        if result.ok:
            user, created = login_or_register(phone)
            if not user.is_active:
                messages.error(request, "این حساب غیرفعال است.")
                return redirect("accounts:login")
            nxt = _safe_next(request, request.session.get("otp_next"))
            guest_cart = dict(request.session.get(GUEST_CART_SESSION_KEY) or {})  # read BEFORE login() touches the session
            login(request, user, backend=BACKEND)  # cycles the session key
            publish(UserLoggedIn(user_id=user.pk, request=request, guest_cart=guest_cart))  # cart app merges it
            request.session.pop("otp_phone", None)
            request.session.pop("otp_next", None)
            if not user.first_name:
                return redirect(f"{reverse('accounts:profile')}?welcome=1&next={nxt}")
            return redirect(nxt)
        messages.error(request, VERIFY_ERRORS[result.reason])
    return render(request, "accounts/verify.html", {"form": form, "phone": phone})


@require_POST
def login_resend(request):
    phone = request.session.get("otp_phone")
    if not phone:
        return redirect("accounts:login")
    _notify(request, request_otp(phone, get_client_ip(request)))
    return redirect("accounts:verify")


@require_POST
def logout_view(request):
    logout(request)
    return redirect("/")


@login_required
@require_http_methods(["GET", "POST"])
def profile(request):
    form = ProfileForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "اطلاعات شما ذخیره شد.")
        return redirect(_safe_next(request, request.POST.get("next") or request.GET.get("next")) if request.GET.get("welcome") else "accounts:profile")
    return render(request, "accounts/profile.html", {"form": form, "welcome": request.GET.get("welcome")})


# ---- addresses ------------------------------------------------------------------------------------------
def _own_address_or_404(request, pk):
    from django.shortcuts import get_object_or_404

    return get_object_or_404(Address, pk=pk, user=request.user, is_deleted=False)


def _after_address(request, default="accounts:addresses"):
    nxt = request.POST.get("next") or request.GET.get("next") or ""
    ok = nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}, require_https=request.is_secure())
    return redirect(nxt) if ok else redirect(default)


@login_required
def address_list(request):
    addresses = Address.objects.filter(user=request.user, is_deleted=False).select_related("province", "city").order_by("-is_default", "-pk")
    return render(request, "accounts/addresses.html", {"addresses": addresses})


@login_required
@require_http_methods(["GET", "POST"])
def address_edit(request, pk=None):
    instance = _own_address_or_404(request, pk) if pk else None
    initial = {} if instance else {"receiver_name": request.user.get_full_name(), "receiver_phone": request.user.phone}
    form = AddressForm(request.POST or None, instance=instance, initial=initial)
    if request.method == "POST" and form.is_valid():
        address = form.save(commit=False)
        address.user = request.user
        first = not Address.objects.filter(user=request.user, is_deleted=False).exists()
        wants_default = form.cleaned_data.get("is_default") or first
        address.is_default = False  # the service flips exactly one default atomically
        address.save()
        if wants_default:
            set_default_address(address)
        messages.success(request, "نشانی ذخیره شد.")
        return _after_address(request)
    return render(request, "accounts/address_form.html", {"form": form, "address": instance,
                                                          "next": request.GET.get("next") or request.POST.get("next", "")})


@login_required
@require_POST
def address_delete(request, pk):
    address = _own_address_or_404(request, pk)
    address.is_deleted, address.is_default = True, False
    address.save(update_fields=["is_deleted", "is_default", "updated_at"])
    messages.info(request, "نشانی حذف شد.")
    return redirect("accounts:addresses")


@login_required
@require_POST
def address_make_default(request, pk):
    set_default_address(_own_address_or_404(request, pk))
    return redirect("accounts:addresses")


@login_required
def address_cities(request):
    """HTMX: <option> list for the chosen province."""
    from apps.locations.models import City

    pid = request.GET.get("province", "")
    cities = City.objects.filter(is_active=True, province_id=int(pid)) if pid.isdigit() else City.objects.none()
    return render(request, "accounts/_city_options.html", {"cities": cities})
