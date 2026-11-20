import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class Role(models.TextChoices):
    SUBMITTER = "submitter", "Submitter"
    EVALUATOR = "evaluator", "Evaluator"
    ADJUDICATOR = "adjudicator", "Adjudicator"
    CONSULTANT = "consultant", "CEDA service consultant"
    OBSERVER = "observer", "Committee observer"
    ADMIN = "admin", "Administrator"


class UserManager(BaseUserManager):
    """Users sign in with their email address, not a username."""

    use_in_migrations = True

    def _create_user(self, email, password, **extra):
        if not email:
            raise ValueError("An email address is required.")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.update(is_staff=True, is_superuser=True, role=Role.ADMIN, email_verified=True)
        return self._create_user(email, password, **extra)


def id_document_path(instance, filename):
    import os
    import uuid
    return f"identity/{uuid.uuid4().hex}{os.path.splitext(filename)[1].lower()}"


def omang_problem(number):
    """Why an Omang number isn't valid, or None. Omang numbers have nine digits and the
    middle (fifth) digit is 1 or 2."""
    digits = "".join(ch for ch in str(number) if ch.isdigit())
    if len(digits) != 9 or len(digits) != len(str(number).replace(" ", "")):
        return "An Omang number has exactly nine digits."
    if digits[4] not in "12":
        return "That isn't a valid Omang number. Check it against your card."
    return None


def omang_hash(number):
    import hashlib
    import hmac
    digits = "".join(ch for ch in str(number) if ch.isdigit())
    key = (getattr(settings, "OMANG_PEPPER", "") or settings.SECRET_KEY).encode()
    return hmac.new(key, digits.encode(), hashlib.sha256).hexdigest()


class User(AbstractUser):
    username = None
    email = models.EmailField("email address", unique=True)
    phone = models.CharField("mobile number", max_length=20, blank=True)
    organisation = models.CharField(max_length=150, blank=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.SUBMITTER)
    email_verified = models.BooleanField(default=False)
    data_consent_at = models.DateTimeField(null=True, blank=True)
    email_alerts = models.BooleanField(
        "email me when my submissions are updated", default=True,
        help_text="Free alerts. You can switch them off at any time.",
    )

    # Identity (Omang). The number itself is never stored: only a keyed hash, to stop one
    # person holding two accounts, and the last 4 digits, to show back to people.
    class IdStatus(models.TextChoices):
        NONE = "none", "Not provided"
        PENDING = "pending", "Waiting for CEDA to check"
        VERIFIED = "verified", "Verified"
        REJECTED = "rejected", "Not accepted"

    omang_hash = models.CharField(max_length=64, unique=True, null=True, blank=True, editable=False)
    omang_last4 = models.CharField("Omang (last 4 digits)", max_length=4, blank=True)
    id_document = models.FileField(upload_to=id_document_path, blank=True)
    id_status = models.CharField("identity check", max_length=10, choices=IdStatus.choices, default=IdStatus.NONE)
    id_note = models.CharField("note from CEDA", max_length=255, blank=True)
    id_checked_at = models.DateTimeField(null=True, blank=True)
    id_checked_by = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    objects = UserManager()

    class Meta:
        ordering = ["first_name", "last_name"]

    def __str__(self):
        return self.get_full_name() or self.email

    def has_role(self, *roles):
        return self.is_authenticated and (self.role in roles or self.is_superuser)

    def set_omang(self, number):
        self.omang_hash = omang_hash(number)
        self.omang_last4 = "".join(ch for ch in str(number) if ch.isdigit())[-4:]

    @property
    def omang_masked(self):
        return f"•••••{self.omang_last4}" if self.omang_last4 else ""

    @property
    def identity_ready(self):
        """Enough to submit an idea: an Omang number and a card copy waiting for, or past, CEDA's check."""
        return bool(self.omang_hash) and self.id_status in (self.IdStatus.PENDING, self.IdStatus.VERIFIED)

    @property
    def is_staff_role(self):
        """Anyone working on CEDA's side, as opposed to an applicant."""
        return self.role != Role.SUBMITTER


class OneTimeCode(models.Model):
    """A short-lived numeric PIN sent by email. Only a hash is stored."""

    class Purpose(models.TextChoices):
        VERIFY_EMAIL = "verify", "Verify email"
        SIGN_IN = "signin", "Sign in"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="otps")
    purpose = models.CharField(max_length=10, choices=Purpose.choices)
    code_hash = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["user", "purpose", "-created_at"])]

    @classmethod
    def issue(cls, user, purpose):
        """Invalidate earlier codes for this purpose and return (record, plain code)."""
        cls.objects.filter(user=user, purpose=purpose, used_at__isnull=True).update(used_at=timezone.now())
        code = "".join(secrets.choice("0123456789") for _ in range(settings.OTP_LENGTH))
        record = cls.objects.create(
            user=user,
            purpose=purpose,
            code_hash=make_password(code),
            expires_at=timezone.now() + timedelta(minutes=settings.OTP_TTL_MINUTES),
        )
        return record, code

    @property
    def usable(self):
        return self.used_at is None and timezone.now() < self.expires_at and self.attempts < settings.OTP_MAX_ATTEMPTS

    def verify(self, code):
        """Return True and consume the code if it matches; count the attempt either way."""
        if not self.usable:
            return False
        self.attempts += 1
        ok = check_password((code or "").strip(), self.code_hash)
        if ok:
            self.used_at = timezone.now()
        self.save(update_fields=["attempts", "used_at"])
        return ok
