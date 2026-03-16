"""Migration: change generated_at from auto_now_add to a regular DateTimeField with default."""
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("imcp", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="toolcachemetadata",
            name="generated_at",
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
    ]
