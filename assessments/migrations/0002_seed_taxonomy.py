from django.db import migrations


def seed_taxonomy(apps, schema_editor):
    Category = apps.get_model("assessments", "AssessmentCategory")
    Tag = apps.get_model("assessments", "AssessmentTag")

    categories = [
        ("trauma", "Trauma", "Assessments focused on trauma-informed care."),
        ("anxiety", "Anxiety", "Tools measuring anxiety symptoms and severity."),
        ("mood", "Mood", "Mood and affect related assessments."),
        ("screening", "Screening", "General screening instruments for clinicians."),
    ]

    for slug, name, description in categories:
        Category.objects.update_or_create(
            slug=slug,
            defaults={"name": name, "description": description},
        )

    tags = [
        ("trauma", "Trauma"),
        ("adolescent", "Adolescent"),
        ("clinician-report", "Clinician Report"),
        ("depression", "Depression"),
        ("primary-care", "Primary Care"),
        ("screening", "Screening"),
        ("self-report", "Self Report"),
        ("wellbeing", "Wellbeing"),
    ]

    for slug, name in tags:
        Tag.objects.update_or_create(
            slug=slug,
            defaults={"name": name},
        )


def unseed_taxonomy(apps, schema_editor):
    Category = apps.get_model("assessments", "AssessmentCategory")
    Tag = apps.get_model("assessments", "AssessmentTag")
    Category.objects.filter(slug__in=["trauma", "anxiety", "mood", "screening"]).delete()
    Tag.objects.filter(slug__in=[
        "trauma",
        "adolescent",
        "clinician-report",
        "depression",
        "primary-care",
        "screening",
        "self-report",
        "wellbeing",
    ]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("assessments", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_taxonomy, unseed_taxonomy),
    ]
