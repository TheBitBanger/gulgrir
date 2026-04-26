from django.db import migrations, models


def forward_backfill_assignment_mode(apps, schema_editor):
    assignment_model = apps.get_model("tracker", "TimeBucketAssignment")
    db_alias = schema_editor.connection.alias

    assignment_model.objects.using(db_alias).filter(is_ignored=True).update(
        assignment_mode="ignored"
    )
    assignment_model.objects.using(db_alias).filter(
        is_ignored=False,
        bucket_id__isnull=False,
    ).update(assignment_mode="bucket")
    assignment_model.objects.using(db_alias).filter(
        is_ignored=False,
        bucket_id__isnull=True,
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("tracker", "0020_profile_time_dashboard_day_cutoff"),
    ]

    operations = [
        migrations.AddField(
            model_name="timebucketassignment",
            name="assignment_mode",
            field=models.CharField(
                choices=[
                    ("bucket", "Bucket"),
                    ("top_level", "Top level"),
                    ("ignored", "Ignored"),
                ],
                default="bucket",
                max_length=16,
            ),
        ),
        migrations.RunPython(
            forward_backfill_assignment_mode,
            migrations.RunPython.noop,
        ),
        migrations.RemoveField(
            model_name="timebucketassignment",
            name="is_ignored",
        ),
    ]
