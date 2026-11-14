from django.conf import settings
from django.db import models


class AuditEvent(models.Model):
    """Append-only record of who did what, when and from where.

    Rows are never edited or deleted through the application: the admin is
    read-only and save() refuses updates to existing rows.
    """

    at = models.DateTimeField(auto_now_add=True, db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_events"
    )
    actor_label = models.CharField(max_length=200, blank=True, help_text="Kept even if the user is later anonymised.")
    role = models.CharField(max_length=20, blank=True)
    action = models.CharField(max_length=60, db_index=True)
    target = models.CharField(max_length=120, blank=True, db_index=True)
    detail = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-at"]

    def __str__(self):
        return f"{self.at:%Y-%m-%d %H:%M} {self.actor_label or 'system'} {self.action} {self.target}"

    def save(self, *args, **kwargs):
        if self.pk:
            raise RuntimeError("Audit events are append-only.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError("Audit events are append-only.")
