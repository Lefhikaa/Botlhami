"""Give awards made before implementation tracking existed the standard plan, dated from the award."""
from datetime import timedelta

from django.db import migrations

PLAN = [
    ("Accept the award", "Confirm you accept the award and its conditions.", 14),
    ("Onboarding meeting with your CEDA officer", "Agree how you'll work together and how progress is reported.", 30),
    ("Implementation plan and budget agreed", "A month-by-month plan with costs, jobs and the results you expect.", 60),
    ("First progress report", "What's done, what's next, money spent and jobs created so far.", 90),
    ("Six-month review", "Review results with CEDA and adjust the plan if needed.", 180),
    ("Final report and impact results", "Jobs created, revenue and the difference the solution has made.", 365),
]


def forwards(apps, schema_editor):
    Award = apps.get_model("ideas", "Award")
    Milestone = apps.get_model("ideas", "Milestone")
    for award in Award.objects.filter(milestones__isnull=True):
        start = award.granted_at.date()
        Milestone.objects.bulk_create([
            Milestone(award=award, title=t, description=d, due_date=start + timedelta(days=days), order=i)
            for i, (t, d, days) in enumerate(PLAN)
        ])


class Migration(migrations.Migration):
    dependencies = [("ideas", "0004_implementation_milestones")]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
