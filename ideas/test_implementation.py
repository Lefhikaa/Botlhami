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


@override_settings(MEDIA_ROOT=MEDIA)
class NotAwardedAndIdentityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", password="Demo-pass-2026", stdout=open("/dev/null", "w"))

    def test_declined_applicant_gets_report_certificate_and_new_version(self):
        idea = Idea.objects.get(title__startswith="Sebaka")
        svc.decide(idea, demo("kefilwe.tau"), Status.REJECTED, "Demand isn't shown yet.")
        self.assertTrue(idea.submitter.notifications.filter(text__contains="development report").exists())
        self.client.force_login(idea.submitter)
        r = self.client.get(reverse("ideas:development", args=[idea.pk]))
        self.assertContains(r, "Your next steps")
        self.assertContains(r, "Demand isn&#x27;t shown yet.")
        self.assertGreaterEqual(len(r.context["r"]["steps"]), 2)
        self.assertContains(self.client.get(reverse("ideas:certificate", args=[idea.pk])), "Certificate of participation")
        r = self.client.post(reverse("ideas:new_version", args=[idea.pk]))
        new = Idea.objects.filter(submitter=idea.submitter, status=Status.DRAFT).latest("pk")
        self.assertEqual(new.title, idea.title)
        self.assertRedirects(r, reverse("ideas:edit", args=[new.pk]))
        # other people can't see the report
        self.client.force_login(demo("onalenna.dube"))
        self.assertEqual(self.client.get(reverse("ideas:development", args=[idea.pk])).status_code, 403)

    def test_report_only_for_declined_ideas(self):
        idea = Idea.objects.get(title__startswith="Kgomo")
        self.client.force_login(idea.submitter)
        self.assertEqual(self.client.get(reverse("ideas:development", args=[idea.pk])).status_code, 404)

    def test_no_submission_without_omang_and_no_award_without_verification(self):
        u = User.objects.create_user("new@x.bw", "Pass-word-123", role=Role.SUBMITTER, email_verified=True)
        draft = Idea.objects.get(title__startswith="TenderPing")
        draft.pk = None
        draft.submitter, draft.status, draft.reference = u, Status.DRAFT, ""
        draft.save()
        with self.assertRaisesMessage(svc.WorkflowError, "Omang"):
            svc.submit(draft, u)
        # Tumelo's Omang is still waiting for CEDA: approving works, awarding doesn't
        thuto = Idea.objects.get(title__startswith="Thuto")
        svc.decide(thuto, demo("kefilwe.tau"), Status.APPROVED, "Approved after discussion.")
        with self.assertRaisesMessage(svc.WorkflowError, "must be verified"):
            svc.grant_award(thuto, demo("kefilwe.tau"), "pilot", "Pilot with CEDA.")


class LeftoverAwardTests(TestCase):
    """An award left behind without the idea being marked awarded must not block granting."""

    def test_grant_replaces_a_leftover_award(self):
        from accounts.models import Role
        from audit.models import AuditEvent
        from ideas import services as svc
        from ideas.models import Award, Idea, Status
        from ideas.tests import make_user
        adj = make_user("adj@example.com", Role.ADJUDICATOR)
        sub = make_user("sub@example.com", Role.SUBMITTER)
        idea = Idea.objects.create(submitter=sub, title="Leftover", status=Status.APPROVED, reference="IDX-T-1")
        Award.objects.create(idea=idea, category="champion", message="added by hand", granted_by=adj)
        svc.grant_award(idea, adj, "seed", "Well done", None)
        idea.refresh_from_db()
        self.assertEqual(idea.status, Status.AWARDED)
        self.assertEqual(Award.objects.get(idea=idea).category, "seed")
        self.assertTrue(idea.award.milestones.exists())
        self.assertTrue(AuditEvent.objects.filter(action="award.replaced").exists())

    def test_second_grant_is_refused_politely(self):
        from accounts.models import Role
        from ideas import services as svc
        from ideas.models import Idea, Status
        from ideas.tests import make_user
        adj = make_user("adj2@example.com", Role.ADJUDICATOR)
        sub = make_user("sub2@example.com", Role.SUBMITTER)
        idea = Idea.objects.create(submitter=sub, title="Twice", status=Status.APPROVED, reference="IDX-T-2")
        svc.grant_award(idea, adj, "seed", "Well done", None)
        stale = Idea.objects.get(pk=idea.pk)
        stale.status = Status.APPROVED  # as if the page was open in a second tab
        with self.assertRaises(svc.WorkflowError):
            svc.grant_award(stale, adj, "pilot", "Again", None)

    def test_awards_are_view_only_in_admin(self):
        from django.contrib.admin.sites import site
        from ideas.models import Award
        self.assertFalse(site._registry[Award].has_add_permission(None))


class SeedOmangTests(TestCase):
    def test_reseed_rehashes_demo_omang_and_resets_checks(self):
        from django.test import override_settings
        from accounts.models import User, omang_hash
        call_command("seed_demo", password="Demo-pass-12345")
        tumelo = User.objects.get(email="tumelo.phiri@demo.botlhami.bw")
        tumelo.id_status = User.IdStatus.VERIFIED
        tumelo.save()
        with override_settings(OMANG_PEPPER="a-new-pepper-value"):
            call_command("seed_demo", password="Demo-pass-12345")
            tumelo.refresh_from_db()
            self.assertEqual(tumelo.omang_hash, omang_hash("999910003"))
            self.assertEqual(tumelo.id_status, User.IdStatus.PENDING)


class DeleteDraftTests(TestCase):
    def setUp(self):
        from accounts.models import Role
        from ideas.tests import make_user
        self.me = make_user("drafter@example.com", Role.SUBMITTER)
        self.other = make_user("other@example.com", Role.SUBMITTER)

    def test_applicant_deletes_own_draft(self):
        from ideas.models import Idea
        d = Idea.objects.create(submitter=self.me, title="Half an idea")
        self.client.force_login(self.me)
        r = self.client.post(reverse("ideas:delete_draft", args=[d.pk]))
        self.assertRedirects(r, reverse("ideas:mine"))
        self.assertFalse(Idea.objects.filter(pk=d.pk).exists())

    def test_submitted_ideas_and_other_peoples_drafts_are_safe(self):
        from ideas.models import Idea, Status
        sent = Idea.objects.create(submitter=self.me, title="Sent", status=Status.SUBMITTED, reference="IDX-T-9")
        theirs = Idea.objects.create(submitter=self.other, title="Theirs")
        self.client.force_login(self.me)
        self.assertEqual(self.client.post(reverse("ideas:delete_draft", args=[sent.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse("ideas:delete_draft", args=[theirs.pk])).status_code, 404)
        self.assertEqual(Idea.objects.filter(pk__in=[sent.pk, theirs.pk]).count(), 2)


class SeedTakesBackDemoOmangTests(TestCase):
    def test_reset_frees_a_demo_omang_used_by_a_test_account(self):
        from accounts.models import User
        call_command("seed_demo", password="Demo-pass-12345")
        neo = User.objects.get(email="neo.kgosi@demo.botlhami.bw")
        neo.omang_hash = None
        neo.save()
        tester = User.objects.create_user("tester@example.com", "x-Pass-12345")
        tester.set_omang("999910001")
        tester.save()
        call_command("seed_demo", password="Demo-pass-12345", reset_ideas=True)
        tester.refresh_from_db()
        neo.refresh_from_db()
        self.assertIsNone(tester.omang_hash)
        self.assertTrue(neo.omang_hash)


class SeedWithTestersIdeasTests(TestCase):
    def test_reset_recreates_demo_ideas_even_when_testers_have_ideas(self):
        from accounts.models import User
        from ideas.models import Idea
        call_command("seed_demo", password="Demo-pass-12345", reset_ideas=True)
        tester = User.objects.create_user("tester2@example.com", "x-Pass-12345")
        mine = Idea.objects.create(submitter=tester, title="Tester's idea")
        call_command("seed_demo", password="Demo-pass-12345", reset_ideas=True)
        self.assertEqual(Idea.objects.filter(submitter__email__endswith="@demo.botlhami.bw").count(), 7)
        self.assertTrue(Idea.objects.filter(pk=mine.pk).exists())
        call_command("seed_demo", password="Demo-pass-12345", reset_ideas=True, all_ideas=True)
        self.assertFalse(Idea.objects.filter(pk=mine.pk).exists())
        self.assertEqual(Idea.objects.count(), 7)
