import os
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


# --- content administrators manage ------------------------------------------
def resource_path(instance, filename):
    _, ext = os.path.splitext(filename)
    return f"resources/{timezone.now():%Y%m%d%H%M%S}{ext.lower()}"


class Resource(models.Model):
    """Application forms and the documents applicants must supply, published by administrators."""

    class Kind(models.TextChoices):
        APPLICATION_FORM = "form", "Application form"
        REQUIRED = "required", "Required document"
        TEMPLATE = "template", "Template"
        GUIDE = "guide", "Guide"

    ALLOWED = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".txt"}
    MAX_BYTES = 10 * 1024 * 1024

    title = models.CharField(max_length=150)
    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.REQUIRED)
    description = models.TextField(blank=True, help_text="What it is and when applicants need it.")
    mandatory = models.BooleanField(default=False, help_text="Applicants must include this with their idea.")
    file = models.FileField(upload_to=resource_path, blank=True)
    original_name = models.CharField(max_length=200, blank=True)
    size = models.PositiveIntegerField(default=0)
    published = models.BooleanField(default=True)
    order = models.PositiveSmallIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ["kind", "order", "title"]

    def __str__(self):
        return self.title


class FAQ(models.Model):
    class Category(models.TextChoices):
        APPLYING = "applying", "Applying"
        EVALUATION = "evaluation", "Evaluation and decisions"
        AWARDS = "awards", "Awards and funding"
        ACCOUNT = "account", "Your account and privacy"
        SUPPORT = "support", "Help and support"

    category = models.CharField(max_length=12, choices=Category.choices, default=Category.APPLYING)
    question = models.CharField(max_length=200)
    answer = models.TextField()
    published = models.BooleanField(default=True)
    order = models.PositiveSmallIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category", "order", "id"]
        verbose_name = "FAQ"
        verbose_name_plural = "FAQs"

    def __str__(self):
        return self.question


class RegulatorContact(models.Model):
    """Regulatory authorities innovators commonly need, shown alongside the FAQs."""

    name = models.CharField(max_length=150)
    acronym = models.CharField(max_length=20, blank=True)
    helps_with = models.CharField(max_length=255, help_text="When an innovator would contact them.")
    phone = models.CharField(max_length=60, blank=True)
    email = models.EmailField(blank=True)
    website = models.URLField(blank=True)
    published = models.BooleanField(default=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self):
        return self.acronym or self.name


# --- support desk and service levels -----------------------------------------
class ServiceLevel(models.Model):
    """Turnaround times for each fault severity. Administrators can change them."""

    severity = models.CharField(max_length=10, unique=True)
    label = models.CharField(max_length=40)
    description = models.CharField(max_length=255)
    response_hours = models.PositiveSmallIntegerField(help_text="Time to first response from the support team.")
    resolution_hours = models.PositiveSmallIntegerField(help_text="Time to fix or provide a workaround.")
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return self.label

    @staticmethod
    def hours_label(h):
        if h < 24 or h % 24:
            return f"{h} hour{'s' if h != 1 else ''}"
        d = h // 24
        return f"{d} day{'s' if d != 1 else ''}"

    @property
    def response_label(self):
        return self.hours_label(self.response_hours)

    @property
    def resolution_label(self):
        return self.hours_label(self.resolution_hours)


class Ticket(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        IN_PROGRESS = "in_progress", "In progress"
        WAITING = "waiting", "Waiting for you"
        RESOLVED = "resolved", "Resolved"
        CLOSED = "closed", "Closed"

    ACTIVE = (Status.OPEN, Status.IN_PROGRESS, Status.WAITING)

    class Area(models.TextChoices):
        ACCESS = "access", "Signing in or registration"
        SUBMISSION = "submission", "Submitting or editing an idea"
        DOCUMENTS = "documents", "Uploading or downloading documents"
        EVALUATION = "evaluation", "Evaluation or adjudication"
        CHAT = "chat", "Live chat or alerts"
        OTHER = "other", "Something else"

    reference = models.CharField(max_length=20, unique=True, blank=True)
    raised_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="tickets")
    subject = models.CharField(max_length=150)
    area = models.CharField("what it affects", max_length=12, choices=Area.choices, default=Area.OTHER)
    description = models.TextField("what happened")
    level = models.ForeignKey(ServiceLevel, on_delete=models.PROTECT, verbose_name="how serious is it")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OPEN, db_index=True)
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_tickets")
    created_at = models.DateTimeField(auto_now_add=True)
    response_due = models.DateTimeField()
    resolution_due = models.DateTimeField()
    first_response_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.reference} {self.subject}"

    def save(self, *args, **kwargs):
        if not self.pk:
            now = timezone.now()
            self.response_due = now + timedelta(hours=self.level.response_hours)
            self.resolution_due = now + timedelta(hours=self.level.resolution_hours)
        super().save(*args, **kwargs)
        if not self.reference:
            self.reference = f"SUP-{self.created_at:%Y}-{self.pk:04d}"
            super().save(update_fields=["reference"])

    @property
    def is_active(self):
        return self.status in self.ACTIVE

    @property
    def response_met(self):
        """True/False once answered, None while still waiting."""
        if self.first_response_at:
            return self.first_response_at <= self.response_due
        return False if timezone.now() > self.response_due else None

    @property
    def resolution_met(self):
        if self.resolved_at:
            return self.resolved_at <= self.resolution_due
        return False if timezone.now() > self.resolution_due else None

    @property
    def next_due(self):
        """The deadline the support team is working to right now."""
        if not self.is_active:
            return None
        return self.response_due if not self.first_response_at else self.resolution_due

    @property
    def overdue(self):
        due = self.next_due
        return bool(due and timezone.now() > due)


class TicketReply(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="replies")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    body = models.TextField()
    internal = models.BooleanField(default=False, help_text="Only visible to the support team.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
