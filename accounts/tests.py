import re

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from audit.models import AuditEvent

from .models import OneTimeCode, Role, User

STRONG = "Gaborone-Ideas-2026!"


def code_from_last_email():
    return re.search(r"\b(\d{6})\b", mail.outbox[-1].body).group(1)


def register(client, email="neo@example.bw", **extra):
    data = {
        "first_name": "Neo", "last_name": "Kgosi", "email": email, "phone": "71234567",
        "organisation": "Kgosi AgriTech", "password1": STRONG, "password2": STRONG, "consent": "on",
        "omang": "123412345",
    }
    data.update(extra)
    return client.post(reverse("accounts:register"), data)


@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
class RegistrationTests(TestCase):
    def test_register_sends_code_and_verification_signs_in(self):
        r = register(self.client)
        self.assertRedirects(r, reverse("accounts:verify"))
        user = User.objects.get(email="neo@example.bw")
        self.assertFalse(user.email_verified)
        self.assertEqual(user.role, Role.SUBMITTER)
        self.assertEqual(user.phone, "+26771234567")
        self.assertIsNotNone(user.data_consent_at)
        self.assertEqual(len(mail.outbox), 1)

        r = self.client.post(reverse("accounts:verify"), {"code": code_from_last_email()})
        self.assertRedirects(r, reverse("core:dashboard"), fetch_redirect_response=False)
        user.refresh_from_db()
        self.assertTrue(user.email_verified)
        self.assertTrue(AuditEvent.objects.filter(action="account.email_verified", actor=user).exists())

    def test_wrong_code_is_rejected_and_audited(self):
        register(self.client)
        r = self.client.post(reverse("accounts:verify"), {"code": "000000"})
        self.assertContains(r, "wrong or has expired")
        self.assertFalse(User.objects.get().email_verified)
        self.assertTrue(AuditEvent.objects.filter(action="account.verify_failed").exists())

    def test_code_locks_after_max_attempts(self):
        register(self.client)
        good = code_from_last_email()
        for _ in range(5):
            self.client.post(reverse("accounts:verify"), {"code": "111111" if good != "111111" else "222222"})
        r = self.client.post(reverse("accounts:verify"), {"code": good})
        self.assertContains(r, "wrong or has expired")

    def test_consent_and_strong_password_required(self):
        r = register(self.client, consent="", password1="12345678", password2="12345678")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(User.objects.exists())

    def test_duplicate_email_rejected(self):
        User.objects.create_user("neo@example.bw", STRONG, first_name="Neo")
        r = register(self.client, email="NEO@example.bw")
        self.assertContains(r, "already exists")

    def test_invalid_botswana_phone_rejected(self):
        r = register(self.client, phone="12345")
        self.assertContains(r, "valid Botswana mobile number")


@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
class SignInTests(TestCase):
    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.user = User.objects.create_user("tumo@example.bw", STRONG, first_name="Tumo", email_verified=True)

    def test_password_sign_in(self):
        r = self.client.post(reverse("accounts:login"), {"username": "tumo@example.bw", "password": STRONG})
        self.assertRedirects(r, reverse("core:dashboard"), fetch_redirect_response=False)
        self.assertTrue(AuditEvent.objects.filter(action="auth.login", actor=self.user).exists())

    def test_unverified_user_is_sent_to_verify(self):
        self.user.email_verified = False
        self.user.save()
        r = self.client.post(reverse("accounts:login"), {"username": "tumo@example.bw", "password": STRONG})
        self.assertRedirects(r, reverse("accounts:verify"))
        self.assertEqual(len(mail.outbox), 1)

    def test_lockout_after_five_failures(self):
        for _ in range(5):
            self.client.post(reverse("accounts:login"), {"username": "tumo@example.bw", "password": "wrong-password"})
        r = self.client.post(reverse("accounts:login"), {"username": "tumo@example.bw", "password": STRONG})
        self.assertContains(r, "Too many failed attempts")
        self.assertTrue(AuditEvent.objects.filter(action="auth.locked_out").exists())
        self.assertEqual(AuditEvent.objects.filter(action="auth.login_failed").count(), 5)

    def test_one_time_code_sign_in(self):
        r = self.client.post(reverse("accounts:code_request"), {"email": "tumo@example.bw"})
        self.assertRedirects(r, reverse("accounts:code_verify"))
        r = self.client.post(reverse("accounts:code_verify"), {"code": code_from_last_email()})
        self.assertRedirects(r, reverse("core:dashboard"), fetch_redirect_response=False)

    def test_code_request_does_not_reveal_unknown_emails(self):
        r = self.client.post(reverse("accounts:code_request"), {"email": "nobody@example.bw"}, follow=True)
        self.assertContains(r, "If nobody@example.bw has an account")
        self.assertEqual(len(mail.outbox), 0)

    def test_password_change(self):
        self.client.force_login(self.user)
        new = "Another-Strong-Pass-99"
        r = self.client.post(reverse("accounts:password_change"), {"old_password": STRONG, "new_password1": new, "new_password2": new})
        self.assertRedirects(r, reverse("accounts:profile"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(new))
        self.assertTrue(AuditEvent.objects.filter(action="auth.password_changed").exists())

    def test_password_reset_flow(self):
        self.client.post(reverse("accounts:password_reset"), {"email": "tumo@example.bw"})
        link = re.search(r"https?://[^\s]+/accounts/password/reset/[^\s]+/", mail.outbox[-1].body).group(0)
        path = link.split("testserver", 1)[1]
        r = self.client.get(path, follow=True)
        new = "Reset-Strong-Pass-77"
        r = self.client.post(r.redirect_chain[-1][0], {"new_password1": new, "new_password2": new})
        self.assertRedirects(r, reverse("accounts:password_reset_complete"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(new))

    def test_passwords_are_hashed_with_argon2(self):
        self.assertTrue(self.user.password.startswith("argon2"))


class OneTimeCodeTests(TestCase):
    def test_new_code_invalidates_old_one(self):
        user = User.objects.create_user("a@example.bw", STRONG)
        first, code1 = OneTimeCode.issue(user, OneTimeCode.Purpose.SIGN_IN)
        _, code2 = OneTimeCode.issue(user, OneTimeCode.Purpose.SIGN_IN)
        first.refresh_from_db()
        self.assertFalse(first.usable)
        self.assertNotIn(code1, first.code_hash)  # stored hashed, never in plain text


class PasswordResetEmailTests(TestCase):
    def test_reset_email_shows_the_full_link_as_text_too(self):
        """Spam folders switch off links, so the address must also be readable and copyable."""
        User.objects.create_user(email="neo@x.bw", password="Pass-word-123", first_name="Neo", email_verified=True)
        self.client.post(reverse("accounts:password_reset"), {"email": "neo@x.bw"}, secure=True)
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        url = re.search(r"https://testserver/accounts/password/reset/\S+/\S+/", msg.body).group(0)
        html = msg.alternatives[0][0]
        self.assertEqual(html.count(url), 2)  # once in the button, once as visible text
        self.assertIn("Not spam", html)
        # and the link works
        r = self.client.get(url, secure=True, follow=True)
        self.assertContains(r, "password")
        self.assertIn("set-password", r.redirect_chain[-1][0])



@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
class OmangTests(TestCase):
    def test_omang_format_rules(self):
        from .models import omang_problem
        self.assertIsNone(omang_problem("123412345"))
        self.assertIsNone(omang_problem("123422345"))
        self.assertIsNotNone(omang_problem("12341234"))     # eight digits
        self.assertIsNotNone(omang_problem("123432345"))    # middle digit must be 1 or 2
        self.assertIsNotNone(omang_problem("12341234a"))

    def test_number_is_never_stored_and_duplicates_are_blocked(self):
        register(self.client, omang="123 412 345")
        u = User.objects.get(email="neo@example.bw")
        self.assertEqual(u.omang_last4, "2345")
        self.assertNotIn("123412345", str(User.objects.filter(pk=u.pk).values().first()))
        self.assertEqual(u.id_status, User.IdStatus.NONE)
        self.client.logout()
        r = register(self.client, email="other@example.bw", omang="123412345")
        self.assertContains(r, "already registered")
        self.assertFalse(User.objects.filter(email="other@example.bw").exists())

    def test_bad_format_is_refused_at_registration(self):
        r = register(self.client, omang="123432345")
        self.assertContains(r, "valid Omang")

    def test_upload_then_staff_verify(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        import tempfile
        with self.settings(MEDIA_ROOT=tempfile.mkdtemp()):
            register(self.client)
            u = User.objects.get(email="neo@example.bw")
            self.client.force_login(u)
            self.assertFalse(u.identity_ready)
            f = SimpleUploadedFile("omang.png", b"\x89PNG fake", content_type="image/png")
            self.client.post(reverse("accounts:identity"), {"omang": "", "id_copy": f})
            u.refresh_from_db()
            self.assertEqual(u.id_status, User.IdStatus.PENDING)
            self.assertTrue(u.identity_ready)
            staff = User.objects.create_user("k@x.bw", STRONG, role=Role.CONSULTANT, email_verified=True)
            self.client.force_login(staff)
            self.assertContains(self.client.get(reverse("accounts:id_queue")), "Neo")
            self.assertEqual(self.client.get(reverse("accounts:id_document", args=[u.pk])).status_code, 200)
            r = self.client.post(reverse("accounts:id_check", args=[u.pk]), {"decision": "rejected", "note": ""})
            self.assertContains(r, "Tell the applicant why")
            self.client.post(reverse("accounts:id_check", args=[u.pk]), {"decision": "verified", "note": ""})
            u.refresh_from_db()
            self.assertEqual(u.id_status, User.IdStatus.VERIFIED)
            self.assertTrue(AuditEvent.objects.filter(action="identity.document_opened").exists())
            # applicants can't open other people's documents
            self.client.force_login(u)
            self.assertEqual(self.client.get(reverse("accounts:id_document", args=[u.pk])).status_code, 403)


class TesterFindingsTests(TestCase):
    """Findings from the full test checklist, 22 November."""

    def test_omang_saved_before_the_pepper_is_still_recognised(self):
        from django.conf import settings
        from django.test import override_settings
        from accounts.forms import clean_omang_number
        from accounts.models import User, _keyed_hash, omang_hash
        from django import forms as djforms
        u = User.objects.create_user("early@example.com", "x-Pass-12345")
        u.omang_hash = _keyed_hash(settings.SECRET_KEY, "123412345")
        u.omang_last4 = "2345"
        u.save()
        with override_settings(OMANG_PEPPER="pepper-set-later"):
            with self.assertRaises(djforms.ValidationError):
                clean_omang_number("123412345")
            u.refresh_from_db()
            self.assertEqual(u.omang_hash, omang_hash("123412345"))  # moved onto the new key

    def test_lockout_after_exactly_five_wrong_passwords(self):
        from accounts.models import User
        User.objects.create_user("lock@example.com", "x-Pass-12345", email_verified=True)
        url = reverse("accounts:login")
        for i in range(5):
            r = self.client.post(url, {"username": "lock@example.com", "password": "wrong"}, REMOTE_ADDR="10.0.0.1",
                                 HTTP_X_FORWARDED_FOR=f"102.1.2.3:{5000 + i}")
            self.assertNotContains(r, "Too many failed attempts")
        r = self.client.post(url, {"username": "lock@example.com", "password": "x-Pass-12345"},
                             HTTP_X_FORWARDED_FOR="102.1.2.3:6001")
        self.assertContains(r, "Too many failed attempts")

    def test_ipv6_port_is_stripped(self):
        from django.test import RequestFactory
        from audit.log import client_ip
        req = RequestFactory().get("/", HTTP_X_FORWARDED_FOR="[2001:db8::1]:5678")
        self.assertEqual(client_ip(req), "2001:db8::1")
