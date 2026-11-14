from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string

from .models import OneTimeCode

SUBJECTS = {
    OneTimeCode.Purpose.VERIFY_EMAIL: "Your Botlhami verification code",
    OneTimeCode.Purpose.SIGN_IN: "Your Botlhami sign-in code",
}


def send_code(user, purpose):
    _, code = OneTimeCode.issue(user, purpose)
    ctx = {"user": user, "code": code, "minutes": settings.OTP_TTL_MINUTES, "purpose": purpose}
    send_mail(
        SUBJECTS[purpose],
        render_to_string("emails/otp.txt", ctx),
        None,
        [user.email],
        html_message=render_to_string("emails/otp.html", ctx),
    )


def check_code(user, purpose, code):
    record = OneTimeCode.objects.filter(user=user, purpose=purpose, used_at__isnull=True).order_by("-created_at").first()
    return bool(record and record.verify(code))
