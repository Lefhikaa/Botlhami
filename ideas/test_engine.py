import shutil
import tempfile

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import Role, User

from . import engine
from .models import Criterion, Idea, Status

MEDIA = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=MEDIA)
class EngineTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", password="Demo-pass-2026", stdout=open("/dev/null", "w"))

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def idea(self, start):
        return Idea.objects.get(title__startswith=start)

    def test_six_criteria_total_100(self):
        active = Criterion.objects.filter(active=True)
        self.assertEqual(active.count(), 6)
        self.assertEqual(sum(c.weight for c in active), 100)
        self.assertTrue(active.filter(name="Scalability").exists())

    def test_agreeing_strong_idea_is_recommended_for_approval(self):
        a = engine.analyse(self.idea("Kgomo Trace"))
        self.assertEqual(a.verdict, engine.APPROVE)
        self.assertEqual(a.combined, 86)
        self.assertFalse(a.disagreements)
        self.assertIn("Both evaluators recommend advancing.", a.summary)
        self.assertIn("strategic alignment with CEDA", " ".join(a.summary))

    def test_split_idea_needs_further_assessment_with_reasons(self):
        a = engine.analyse(self.idea("Thuto Pocket"))
        self.assertEqual(a.verdict, engine.FURTHER)
        self.assertEqual([c.name for c in a.disagreements], ["Innovation and originality", "Scalability", "Economic and social impact"])
        reasons = " ".join(a.reasons)
        self.assertIn("differ by 34 points", reasons)
        self.assertIn("advancing and another recommends declining", reasons)

    def test_weak_idea_is_recommended_for_decline(self):
        a = engine.analyse(self.idea("Sebaka"))
        self.assertEqual(a.verdict, engine.DECLINE)
        self.assertTrue(a.weaknesses)
        self.assertFalse(a.strengths)

    def test_engine_waits_until_all_evaluations_are_in(self):
        a = engine.analyse(self.idea("BoreSense"))
        self.assertEqual(a.verdict, engine.WAITING)
        self.assertIsNone(engine.analyse(self.idea("TenderPing")))

    def test_radar_has_one_axis_per_criterion_and_an_average(self):
        svg = engine.analyse(self.idea("Thuto Pocket")).radar()
        self.assertTrue(svg.startswith("<svg"))
        self.assertEqual(svg.count('class="radar-axis"'), 6)
        self.assertIn("Average", svg)
        self.assertIn("Evaluator A: Innovation and originality 5/5", svg)

    def test_report_is_for_the_panel_only_and_never_names_evaluators(self):
        idea = self.idea("Thuto Pocket")
        url = reverse("ideas:score_report", args=[idea.pk])
        for email in ["neo.kgosi", "mpho.sebina", "masego.ntsima"]:
            self.client.force_login(User.objects.get(email=f"{email}@demo.botlhami.bw"))
            self.assertEqual(self.client.get(url).status_code, 403, email)
        self.client.force_login(User.objects.get(email="kefilwe.tau@demo.botlhami.bw"))
        r = self.client.get(url)
        self.assertContains(r, "Needs further assessment")
        self.assertContains(r, "Evaluator B")
        self.assertNotContains(r, "Sebina")
        self.assertNotContains(r, "Kenosi")

    def test_further_assessment_sends_idea_back_with_a_third_evaluator(self):
        idea = self.idea("Thuto Pocket")
        lorato = User.objects.get(email="lorato.mosweu@demo.botlhami.bw")
        self.client.force_login(User.objects.get(email="kefilwe.tau@demo.botlhami.bw"))
        self.client.post(reverse("ideas:further_assessment", args=[idea.pk]), {"evaluator": lorato.pk})
        idea.refresh_from_db()
        self.assertEqual(idea.status, Status.IN_REVIEW)
        self.assertEqual(idea.active_assignments().count(), 3)
        self.assertTrue(lorato.notifications.filter(idea=idea).exists())
        self.assertEqual(engine.analyse(idea).verdict, engine.WAITING)

    def test_portfolio_compares_chosen_ideas(self):
        self.client.force_login(User.objects.get(email="goitseone.modise@demo.botlhami.bw"))
        a, b = self.idea("Kgomo Trace"), self.idea("Sebaka")
        r = self.client.get(reverse("ideas:scores"), {"compare": [a.pk, b.pk], "sort": "verdict"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["chosen"], [a.pk, b.pk] if r.context["chosen"][0] == a.pk else [b.pk, a.pk])
        self.assertEqual(r.context["rows"][0]["a"].verdict, engine.FURTHER)
        self.assertContains(r, "Recommend approval")
