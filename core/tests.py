from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.urls import reverse

from accounts.models import Role, User
from audit.models import AuditEvent
from core.permissions import role_required


class CoreTests(TestCase):
    def test_health(self):
        r = self.client.get(reverse("core:health"))
        self.assertEqual(r.json(), {"status": "ok"})

    def test_security_headers(self):
        r = self.client.get(reverse("core:home"))
        self.assertIn("default-src 'self'", r["Content-Security-Policy"])
        self.assertEqual(r["X-Frame-Options"], "DENY")

    def test_dashboard_requires_sign_in(self):
        r = self.client.get(reverse("core:dashboard"))
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse("accounts:login"), r["Location"])

    def test_role_required_denies_and_audits(self):
        from django.core.exceptions import PermissionDenied

        user = User.objects.create_user("s@example.bw", "Strong-Pass-123!", role=Role.SUBMITTER)
        view = role_required(Role.ADMIN)(lambda request: HttpResponse("ok"))
        request = RequestFactory().get("/admin-only/")
        request.user = user
        with self.assertRaises(PermissionDenied):
            view(request)
        self.assertTrue(AuditEvent.objects.filter(action="access.denied", target="/admin-only/").exists())

        admin = User.objects.create_user("a@example.bw", "Strong-Pass-123!", role=Role.ADMIN)
        request.user = admin
        self.assertEqual(view(request).status_code, 200)


class AuditTests(TestCase):
    def test_audit_events_are_append_only(self):
        event = AuditEvent.objects.create(action="test.event", target="x")
        event.detail = "changed"
        with self.assertRaises(RuntimeError):
            event.save()
        with self.assertRaises(RuntimeError):
            event.delete()
