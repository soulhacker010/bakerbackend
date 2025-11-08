from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0004_results_delivery_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="PasswordResetToken",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("token_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("token_hash", models.CharField(max_length=128, unique=True)),
                ("token_salt", models.CharField(max_length=32)),
                ("expires_at", models.DateTimeField()),
                ("used_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="password_reset_tokens",
                        to="accounts.user",
                    ),
                ),
            ],
            options={
                "ordering": ("-created_at",),
            },
        ),
        migrations.AddIndex(
            model_name="passwordresettoken",
            index=models.Index(fields=("user", "created_at"), name="accounts_pa_user_id_f22042_idx"),
        ),
        migrations.AddIndex(
            model_name="passwordresettoken",
            index=models.Index(fields=("expires_at",), name="accounts_pa_expires_1ccf75_idx"),
        ),
        migrations.AddIndex(
            model_name="passwordresettoken",
            index=models.Index(fields=("token_hash",), name="accounts_pa_token_ha_3ab43f_idx"),
        ),
    ]
