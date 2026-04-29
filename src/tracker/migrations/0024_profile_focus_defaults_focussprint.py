from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("tracker", "0023_item_identity_and_protect_useritem_item"),
    ]

    operations = [
        migrations.AddField(
            model_name="profile",
            name="focus_default_overflow_soft_cap_minutes",
            field=models.PositiveIntegerField(default=300),
        ),
        migrations.AddField(
            model_name="profile",
            name="focus_default_target_minutes",
            field=models.PositiveIntegerField(default=720),
        ),
        migrations.CreateModel(
            name="FocusSprint",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "scope_type",
                    models.CharField(
                        choices=[("bucket", "Bucket"), ("item", "Item")],
                        max_length=16,
                    ),
                ),
                ("target_minutes", models.PositiveIntegerField(default=720)),
                (
                    "overflow_soft_cap_minutes",
                    models.PositiveIntegerField(default=300),
                ),
                ("started_at", models.DateTimeField(auto_now_add=True)),
                ("closed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "time_bucket",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="focus_sprints",
                        to="tracker.timebucket",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="focus_sprints",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "user_item",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="focus_sprints",
                        to="tracker.useritem",
                    ),
                ),
            ],
            options={"ordering": ("-started_at",)},
        ),
    ]
