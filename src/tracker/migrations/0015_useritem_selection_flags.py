from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tracker", "0014_useritem_is_pinned"),
    ]

    operations = [
        migrations.AddField(
            model_name="useritem",
            name="is_redoing",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="useritem",
            name="is_endless",
            field=models.BooleanField(default=False),
        ),
    ]
