from django.db import migrations


def drop_authtoken_table(apps, schema_editor):
    # Remove legacy permissions first to avoid FK violations.
    schema_editor.execute(
        "DELETE FROM auth_permission WHERE content_type_id IN ("
        "SELECT id FROM django_content_type WHERE app_label = 'authtoken'"
        ");"
    )
    # Drop the token table if it still exists.
    schema_editor.execute("DROP TABLE IF EXISTS authtoken_token;")
    # Finally remove the content type rows (if any) for authtoken.
    schema_editor.execute("DELETE FROM django_content_type WHERE app_label = 'authtoken';")


def noop(apps, schema_editor):
    """No-op reverse migration."""
    # We intentionally do not recreate legacy token tables.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0006_rename_accounts_pa_user_id_f22042_idx_accounts_pa_user_id_8cd138_idx_and_more"),
    ]

    operations = [
        migrations.RunPython(drop_authtoken_table, noop),
    ]
