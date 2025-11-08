from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0003_twofactorchallenge"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="results_copy_email",
            field=models.EmailField(blank=True, max_length=254),
        ),
        migrations.AddField(
            model_name="user",
            name="results_delivery_format",
            field=models.CharField(
                choices=[("link", "Send as secure link"), ("attachment", "Send as PDF attachment")],
                default="link",
                max_length=16,
            ),
        ),
    ]
