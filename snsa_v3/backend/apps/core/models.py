from django.db import models


class SystemConfiguration(models.Model):
    session_timeout_minutes = models.PositiveIntegerField(
        default=30,
        help_text="Minutes of inactivity before a scan session expires."
    )
    allow_duplicate_sn_across_sessions = models.BooleanField(
        default=False,
        help_text="If enabled, the same SN may appear across different sessions."
    )
    enable_ip_whitelist = models.BooleanField(
        default=False,
        help_text="If enabled, only whitelisted IPs are allowed to access the application."
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "System Configuration"
        verbose_name_plural = "System Configuration"

    def __str__(self):
        return "System Configuration"

    def save(self, *args, **kwargs):
        # Singleton: always force pk=1
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class AllowedIP(models.Model):
    """
    Whitelist of IP addresses allowed when enable_ip_whitelist is active.
    """
    ip_address = models.GenericIPAddressField(
        unique=True,
        help_text="Exact IPv4 or IPv6 address allowed to access the application."
    )
    description = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Optional description identifying the origin of the IP."
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Allowed IP"
        verbose_name_plural = "Allowed IPs"
        ordering = ["ip_address"]

    def __str__(self):
        if self.description:
            return f"{self.ip_address} — {self.description}"
        return self.ip_address
