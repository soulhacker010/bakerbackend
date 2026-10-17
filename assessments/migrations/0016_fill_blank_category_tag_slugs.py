from django.db import migrations
from django.utils.text import slugify


def fill_blank_slugs(apps, schema_editor):
    """Categories and tags created through the API before slugs were set."""
    for name in ("AssessmentCategory", "AssessmentTag"):
        model = apps.get_model("assessments", name)
        for row in model.objects.filter(slug=""):
            row.slug = slugify(row.name)
            row.save(update_fields=["slug"])


class Migration(migrations.Migration):
    dependencies = [("assessments", "0015_assessment_bundles")]

    operations = [migrations.RunPython(fill_blank_slugs, migrations.RunPython.noop)]
