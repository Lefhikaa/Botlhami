import os
from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

SECTORS = [
    "Agriculture & agro-processing", "Manufacturing", "ICT & digital services", "Financial services & fintech",
    "Energy & water", "Education & skills", "Health", "Tourism & creative industries",
    "Mining & mining services", "Logistics & transport", "Other",
]
MATURITY = ["Concept", "Prototype", "Pilot", "Early revenue", "Scaling"]
LOCATIONS = [
    "Gaborone", "Francistown", "Maun", "Kasane", "Serowe", "Palapye", "Kanye", "Molepolole",
    "Mahalapye", "Lobatse", "Selebi-Phikwe", "Ghanzi", "Tsabong", "Other",
]
SDGS = {
    1: "No poverty", 2: "Zero hunger", 3: "Good health", 4: "Quality education", 5: "Gender equality",
    6: "Clean water & sanitation", 7: "Affordable & clean energy", 8: "Decent work & growth",
    9: "Industry, innovation & infrastructure", 11: "Sustainable cities", 12: "Responsible consumption",
    13: "Climate action",
}


class Status(models.TextChoices):
    DRAFT = "draft", "Draft"
    SUBMITTED = "submitted", "Awaiting screening"
    IN_REVIEW = "in_review", "Under evaluation"
    REVISION = "revision", "Revision requested"
    ADJUDICATION = "adjudication", "In adjudication"
    APPROVED = "approved", "Approved, award pending"
    AWARDED = "awarded", "Awarded"
    REJECTED = "rejected", "Not approved"


# The five stages CEDA asked to track: submission, review, feedback, approval, award.
STAGES = ["Submission", "Review", "Feedback", "Approval", "Award"]
STAGE_INDEX = {
    Status.DRAFT: -1, Status.SUBMITTED: 0, Status.IN_REVIEW: 1, Status.REVISION: 2,
    Status.ADJUDICATION: 3, Status.APPROVED: 4, Status.AWARDED: 5, Status.REJECTED: 3,
}


class WorkflowSettings(models.Model):
    """Single row of settings administrators can change without code."""

    evaluators_per_idea = models.PositiveSmallIntegerField(default=2, validators=[MinValueValidator(1), MaxValueValidator(7)])
    pass_mark = models.PositiveSmallIntegerField(default=65, validators=[MaxValueValidator(100)])
    blind_review = models.BooleanField(default=True, help_text="Hide applicant names from evaluators.")
    score_gap_flag = models.PositiveSmallIntegerField(default=20, help_text="Flag ideas when evaluator scores differ by this many points.")
    screening_days = models.PositiveSmallIntegerField(default=5)
    evaluation_days = models.PositiveSmallIntegerField(default=14)
    adjudication_days = models.PositiveSmallIntegerField(default=7)

    class Meta:
        verbose_name = verbose_name_plural = "Workflow settings"

    def __str__(self):
        return "Workflow settings"

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def target_days(self, status):
        return {
            Status.SUBMITTED: self.screening_days,
            Status.IN_REVIEW: self.evaluation_days,
            Status.ADJUDICATION: self.adjudication_days,
        }.get(status)


class Criterion(models.Model):
    name = models.CharField(max_length=80)
    guidance = models.CharField(max_length=255, help_text="What evaluators should look for.")
    weight = models.PositiveSmallIntegerField(default=20, validators=[MaxValueValidator(100)])
    active = models.BooleanField(default=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]
        verbose_name_plural = "criteria"

    def __str__(self):
        return f"{self.name} ({self.weight}%)"


class Idea(models.Model):
    reference = models.CharField(max_length=20, unique=True, blank=True)
    submitter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="ideas")
    title = models.CharField(max_length=120)
    sector = models.CharField(max_length=60, blank=True, choices=[(s, s) for s in SECTORS])
    maturity = models.CharField("stage of development", max_length=30, blank=True, choices=[(m, m) for m in MATURITY])
    location = models.CharField(max_length=40, blank=True, choices=[(loc, loc) for loc in LOCATIONS])
    problem = models.TextField(blank=True)
    solution = models.TextField(blank=True)
    beneficiaries = models.CharField("who benefits", max_length=255, blank=True)
    impact = models.TextField("expected impact", blank=True)
    jobs = models.PositiveIntegerField("jobs expected within 24 months", null=True, blank=True)
    budget = models.DecimalField("estimated budget (BWP)", max_digits=12, decimal_places=2, null=True, blank=True)
    sdgs = models.JSONField(default=list, blank=True)
    team = models.TextField("team members and roles", blank=True)
    ip_declared = models.BooleanField(default=False)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    round = models.PositiveSmallIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    status_changed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-status_changed_at"]

    def __str__(self):
        return f"{self.reference} {self.title}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.reference:
            self.reference = f"IDX-{self.created_at:%Y}-{self.pk:04d}"
            super().save(update_fields=["reference"])

    # --- completeness -------------------------------------------------
    def missing_items(self):
        """Mandatory items still missing before the idea can be submitted."""
        checks = [
            ("Title", bool(self.title.strip())),
            ("Sector", bool(self.sector)),
            ("Stage of development", bool(self.maturity)),
            ("Location", bool(self.location)),
            ("Problem (at least 50 characters)", len(self.problem.strip()) >= 50),
            ("Solution (at least 50 characters)", len(self.solution.strip()) >= 50),
            ("Who benefits", bool(self.beneficiaries.strip())),
            ("Expected impact", bool(self.impact.strip())),
            ("Jobs expected", self.jobs is not None),
            ("Estimated budget", self.budget is not None),
            ("At least one SDG", bool(self.sdgs)),
            ("Team members and roles", bool(self.team.strip())),
            ("Originality and IP declaration", self.ip_declared),
        ]
        return [label for label, ok in checks if not ok]

    # --- workflow -----------------------------------------------------
    @property
    def stage_index(self):
        return STAGE_INDEX[self.status]

    @property
    def editable_by_submitter(self):
        return self.status in (Status.DRAFT, Status.REVISION)

    def set_status(self, new_status, actor=None, note=""):
        old = self.status
        self.status = new_status
        self.status_changed_at = timezone.now()
        if new_status == Status.SUBMITTED and not self.submitted_at:
            self.submitted_at = self.status_changed_at
        self.save()
        StatusEvent.objects.create(idea=self, from_status=old, to_status=new_status, actor=actor, note=note)

    def days_in_status(self):
        return (timezone.now() - self.status_changed_at).days

    def is_overdue(self, ws=None):
        target = (ws or WorkflowSettings.get()).target_days(self.status)
        return bool(target and self.days_in_status() > target)

    def active_assignments(self):
        return self.assignments.filter(round=self.round, recused=False).select_related("evaluator")

    def round_evaluations(self):
        return self.evaluations.filter(round=self.round).select_related("evaluator")

    def combined_score(self):
        scores = [e.total for e in self.round_evaluations()]
        return round(sum(scores) / len(scores)) if scores else None

    def score_gap(self):
        scores = [e.total for e in self.round_evaluations()]
        return max(scores) - min(scores) if len(scores) > 1 else 0

    def all_evaluations_in(self):
        assigned = set(self.active_assignments().values_list("evaluator_id", flat=True))
        done = set(self.round_evaluations().values_list("evaluator_id", flat=True))
        return bool(assigned) and assigned <= done


def document_path(instance, filename):
    base, ext = os.path.splitext(filename)
    return f"ideas/{instance.idea_id}/{timezone.now():%Y%m%d%H%M%S}{ext.lower()}"


class IdeaDocument(models.Model):
    ALLOWED = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".png", ".jpg", ".jpeg"}
    MAX_BYTES = 10 * 1024 * 1024

    idea = models.ForeignKey(Idea, on_delete=models.CASCADE, related_name="documents")
    file = models.FileField(upload_to=document_path)
    original_name = models.CharField(max_length=200)
    size = models.PositiveIntegerField()
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.original_name


class Assignment(models.Model):
    idea = models.ForeignKey(Idea, on_delete=models.CASCADE, related_name="assignments")
    evaluator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="assignments")
    round = models.PositiveSmallIntegerField()
    assigned_at = models.DateTimeField(auto_now_add=True)
    due_at = models.DateTimeField()
    recused = models.BooleanField(default=False)

    class Meta:
        unique_together = [("idea", "evaluator", "round")]


class Evaluation(models.Model):
    class Recommendation(models.TextChoices):
        ADVANCE = "advance", "Advance"
        REVISE = "revise", "Revise and resubmit"
        DECLINE = "decline", "Decline"

    idea = models.ForeignKey(Idea, on_delete=models.CASCADE, related_name="evaluations")
    evaluator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="evaluations")
    round = models.PositiveSmallIntegerField()
    rubric = models.JSONField(help_text="The criteria and weights in force when this was scored.")
    scores = models.JSONField(help_text="{criterion id: score 1-5}")
    comment = models.TextField("feedback for the applicant")
    private_note = models.TextField("private note for adjudicators", blank=True)
    recommendation = models.CharField(max_length=10, choices=Recommendation.choices)
    coi_declared = models.BooleanField(default=False)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("idea", "evaluator", "round")]
        ordering = ["round", "submitted_at"]

    @property
    def total(self):
        """Weighted score out of 100."""
        weight_sum = Decimal(0)
        points = Decimal(0)
        for c in self.rubric:
            s = self.scores.get(str(c["id"]))
            if s:
                weight_sum += c["weight"]
                points += Decimal(s) / 5 * c["weight"]
        return int(round(points / weight_sum * 100)) if weight_sum else 0

    def criterion_scores(self):
        return [(c["name"], c["weight"], self.scores.get(str(c["id"]))) for c in self.rubric]


class Message(models.Model):
    idea = models.ForeignKey(Idea, on_delete=models.CASCADE, related_name="messages")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class StatusEvent(models.Model):
    idea = models.ForeignKey(Idea, on_delete=models.CASCADE, related_name="history")
    from_status = models.CharField(max_length=20, choices=Status.choices)
    to_status = models.CharField(max_length=20, choices=Status.choices)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    note = models.TextField(blank=True)
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["at", "id"]


class Award(models.Model):
    CATEGORIES = [
        ("seed", "Seed funding referral"),
        ("incubation", "Incubation and mentorship placement"),
        ("champion", "Innovation Champion recognition"),
        ("pilot", "Pilot partnership with CEDA"),
    ]
    idea = models.OneToOneField(Idea, on_delete=models.CASCADE, related_name="award")
    category = models.CharField(max_length=20, choices=CATEGORIES)
    amount = models.DecimalField("value (BWP)", max_digits=12, decimal_places=2, null=True, blank=True)
    message = models.TextField("message to the applicant")
    granted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    granted_at = models.DateTimeField(auto_now_add=True)
    officer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name="awards_supported", verbose_name="CEDA officer",
                                help_text="The person who supports the applicant during implementation.")

    def progress(self):
        ms = list(self.milestones.all())
        done = sum(1 for m in ms if m.status == Milestone.Status.DONE)
        return {"done": done, "total": len(ms), "pct": round(done * 100 / len(ms)) if ms else 0,
                "overdue": sum(1 for m in ms if m.overdue), "at_risk": sum(1 for m in ms if m.status == Milestone.Status.AT_RISK),
                "next": next((m for m in ms if m.status != Milestone.Status.DONE), None)}


class Milestone(models.Model):
    """A step in putting an awarded idea into practice. The applicant reports progress; CEDA confirms."""

    class Status(models.TextChoices):
        PLANNED = "planned", "Not started"
        IN_PROGRESS = "in_progress", "In progress"
        AT_RISK = "at_risk", "At risk"
        DONE = "done", "Done"

    award = models.ForeignKey(Award, on_delete=models.CASCADE, related_name="milestones")
    title = models.CharField(max_length=150)
    description = models.CharField(max_length=255, blank=True)
    due_date = models.DateField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PLANNED)
    update = models.TextField("latest update", blank=True)
    updated_at = models.DateTimeField(null=True, blank=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    confirmed_at = models.DateTimeField(null=True, blank=True)
    confirmed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "due_date", "id"]

    def __str__(self):
        return self.title

    @property
    def overdue(self):
        return self.status != self.Status.DONE and self.due_date < timezone.localdate()

    @property
    def awaiting_confirmation(self):
        return self.status == self.Status.DONE and not self.confirmed_at


class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    idea = models.ForeignKey(Idea, on_delete=models.CASCADE, null=True, blank=True)
    text = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
