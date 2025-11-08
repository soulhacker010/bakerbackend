from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_user_country_user_notify_admin_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="TwoFactorChallenge",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("challenge_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("code_hash", models.CharField(max_length=128)),
                ("code_salt", models.CharField(max_length=32)),
                ("expires_at", models.DateTimeField()),
                ("attempts", models.PositiveSmallIntegerField(default=0)),
                ("last_sent_at", models.DateTimeField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="two_factor_challenges",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.AddIndex(
            model_name="twofactorchallenge",
            index=models.Index(fields=("user", "challenge_id"), name="accounts_tw_user_chal_5b124b_idx"),
        ),
        migrations.AddIndex(
            model_name="twofactorchallenge",
            index=models.Index(fields=("expires_at",), name="accounts_tw_expires_ea2213_idx"),
        ),
    ]
