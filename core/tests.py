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


class AzureEmailBackendTests(TestCase):
    def test_sends_plain_and_html_via_acs(self):
        from unittest import mock

        from django.core.mail import EmailMultiAlternatives
        from django.test import override_settings

        from core.email_backends import AzureCommunicationEmailBackend

        with override_settings(ACS_CONNECTION_STRING="endpoint=https://x/;accesskey=y", ACS_SENDER_ADDRESS="DoNotReply@x.azurecomm.net"):
            backend = AzureCommunicationEmailBackend()
            backend._client = mock.Mock()
            msg = EmailMultiAlternatives("Hi", "plain body", None, ["a@example.bw"])
            msg.attach_alternative("<p>html</p>", "text/html")
            self.assertEqual(backend.send_messages([msg]), 1)
            payload = backend._client.begin_send.call_args.args[0]
            self.assertEqual(payload["senderAddress"], "DoNotReply@x.azurecomm.net")
            self.assertEqual(payload["content"]["html"], "<p>html</p>")
            self.assertEqual(payload["recipients"]["to"], [{"address": "a@example.bw"}])


class HomePageTests(TestCase):
    def test_home_shows_live_platform_figures(self):
        from accounts.models import Role, User
        from ideas.models import Idea, Status

        u = User.objects.create_user(email="a@x.bw", password="Pass-word-123", role=Role.SUBMITTER)
        Idea.objects.create(submitter=u, title="Draft only")  # drafts aren't counted
        Idea.objects.create(submitter=u, title="Awarded", status=Status.AWARDED, jobs=9)
        Idea.objects.create(submitter=u, title="In review", status=Status.IN_REVIEW)
        r = self.client.get("/")
        self.assertContains(r, "Where ideas become innovation.")
        self.assertEqual(r.context["stats"], {"submitted": 2, "review": 1, "approved": 1, "awarded": 1, "jobs": 9})
        self.assertContains(r, "expect to create 9 jobs")
