from typing import Any, Dict, Iterable, List, Optional

from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify
from rest_framework import serializers

from clients.models import Client

from .models import (
    Assessment,
    AssessmentCategory,
    AssessmentQuestion,
    AssessmentResponse,
    AssessmentScoringConfig,
    AssessmentTag,
    RespondentInviteSchedule,
    RespondentInviteScheduleRun,
)


def generate_unique_assessment_slug(base: str) -> str:
    base_slug = slugify(base) or "assessment"
    slug = base_slug
    suffix = 1
    while Assessment.objects.filter(slug=slug).exists():
        suffix += 1
        slug = f"{base_slug}-{suffix}"
    return slug


class AssessmentCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = AssessmentCategory
        fields = ("id", "name", "slug", "description", "created_at", "updated_at")
        read_only_fields = ("id", "slug", "created_at", "updated_at")


class AssessmentTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssessmentTag
        fields = ("id", "name", "slug", "created_at", "updated_at")
        read_only_fields = ("id", "slug", "created_at", "updated_at")


class RespondentInviteScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = RespondentInviteSchedule
        fields = (
            "reference",
            "subject",
            "message",
            "include_consent",
            "share_results",
            "start_at",
            "frequency",
            "cycles",
            "assessments",
            "created_at",
        )
        read_only_fields = fields


class RespondentInviteScheduleRunSerializer(serializers.ModelSerializer):
    schedule_reference = serializers.UUIDField(source="schedule.reference", read_only=True)
    subject = serializers.CharField(source="schedule.subject", read_only=True)
    message = serializers.CharField(source="schedule.message", read_only=True)
    include_consent = serializers.BooleanField(source="schedule.include_consent", read_only=True)
    share_results = serializers.BooleanField(source="schedule.share_results", read_only=True)
    frequency = serializers.CharField(source="schedule.frequency", read_only=True)
    cycles = serializers.IntegerField(source="schedule.cycles", read_only=True)
    assessments = serializers.ListField(child=serializers.CharField(), source="schedule.assessments", read_only=True)
    client_slug = serializers.CharField(source="schedule.client.slug", read_only=True)
    client_name = serializers.SerializerMethodField()

    class Meta:
        model = RespondentInviteScheduleRun
        fields = (
            "id",
            "schedule_reference",
            "scheduled_at",
            "sent_at",
            "status",
            "created_at",
            "subject",
            "message",
            "include_consent",
            "share_results",
            "frequency",
            "cycles",
            "assessments",
            "client_slug",
            "client_name",
        )
        read_only_fields = fields

    def get_client_name(self, obj: RespondentInviteScheduleRun) -> str:
        client = obj.schedule.client
        return (f"{client.first_name} {client.last_name}".strip() or client.email or client.slug)


class AssessmentQuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssessmentQuestion
        fields = (
            "id",
            "identifier",
            "order",
            "text",
            "help_text",
            "response_type",
            "required",
            "config",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class AssessmentScoringSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssessmentScoringConfig
        fields = ("method", "configuration", "notes")


class AssessmentSerializer(serializers.ModelSerializer):
    category = serializers.SlugRelatedField(
        slug_field="slug",
        queryset=AssessmentCategory.objects.all(),
        required=False,
        allow_null=True,
    )
    tags = serializers.SlugRelatedField(
        slug_field="slug",
        queryset=AssessmentTag.objects.all(),
        many=True,
        required=False,
    )
    questions = AssessmentQuestionSerializer(many=True, required=False)
    scoring = AssessmentScoringSerializer(required=False, allow_null=True)

    class Meta:
        model = Assessment
        fields = (
            "id",
            "title",
            "slug",
            "summary",
            "description",
            "highlights",
            "duration_minutes",
            "age_range",
            "delivery_modes",
            "status",
            "published_at",
            "category",
            "tags",
            "questions",
            "scoring",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "slug",
            "published_at",
            "created_at",
            "updated_at",
        )

    def validate(self, attrs):
        status = attrs.get("status", getattr(self.instance, "status", Assessment.Status.DRAFT))
        questions = attrs.get("questions")
        if questions is not None:
            has_questions = bool(questions)
        elif self.instance:
            has_questions = self.instance.questions.exists()
        else:
            has_questions = False
        if status == Assessment.Status.PUBLISHED and not has_questions:
            raise serializers.ValidationError("Published assessments must include questions.")
        return attrs

    def create(self, validated_data):
        tags = validated_data.pop("tags", [])
        questions = validated_data.pop("questions", [])
        scoring = validated_data.pop("scoring", None)

        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            validated_data.setdefault("created_by", user)
            validated_data.setdefault("updated_by", user)

        title = validated_data.get("title") or "Assessment"
        if not validated_data.get("slug"):
            validated_data["slug"] = generate_unique_assessment_slug(title)

        with transaction.atomic():
            assessment = Assessment.objects.create(**validated_data)
            self._sync_tags(assessment, tags)
            self._sync_questions(assessment, questions)
            self._sync_scoring(assessment, scoring)
            self._apply_publish_state(assessment, validated_data.get("status"))

        return assessment

    def update(self, instance, validated_data):
        tags = validated_data.pop("tags", None)
        questions = validated_data.pop("questions", None)
        scoring = validated_data.pop("scoring", None)

        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            validated_data["updated_by"] = user

        status = validated_data.get("status", instance.status)

        with transaction.atomic():
            for field, value in validated_data.items():
                setattr(instance, field, value)
            instance.save()

            if tags is not None:
                self._sync_tags(instance, tags)
            if questions is not None:
                self._sync_questions(instance, questions)
            if scoring is not None:
                self._sync_scoring(instance, scoring)
            self._apply_publish_state(instance, status)

        return instance

    def _sync_tags(self, assessment: Assessment, tags: Iterable[AssessmentTag]) -> None:
        if tags is not None:
            assessment.tags.set(tags)

    def _sync_questions(self, assessment: Assessment, questions_data: List[dict]) -> None:
        if questions_data is None:
            return

        existing_by_id = {question.id: question for question in assessment.questions.all()}
        existing_by_identifier = {question.identifier: question for question in assessment.questions.all()}
        used_identifiers: set[str] = set(existing_by_identifier.keys())
        seen_ids: set[int] = set()

        def ensure_identifier(
            *, candidate: Optional[str], text: Optional[str], fallback: str, current_identifier: Optional[str]
        ) -> str:
            base = candidate or slugify(text or fallback) or fallback
            base = slugify(base) or fallback
            resolved = base
            counter = 1
            while resolved in used_identifiers and resolved != current_identifier:
                counter += 1
                resolved = f"{base}-{counter}"
            used_identifiers.add(resolved)
            return resolved

        for index, payload in enumerate(questions_data):
            question_id = payload.get("id")
            existing_question = existing_by_id.get(question_id) if question_id else None
            identifier = ensure_identifier(
                candidate=payload.get("identifier"),
                text=payload.get("text"),
                fallback=f"question-{index + 1}",
                current_identifier=getattr(existing_question, "identifier", None),
            )

            if not existing_question and identifier in existing_by_identifier:
                existing_question = existing_by_identifier[identifier]
                question_id = existing_question.id

            defaults = {
                "identifier": identifier,
                "order": payload.get("order", index + 1),
                "text": payload.get("text", ""),
                "help_text": payload.get("help_text", ""),
                "response_type": payload.get(
                    "response_type",
                    AssessmentQuestion.ResponseType.FREE_TEXT,
                ),
                "required": payload.get("required", True),
                "config": payload.get("config", {}),
            }

            if existing_question:
                question = existing_question
                for field, value in defaults.items():
                    setattr(question, field, value)
                question.save()
                seen_ids.add(question_id)
            else:
                question = AssessmentQuestion.objects.create(assessment=assessment, **defaults)
                existing_by_identifier[question.identifier] = question
                seen_ids.add(question.id)

        # Delete removed questions
        assessment.questions.exclude(id__in=seen_ids).delete()

    def _sync_scoring(self, assessment: Assessment, scoring_data: Optional[dict]) -> None:
        if scoring_data is None:
            return

        if not scoring_data:
            scoring_instance = getattr(assessment, "scoring", None)
            if scoring_instance:
                scoring_instance.delete()
            return

        AssessmentScoringConfig.objects.update_or_create(
            assessment=assessment,
            defaults={
                "method": scoring_data.get("method", AssessmentScoringConfig.Method.SUM),
                "configuration": scoring_data.get("configuration", {}),
                "notes": scoring_data.get("notes", ""),
            },
        )

    def _apply_publish_state(self, assessment: Assessment, status: str) -> None:
        if status == Assessment.Status.PUBLISHED and assessment.published_at is None:
            assessment.published_at = timezone.now()
            assessment.save(update_fields=["published_at"])
        elif status == Assessment.Status.DRAFT and assessment.published_at is not None:
            assessment.published_at = None
            assessment.save(update_fields=["published_at"])


class AssessmentResponseSerializer(serializers.ModelSerializer):
    class ResponseItemSerializer(serializers.Serializer):
        question_identifier = serializers.CharField()
        value = serializers.JSONField()

    assessment_slug = serializers.SlugRelatedField(
        source="assessment",
        slug_field="slug",
        queryset=Assessment.objects.all(),
    )
    client_slug = serializers.SlugRelatedField(
        source="client",
        slug_field="slug",
        queryset=Client.objects.all(),
        required=False,
        allow_null=True,
    )
    responses = ResponseItemSerializer(many=True, write_only=True)
    client = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = AssessmentResponse
        fields = (
            "id",
            "assessment_slug",
            "client_slug",
            "client",
            "responses",
            "score",
            "highlights",
            "submitted_at",
        )
        read_only_fields = ("id", "client", "score", "highlights", "submitted_at")

    def validate_responses(self, value: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        identifiers = set()
        for item in value:
            identifier = item.get("question_identifier")
            if not identifier:
                raise serializers.ValidationError("Each response must include a question_identifier.")
            if identifier in identifiers:
                raise serializers.ValidationError("Duplicate question_identifier provided.")
            identifiers.add(identifier)
        return value

    def create(self, validated_data: Dict[str, Any]) -> AssessmentResponse:
        request = self.context.get("request")
        assessment: Assessment = validated_data["assessment"]
        client: Client | None = validated_data.get("client")
        response_items: List[Dict[str, Any]] = validated_data.pop("responses", [])

        question_map = {question.identifier: question for question in assessment.questions.all()}
        response_map: Dict[str, Any] = {}

        for item in response_items:
            identifier = item["question_identifier"].strip()
            question = question_map.get(identifier)
            if question is None:
                raise serializers.ValidationError({
                    "responses": f"Unknown question identifier: {identifier}",
                })
            value = item.get("value")
            if question.required and (value is None or value == "" or value == []):
                raise serializers.ValidationError({
                    "responses": f"Question '{identifier}' requires an answer.",
                })
            response_map[identifier] = value

        missing_required = [identifier for identifier, question in question_map.items() if question.required and identifier not in response_map]
        if missing_required:
            raise serializers.ValidationError({
                "responses": f"Missing required responses for: {', '.join(sorted(missing_required))}",
            })

        score_payload, highlights = self._calculate_score(assessment, response_map)

        submitted_by = None
        if request and getattr(request, "user", None) and request.user.is_authenticated:
            submitted_by = request.user

        return AssessmentResponse.objects.create(
            assessment=assessment,
            client=client,
            submitted_by=submitted_by,
            responses=response_map,
            score=score_payload,
            highlights=highlights,
        )

    def get_client(self, obj: AssessmentResponse) -> Dict[str, str] | None:
        if not obj.client:
            return None
        full_name = f"{obj.client.first_name} {obj.client.last_name}".strip() or obj.client.email or obj.client.slug
        return {
            "slug": obj.client.slug,
            "name": full_name,
        }

    def _calculate_score(
        self,
        assessment: Assessment,
        responses: Dict[str, Any],
    ) -> tuple[Dict[str, Any], List[str]]:
        scoring = getattr(assessment, "scoring", None)
        if not scoring:
            return ({}, [])

        method = scoring.method
        configuration = scoring.configuration or {}

        if method == AssessmentScoringConfig.Method.SUM:
            return self._calculate_sum_score(configuration, responses)

        # Fallback for unsupported methods
        return ({"method": method}, [])

    def _calculate_sum_score(
        self,
        configuration: Dict[str, Any],
        responses: Dict[str, Any],
    ) -> tuple[Dict[str, Any], List[str]]:
        total = 0.0
        for value in responses.values():
            if isinstance(value, (int, float)):
                total += float(value)
            elif isinstance(value, str):
                try:
                    total += float(value)
                except ValueError:
                    continue

        band_id: str | None = None
        band_label: str | None = None
        band_description: str | None = None

        bands = configuration.get("bands") if isinstance(configuration, dict) else None
        if isinstance(bands, list):
            for band in bands:
                if not isinstance(band, dict):
                    continue
                lower = band.get("min")
                upper = band.get("max")
                if lower is None or upper is None:
                    continue
                try:
                    if float(lower) <= total <= float(upper):
                        band_id = band.get("id") or band.get("label")
                        band_label = band.get("label")
                        band_description = band.get("description")
                        break
                except (TypeError, ValueError):
                    continue

        score_payload: Dict[str, Any] = {"total": round(total, 2)}
        if band_id:
            score_payload["band"] = band_id
        if band_label:
            score_payload["band_label"] = band_label
        if band_description:
            score_payload["interpretation"] = band_description

        highlights = [band_description] if band_description else []
        return score_payload, highlights
