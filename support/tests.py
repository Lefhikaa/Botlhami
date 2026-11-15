import shutil
import tempfile
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role, User
from audit.models import AuditEvent

from .models import FAQ, RegulatorContact, Resource, ServiceLevel, Ticket

MEDIA = tempfile.mkdtemp()


def make(email, role):
    return User.objects.create_user(email=email, password="Pass-word-123", role=role, first_name=email.split("@")[0].title(), email_verified=True)


@override_settings(MEDIA_ROOT=MEDIA)
class HelpCentreTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def test_starter_content_is_seeded(self):
        self.assertEqual(ServiceLevel.objects.count(), 4)
        self.assertTrue(FAQ.objects.exists())
        self.assertTrue(RegulatorContact.objects.filter(acronym="CIPA").exists())

    def test_public_pages_open_without_signing_in(self):
        for name in ["support:help", "support:documents", "support:sla"]:
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)

    def test_faq_search(self):
        r = self.client.get(reverse("support:help"), {"q": "password"})
        self.assertContains(r, "I forgot my password")
        self.assertNotContains(r, "Who owns my idea?")

    def test_admin_uploads_edits_and_deletes_a_document(self):
        admin = make("admin@x.bw", Role.ADMIN)
        self.client.force_login(admin)
        f = SimpleUploadedFile("form.pdf", b"%PDF-1.4 test", content_type="application/pdf")
        r = self.client.post(reverse("support:manage_new", args=["documents"]),
                             {"title": "Application form", "kind": "form", "description": "", "published": "on", "order": 0, "upload": f})
        self.assertRedirects(r, reverse("support:manage", args=["documents"]))
        res = Resource.objects.get()
        self.assertEqual(res.original_name, "form.pdf")
        self.client.logout()
        download = self.client.get(reverse("support:download", args=[res.pk]))
        self.assertEqual(download.status_code, 200)
        self.assertEqual(b"".join(download.streaming_content), b"%PDF-1.4 test")

        self.client.force_login(admin)
        self.client.post(reverse("support:manage_edit", args=["documents", res.pk]),
                         {"title": "Application form 2026", "kind": "form", "description": "", "order": 0})
        res.refresh_from_db()
        self.assertEqual(res.title, "Application form 2026")
        self.assertFalse(res.published)  # unticked box hides it
        self.client.logout()
        self.assertEqual(self.client.get(reverse("support:download", args=[res.pk])).status_code, 404)

        self.client.force_login(admin)
        self.client.post(reverse("support:manage_delete", args=["documents", res.pk]))
        self.assertFalse(Resource.objects.exists())
        self.assertTrue(AuditEvent.objects.filter(action="content.deleted").exists())

    def test_upload_rejects_unsafe_file_types(self):
        self.client.force_login(make("admin@x.bw", Role.ADMIN))
        f = SimpleUploadedFile("run.exe", b"MZ", content_type="application/octet-stream")
        r = self.client.post(reverse("support:manage_new", args=["documents"]), {"title": "x", "kind": "form", "order": 0, "upload": f})
        self.assertContains(r, "isn&#x27;t allowed")
        self.assertFalse(Resource.objects.exists())

    def test_only_admins_manage_content(self):
        self.client.force_login(make("ev@x.bw", Role.EVALUATOR))
        self.assertEqual(self.client.get(reverse("support:manage", args=["faqs"])).status_code, 403)

    def test_service_levels_can_be_edited_but_not_deleted(self):
        self.client.force_login(make("admin@x.bw", Role.ADMIN))
        lvl = ServiceLevel.objects.get(severity="critical")
        self.client.post(reverse("support:manage_edit", args=["service-levels", lvl.pk]),
                         {"label": "Critical", "description": "Down", "response_hours": 2, "resolution_hours": 6})
        lvl.refresh_from_db()
        self.assertEqual(lvl.response_hours, 2)
        self.assertEqual(self.client.post(reverse("support:manage_delete", args=["service-levels", lvl.pk])).status_code, 403)


class TicketTests(TestCase):
    def setUp(self):
        self.user = make("neo@x.bw", Role.SUBMITTER)
        self.other = make("ona@x.bw", Role.SUBMITTER)
        self.agent = make("kabo@x.bw", Role.CONSULTANT)
        self.high = ServiceLevel.objects.get(severity="high")

    def raise_ticket(self):
        self.client.force_login(self.user)
        self.client.post(reverse("support:new"), {"subject": "Can't upload", "area": "documents", "level": self.high.pk, "description": "Error on upload"})
        return Ticket.objects.get()

    def test_raising_a_ticket_sets_targets_and_alerts_staff(self):
        t = self.raise_ticket()
        self.assertTrue(t.reference.startswith("SUP-"))
        self.assertAlmostEqual((t.response_due - t.created_at).total_seconds(), 4 * 3600, delta=5)
        self.assertAlmostEqual((t.resolution_due - t.created_at).total_seconds(), 24 * 3600, delta=5)
        self.assertTrue(self.agent.notifications.exists())

    def test_people_only_see_their_own_tickets(self):
        t = self.raise_ticket()
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("support:ticket", args=[t.pk])).status_code, 403)
        self.client.force_login(self.agent)
        self.assertEqual(self.client.get(reverse("support:ticket", args=[t.pk])).status_code, 200)

    def test_first_staff_reply_records_response_and_resolving_records_fix(self):
        t = self.raise_ticket()
        self.client.force_login(self.agent)
        url = reverse("support:ticket", args=[t.pk])
        self.client.post(url, {"body": "Internal: checking logs", "internal": "on", "status": "open", "assigned_to": self.agent.pk})
        t.refresh_from_db()
        self.assertIsNone(t.first_response_at)  # internal notes don't count as a response
        self.client.post(url, {"body": "Compress the PDF under 10 MB.", "status": "resolved", "assigned_to": self.agent.pk})
        t.refresh_from_db()
        self.assertIsNotNone(t.first_response_at)
        self.assertEqual(t.status, Ticket.Status.RESOLVED)
        self.assertTrue(t.response_met)
        self.assertTrue(t.resolution_met)
        # The user doesn't see the internal note.
        self.client.force_login(self.user)
        r = self.client.get(url)
        self.assertContains(r, "Compress the PDF")
        self.assertNotContains(r, "checking logs")

    def test_late_ticket_is_flagged(self):
        t = self.raise_ticket()
        Ticket.objects.filter(pk=t.pk).update(response_due=timezone.now() - timedelta(hours=1))
        t.refresh_from_db()
        self.assertTrue(t.overdue)
        self.assertFalse(t.response_met)
        self.client.force_login(self.agent)
        self.assertContains(self.client.get(reverse("support:queue")), "1 past target")

    def test_user_reply_reopens_resolved_ticket(self):
        t = self.raise_ticket()
        Ticket.objects.filter(pk=t.pk).update(status=Ticket.Status.RESOLVED, resolved_at=timezone.now())
        self.client.post(reverse("support:ticket", args=[t.pk]), {"body": "Still failing"})
        t.refresh_from_db()
        self.assertEqual(t.status, Ticket.Status.IN_PROGRESS)
        self.assertIsNone(t.resolved_at)
