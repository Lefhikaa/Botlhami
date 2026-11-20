"""Create demo accounts and sample ideas so judges can try every role.

Usage: python manage.py seed_demo --password "<shared demo password>"
All people and ideas are fictional.
"""
from datetime import timedelta

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import Role, User
from ideas import services as svc
from ideas.models import Criterion, Idea, Notification, Status, StatusEvent
from support.models import Resource, ServiceLevel, Ticket

# Days each demo idea spent in each status, so the reports show realistic timelines.
DAYS_IN = {Status.SUBMITTED: 3, Status.IN_REVIEW: 10, Status.ADJUDICATION: 4, Status.APPROVED: 2, Status.REVISION: 0}

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

# Scores per criterion, in this order: innovation, market, feasibility, impact, strategic alignment, scalability.
CRITERIA_ORDER = ["Innovation and originality", "Market potential", "Feasibility", "Economic and social impact",
                  "Strategic alignment with CEDA", "Scalability"]

IDEAS = [
    ("neo", dict(title="SolarCool: solar cold rooms for horticulture farmers", sector="Energy & water", maturity="Pilot", location="Gaborone",
        problem="Smallholder farmers lose much of their produce before it reaches buyers because they have no cold storage near their fields.",
        solution="Containerised cold rooms powered by solar panels, rented per crate per day at farmer collection points and paid by mobile money.",
        beneficiaries="Smallholder horticulture farmers", impact="Less post-harvest loss and steadier income; technician jobs.", jobs=12, budget=480000, sdgs=[2, 7, 8],
        team="Neo Kgosi (founder)\nTwo refrigeration technicians"), "awarded", [
        ("mpho", (5, 4, 4, 5, 4, 4), "advance", "Clear problem with pilot evidence. The rental model fits farmers' cash flow."),
        ("thato", (4, 5, 4, 4, 5, 4), "advance", "Strong demand and good fit with CEDA's agriculture focus. Show unit costs per crate.")]),
    ("onalenna", dict(title="Morula Gold: value-added morula products", sector="Agriculture & agro-processing", maturity="Prototype", location="Serowe",
        problem="Morula fruit is harvested by rural women but mostly sold raw at low prices, and much of the crop goes to waste.",
        solution="A small processing unit turning morula into juice concentrate, jam and cosmetic oil, buying from harvester cooperatives.",
        beneficiaries="Rural women harvesters", impact="Higher, predictable harvester income.", jobs=15, budget=390000, sdgs=[1, 5, 8],
        team="Onalenna Dube (founder, food technologist)"), "revision", [
        ("mpho", (3, 4, 2, 4, 4, 3), "revise", "Strong social impact, but the sourcing plan across seasons is unclear."),
        ("thato", (3, 3, 2, 4, 3, 2), "revise", "Promising products. Add cost per unit and a plan for the months without fruit.")]),
    ("tumelo", dict(title="BoreSense: remote monitoring for village boreholes", sector="Energy & water", maturity="Pilot", location="Kanye",
        problem="Borehole pumps fail without warning and are only reported when taps run dry, leaving villages without water for days.",
        solution="Low-cost sensors on pumps send water-level and pump-health readings to a maintenance dashboard and SMS alerts.",
        beneficiaries="Rural communities and councils", impact="Fewer, shorter outages; technician jobs.", jobs=8, budget=310000, sdgs=[6, 9, 11],
        team="Tumelo Phiri (founder, electrical engineer)"), "half", [
        ("mpho", (4, 4, 4, 5, 4, 4), "advance", "A real public need with a credible pilot. Councils are a clear buyer.")]),
    ("neo", dict(title="TenderPing: tender alerts for SMEs", sector="ICT & digital services", maturity="Prototype", location="Gaborone",
        problem="Small citizen-owned businesses miss public tenders because notices are scattered and bid documents are hard to prepare.",
        solution="A WhatsApp and web service that matches tenders to each SME's sectors and provides bid checklists and templates.",
        beneficiaries="Citizen-owned SMEs", impact="More SMEs bidding for and winning contracts.", jobs=5, budget=150000, sdgs=[8, 9],
        team="Neo Kgosi (founder)\nFull-stack developer"), "submitted", []),
    ("tumelo", dict(title="Thuto Pocket: offline maths tutor on basic phones", sector="Education & skills", maturity="Prototype", location="Maun",
        problem="Many secondary pupils outside the cities have no tutor and no data bundles, so they fall behind in maths.",
        solution="Short maths lessons and quizzes delivered by USSD and SMS, which work on any phone without data, with weekly progress reports for teachers.",
        beneficiaries="Secondary school pupils and teachers", impact="Better maths results; local content jobs.", jobs=6, budget=220000, sdgs=[4, 10],
        team="Tumelo Phiri (founder)\nTwo maths teachers"), "adjudication", [
        ("mpho", (5, 4, 3, 5, 4, 5), "advance", "Genuinely new for Botswana and could reach every district. Needs a partner school pilot."),
        ("thato", (2, 3, 3, 3, 3, 2), "decline", "Similar SMS tutoring has been tried. I'm not convinced pupils will pay or schools will adopt it.")]),
    ("onalenna", dict(title="Kgomo Trace: cattle traceability with low-cost tags", sector="Agriculture & agro-processing", maturity="Pilot", location="Francistown",
        problem="Small cattle farmers struggle to prove where their animals come from, which keeps them out of higher-paying export markets.",
        solution="Low-cost tags read by a phone app record each animal's movements and treatments, ready for buyers and inspectors.",
        beneficiaries="Small and emerging cattle farmers", impact="Access to export prices; fewer disputes over stock.", jobs=10, budget=360000, sdgs=[1, 8, 9],
        team="Onalenna Dube (founder)\nVeterinary adviser"), "adjudication", [
        ("mpho", (4, 5, 4, 4, 5, 4), "advance", "Strong market pull from export buyers and a clear fit with CEDA's agriculture priorities."),
        ("lorato", (4, 4, 4, 4, 5, 5), "advance", "Well-run pilot. Scales easily to other districts and to neighbouring countries.")]),
    ("neo", dict(title="Sebaka: shipping-container co-working spaces", sector="Other", maturity="Concept", location="Palapye",
        problem="Young freelancers in smaller towns have nowhere affordable to work with reliable power and internet.",
        solution="Converted shipping containers fitted out as co-working spaces, rented by the day or month.",
        beneficiaries="Freelancers and young entrepreneurs", impact="Affordable workspace in smaller towns.", jobs=3, budget=280000, sdgs=[8, 11],
        team="Neo Kgosi (founder)"), "adjudication", [
        ("thato", (2, 2, 3, 2, 2, 2), "decline", "Co-working spaces already exist, and demand in Palapye isn't shown."),
        ("lorato", (2, 3, 2, 2, 2, 2), "decline", "Needs evidence of demand and a cheaper way to start, such as renting an existing building.")]),
]


class Command(BaseCommand):
    help = "Create demo users for every role and sample ideas at different stages."

    def add_arguments(self, parser):
        parser.add_argument("--password", required=True, help="Password for every demo account.")
        parser.add_argument("--reset-ideas", action="store_true",
                            help="Delete the demo applicants' ideas (and their evaluations and alerts) and create them again.")

    @transaction.atomic
    def handle(self, *args, password, reset_ideas=False, **opts):
        users = {}
        for email, first, last, role, org in PEOPLE:
            u, _ = User.objects.get_or_create(email=email, defaults=dict(first_name=first, last_name=last, role=role, organisation=org, email_verified=True))
            u.set_password(password)
            u.save()
            users[first.lower()] = u
        self.seed_support(users)
        if reset_ideas:
            demo_ideas = Idea.objects.filter(submitter__email__endswith="@demo.botlhami.bw")
            Notification.objects.filter(idea__in=demo_ideas).delete()
            n = demo_ideas.count()
            demo_ideas.delete()
            self.stdout.write(f"Deleted {n} demo ideas.")
        if Idea.objects.exists():
            self.stdout.write("Ideas already exist; only demo users and help content were refreshed.")
            return
        crit = {c.name: c for c in Criterion.objects.filter(active=True)}
        admin, adj = users["goitseone"], users["kefilwe"]
        for who, data, stage, evals in IDEAS:
            idea = Idea.objects.create(submitter=users[who], ip_declared=True, **data)
            svc.submit(idea, idea.submitter)
            if stage == "submitted":
                continue
            svc.accept_and_assign(idea, admin, [users[e[0]] for e in evals] if stage != "half" else [users["mpho"], users["thato"]])
            for ev, vals, rec, comment in evals:
                scores = {str(crit[name].pk): v for name, v in zip(CRITERIA_ORDER, vals) if name in crit}
                svc.submit_evaluation(idea, users[ev], scores, comment, rec, coi_declared=True)
            if stage == "awarded":
                svc.decide(idea, adj, Status.APPROVED, "Strong pilot evidence and clear job creation.")
                svc.grant_award(idea, adj, "seed", "Referred to CEDA financing with incubation support.", 250000)
            elif stage == "revision":
                svc.decide(idea, adj, Status.REVISION, "Add a seasonal sourcing plan and a cost-per-unit estimate, then resubmit.")
        for n, idea in enumerate(Idea.objects.order_by("pk")):
            self.backdate(idea, start_days_ago=[48, 36, 20, 2, 15, 12, 10][n % 7])
        self.stdout.write(self.style.SUCCESS(f"Created {len(PEOPLE)} demo users and {len(IDEAS)} ideas."))

    @staticmethod
    def backdate(idea, start_days_ago):
        """Spread an idea's status history over past days (the seed runs it all in one second)."""
        at = timezone.now() - timedelta(days=start_days_ago)
        events = list(StatusEvent.objects.filter(idea=idea).order_by("at", "id"))
        for e in events:
            StatusEvent.objects.filter(pk=e.pk).update(at=at)
            if e.to_status == Status.SUBMITTED and e.from_status == Status.DRAFT:
                Idea.objects.filter(pk=idea.pk).update(submitted_at=at)
            last = at
            at = min(at + timedelta(days=DAYS_IN.get(e.to_status, 1), hours=5), timezone.now())
        if events:
            Idea.objects.filter(pk=idea.pk).update(status_changed_at=last)

    def seed_support(self, users):
        if not Resource.objects.exists():
            for title, kind, mandatory, desc, lines in DOCS:
                r = Resource(title=title, kind=kind, mandatory=mandatory, description=desc, updated_by=users["goitseone"])
                pdf = simple_pdf(title, lines)
                name = title.lower().replace(" ", "-").replace(",", "") + ".pdf"
                r.file.save(name, ContentFile(pdf), save=False)
                r.original_name, r.size = name, len(pdf)
                r.save()
        if Ticket.objects.exists():
            return
        lv = {lvl.severity: lvl for lvl in ServiceLevel.objects.all()}
        kabo, admin = users["kabo"], users["goitseone"]
        for who, subject, area, sev, desc, days_ago, outcome in TICKETS:
            t = Ticket.objects.create(raised_by=users[who], subject=subject, area=area, level=lv[sev], description=desc)
            made = timezone.now() - timedelta(days=days_ago)
            fields = dict(created_at=made, response_due=made + timedelta(hours=t.level.response_hours),
                          resolution_due=made + timedelta(hours=t.level.resolution_hours))
            if outcome:
                reply_after, fix_after, text = outcome
                reply = t.replies.create(author=kabo, body=text)
                type(reply).objects.filter(pk=reply.pk).update(created_at=made + timedelta(hours=reply_after))
                fields.update(first_response_at=made + timedelta(hours=reply_after), assigned_to=kabo)
                if fix_after:
                    fields.update(resolved_at=made + timedelta(hours=fix_after), status=Ticket.Status.RESOLVED)
                else:
                    fields.update(status=Ticket.Status.IN_PROGRESS)
            Ticket.objects.filter(pk=t.pk).update(**fields)


DOCS = [
    ("Innovation application form", Resource.Kind.APPLICATION_FORM, False,
     "The full application form. You can complete the same questions online when you submit an idea.",
     ["Section 1: The idea - title, sector, stage of development, location",
      "Section 2: The problem and your solution",
      "Section 3: Impact - who benefits, jobs expected, budget, SDGs",
      "Section 4: Team members and roles",
      "Section 5: Originality and IP declaration"]),
    ("Business plan template", Resource.Kind.TEMPLATE, True,
     "Use this structure for the business plan you upload with your idea.",
     ["1. Executive summary", "2. Market and customers", "3. Product or service",
      "4. Operations and team", "5. Financial projections for 3 years", "6. Funding required and its use"]),
    ("Supporting documents checklist", Resource.Kind.REQUIRED, True,
     "The documents to upload with your idea.",
     ["Certified copy of national ID (Omang) for each owner",
      "Company registration certificate from CIPA, if registered",
      "Business plan (use the template)",
      "Any evidence of pilots, letters of support or sales"]),
]

TICKETS = [
    ("neo", "Upload failed for my business plan", "documents", "high",
     "I get an error when uploading a 12 MB PDF to my idea.", 9,
     (2, 6, "Files must be 10 MB or smaller. Compressing the PDF fixed it - thanks for confirming.")),
    ("onalenna", "Didn't receive the sign-in code", "access", "medium",
     "I chose 'email me a code' but nothing arrived.", 5,
     (3, 20, "The email was in your spam folder. We've added guidance to the sign-in page.")),
    ("tumelo", "Question about the evaluation criteria", "evaluation", "low",
     "Can I see how each criterion is weighted before I submit?", 1,
     (6, None, "Yes - the criteria and weights are listed in the Help centre. We're adding them to the form too.")),
    ("neo", "Page is slow when opening my idea", "submission", "medium",
     "Opening my idea takes a long time on mobile data.", 0, None),
]


def simple_pdf(title, lines):
    """A minimal one-page PDF, so the demo has real files to download."""
    def esc(t):
        return t.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    text = [f"BT /F1 20 Tf 60 770 Td ({esc(title)}) Tj ET", "BT /F1 10 Tf 60 748 Td (Botlhami demo document - replace with the official CEDA version.) Tj ET"]
    y = 715
    for line in lines:
        text.append(f"BT /F1 12 Tf 60 {y} Td ({esc(line)}) Tj ET")
        y -= 22
    stream = "\n".join(text).encode("latin-1", "replace")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)
