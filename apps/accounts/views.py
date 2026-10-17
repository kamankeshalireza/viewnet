from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_POST

from apps.core.http import get_client_ip

from .forms import CodeForm, PhoneForm, ProfileForm
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
            # NOTE (Phase 4): read the guest cart BEFORE login() and merge it here.
            login(request, user, backend=BACKEND)  # cycles the session key
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
