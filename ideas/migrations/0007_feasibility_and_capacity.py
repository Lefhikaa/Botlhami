"""Rename Feasibility to 'Feasibility and implementation capacity' (team feedback, 20 November 2026).

The weight stays at 15%, so the six criteria still total 100%. Past evaluations keep
their stored rubric, so their criterion names don't change.
"""
from django.db import migrations

NEW = "Feasibility and implementation capacity"
GUIDANCE = ("Can the team deliver it? Look at their skills and experience, the resources already in place, "
            "partners, and how they'll fill any gaps, as well as realistic costs and timelines.")


def forwards(apps, schema_editor):
    Criterion = apps.get_model("ideas", "Criterion")
    Criterion.objects.filter(name="Feasibility").update(name=NEW, guidance=GUIDANCE)


def backwards(apps, schema_editor):
    Criterion = apps.get_model("ideas", "Criterion")
    Criterion.objects.filter(name=NEW).update(name="Feasibility")


class Migration(migrations.Migration):
    dependencies = [("ideas", "0006_implementation_capacity")]
    operations = [migrations.RunPython(forwards, backwards)]
