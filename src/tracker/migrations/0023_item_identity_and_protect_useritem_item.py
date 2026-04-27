import django.db.models.deletion
import django.db.models.functions.text
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tracker", "0022_profile_time_default_layout"),
    ]

    operations = [
        migrations.AlterField(
            model_name="useritem",
            name="item",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to="tracker.item",
            ),
        ),
        migrations.AddConstraint(
            model_name="item",
            constraint=models.UniqueConstraint(
                django.db.models.functions.text.Lower("title"),
                models.F("media_type"),
                name="uniq_item_lower_title_media_type",
            ),
        ),
    ]
