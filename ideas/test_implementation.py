import shutil
import tempfile
from datetime import timedelta

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role, User

from . import services as svc
from .models import Award, Idea, Milestone, Status

MEDIA = tempfile.mkdtemp()


def demo(name):
    return User.objects.get(email=f"{name}@demo.botlhami.bw")


@override_settings(MEDIA_ROOT=MEDIA)
class ImplementationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", password="Demo-pass-2026", stdout=open("/dev/null", "w"))

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def award_new(self, officer=None):
        idea = Idea.objects.get(title__startswith="Kgomo Trace")
        svc.decide(idea, demo("kefilwe.tau"), Status.APPROVED, "Strong and agreed.")
        return svc.grant_award(idea, demo("kefilwe.tau"), "pilot", "Pilot with CEDA.", 100000, officer=officer)

    def test_award_creates_a_dated_plan_and_tells_the_officer(self):
        kabo = demo("kabo.molefe")
        award = self.award_new(officer=kabo)
        plan = list(award.milestones.all())
        self.assertEqual(len(plan), 7)
        self.assertEqual(plan[0].due_date, timezone.localdate() + timedelta(days=14))
        self.assertEqual(plan[2].title, "Pilot agreement and site confirmed")  # depends on the award type
        self.assertTrue(kabo.notifications.filter(idea=award.idea).exists())

    def test_applicant_reports_progress_and_officer_confirms(self):
        kabo = demo("kabo.molefe")
        award = self.award_new(officer=kabo)
        first = award.milestones.first()
        applicant = award.idea.submitter
        self.client.force_login(applicant)
        url = reverse("ideas:milestone_update", args=[award.idea.pk, first.pk])
        self.client.post(url, {"status": "done", "note": "Accepted, thank you."})
        first.refresh_from_db()
        self.assertEqual(first.status, Milestone.Status.DONE)
        self.assertTrue(first.awaiting_confirmation)
        self.assertTrue(kabo.notifications.filter(text__contains="Accept the award").exists())
        # the officer (a consultant) can open the idea and confirm
        self.client.force_login(kabo)
        self.assertContains(self.client.get(reverse("ideas:detail", args=[award.idea.pk])), "Waiting for CEDA to confirm")
        self.client.post(url, {"status": "done", "action": "confirm"})
        first.refresh_from_db()
        self.assertIsNotNone(first.confirmed_at)
        self.assertEqual(award.progress()["done"], 1)

    def test_applicant_must_say_what_changed(self):
        award = self.award_new()
        m = award.milestones.first()
        with self.assertRaises(svc.WorkflowError):
            svc.update_milestone(m, award.idea.submitter, "in_progress", "")

    def test_other_people_cannot_change_the_plan(self):
        award = self.award_new()
        m = award.milestones.first()
        for name in ["neo.kgosi", "mpho.sebina", "kabo.molefe"]:  # another applicant, an evaluator, a consultant who isn't the officer
            with self.assertRaises(svc.WorkflowError):
                svc.update_milestone(m, demo(name), "done", "x")
        self.client.force_login(demo("kabo.molefe"))
        self.assertEqual(self.client.get(reverse("ideas:detail", args=[award.idea.pk])).status_code, 403)

    def test_staff_can_add_a_milestone(self):
        award = self.award_new()
        self.client.force_login(demo("goitseone.modise"))
        self.client.post(reverse("ideas:milestone_add", args=[award.idea.pk]),
                         {"title": "Site visit", "due_date": "2027-02-01", "description": ""})
        self.assertTrue(award.milestones.filter(title="Site visit").exists())

    def test_overdue_steps_are_flagged(self):
        award = Award.objects.get(idea__title__startswith="SolarCool")
        m = award.milestones.filter(status=Milestone.Status.PLANNED).first()
        Milestone.objects.filter(pk=m.pk).update(due_date=timezone.localdate() - timedelta(days=1))
        self.assertEqual(award.progress()["overdue"], 1)
        self.client.force_login(demo("goitseone.modise"))
        r = self.client.get(reverse("ideas:implementation"))
        self.assertContains(r, "1 overdue")
        self.assertContains(self.client.get(reverse("reports:dashboard")), "After the award")

    def test_demo_award_shows_progress_to_the_applicant(self):
        award = Award.objects.get(idea__title__startswith="SolarCool")
        self.client.force_login(award.idea.submitter)
        r = self.client.get(reverse("ideas:detail", args=[award.idea.pk]))
        self.assertContains(r, "Implementation plan")
        self.assertContains(r, "What happens next")
        self.assertContains(r, "2 of 7 done")
