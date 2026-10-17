from django.contrib import admin

from .models import City, Province


@admin.register(Province)
class ProvinceAdmin(admin.ModelAdmin):
    search_fields = ["name"]


@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    list_display = ["name", "province", "is_active"]
    list_filter = ["province", "is_active"]
    search_fields = ["name"]
