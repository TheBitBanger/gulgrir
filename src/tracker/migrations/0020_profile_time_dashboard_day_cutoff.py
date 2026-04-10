from datetime import time

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tracker", "0019_profile_time_dashboard_sort_dir"),
    ]

    operations = [
        migrations.AddField(
            model_name="profile",
            name="time_dashboard_day_cutoff",
            field=models.TimeField(default=time(0, 0)),
        ),
    ]
