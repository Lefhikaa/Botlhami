from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ("email",)
    list_display = ("email", "first_name", "last_name", "role", "email_verified", "id_status", "is_active", "date_joined")
    list_filter = ("role", "email_verified", "id_status", "is_active")
    search_fields = ("email", "first_name", "last_name", "organisation")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Person", {"fields": ("first_name", "last_name", "phone", "organisation")}),
        ("Access", {"fields": ("role", "email_verified", "is_active", "is_staff", "is_superuser")}),
        ("Identity (Omang)", {"fields": ("omang_last4", "id_status", "id_note", "id_checked_at", "id_checked_by")}),
        ("Data protection", {"fields": ("data_consent_at",)}),
        ("Dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "first_name", "last_name", "role", "password1", "password2")}),)
    readonly_fields = ("last_login", "date_joined", "data_consent_at", "omang_last4", "id_checked_at", "id_checked_by")
