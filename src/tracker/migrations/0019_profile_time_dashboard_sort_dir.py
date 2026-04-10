from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tracker", "0018_profile_time_dashboard_expand_depth"),
    ]

    operations = [
        migrations.AddField(
            model_name="profile",
            name="time_dashboard_sort_dir",
            field=models.CharField(default="desc", max_length=4),
        ),
    ]
