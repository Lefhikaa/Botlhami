from datetime import date

from django.db import migrations

# Botswana public holidays for the rest of 2026 and 2027. Check against the Government Gazette each year;
# administrators can add, edit or remove dates in the admin.
HOLIDAYS = [
    (date(2026, 12, 25), "Christmas Day"), (date(2026, 12, 26), "Boxing Day"),
    (date(2027, 1, 1), "New Year's Day"), (date(2027, 1, 2), "New Year Holiday"),
    (date(2027, 3, 26), "Good Friday"), (date(2027, 3, 27), "Holy Saturday"), (date(2027, 3, 29), "Easter Monday"),
    (date(2027, 5, 1), "Labour Day"), (date(2027, 5, 6), "Ascension Day"),
    (date(2027, 7, 1), "Sir Seretse Khama Day"), (date(2027, 7, 19), "President's Day"), (date(2027, 7, 20), "President's Day Holiday"),
    (date(2027, 9, 30), "Botswana Day"), (date(2027, 10, 1), "Botswana Day Holiday"),
    (date(2027, 12, 25), "Christmas Day"), (date(2027, 12, 26), "Boxing Day"),
]


def add(apps, schema_editor):
    PublicHoliday = apps.get_model("chat", "PublicHoliday")
    for d, name in HOLIDAYS:
        PublicHoliday.objects.get_or_create(date=d, defaults={"name": name})
    apps.get_model("chat", "ChatSettings").objects.get_or_create(pk=1)


class Migration(migrations.Migration):
    dependencies = [("chat", "0001_initial")]
    operations = [migrations.RunPython(add, migrations.RunPython.noop)]
