from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


class ChatSettings(models.Model):
    """Opening hours and capacity, editable by administrators."""

    opens_at = models.TimeField(default="09:00")
    closes_at = models.TimeField(default="16:00")
    max_chats_per_agent = models.PositiveSmallIntegerField(default=4, help_text="An agent is 'busy' at this many active chats.")
    closed_message = models.CharField(
        max_length=255,
        default="Our consultants are available from 09:00 to 16:00 on working days. Leave a message and we'll reply by email.",
    )
    busy_message = models.CharField(
        max_length=255,
        default="All our consultants are helping other clients right now. Please wait, or leave a message and we'll reply by email.",
    )
    offline_message = models.CharField(
        max_length=255,
        default="No agent is available at the moment. Leave a message and we'll reply by email.",
    )

    class Meta:
        verbose_name = verbose_name_plural = "Chat settings"

    def __str__(self):
        return "Chat settings"

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class PublicHoliday(models.Model):
    date = models.DateField(unique=True)
    name = models.CharField(max_length=80)

    class Meta:
        ordering = ["date"]

    def __str__(self):
        return f"{self.date:%d %b %Y} {self.name}"


class AgentPresence(models.Model):
    """Whether a consultant is taking chats. Kept fresh by the console's polling."""

    agent = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chat_presence")
    available = models.BooleanField(default=False)
    last_seen = models.DateTimeField(default=timezone.now)

    STALE_AFTER = timedelta(minutes=2)

    @property
    def online(self):
        return self.available and timezone.now() - self.last_seen < self.STALE_AFTER


class Conversation(models.Model):
    class Status(models.TextChoices):
        WAITING = "waiting", "Waiting for an agent"
        ACTIVE = "active", "In progress"
        CLOSED = "closed", "Closed"
        OFFLINE = "offline", "Offline message"

    customer = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="chats")
    guest_name = models.CharField(max_length=100, blank=True)
    guest_email = models.EmailField(blank=True)
    topic = models.CharField(max_length=60, blank=True)
    agent = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="handled_chats")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.WAITING, db_index=True)
    started_as = models.CharField(max_length=10, default="open", help_text="Availability when the client started: open, busy, closed or offline.")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    rating = models.PositiveSmallIntegerField(null=True, blank=True)
    customer_seen_id = models.PositiveBigIntegerField(default=0)
    agent_seen_id = models.PositiveBigIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Chat {self.pk} with {self.display_name}"

    @property
    def display_name(self):
        return str(self.customer) if self.customer else (self.guest_name or "Guest")

    @property
    def contact_email(self):
        return self.customer.email if self.customer else self.guest_email

    @property
    def wait_seconds(self):
        end = self.accepted_at or self.closed_at
        return (end - self.created_at).total_seconds() if end else None

    @property
    def duration_seconds(self):
        return (self.closed_at - self.accepted_at).total_seconds() if self.accepted_at and self.closed_at else None


class ChatMessage(models.Model):
    class Kind(models.TextChoices):
        CUSTOMER = "customer"
        AGENT = "agent"
        SYSTEM = "system"

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    body = models.TextField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def as_dict(self):
        name = "CEDA" if self.kind == self.Kind.SYSTEM else (
            self.sender.first_name or str(self.sender) if self.sender else self.conversation.display_name
        )
        return {"id": self.pk, "kind": self.kind, "name": name, "body": self.body, "at": timezone.localtime(self.created_at).strftime("%H:%M")}


class AssistantQuery(models.Model):
    """What people ask the assistant, so the Innovation Office can see which questions it couldn't answer."""
    question = models.CharField(max_length=500)
    matched = models.CharField(max_length=255, blank=True)
    answered = models.BooleanField(default=False)
    helpful = models.BooleanField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
