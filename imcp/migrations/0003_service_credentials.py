from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("imcp", "0002_toolcachemetadata_generated_at_default"),
    ]

    operations = [
        migrations.AddField(
            model_name="service",
            name="credentials_enc",
            field=models.TextField(blank=True, null=True),
        ),
    ]
