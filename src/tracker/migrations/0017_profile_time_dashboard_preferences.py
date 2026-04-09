from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tracker", "0016_backfill_useritem_created_by"),
    ]

    operations = [
        migrations.AddField(
            model_name="profile",
            name="time_dashboard_mode",
            field=models.CharField(blank=True, default="", max_length=16),
        ),
        migrations.AddField(
            model_name="profile",
            name="time_dashboard_window_key",
            field=models.CharField(blank=True, default="", max_length=32),
        ),
        migrations.AddField(
            model_name="profile",
            name="time_dashboard_range_start",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="profile",
            name="time_dashboard_range_end",
            field=models.DateField(blank=True, null=True),
        ),
    ]
