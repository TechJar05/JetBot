from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from django.contrib.admin import SimpleListFilter
from .models import User, Interview, Report, AnalyticsExport
from django.utils import timezone
from datetime import date
from django.contrib import admin
from .models import Interview

class DateFilter(admin.SimpleListFilter):
    title = "Interview Date"
    parameter_name = "created_at"

    def lookups(self, request, model_admin):
        return [
            ("today", "Today"),
            ("yesterday", "Yesterday"),
            ("last_7_days", "Last 7 Days"),
            ("this_month", "This Month"),
        ]

    def queryset(self, request, queryset):
        today = timezone.now().date()

        if self.value() == "today":
            return queryset.filter(created_at__date=today)

        if self.value() == "yesterday":
            return queryset.filter(created_at__date=today - timezone.timedelta(days=1))

        if self.value() == "last_7_days":
            return queryset.filter(created_at__date__gte=today - timezone.timedelta(days=7))

        if self.value() == "this_month":
            return queryset.filter(created_at__month=today.month, created_at__year=today.year)

        return queryset



# --------------------------
# Custom Filter: Center
# --------------------------
class CenterListFilter(SimpleListFilter):
    title = "Center"
    parameter_name = "center"

    def lookups(self, request, model_admin):
        centers = User.objects.values_list("center", flat=True).distinct()
        return [(center, center) for center in centers if center]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(center=self.value())
        return queryset


# --------------------------
# Custom User Admin
# --------------------------
class UserAdmin(BaseUserAdmin):
    ordering = ["id"]
    list_display = (
        "email",
        "role",
        "name",
        "center",
        "mobile_no",
        "created_at",  # ✅ Added created_at to list
        "is_active",
        "is_staff",
    )
    list_filter = (
        "role",
        "is_active",
        "is_staff",
        CenterListFilter,
        "created_at",  # ✅ Django automatically provides a date filter
    )
    search_fields = ("email", "name", "mobile_no", "course_name", "center")

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (_("Personal Info"), {"fields": ("name", "course_name", "mobile_no", "center", "batch_no")}),
        (_("Roles & Permissions"), {
            "fields": ("role", "is_active", "is_staff", "is_superuser", "groups", "user_permissions")
        }),
        (_("Important Dates"), {"fields": ("last_login", "created_at")}),
    )

    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "password1", "password2", "role", "is_active", "is_staff"),
        }),
    )

    readonly_fields = ("created_at",)

    # ✅ Display total count for current filters
    def changelist_view(self, request, extra_context=None):
        response = super().changelist_view(request, extra_context)
        try:
            qs = response.context_data["cl"].queryset
            total_count = qs.count()
            response.context_data["summary"] = format_html(
                "<h3 style='margin-top:10px;'>📊 Total Users for Selected Filters: <b>{}</b></h3>",
                total_count
            )
        except Exception:
            pass
        return response


# --------------------------
# Interview Admin
# --------------------------
class InterviewAdmin(admin.ModelAdmin):
    list_display = ("id", "student", "difficulty_level", "scheduled_time", "status", "created_at")
    list_filter = ("difficulty_level", "status", DateFilter)  # ✅ Added custom date filter
    search_fields = ("student__email", "jd")
    ordering = ("-created_at",)

    # ✅ Optional: Show only today's completed interviews by default
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        today = timezone.now().date()
        # Show today's completed interviews by default
        return qs.filter(created_at__date=today, status="completed")


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
