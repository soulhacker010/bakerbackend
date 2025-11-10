# Generated manually by Cascade
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Notification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("read_at", models.DateTimeField(blank=True, null=True)),
                ("event_type", models.CharField(choices=[
                    ("generic", "Generic"),
                    ("client.created", "Client created"),
                    ("assessment.completed", "Assessment completed"),
                    ("schedule.sent", "Schedule sent"),
                ], max_length=64)),
                ("title", models.CharField(max_length=255)),
                ("body", models.TextField(blank=True)),
                ("payload", models.JSONField(blank=True, default=dict, help_text="Arbitrary structured data for client use.")),
                ("recipient", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="notifications", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ("-created_at",),
            },
        ),
        migrations.AddIndex(
            model_name="notification",
            index=models.Index(fields=("recipient", "read_at"), name="notification_read_idx"),
        ),
        migrations.AddIndex(
            model_name="notification",
            index=models.Index(fields=("recipient", "created_at"), name="notification_created_idx"),
        ),
    ]
