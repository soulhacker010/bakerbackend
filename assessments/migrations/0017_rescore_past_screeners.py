"""Give past PHQ-9, GAD-7 and CAGE-AID results the band they were missing.

These three had no interpretation ranges until 17 October 2026, so results
submitted before then were stored as a bare total. Each is re-scored with the
card now on the assessment. A result is only rewritten when the new total is
the same as the stored one, so no past answer is ever read differently - the
result only gains its band, interpretation and flags.

Also fills in delivery modes on assessments that never had any, with the same
two every other assessment lists.
"""
from django.db import migrations

SLUGS = (
    "patient-health-questionnaire-9-phq-9",
    "generalized-anxiety-disorder-7-item-scale-gad-7",
    "cage-questions-adapted-to-include-drug-use-cage-aid",
)
DEFAULT_MODES = ["self-entry", "interview"]


def forwards(apps, schema_editor):
    from assessments.scoring import score_assessment
    from assessments.scoring.loader import card_from_dict
    from assessments.scoring.service import build_payload

    Assessment = apps.get_model("assessments", "Assessment")
    Response = apps.get_model("assessments", "AssessmentResponse")
    Scoring = apps.get_model("assessments", "AssessmentScoringConfig")

    for assessment in Assessment.objects.filter(slug__in=SLUGS):
        scoring = Scoring.objects.filter(assessment=assessment).first()
        card_data = ((scoring.configuration or {}).get("card") if scoring else None)
        if not card_data:
            continue
        card = card_from_dict(card_data)
        for response in Response.objects.filter(assessment=assessment):
            stored = response.score or {}
            if stored.get("band") or "total" not in stored:
                continue
            payload, highlights = build_payload(card, score_assessment(card, response.responses or {}))
            if payload.get("total") != stored.get("total") or not payload.get("band"):
                continue
            response.score = payload
            response.highlights = highlights
            response.save(update_fields=["score", "highlights"])

    for assessment in Assessment.objects.all():
        if not assessment.delivery_modes:
            assessment.delivery_modes = list(DEFAULT_MODES)
            assessment.save(update_fields=["delivery_modes"])


class Migration(migrations.Migration):
    dependencies = [("assessments", "0016_fill_blank_category_tag_slugs")]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
