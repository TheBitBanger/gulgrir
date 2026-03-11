from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tracker", "0013_timelayout_timebucket_timebucketassignment"),
    ]

    operations = [
        migrations.AddField(
            model_name="useritem",
            name="is_pinned",
            field=models.BooleanField(default=False),
        ),
    ]
