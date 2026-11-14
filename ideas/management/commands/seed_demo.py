"""Create demo accounts and sample ideas so judges can try every role.

Usage: python manage.py seed_demo --password "<shared demo password>"
All people and ideas are fictional.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import Role, User
from ideas import services as svc
from ideas.models import Criterion, Idea, Status

PEOPLE = [
    ("neo.kgosi@demo.botlhami.bw", "Neo", "Kgosi", Role.SUBMITTER, "Kgosi AgriTech"),
    ("onalenna.dube@demo.botlhami.bw", "Onalenna", "Dube", Role.SUBMITTER, "Dube Foods"),
    ("tumelo.phiri@demo.botlhami.bw", "Tumelo", "Phiri", Role.SUBMITTER, "Phiri Systems"),
    ("mpho.sebina@demo.botlhami.bw", "Mpho", "Sebina", Role.EVALUATOR, "Innovation Committee"),
    ("thato.kenosi@demo.botlhami.bw", "Thato", "Kenosi", Role.EVALUATOR, "Innovation Committee"),
    ("lorato.mosweu@demo.botlhami.bw", "Lorato", "Mosweu", Role.EVALUATOR, "External expert panel"),
    ("kefilwe.tau@demo.botlhami.bw", "Kefilwe", "Tau", Role.ADJUDICATOR, "Adjudication panel"),
    ("goitseone.modise@demo.botlhami.bw", "Goitseone", "Modise", Role.ADMIN, "Innovation Office"),
    ("masego.ntsima@demo.botlhami.bw", "Masego", "Ntsima", Role.OBSERVER, "Innovation Committee"),
    ("kabo.molefe@demo.botlhami.bw", "Kabo", "Molefe", Role.CONSULTANT, "CEDA customer service"),
]

IDEAS = [
    ("neo", dict(title="SolarCool: solar cold rooms for horticulture farmers", sector="Energy & water", maturity="Pilot", location="Gaborone",
        problem="Smallholder farmers lose much of their produce before it reaches buyers because they have no cold storage near their fields.",
        solution="Containerised cold rooms powered by solar panels, rented per crate per day at farmer collection points and paid by mobile money.",
        beneficiaries="Smallholder horticulture farmers", impact="Less post-harvest loss and steadier income; technician jobs.", jobs=12, budget=480000, sdgs=[2, 7, 8],
        team="Neo Kgosi (founder)\nTwo refrigeration technicians"), "awarded"),
    ("onalenna", dict(title="Morula Gold: value-added morula products", sector="Agriculture & agro-processing", maturity="Prototype", location="Serowe",
        problem="Morula fruit is harvested by rural women but mostly sold raw at low prices, and much of the crop goes to waste.",
        solution="A small processing unit turning morula into juice concentrate, jam and cosmetic oil, buying from harvester cooperatives.",
        beneficiaries="Rural women harvesters", impact="Higher, predictable harvester income.", jobs=15, budget=390000, sdgs=[1, 5, 8],
        team="Onalenna Dube (founder, food technologist)"), "revision"),
    ("tumelo", dict(title="BoreSense: remote monitoring for village boreholes", sector="Energy & water", maturity="Pilot", location="Kanye",
        problem="Borehole pumps fail without warning and are only reported when taps run dry, leaving villages without water for days.",
        solution="Low-cost sensors on pumps send water-level and pump-health readings to a maintenance dashboard and SMS alerts.",
        beneficiaries="Rural communities and councils", impact="Fewer, shorter outages; technician jobs.", jobs=8, budget=310000, sdgs=[6, 9, 11],
        team="Tumelo Phiri (founder, electrical engineer)"), "half"),
    ("neo", dict(title="TenderPing: tender alerts for SMEs", sector="ICT & digital services", maturity="Prototype", location="Gaborone",
        problem="Small citizen-owned businesses miss public tenders because notices are scattered and bid documents are hard to prepare.",
        solution="A WhatsApp and web service that matches tenders to each SME's sectors and provides bid checklists and templates.",
        beneficiaries="Citizen-owned SMEs", impact="More SMEs bidding for and winning contracts.", jobs=5, budget=150000, sdgs=[8, 9],
        team="Neo Kgosi (founder)\nFull-stack developer"), "submitted"),
]


class Command(BaseCommand):
    help = "Create demo users for every role and sample ideas at different stages."

    def add_arguments(self, parser):
        parser.add_argument("--password", required=True, help="Password for every demo account.")

    @transaction.atomic
    def handle(self, *args, password, **opts):
        users = {}
        for email, first, last, role, org in PEOPLE:
            u, _ = User.objects.get_or_create(email=email, defaults=dict(first_name=first, last_name=last, role=role, organisation=org, email_verified=True))
            u.set_password(password)
            u.save()
            users[first.lower()] = u
        if Idea.objects.exists():
            self.stdout.write("Ideas already exist; only demo users were refreshed.")
            return
        scores = lambda v: {str(c.pk): v for c in Criterion.objects.filter(active=True)}  # noqa: E731
        admin, adj, ev1, ev2 = users["goitseone"], users["kefilwe"], users["mpho"], users["thato"]
        for who, data, stage in IDEAS:
            idea = Idea.objects.create(submitter=users[who], ip_declared=True, **data)
            svc.submit(idea, idea.submitter)
            if stage == "submitted":
                continue
            svc.accept_and_assign(idea, admin, [ev1, ev2])
            svc.submit_evaluation(idea, ev1, scores(4), "Clear problem and a credible plan. Show unit costs next.", "advance", coi_declared=True)
            if stage == "half":
                continue
            svc.submit_evaluation(idea, ev2, scores(5 if stage == "awarded" else 3), "Strong social impact; sourcing and costs need more detail.",
                                  "advance" if stage == "awarded" else "revise", coi_declared=True)
            if stage == "awarded":
                svc.decide(idea, adj, Status.APPROVED, "Strong pilot evidence and clear job creation.")
                svc.grant_award(idea, adj, "seed", "Referred to CEDA financing with incubation support.", 250000)
            elif stage == "revision":
                svc.decide(idea, adj, Status.REVISION, "Add a seasonal sourcing plan and a cost-per-unit estimate, then resubmit.")
        self.stdout.write(self.style.SUCCESS(f"Created {len(PEOPLE)} demo users and {len(IDEAS)} ideas."))
