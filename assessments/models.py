import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

from clients.models import Client


class AssessmentCategory(models.Model):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True)
    description = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:  # pragma: no cover - display helper
        return self.name


class AssessmentTag(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:  # pragma: no cover - display helper
        return self.name


class Assessment(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"

    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    summary = models.TextField(blank=True)
    description = models.TextField(blank=True)
    highlights = models.JSONField(default=list, blank=True)

    duration_minutes = models.PositiveIntegerField(blank=True, null=True)
    age_range = models.CharField(max_length=120, blank=True)
    delivery_modes = models.JSONField(default=list, blank=True)
    clinician_notes = models.TextField(blank=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    published_at = models.DateTimeField(blank=True, null=True)

    category = models.ForeignKey(
        AssessmentCategory,
        related_name="assessments",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
    )
    tags = models.ManyToManyField(AssessmentTag, related_name="assessments", blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="assessments_created",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="assessments_updated",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("title",)

    def __str__(self) -> str:  # pragma: no cover - display helper
        return self.title

    def save(self, *args, **kwargs):  # pragma: no cover - simple helper
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)


class AssessmentQuestion(models.Model):
    class ResponseType(models.TextChoices):
        SINGLE_CHOICE = "single_choice", "Single choice"
        MULTI_CHOICE = "multi_choice", "Multiple choice"
        LIKERT = "likert", "Likert scale"
        YES_NO = "yes_no", "Yes / No"
        FREE_TEXT = "free_text", "Free text"
        NUMERIC = "numeric", "Numeric"

    assessment = models.ForeignKey(
        Assessment,
        related_name="questions",
        on_delete=models.CASCADE,
    )
    identifier = models.SlugField(
        max_length=160,
        help_text="Stable identifier for scoring references.",
    )
    order = models.PositiveIntegerField()
    text = models.TextField()
    help_text = models.TextField(blank=True)
    response_type = models.CharField(max_length=20, choices=ResponseType.choices)
    required = models.BooleanField(default=True)
    config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional metadata such as options, scale anchors, validation.",
    )
    domain = models.CharField(
        max_length=120,
        default="general",
        help_text="Cognitive or skill domain this question targets.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("assessment", "order")
        unique_together = ("assessment", "identifier")

    def __str__(self) -> str:  # pragma: no cover - display helper
        return f"{self.assessment.title}: {self.text[:50]}"


class AssessmentScoringConfig(models.Model):
    class Method(models.TextChoices):
        SUM = "sum", "Sum"
        AVERAGE = "average", "Average"
        RULES = "rules", "Rule based"
        CUSTOM = "custom", "Custom"

    assessment = models.OneToOneField(
        Assessment,
        related_name="scoring",
        on_delete=models.CASCADE,
    )
    method = models.CharField(max_length=20, choices=Method.choices, default=Method.SUM)
    configuration = models.JSONField(
        default=dict,
        blank=True,
        help_text="Declarative scoring rules, value mappings, thresholds, narratives.",
    )
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Assessment scoring configuration"
        verbose_name_plural = "Assessment scoring configurations"

    def __str__(self) -> str:  # pragma: no cover - display helper
        return f"Scoring for {self.assessment.title}"


class AssessmentResponse(models.Model):
    assessment = models.ForeignKey(
        Assessment,
        related_name="responses",
        on_delete=models.CASCADE,
    )
    client = models.ForeignKey(
        Client,
        related_name="assessment_responses",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="assessment_responses_submitted",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    responses = models.JSONField(help_text="Raw responses keyed by question identifier.")
    highlights = models.JSONField(blank=True, default=list, help_text="Highlights derived from scoring.")
    score = models.JSONField(blank=True, default=dict, help_text="Calculated scoring payload including totals and bands.")
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-submitted_at",)
        indexes = (
            models.Index(fields=("assessment", "submitted_at")),
            models.Index(fields=("client", "submitted_at")),
        )

    def __str__(self) -> str:  # pragma: no cover - display helper
        return f"Response for {self.assessment.slug} at {self.submitted_at:%Y-%m-%d %H:%M:%S}"


class RespondentInviteSchedule(models.Model):
    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="respondent_invite_schedules",
        on_delete=models.CASCADE,
    )
    client = models.ForeignKey(
        Client,
        related_name="respondent_invite_schedules",
        on_delete=models.CASCADE,
    )
    assessments = models.JSONField(help_text="Assessment slugs included in this schedule")
    subject = models.CharField(max_length=255)
    message = models.TextField(blank=True)
    include_consent = models.BooleanField(default=True)
    share_results = models.BooleanField(default=False)
    start_at = models.DateTimeField()
    frequency = models.CharField(max_length=32)
    cycles = models.PositiveSmallIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:  # pragma: no cover - debug helper
        return f"Schedule {self.reference} for {self.client.slug}"


class RespondentInviteScheduleRun(models.Model):
    schedule = models.ForeignKey(RespondentInviteSchedule, related_name="runs", on_delete=models.CASCADE)
    token = models.TextField()
    scheduled_at = models.DateTimeField()
    sent_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=32, default="scheduled")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("scheduled_at",)

    def mark_sent(self) -> None:
        self.status = "sent"
        self.sent_at = timezone.now()
        self.save(update_fields=["status", "sent_at"])

    def __str__(self) -> str:  # pragma: no cover - debug helper
        return f"Run for schedule {self.schedule_id} at {self.scheduled_at.isoformat()}"

 
class RespondentInvite(models.Model):
    token = models.TextField(unique=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="respondent_invites",
        on_delete=models.CASCADE,
    )
    assessments = models.JSONField(help_text="Assessment slugs embedded in this invitation")
    mode = models.CharField(max_length=20)
    client = models.ForeignKey(
        Client,
        related_name="respondent_invites",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    share_results = models.BooleanField(default=False)
    pending_client = models.BooleanField(default=False)
    issued_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    max_uses = models.PositiveSmallIntegerField(default=1)
    uses = models.PositiveSmallIntegerField(default=0)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = (
            models.Index(fields=("token",)),
            models.Index(fields=("owner", "issued_at")),
            models.Index(fields=("expires_at",)),
        )

    def mark_used(self) -> None:
        self.uses += 1
        self.used_at = timezone.now()
        self.save(update_fields=["uses", "used_at"])

    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at
