from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tracker", "0017_profile_time_dashboard_preferences"),
    ]

    operations = [
        migrations.AddField(
            model_name="profile",
            name="time_dashboard_expand_depth",
            field=models.PositiveSmallIntegerField(default=3),
        ),
    ]
