import logging
from datetime import date, datetime, time, timedelta, timezone as dt_timezone

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
        queryset = self._base_queryset()
        return self._apply_visibility_rules(queryset)

    def get_permissions(self):
        if self._is_readonly_action():
            return [permissions.IsAuthenticated()]
        return [permissions.IsAuthenticated(), IsAdminOrReadOnly()]

    @action(detail=False, methods=["get"], url_path="published")
    def published(self, request):
        queryset = self.get_queryset().filter(status=Assessment.Status.PUBLISHED)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def _base_queryset(self):
        return Assessment.objects.select_related("category").prefetch_related("tags", "questions")

    def _apply_visibility_rules(self, queryset):
        if self._can_view_all_assessments(self.request.user):
            return queryset.order_by("title")
        return queryset.filter(status=Assessment.Status.PUBLISHED).order_by("title")

    def _can_view_all_assessments(self, user):
        return bool(user and (user.is_staff or user.is_superuser))

    def _is_readonly_action(self):
        return self.action in {"list", "retrieve", "published"}


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

        assessments = self._extract_assessments(payload)
        if isinstance(assessments, Response):
            return assessments

        client = self._resolve_client(request.user, payload)
        if isinstance(client, Response):
            return client

        email_config = self._extract_email_config(payload)
        schedule_config = self._extract_schedule_config(payload)
        if isinstance(schedule_config, Response):
            return schedule_config

        share_results = bool(payload.get("shareResults") or payload.get("share_results"))

        schedule = RespondentInviteSchedule.objects.create(
            owner=request.user,
            client=client,
            assessments=list(assessments),
            subject=email_config["subject"],
            message=email_config["message"],
            include_consent=email_config["include_consent"],
            share_results=share_results,
            start_at=schedule_config["first_run"],
            frequency=schedule_config["frequency"],
            cycles=schedule_config["cycles"],
        )

        runs_response = self._generate_schedule_runs(
            schedule=schedule,
            cycles=schedule_config["cycles"],
            first_run=schedule_config["first_run"],
            frequency_days=schedule_config["delta_days"],
            request_user=request.user,
            assessments=assessments,
            client=client,
            share_results=share_results,
            email_config=email_config,
        )

        if isinstance(runs_response, Response):
            return runs_response

        runs, invite_preview_url = runs_response

        self._notify_schedule_created(request.user, client, assessments, schedule, runs)

        return Response(
            {
                "scheduleId": str(schedule.reference),
                "runs": runs,
                "preview": {
                    "inviteUrl": invite_preview_url,
                    "subject": email_config["subject"],
                    "message": email_config["message"],
                    "includeConsent": email_config["include_consent"],
                    "replyTo": email_config["reply_to"],
                },
            },
            status=status.HTTP_201_CREATED,
        )

    def _extract_assessments(self, payload: dict):
        assessments = payload.get("assessments")
        if not isinstance(assessments, (list, tuple)) or not assessments:
            return Response(
                {"detail": "'assessments' must be a non-empty list of assessment slugs."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return assessments

    def _resolve_client(self, user, payload: dict):
        client_slug = payload.get("clientSlug") or payload.get("client_slug")
        if not client_slug:
            return Response({"detail": "A client slug is required to start a schedule."}, status=status.HTTP_400_BAD_REQUEST)

        client = Client.objects.filter(owner=user, slug=client_slug).first()
        if client is None:
            return Response({"detail": "Client could not be found for this clinician."}, status=status.HTTP_400_BAD_REQUEST)

        if not client.email:
            return Response({"detail": "Client does not have an email address on file."}, status=status.HTTP_400_BAD_REQUEST)

        return client

    def _extract_email_config(self, payload: dict) -> dict:
        email_payload = payload.get("email") or {}
        subject = str(email_payload.get("subject") or "").strip()
        message = str(email_payload.get("message") or "").strip()

        include_consent_value = email_payload.get("includeConsent")
        if include_consent_value is None:
            include_consent_value = email_payload.get("include_consent")
        include_consent = True if include_consent_value is None else bool(include_consent_value)

        reply_to = email_payload.get("replyTo") or email_payload.get("reply_to")
        reply_to_value = str(reply_to).strip() if reply_to else None

        return {
            "subject": subject,
            "message": message,
            "include_consent": include_consent,
            "reply_to": reply_to_value,
        }

    def _extract_schedule_config(self, payload: dict):
        schedule_payload = payload.get("schedule") or {}
        start_date_value = schedule_payload.get("startDate") or schedule_payload.get("start_date")
        frequency_value = schedule_payload.get("frequency") or schedule_payload.get("repeat")
        cycles_value = (
            schedule_payload.get("cycles")
            or schedule_payload.get("cycleCount")
            or schedule_payload.get("cycle_count")
        )

        if not start_date_value:
            return Response({"detail": "A schedule start date is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            start_date = datetime.strptime(str(start_date_value), "%Y-%m-%d").date()
        except ValueError:
            return Response({"detail": "Schedule start date must be provided in YYYY-MM-DD format."}, status=status.HTTP_400_BAD_REQUEST)

        frequency = (str(frequency_value or "none").strip() or "none").lower()
        if frequency not in {"none", *self._FREQUENCY_MAP.keys()}:
            return Response({"detail": "Unsupported schedule frequency."}, status=status.HTTP_400_BAD_REQUEST)

        cycles = self._coerce_cycles(cycles_value)
        if cycles > self._MAX_CYCLES:
            return Response({"detail": "Number of cycles exceeds the supported maximum."}, status=status.HTTP_400_BAD_REQUEST)

        if frequency == "none":
            cycles = 1

        first_run = self._determine_first_run_datetime(start_date)
        delta_days = self._FREQUENCY_MAP.get(frequency, 0)

        return {
            "first_run": first_run,
            "frequency": frequency,
            "cycles": cycles,
            "delta_days": delta_days,
        }

    def _coerce_cycles(self, value) -> int:
        try:
            cycles = int(value or 1)
        except (TypeError, ValueError):
            cycles = 1
        return max(1, cycles)

    def _determine_first_run_datetime(self, start_date: date) -> datetime:
        tz = timezone.get_current_timezone()
        first_run = datetime.combine(start_date, time(hour=9, minute=0))
        if timezone.is_naive(first_run):
            first_run = timezone.make_aware(first_run, tz)

        now = timezone.now()
        if first_run < now:
            first_run = now + timedelta(minutes=self._MINUTES_BUFFER)
        return first_run

    def _generate_schedule_runs(
        self,
        *,
        schedule: RespondentInviteSchedule,
        cycles: int,
        first_run: datetime,
        frequency_days: int,
        request_user,
        assessments,
        client: Client,
        share_results: bool,
        email_config: dict,
    ):
        runs: list[dict[str, str]] = []
        try:
            for index in range(cycles):
                scheduled_at = first_run + timedelta(days=frequency_days * index)
                token = issue_link_token(
                    owner_id=request_user.id,
                    assessments=assessments,
                    mode="linked",
                    client_slug=client.slug,
                    share_results=share_results,
                )

                invite_url = build_invite_url(token)

                try:
                    send_assessment_invite_email(
                        InviteContent(
                            subject=email_config["subject"],
                            message=email_config["message"],
                            include_consent=email_config["include_consent"],
                            invite_url=invite_url,
                            client_email=client.email,
                            reply_to=email_config["reply_to"],
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
        return runs, invite_preview_url

    def _notify_schedule_created(self, user, client: Client, assessments, schedule, runs: list[dict[str, str]]):
        try:
            client_name = str(client)
            create_notification(
                recipient=user,
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


class RespondentLinkResolveView(APIView):
    permission_classes = (permissions.AllowAny,)

    def post(self, request, *args, **kwargs):
        token = request.data.get("token")
        if not token:
            return Response({"detail": "A respondent token is required."}, status=status.HTTP_400_BAD_REQUEST)

        link_payload = self._resolve_link_payload(token)
        if isinstance(link_payload, Response):
            return link_payload

        assessment_payload = self._build_assessment_payload(link_payload)

        client_payload = self._build_client_payload(link_payload)
        if isinstance(client_payload, Response):
            return client_payload

        return Response(self._build_resolve_response(token, link_payload, assessment_payload, client_payload))

    def _resolve_link_payload(self, token: str):
        try:
            return resolve_link_token(token)
        except RespondentLinkError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    def _build_assessment_payload(self, link_payload):
        assessments = (
            Assessment.objects.filter(slug__in=link_payload.assessments)
            .filter(Q(status=Assessment.Status.PUBLISHED) | Q(created_by_id=link_payload.owner_id))
            .select_related("category")
        )
        return [
            {
                "slug": assessment.slug,
                "title": assessment.title,
                "summary": assessment.summary,
                "description": assessment.description,
                "category": assessment.category.slug if assessment.category else None,
            }
            for assessment in assessments
        ]

    def _build_client_payload(self, link_payload):
        if not link_payload.client_slug:
            return None

        client = Client.objects.filter(owner_id=link_payload.owner_id, slug=link_payload.client_slug).first()
        if not client:
            return Response(
                {"detail": "The linked client could not be found. Request a new invitation."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return {
            "slug": client.slug,
            "firstName": client.first_name,
            "lastName": client.last_name,
            "email": client.email,
            "dob": client.dob.isoformat() if client.dob else None,
            "gender": client.gender,
        }

    def _build_resolve_response(self, token: str, link_payload, assessments: list[dict], client_payload):
        return {
            "token": token,
            "mode": link_payload.mode,
            "shareResults": link_payload.share_results,
            "pendingClient": link_payload.pending_client,
            "maxUses": link_payload.max_uses,
            "uses": link_payload.uses,
            "expiresAt": link_payload.expires_at.isoformat() if link_payload.expires_at else None,
            "assessments": assessments,
            "client": client_payload,
        }


class RespondentLinkScheduleRunListView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    _SUPPORTED_FILTERS = {"sent", "future", "scheduled", "pending", "all", ""}

    def get(self, request, *args, **kwargs):
        client = self._resolve_client(request)
        if isinstance(client, Response):
            return client

        status_filter = self._normalize_status_filter(request)
        if isinstance(status_filter, Response):
            return status_filter

        runs = self._fetch_runs_queryset(request.user, client)
        runs = self._apply_status_filter(runs, status_filter)
        serializer = RespondentInviteScheduleRunSerializer(runs, many=True)
        return Response({"runs": serializer.data})

    def _resolve_client(self, request):
        client_slug = request.query_params.get("client")
        if not client_slug:
            return Response({"detail": "A client slug is required to view schedule runs."}, status=status.HTTP_400_BAD_REQUEST)

        client = Client.objects.filter(owner=request.user, slug=client_slug).first()
        if client is None:
            return Response({"detail": "Client could not be found for this clinician."}, status=status.HTTP_400_BAD_REQUEST)
        return client

    def _normalize_status_filter(self, request):
        status_filter = (request.query_params.get("status") or "").strip().lower()
        if status_filter not in self._SUPPORTED_FILTERS:
            return Response({"detail": "Unsupported status filter."}, status=status.HTTP_400_BAD_REQUEST)
        return status_filter

    def _fetch_runs_queryset(self, user, client):
        return RespondentInviteScheduleRun.objects.select_related("schedule", "schedule__client").filter(
            schedule__owner=user,
            schedule__client=client,
        ).order_by("-scheduled_at")

    def _apply_status_filter(self, runs_queryset, status_filter: str):
        now = timezone.now()

        if status_filter in {"future", "pending"}:
            return runs_queryset.filter(status="scheduled", scheduled_at__gte=now)
        if status_filter == "sent":
            return runs_queryset.filter(Q(status="sent") | Q(scheduled_at__lt=now))
        if status_filter == "scheduled":
            return runs_queryset.filter(status="scheduled")
        return runs_queryset


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

        link_payload = self._resolve_link_payload(token)
        if isinstance(link_payload, Response):
            return link_payload

        if not link_payload.pending_client:
            return Response({"detail": "This respondent invitation is already linked to a client."}, status=status.HTTP_400_BAD_REQUEST)

        owner = self._resolve_owner(link_payload.owner_id)
        if isinstance(owner, Response):
            return owner

        client_details = self._normalize_client_details(client_payload)
        if isinstance(client_details, Response):
            return client_details

        client = self._upsert_client(owner, client_details)
        update_client_group_cache(client)

        refreshed_token, refreshed_payload = self._refresh_link_token(link_payload, client)

        return Response(
            self._build_client_response(refreshed_token, client, refreshed_payload),
            status=status.HTTP_201_CREATED,
        )

    def _resolve_link_payload(self, token: str):
        try:
            return resolve_link_token(token)
        except RespondentLinkError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    def _resolve_owner(self, owner_id: int):
        owner = get_user_model().objects.filter(pk=owner_id, is_active=True).first()
        if owner is None:
            return Response({"detail": "The clinician account for this invitation is unavailable."}, status=status.HTTP_400_BAD_REQUEST)
        return owner

    def _normalize_client_details(self, payload: dict):
        first_name = (payload.get("firstName") or "").strip()
        last_name = (payload.get("lastName") or "").strip()
        email = (payload.get("email") or "").strip().lower()
        gender = payload.get("gender") or ""
        if gender and gender not in {choice[0] for choice in Client.Gender.choices}:
            gender = ""

        dob = self._parse_date_of_birth(payload.get("dob") or "")
        if isinstance(dob, Response):
            return dob

        details = {
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "gender": gender,
            "dob": dob,
            "informant1_name": (payload.get("informant1Name") or "").strip(),
            "informant1_email": (payload.get("informant1Email") or "").strip(),
            "informant2_name": (payload.get("informant2Name") or "").strip(),
            "informant2_email": (payload.get("informant2Email") or "").strip(),
        }
        details["base_name"] = f"{first_name} {last_name}".strip() or email or "client"
        return details

    def _parse_date_of_birth(self, value: str):
        if not value:
            return None
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            return Response({"detail": "Date of birth must be provided in YYYY-MM-DD format."}, status=status.HTTP_400_BAD_REQUEST)

    def _upsert_client(self, owner, details: dict):
        existing = None
        if details["email"]:
            existing = Client.objects.filter(owner=owner, email=details["email"]).first()

        if existing:
            updates = {
                "first_name": details["first_name"] or existing.first_name,
                "last_name": details["last_name"] or existing.last_name,
                "gender": details["gender"] or existing.gender,
                "dob": details["dob"] or existing.dob,
                "informant1_name": details["informant1_name"] or existing.informant1_name,
                "informant1_email": details["informant1_email"] or existing.informant1_email,
                "informant2_name": details["informant2_name"] or existing.informant2_name,
                "informant2_email": details["informant2_email"] or existing.informant2_email,
            }
            for field, value in updates.items():
                setattr(existing, field, value)
            existing.save()
            return existing

        slug = generate_unique_client_slug(owner.id, details["base_name"])
        return Client.objects.create(
            owner=owner,
            slug=slug,
            first_name=details["first_name"] or details["base_name"],
            last_name=details["last_name"],
            email=details["email"],
            dob=details["dob"],
            gender=details["gender"],
            informant1_name=details["informant1_name"],
            informant1_email=details["informant1_email"],
            informant2_name=details["informant2_name"],
            informant2_email=details["informant2_email"],
        )

    def _refresh_link_token(self, link_payload, client: Client):
        refreshed_token = refresh_token_for_client(link_payload, client_slug=client.slug)
        refreshed_payload = resolve_link_token(refreshed_token)
        return refreshed_token, refreshed_payload

    def _build_client_response(self, token: str, client: Client, link_payload):
        return {
            "token": token,
            "client": {
                "slug": client.slug,
                "firstName": client.first_name,
                "lastName": client.last_name,
                "email": client.email,
                "dob": client.dob.isoformat() if client.dob else None,
                "gender": client.gender,
            },
            "maxUses": link_payload.max_uses,
            "uses": link_payload.uses,
            "expiresAt": link_payload.expires_at.isoformat() if link_payload.expires_at else None,
        }


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