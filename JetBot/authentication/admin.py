from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _
from .models import User, Interview, Report, AnalyticsExport


# --------------------------
# Custom User Admin
# --------------------------
class UserAdmin(BaseUserAdmin):
    ordering = ["id"]
    list_display = ("email", "role", "name", "mobile_no", "is_active", "is_staff")
    list_filter = ("role", "is_active", "is_staff")
    search_fields = ("email", "name", "mobile_no", "course_name", "center")

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (_("Personal Info"), {"fields": ("name", "course_name", "mobile_no", "center", "batch_no")}),
        (_("Roles & Permissions"), {"fields": ("role", "is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        (_("Important Dates"), {"fields": ("last_login", "created_at")}),
    )

    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "password1", "password2", "role", "is_active", "is_staff"),
        }),
    )

    readonly_fields = ("created_at",)


# --------------------------
# Interview Admin
# --------------------------
class InterviewAdmin(admin.ModelAdmin):
    list_display = ("id", "student", "difficulty_level", "scheduled_time", "status", "created_at")
    list_filter = ("difficulty_level", "status")
    search_fields = ("student__email", "jd")
    ordering = ("-created_at",)


# --------------------------
# Report Admin
# --------------------------
class ReportAdmin(admin.ModelAdmin):
    list_display = ("id", "interview", "created_at")
    search_fields = ("interview__student__email",)
    ordering = ("-created_at",)


# --------------------------
# AnalyticsExport Admin
# --------------------------
class AnalyticsExportAdmin(admin.ModelAdmin):
    list_display = ("id", "interview", "status", "exported_at")
    list_filter = ("status",)
    search_fields = ("interview__student__email",)
    ordering = ("-exported_at",)


# --------------------------
# Register Models
# --------------------------
admin.site.register(User, UserAdmin)
admin.site.register(Interview, InterviewAdmin)
admin.site.register(Report, ReportAdmin)
admin.site.register(AnalyticsExport, AnalyticsExportAdmin)
