from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.core.models import TimeStampedModel
from apps.core.text import normalize_phone


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create(self, phone, password, **extra):
        normalized = normalize_phone(phone)
        if not normalized:
            raise ValueError("شمارهٔ موبایل نامعتبر است")
        user = self.model(phone=normalized, **extra)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_user(self, phone, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create(phone, password, **extra)

    def create_superuser(self, phone, password=None, **extra):
        if not password:
            raise ValueError("ادمین باید رمز عبور داشته باشد")
        extra.update(is_staff=True, is_superuser=True)
        return self._create(phone, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    phone = models.CharField("موبایل", max_length=11, unique=True,
                             validators=[RegexValidator(r"^09\d{9}$", "شمارهٔ موبایل نامعتبر است")])
    first_name = models.CharField("نام", max_length=60, blank=True)
    last_name = models.CharField("نام خانوادگی", max_length=80, blank=True)
    email = models.EmailField("ایمیل", blank=True)
    is_active = models.BooleanField("فعال", default=True)
    is_staff = models.BooleanField("دسترسی به پنل", default=False)
    phone_verified_at = models.DateTimeField("زمان تأیید موبایل", null=True, blank=True)
    date_joined = models.DateTimeField("تاریخ عضویت", default=timezone.now)

    objects = UserManager()
    USERNAME_FIELD = "phone"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        verbose_name, verbose_name_plural = "کاربر", "کاربران"
        constraints = [
            models.CheckConstraint(condition=Q(phone__regex=r"^09[0-9]{9}$"), name="user_phone_format"),
            models.UniqueConstraint(fields=["email"], condition=~Q(email=""), name="user_email_unique_if_set"),
        ]

    def __str__(self):
        return self.get_full_name() or self.phone

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def get_short_name(self):
        return self.first_name or self.phone


class OTPChallenge(models.Model):
    """One issued OTP. The code itself is never stored — only an HMAC of it."""

    phone = models.CharField(max_length=11, db_index=False)
    purpose = models.CharField(max_length=20, default="login")
    code_hash = models.CharField(max_length=64)
    salt = models.CharField(max_length=32)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=5)
    consumed_at = models.DateTimeField(null=True, blank=True)
    invalidated_at = models.DateTimeField(null=True, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    provider = models.CharField(max_length=30, blank=True)
    provider_message_id = models.CharField(max_length=80, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["phone", "-created_at"]), models.Index(fields=["created_at"])]

    def __str__(self):
        return f"OTP#{self.pk}"


class Address(TimeStampedModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="addresses")
    province = models.ForeignKey("locations.Province", on_delete=models.PROTECT, verbose_name="استان")
    city = models.ForeignKey("locations.City", on_delete=models.PROTECT, verbose_name="شهر")
    address_line = models.TextField("نشانی")
    plaque = models.CharField("پلاک", max_length=10, blank=True)
    unit = models.CharField("واحد", max_length=10, blank=True)
    postal_code = models.CharField("کد پستی", max_length=10,
                                   validators=[RegexValidator(r"^\d{10}$", "کد پستی باید ۱۰ رقم باشد")])
    receiver_name = models.CharField("نام گیرنده", max_length=100)
    receiver_phone = models.CharField("موبایل گیرنده", max_length=11,
                                      validators=[RegexValidator(r"^09\d{9}$", "شمارهٔ موبایل نامعتبر است")])
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    is_default = models.BooleanField("پیش‌فرض", default=False)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        verbose_name, verbose_name_plural = "نشانی", "نشانی‌ها"
        constraints = [
            models.UniqueConstraint(fields=["user"], condition=Q(is_default=True, is_deleted=False),
                                    name="one_default_address_per_user"),
            models.CheckConstraint(condition=Q(postal_code__regex=r"^[0-9]{10}$"), name="address_postal_code_format"),
        ]

    def __str__(self):
        return f"{self.receiver_name} — {self.city}"
