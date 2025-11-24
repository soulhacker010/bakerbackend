import logging
from datetime import datetime, time, timedelta, timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.db.models import Q
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from clients.models import Client
from clients.serializers import generate_unique_client_slug, update_client_group_cache
from django.utils import timezone

from notifications.models import Notification
from notifications.services import create_notification

from .email_invites import EmailInviteError, InviteContent, build_invite_url, send_assessment_invite_email
from .models import (
    Assessment,
    AssessmentCategory,
    AssessmentResponse,
    AssessmentTag,
    RespondentInviteSchedule,
    RespondentInviteScheduleRun,
)
from .permissions import IsAdminOrReadOnly
from .serializers import (
    AssessmentCategorySerializer,
    AssessmentResponseSerializer,
    AssessmentSerializer,
    AssessmentTagSerializer,
    RespondentInviteScheduleRunSerializer,
)
from .respondent_links import (
    RespondentLinkError,
    issue_link_token,
    refresh_token_for_client,
    resolve_link_token,
    mark_invite_used,
)


logger = logging.getLogger(__name__)


class AssessmentCategoryViewSet(viewsets.ModelViewSet):
    serializer_class = AssessmentCategorySerializer
    permission_classes = (IsAdminOrReadOnly,)
    lookup_field = "slug"

    def get_queryset(self):
        return AssessmentCategory.objects.all()


class AssessmentTagViewSet(viewsets.ModelViewSet):
    serializer_class = AssessmentTagSerializer
    permission_classes = (IsAdminOrReadOnly,)
    lookup_field = "slug"

    def get_queryset(self):
        return AssessmentTag.objects.all()


class AssessmentViewSet(viewsets.ModelViewSet):
    serializer_class = AssessmentSerializer
    permission_classes = (permissions.IsAuthenticated, IsAdminOrReadOnly)
    lookup_field = "slug"

    def get_queryset(self):
        queryset = Assessment.objects.select_related("category").prefetch_related("tags", "questions")
        user = self.request.user
        if user.is_staff or user.is_superuser:
            return queryset.order_by("title")
        return queryset.filter(status=Assessment.Status.PUBLISHED).order_by("title")

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [permissions.IsAuthenticated()]
        return [permissions.IsAuthenticated(), IsAdminOrReadOnly()]

    @action(detail=False, methods=["get"], url_path="published")
    def published(self, request):
        queryset = self.get_queryset().filter(status=Assessment.Status.PUBLISHED)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class AssessmentResponseViewSet(viewsets.ModelViewSet):
    serializer_class = AssessmentResponseSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        user = self.request.user
        queryset = AssessmentResponse.objects.select_related("assessment", "client")

        if not user.is_staff and not user.is_superuser:
            queryset = queryset.filter(
                Q(assessment__created_by=user)
                | Q(client__owner=user)
                | Q(submitted_by=user)
            )

        assessment_slug = self.request.query_params.get("assessment")
        if assessment_slug:
            queryset = queryset.filter(assessment__slug=assessment_slug)

        client_slug = self.request.query_params.get("client")
        if client_slug:
            queryset = queryset.filter(client__slug=client_slug)

        return queryset.order_by("-submitted_at")


class RespondentLinkIssueView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, *args, **kwargs):
        payload = request.data or {}
        assessments = payload.get("assessments")
        if not isinstance(assessments, (list, tuple)):
            return Response({"detail": "'assessments' must be a list of assessment slugs."}, status=status.HTTP_400_BAD_REQUEST)

        mode = str(payload.get("mode") or "self-entry")
        client_slug = payload.get("clientSlug") or payload.get("client_slug")
        share_results = bool(payload.get("shareResults") or payload.get("share_results"))

        try:
            token = issue_link_token(
                owner_id=request.user.id,
                assessments=assessments,
                mode=mode,
                client_slug=client_slug,
                share_results=share_results,
            )
        except RespondentLinkError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "token": token,
            },
            status=status.HTTP_201_CREATED,
        )


class RespondentLinkEmailInviteView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, *args, **kwargs):
        payload = request.data or {}
        assessments = payload.get("assessments")
        if not isinstance(assessments, (list, tuple)) or not assessments:
            return Response(
                {"detail": "'assessments' must be a non-empty list of assessment slugs."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        client_slug = payload.get("clientSlug") or payload.get("client_slug")
        if not client_slug:
            return Response({"detail": "A client slug is required to send an invite."}, status=status.HTTP_400_BAD_REQUEST)

        client = Client.objects.filter(owner=request.user, slug=client_slug).first()
        if client is None:
            return Response({"detail": "Client could not be found for this clinician."}, status=status.HTTP_400_BAD_REQUEST)

        if not client.email:
            return Response({"detail": "Client does not have an email address on file."}, status=status.HTTP_400_BAD_REQUEST)

        share_results = bool(payload.get("shareResults") or payload.get("share_results"))

        email_payload = payload.get("email") or {}
        subject = str(email_payload.get("subject") or "").strip()
        message = str(email_payload.get("message") or "").strip()

        include_consent_value = email_payload.get("includeConsent")
        if include_consent_value is None:
            include_consent_value = email_payload.get("include_consent")
        include_consent = True if include_consent_value is None else bool(include_consent_value)

        reply_to = email_payload.get("replyTo") or email_payload.get("reply_to")
        if reply_to:
            reply_to = str(reply_to).strip()

        try:
            token = issue_link_token(
                owner_id=request.user.id,
                assessments=assessments,
                mode="linked",
                client_slug=client.slug,
                share_results=share_results,
            )
        except RespondentLinkError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        invite_url = build_invite_url(token)

        try:
            send_assessment_invite_email(
                InviteContent(
                    subject=subject,
                    message=message,
                    include_consent=include_consent,
                    invite_url=invite_url,
                    client_email=client.email,
                    reply_to=reply_to or None,
                )
            )
        except EmailInviteError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        return Response({"token": token}, status=status.HTTP_201_CREATED)


class RespondentLinkScheduleView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    _FREQUENCY_MAP = {
        "day": 1,
        "week": 7,
        "fortnight": 14,
        "month": 30,
        "three-months": 90,
    }
    _MAX_CYCLES = 99
    _MINUTES_BUFFER = 5

    def post(self, request, *args, **kwargs):
        payload = request.data or {}

        assessments = payload.get("assessments")
        if not isinstance(assessments, (list, tuple)) or not assessments:
            return Response(
                {"detail": "'assessments' must be a non-empty list of assessment slugs."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        client_slug = payload.get("clientSlug") or payload.get("client_slug")
        if not client_slug:
            return Response({"detail": "A client slug is required to start a schedule."}, status=status.HTTP_400_BAD_REQUEST)

        client = Client.objects.filter(owner=request.user, slug=client_slug).first()
        if client is None:
            return Response({"detail": "Client could not be found for this clinician."}, status=status.HTTP_400_BAD_REQUEST)

        if not client.email:
            return Response({"detail": "Client does not have an email address on file."}, status=status.HTTP_400_BAD_REQUEST)

        share_results = bool(payload.get("shareResults") or payload.get("share_results"))

        email_payload = payload.get("email") or {}
        subject = str(email_payload.get("subject") or "").strip()
        message = str(email_payload.get("message") or "").strip()

        include_consent_value = email_payload.get("includeConsent")
        if include_consent_value is None:
            include_consent_value = email_payload.get("include_consent")
        include_consent = True if include_consent_value is None else bool(include_consent_value)

        reply_to = email_payload.get("replyTo") or email_payload.get("reply_to")
        if reply_to:
            reply_to = str(reply_to).strip()

        schedule_payload = payload.get("schedule") or {}
        start_date_value = schedule_payload.get("startDate") or schedule_payload.get("start_date")
        frequency = schedule_payload.get("frequency") or schedule_payload.get("repeat")
        cycles_value = schedule_payload.get("cycles") or schedule_payload.get("cycleCount") or schedule_payload.get("cycle_count")

        if not start_date_value:
            return Response({"detail": "A schedule start date is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            start_date = datetime.strptime(str(start_date_value), "%Y-%m-%d").date()
        except ValueError:
            return Response({"detail": "Schedule start date must be provided in YYYY-MM-DD format."}, status=status.HTTP_400_BAD_REQUEST)

        frequency = (str(frequency or "none").strip() or "none").lower()
        if frequency not in {"none", *self._FREQUENCY_MAP.keys()}:
            return Response({"detail": "Unsupported schedule frequency."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            cycles = int(cycles_value or 1)
        except (TypeError, ValueError):
            cycles = 1

        if cycles < 1:
            cycles = 1
        if cycles > self._MAX_CYCLES:
            return Response({"detail": "Number of cycles exceeds the supported maximum."}, status=status.HTTP_400_BAD_REQUEST)

        if frequency == "none":
            cycles = 1

        tz = timezone.get_current_timezone()
        first_run_dt = datetime.combine(start_date, time(hour=9, minute=0))
        if timezone.is_naive(first_run_dt):
            first_run_dt = timezone.make_aware(first_run_dt, tz)

        now = timezone.now()
        if first_run_dt < now:
            first_run_dt = now + timedelta(minutes=self._MINUTES_BUFFER)

        delta_days = self._FREQUENCY_MAP.get(frequency, 0)

        schedule = RespondentInviteSchedule.objects.create(
            owner=request.user,
            client=client,
            assessments=list(assessments),
            subject=subject,
            message=message,
            include_consent=include_consent,
            share_results=share_results,
            start_at=first_run_dt,
            frequency=frequency,
            cycles=cycles,
        )

        runs: list[dict[str, str]] = []

        try:
            for index in range(cycles):
                scheduled_at = first_run_dt + timedelta(days=delta_days * index)

                token = issue_link_token(
                    owner_id=request.user.id,
                    assessments=assessments,
                    mode="linked",
                    client_slug=client.slug,
                    share_results=share_results,
                )

                invite_url = build_invite_url(token)

                try:
                    send_assessment_invite_email(
                        InviteContent(
                            subject=subject,
                            message=message,
                            include_consent=include_consent,
                            invite_url=invite_url,
                            client_email=client.email,
                            reply_to=reply_to or None,
                            send_at=scheduled_at,
                        )
                    )
                except EmailInviteError as exc:
                    schedule.delete()
                    return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

                runs.append(
                    {
                        "token": token,
                        "scheduledAt": scheduled_at.astimezone(dt_timezone.utc)
                        .replace(microsecond=0)
                        .isoformat()
                        .replace("+00:00", "Z"),
                    }
                )

                RespondentInviteScheduleRun.objects.create(
                    schedule=schedule,
                    token=token,
                    scheduled_at=scheduled_at,
                )

        except RespondentLinkError as exc:
            schedule.delete()
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        invite_preview_url = build_invite_url(runs[0]["token"]) if runs else None

        try:
            client_name = str(client)
            create_notification(
                recipient=request.user,
                event_type=Notification.EventType.SCHEDULE_SENT,
                title="Assessment schedule created",
                body=f"A schedule for {client_name} has been created.",
                payload={
                    "scheduleId": str(schedule.reference),
                    "clientSlug": client.slug,
                    "clientName": client_name,
                    "assessmentSlugs": list(assessments),
                    "firstRunAt": runs[0]["scheduledAt"] if runs else None,
                },
            )
        except Exception:  # pragma: no cover - notifications must not block scheduling
            logger.exception("Unable to create schedule notification")

        return Response(
            {
                "scheduleId": str(schedule.reference),
                "runs": runs,
                "preview": {
                    "inviteUrl": invite_preview_url,
                    "subject": subject,
                    "message": message,
                    "includeConsent": include_consent,
                    "replyTo": reply_to,
                },
            },
            status=status.HTTP_201_CREATED,
        )


class RespondentLinkResolveView(APIView):
    permission_classes = (permissions.AllowAny,)

    def post(self, request, *args, **kwargs):
        token = request.data.get("token")
        if not token:
            return Response({"detail": "A respondent token is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            link_payload = resolve_link_token(token)
        except RespondentLinkError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        assessments = list(
            Assessment.objects.filter(slug__in=link_payload.assessments).filter(
                Q(status=Assessment.Status.PUBLISHED) | Q(created_by_id=link_payload.owner_id)
            )
        )
        assessment_payload = [
            {
                "slug": assessment.slug,
                "title": assessment.title,
                "summary": assessment.summary,
                "description": assessment.description,
                "category": assessment.category.slug if assessment.category else None,
            }
            for assessment in assessments
        ]

        client_data = None
        if link_payload.client_slug:
            client = Client.objects.filter(owner_id=link_payload.owner_id, slug=link_payload.client_slug).first()
            if not client:
                return Response(
                    {"detail": "The linked client could not be found. Request a new invitation."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            client_data = {
                "slug": client.slug,
                "firstName": client.first_name,
                "lastName": client.last_name,
                "email": client.email,
                "dob": client.dob.isoformat() if client.dob else None,
                "gender": client.gender,
            }

        return Response(
            {
                "token": token,
                "mode": link_payload.mode,
                "shareResults": link_payload.share_results,
                "pendingClient": link_payload.pending_client,
                "maxUses": link_payload.max_uses,
                "uses": link_payload.uses,
                "expiresAt": link_payload.expires_at.isoformat() if link_payload.expires_at else None,
                "assessments": assessment_payload,
                "client": client_data,
            }
        )


class RespondentLinkScheduleRunListView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    _SUPPORTED_FILTERS = {"sent", "future", "scheduled", "pending", "all", ""}

    def get(self, request, *args, **kwargs):
        client_slug = request.query_params.get("client")
        if not client_slug:
            return Response({"detail": "A client slug is required to view schedule runs."}, status=status.HTTP_400_BAD_REQUEST)

        client = Client.objects.filter(owner=request.user, slug=client_slug).first()
        if client is None:
            return Response({"detail": "Client could not be found for this clinician."}, status=status.HTTP_400_BAD_REQUEST)

        status_filter = (request.query_params.get("status") or "").strip().lower()
        if status_filter not in self._SUPPORTED_FILTERS:
            return Response({"detail": "Unsupported status filter."}, status=status.HTTP_400_BAD_REQUEST)

        runs = RespondentInviteScheduleRun.objects.select_related("schedule", "schedule__client").filter(
            schedule__owner=request.user,
            schedule__client=client,
        )

        now = timezone.now()

        if status_filter in {"future", "pending"}:
            runs = runs.filter(status="scheduled", scheduled_at__gte=now)
        elif status_filter == "sent":
            runs = runs.filter(Q(status="sent") | Q(scheduled_at__lt=now))
        elif status_filter == "scheduled":
            runs = runs.filter(status="scheduled")

        runs = runs.order_by("-scheduled_at")

        serializer = RespondentInviteScheduleRunSerializer(runs, many=True)
        return Response({"runs": serializer.data})


class RespondentLinkScheduleDetailView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def delete(self, request, reference: str, *args, **kwargs):
        schedule = RespondentInviteSchedule.objects.filter(owner=request.user, reference=reference).first()
        if schedule is None:
            return Response({"detail": "Schedule not found."}, status=status.HTTP_404_NOT_FOUND)

        schedule.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class RespondentLinkClientView(APIView):
    permission_classes = (permissions.AllowAny,)

    def post(self, request, *args, **kwargs):
        token = request.data.get("token")
        if not token:
            return Response({"detail": "A respondent token is required."}, status=status.HTTP_400_BAD_REQUEST)

        client_payload = request.data.get("client") or {}
        if not isinstance(client_payload, dict):
            return Response({"detail": "'client' must be an object."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            link_payload = resolve_link_token(token)
        except RespondentLinkError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        if not link_payload.pending_client:
            return Response({"detail": "This respondent invitation is already linked to a client."}, status=status.HTTP_400_BAD_REQUEST)

        owner = get_user_model().objects.filter(pk=link_payload.owner_id, is_active=True).first()
        if owner is None:
            return Response({"detail": "The clinician account for this invitation is unavailable."}, status=status.HTTP_400_BAD_REQUEST)

        first_name = (client_payload.get("firstName") or "").strip()
        last_name = (client_payload.get("lastName") or "").strip()
        email = (client_payload.get("email") or "").strip().lower()
        gender = client_payload.get("gender") or ""
        if gender and gender not in {choice[0] for choice in Client.Gender.choices}:
            gender = ""

        dob_value = client_payload.get("dob") or ""
        dob = None
        if dob_value:
            try:
                dob = datetime.strptime(dob_value, "%Y-%m-%d").date()
            except ValueError:
                return Response({"detail": "Date of birth must be provided in YYYY-MM-DD format."}, status=status.HTTP_400_BAD_REQUEST)

        informant1_name = (client_payload.get("informant1Name") or "").strip()
        informant1_email = (client_payload.get("informant1Email") or "").strip()
        informant2_name = (client_payload.get("informant2Name") or "").strip()
        informant2_email = (client_payload.get("informant2Email") or "").strip()

        base_name = f"{first_name} {last_name}".strip() or email or "client"

        existing = None
        if email:
            existing = Client.objects.filter(owner=owner, email=email).first()

        if existing:
            client = existing
            updates = {
                "first_name": first_name or client.first_name,
                "last_name": last_name or client.last_name,
                "gender": gender or client.gender,
                "dob": dob or client.dob,
                "informant1_name": informant1_name or client.informant1_name,
                "informant1_email": informant1_email or client.informant1_email,
                "informant2_name": informant2_name or client.informant2_name,
                "informant2_email": informant2_email or client.informant2_email,
            }
            for field, value in updates.items():
                setattr(client, field, value)
            client.save()
        else:
            slug = generate_unique_client_slug(owner.id, base_name)
            client = Client.objects.create(
                owner=owner,
                slug=slug,
                first_name=first_name or base_name,
                last_name=last_name,
                email=email,
                dob=dob,
                gender=gender,
                informant1_name=informant1_name,
                informant1_email=informant1_email,
                informant2_name=informant2_name,
                informant2_email=informant2_email,
            )

        update_client_group_cache(client)

        refreshed_token = refresh_token_for_client(link_payload, client_slug=client.slug)

        refreshed_payload = resolve_link_token(refreshed_token)

        return Response(
            {
                "token": refreshed_token,
                "client": {
                    "slug": client.slug,
                    "firstName": client.first_name,
                    "lastName": client.last_name,
                    "email": client.email,
                    "dob": client.dob.isoformat() if client.dob else None,
                    "gender": client.gender,
                },
                "maxUses": refreshed_payload.max_uses,
                "uses": refreshed_payload.uses,
                "expiresAt": refreshed_payload.expires_at.isoformat() if refreshed_payload.expires_at else None,
            },
            status=status.HTTP_201_CREATED,
        )


class RespondentAssessmentDetailView(APIView):
    permission_classes = (permissions.AllowAny,)

    def post(self, request, *args, **kwargs):
        token = request.data.get("token")
        slug = request.data.get("assessment")

        if not token:
            return Response({"detail": "A respondent token is required."}, status=status.HTTP_400_BAD_REQUEST)
        if not slug:
            return Response({"detail": "An assessment slug is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            link_payload = resolve_link_token(token)
        except RespondentLinkError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        if slug not in link_payload.assessments:
            return Response({"detail": "This assessment is not part of the invitation."}, status=status.HTTP_403_FORBIDDEN)

        assessment = (
            Assessment.objects.filter(slug=slug, status=Assessment.Status.PUBLISHED)
            .select_related("category")
            .prefetch_related("tags", "questions")
            .first()
        )
        if assessment is None:
            return Response({"detail": "Assessment is unavailable."}, status=status.HTTP_404_NOT_FOUND)

        payload = AssessmentSerializer(instance=assessment).data
        return Response(payload)


class RespondentAssessmentResponseView(APIView):
    permission_classes = (permissions.AllowAny,)

    def post(self, request, *args, **kwargs):
        token = request.data.get("token")
        payload = request.data.get("response") or {}

        if not token:
            return Response({"detail": "A respondent token is required."}, status=status.HTTP_400_BAD_REQUEST)
        if not isinstance(payload, dict):
            return Response({"detail": "'response' must be an object."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            link_payload = resolve_link_token(token)
        except RespondentLinkError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        serializer = AssessmentResponseSerializer(data=payload, context={"request": request})
        serializer.is_valid(raise_exception=True)

        assessment_slug = serializer.validated_data["assessment"].slug
        if assessment_slug not in link_payload.assessments:
            return Response({"detail": "This assessment is not part of the invitation."}, status=status.HTTP_403_FORBIDDEN)

        client = serializer.validated_data.get("client")
        if link_payload.client_slug:
            if client is None or client.slug != link_payload.client_slug:
                return Response({"detail": "Responses must be recorded for the invited client."}, status=status.HTTP_403_FORBIDDEN)
        else:
            if link_payload.pending_client:
                return Response({"detail": "Complete your details before starting the assessment."}, status=status.HTTP_403_FORBIDDEN)

        instance = serializer.save()

        mark_invite_used(token)

        response_data = AssessmentResponseSerializer(instance).data
        return Response(response_data, status=status.HTTP_201_CREATED)
