import shutil
import tempfile

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import Role, User

MEDIA = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=MEDIA)
class ReportsTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", password="Demo-pass-2026", stdout=open("/dev/null", "w"))

    def test_report_roles_can_open_the_dashboard(self):
        for email in ["goitseone.modise", "kefilwe.tau", "masego.ntsima"]:
            self.client.force_login(User.objects.get(email=f"{email}@demo.botlhami.bw"))
            for days in (30, 90, 365, 0):
                r = self.client.get(reverse("reports:dashboard"), {"days": days})
                self.assertEqual(r.status_code, 200, (email, days))
        self.assertContains(r, "Average days per stage")

    def test_figures_reflect_the_data(self):
        self.client.force_login(User.objects.get(role=Role.ADMIN, email__startswith="goitseone"))
        r = self.client.get(reverse("reports:dashboard"), {"days": 0})
        kpi = r.context["r"]["kpi"]
        self.assertEqual(kpi["submitted"], 7)
        self.assertEqual(kpi["awards"], 1)
        self.assertEqual(kpi["approval_rate"], 100)
        self.assertEqual(kpi["revised"], 1)
        screening = r.context["r"]["stages"][0]
        self.assertEqual(screening["label"], "Screening")
        self.assertGreater(screening["avg"], 0)

    def test_applicants_and_evaluators_cannot_see_reports(self):
        for email in ["neo.kgosi", "mpho.sebina"]:
            self.client.force_login(User.objects.get(email=f"{email}@demo.botlhami.bw"))
            self.assertEqual(self.client.get(reverse("reports:dashboard")).status_code, 403)

    def test_csv_export_leaves_out_applicant_names(self):
        self.client.force_login(User.objects.get(email="masego.ntsima@demo.botlhami.bw"))
        r = self.client.get(reverse("reports:export"), {"days": 0})
        body = r.content.decode("utf-8-sig")
        self.assertEqual(r["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("IDX-", body)
        self.assertNotIn("Kgosi", body)
        self.assertEqual(len(body.strip().splitlines()), 8)  # header + 7 ideas
