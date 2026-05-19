from django.contrib import admin
from .models import AllowedIP, SystemConfiguration


@admin.register(SystemConfiguration)
class SystemConfigurationAdmin(admin.ModelAdmin):
    list_display = [
        "session_timeout_minutes",
        "allow_duplicate_sn_across_sessions",
        "enable_ip_whitelist",
        "updated_at",
    ]

    def has_add_permission(self, request):
        # Prevent multiple rows from being created via the admin
        return not SystemConfiguration.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AllowedIP)
class AllowedIPAdmin(admin.ModelAdmin):
    list_display = ["ip_address", "description", "is_active", "updated_at"]
    list_filter = ["is_active"]
    search_fields = ["ip_address", "description"]
    ordering = ["ip_address"]
