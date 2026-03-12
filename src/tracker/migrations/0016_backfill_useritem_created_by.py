from django.db import migrations, models


def backfill_created_by(apps, schema_editor):
    UserItem = apps.get_model("tracker", "UserItem")
    UserItem.objects.filter(created_by__isnull=True).update(created_by=models.F("user"))


class Migration(migrations.Migration):
    dependencies = [
        ("tracker", "0015_useritem_selection_flags"),
    ]

    operations = [
        migrations.RunPython(backfill_created_by, migrations.RunPython.noop),
    ]
