import tempfile

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import Role, User
from audit.models import AuditEvent

from . import services as svc
from .models import Criterion, Idea, Notification, Status

PW = "Strong-Pass-2026!"


def make_user(email, role, **kw):
    return User.objects.create_user(email, PW, first_name=email.split("@")[0].title(), role=role, email_verified=True, **kw)


def complete_idea(submitter, **kw):
    data = dict(
        submitter=submitter, title="SolarCool cold rooms", sector="Energy & water", maturity="Pilot", location="Gaborone",
        problem="Farmers lose much of their produce because they have no cold storage near their fields.",
        solution="Solar-powered cold rooms rented per crate per day, paid by mobile money, at collection points.",
        beneficiaries="Smallholder farmers", impact="Less waste and higher income", jobs=12, budget=480000,
        sdgs=[2, 7], team="Neo (founder)", ip_declared=True,
    )
    data.update(kw)
    return Idea.objects.create(**data)


SCORES = lambda v: {str(c.pk): v for c in Criterion.objects.filter(active=True)}  # noqa: E731


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class WorkflowTests(TestCase):
    def setUp(self):
        self.applicant = make_user("neo@example.bw", Role.SUBMITTER)
        self.other = make_user("kagiso@example.bw", Role.SUBMITTER)
        self.admin = make_user("goitse@example.bw", Role.ADMIN)
        self.ev1 = make_user("mpho@example.bw", Role.EVALUATOR)
        self.ev2 = make_user("thato@example.bw", Role.EVALUATOR)
        self.adj = make_user("kefilwe@example.bw", Role.ADJUDICATOR)
        self.obs = make_user("masego@example.bw", Role.OBSERVER)

    def _to_adjudication(self, idea, scores=(4, 4)):
        svc.submit(idea, self.applicant)
        svc.accept_and_assign(idea, self.admin, [self.ev1, self.ev2])
        svc.submit_evaluation(idea, self.ev1, SCORES(scores[0]), "Clear problem and a working pilot.", "advance", coi_declared=True)
        svc.submit_evaluation(idea, self.ev2, SCORES(scores[1]), "Good impact; show unit economics.", "advance", coi_declared=True)
        idea.refresh_from_db()

    def test_full_lifecycle_to_award(self):
        idea = complete_idea(self.applicant)
        self.assertTrue(idea.reference.startswith("IDX-"))
        self._to_adjudication(idea)
        self.assertEqual(idea.status, Status.ADJUDICATION)
        self.assertEqual(idea.combined_score(), 80)
        svc.decide(idea, self.adj, Status.APPROVED, "Strong pilot evidence.")
        svc.grant_award(idea, self.adj, "seed", "Referred to CEDA financing.", 250000)
        idea.refresh_from_db()
        self.assertEqual(idea.status, Status.AWARDED)
        self.assertEqual(
            list(idea.history.values_list("to_status", flat=True)),
            ["submitted", "in_review", "adjudication", "approved", "awarded"],
        )
        for action in ["idea.submitted", "idea.screened", "evaluation.submitted", "decision.approved", "award.granted"]:
            self.assertTrue(AuditEvent.objects.filter(action=action, target=idea.reference).exists(), action)
        self.assertTrue(Notification.objects.filter(user=self.applicant, text__startswith="Congratulations").exists())
        self.assertTrue(any("Congratulations" in m.subject for m in mail.outbox))

    def test_incomplete_idea_cannot_be_submitted(self):
        idea = Idea.objects.create(submitter=self.applicant, title="Half done")
        with self.assertRaises(svc.WorkflowError) as e:
            svc.submit(idea, self.applicant)
        self.assertIn("Problem", str(e.exception))
        self.assertEqual(idea.status, Status.DRAFT)

    def test_screening_needs_enough_evaluators(self):
        idea = complete_idea(self.applicant)
        svc.submit(idea, self.applicant)
        with self.assertRaises(svc.WorkflowError):
            svc.accept_and_assign(idea, self.admin, [self.ev1])

    def test_return_then_resubmit_goes_back_to_screening(self):
        idea = complete_idea(self.applicant)
        svc.submit(idea, self.applicant)
        svc.return_to_applicant(idea, self.admin, "Add a budget breakdown.")
        self.assertEqual(idea.status, Status.REVISION)
        svc.submit(idea, self.applicant)
        self.assertEqual(idea.status, Status.SUBMITTED)
        self.assertEqual(idea.round, 2)

    def test_revision_after_adjudication_opens_new_round_with_same_evaluators(self):
        idea = complete_idea(self.applicant)
        self._to_adjudication(idea)
        svc.decide(idea, self.adj, Status.REVISION, "Add a sourcing plan.")
        svc.submit(idea, self.applicant)
        idea.refresh_from_db()
        self.assertEqual((idea.status, idea.round), (Status.IN_REVIEW, 2))
        self.assertEqual({a.evaluator for a in idea.active_assignments()}, {self.ev1, self.ev2})
        self.assertIsNone(idea.combined_score())  # new round starts with no scores

    def test_evaluation_rules(self):
        idea = complete_idea(self.applicant)
        svc.submit(idea, self.applicant)
        svc.accept_and_assign(idea, self.admin, [self.ev1, self.ev2])
        with self.assertRaises(svc.WorkflowError):  # no conflict declaration
            svc.submit_evaluation(idea, self.ev1, SCORES(4), "Detailed feedback here.", "advance")
        with self.assertRaises(svc.WorkflowError):  # score out of range
            svc.submit_evaluation(idea, self.ev1, SCORES(7), "Detailed feedback here.", "advance", coi_declared=True)
        outsider = make_user("x@example.bw", Role.EVALUATOR)
        with self.assertRaises(svc.WorkflowError):  # not assigned
            svc.submit_evaluation(idea, outsider, SCORES(4), "Detailed feedback here.", "advance", coi_declared=True)

    def test_rubric_snapshot_survives_criteria_changes(self):
        idea = complete_idea(self.applicant)
        self._to_adjudication(idea, scores=(5, 3))
        before = idea.combined_score()
        Criterion.objects.update(weight=1)
        self.assertEqual(idea.combined_score(), before)

    def test_recusal_and_auto_advance(self):
        idea = complete_idea(self.applicant)
        svc.submit(idea, self.applicant)
        svc.accept_and_assign(idea, self.admin, [self.ev1, self.ev2])
        svc.submit_evaluation(idea, self.ev1, SCORES(4), "Clear problem and a working pilot.", "advance", coi_declared=True)
        svc.recuse(idea, self.ev2)
        idea.refresh_from_db()
        self.assertEqual(idea.status, Status.ADJUDICATION)

    def test_only_adjudicators_decide(self):
        idea = complete_idea(self.applicant)
        self._to_adjudication(idea)
        with self.assertRaises(svc.WorkflowError):
            svc.decide(idea, self.admin, Status.APPROVED, "Looks good to me.")

    # --- access control through the web layer ---
    def test_access_rules(self):
        idea = complete_idea(self.applicant)
        url = reverse("ideas:detail", args=[idea.pk])
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertTrue(AuditEvent.objects.filter(action="access.denied", target=idea.reference).exists())

        svc.submit(idea, self.applicant)
        self.client.force_login(self.ev1)
        self.assertEqual(self.client.get(url).status_code, 403)  # not assigned yet
        svc.accept_and_assign(idea, self.admin, [self.ev1, self.ev2])
        svc.submit_evaluation(idea, self.ev2, SCORES(5), "Very strong idea and evidence.", "advance", coi_declared=True)
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Hidden for blind review")
        self.assertNotContains(r, "Score summary")
        self.assertNotContains(r, "Neo (founder)")

        self.client.force_login(self.obs)
        r = self.client.get(url)
        self.assertContains(r, "Observers see progress and scores only")
        self.assertNotContains(r, "Solar-powered cold rooms")

        self.client.force_login(self.applicant)
        self.assertEqual(self.client.get(reverse("ideas:screening")).status_code, 403)

    def test_submitter_web_flow_with_document(self):
        self.client.force_login(self.applicant)
        doc = SimpleUploadedFile("pitch.pdf", b"%PDF-1.4 test", content_type="application/pdf")
        data = dict(
            title="TenderPing", sector="ICT & digital services", maturity="Prototype", location="Gaborone",
            problem="Small businesses miss tenders because notices are scattered across many sites.",
            solution="A WhatsApp and web service that matches tenders to each SME and gives bid templates.",
            beneficiaries="SMEs", impact="More SMEs bidding", jobs=5, budget=150000, sdgs=[8, 9],
            team="Neo (founder)", ip_declared="on", documents=doc, action="submit",
        )
        r = self.client.post(reverse("ideas:new"), data)
        idea = Idea.objects.get(title="TenderPing")
        self.assertRedirects(r, reverse("ideas:detail", args=[idea.pk]))
        self.assertEqual(idea.status, Status.SUBMITTED)
        self.assertEqual(idea.documents.count(), 1)

        # Documents are served only through the access check.
        doc_url = reverse("ideas:document", args=[idea.pk, idea.documents.get().pk])
        self.assertEqual(self.client.get(doc_url).status_code, 200)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(doc_url).status_code, 403)

    def test_rejects_disallowed_file_types(self):
        self.client.force_login(self.applicant)
        bad = SimpleUploadedFile("run.exe", b"MZ", content_type="application/octet-stream")
        r = self.client.post(reverse("ideas:new"), {"title": "X", "documents": bad, "action": "draft"})
        self.assertContains(r, "isn&#x27;t allowed")

    def test_evaluator_and_adjudicator_web_flow(self):
        idea = complete_idea(self.applicant)
        svc.submit(idea, self.applicant)
        self.client.force_login(self.admin)
        r = self.client.post(reverse("ideas:screen", args=[idea.pk]), {"action": "accept", "evaluators": [self.ev1.pk, self.ev2.pk]})
        self.assertRedirects(r, reverse("ideas:screening"))
        for ev in (self.ev1, self.ev2):
            self.client.force_login(ev)
            data = {f"score_{c.pk}": 4 for c in Criterion.objects.all()}
            data.update(coi_declared="on", comment="Strong idea with a clear route to market.", recommendation="advance")
            self.client.post(reverse("ideas:evaluate", args=[idea.pk]), data)
        idea.refresh_from_db()
        self.assertEqual(idea.status, Status.ADJUDICATION)
        self.client.force_login(self.adj)
        self.client.post(reverse("ideas:decide", args=[idea.pk]), {"outcome": "approved", "reason": "Consistent strong scores."})
        self.client.post(reverse("ideas:award", args=[idea.pk]), {"category": "incubation", "message": "Welcome to incubation."})
        idea.refresh_from_db()
        self.assertEqual(idea.status, Status.AWARDED)

    def test_every_page_renders_for_its_role(self):
        idea = complete_idea(self.applicant)
        self._to_adjudication(idea)
        pages = {
            self.applicant: ["ideas:mine", "ideas:new", "ideas:notifications"],
            self.ev1: ["ideas:queue"],
            self.adj: ["ideas:adjudication", "ideas:pipeline"],
            self.admin: ["ideas:screening", "ideas:pipeline", "ideas:adjudication"],
            self.obs: ["ideas:pipeline"],
        }
        for user, names in pages.items():
            self.client.force_login(user)
            for name in names:
                self.assertEqual(self.client.get(reverse(name)).status_code, 200, f"{user.role} {name}")
            self.assertEqual(self.client.get(reverse("ideas:detail", args=[idea.pk])).status_code, 200, user.role)
