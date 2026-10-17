from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import Address, OTPChallenge, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    ordering = ("-date_joined",)
    list_display = ("phone", "first_name", "last_name", "is_staff", "is_active", "date_joined")
    list_filter = ("is_staff", "is_active")
    search_fields = ("phone", "first_name", "last_name", "email")
    fieldsets = (
        (None, {"fields": ("phone", "password")}),
        ("اطلاعات", {"fields": ("first_name", "last_name", "email", "phone_verified_at")}),
        ("دسترسی‌ها", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("تاریخ‌ها", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("phone", "password1", "password2")}),)


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ("receiver_name", "user", "province", "city", "is_default", "is_deleted")
    list_filter = ("province", "is_default", "is_deleted")
    search_fields = ("receiver_name", "user__phone", "postal_code")
    raw_id_fields = ("user",)


@admin.register(OTPChallenge)
class OTPChallengeAdmin(admin.ModelAdmin):
    """Read-only audit view. Codes are not stored, only hashes."""

    list_display = ("id", "phone", "purpose", "attempts", "created_at", "consumed_at", "invalidated_at", "provider")
    list_filter = ("purpose", "provider")
    search_fields = ("phone",)
    exclude = ("code_hash", "salt")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
