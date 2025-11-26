from django.db import transaction
from django.utils.text import slugify
from rest_framework import exceptions, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Client, ClientGroup
from .permissions import HasClientAccess
from .serializers import (
    ClientGroupSerializer,
    ClientImportRowSerializer,
    ClientSerializer,
    generate_unique_client_slug,
    update_client_group_cache,
)


class ClientViewSet(viewsets.ModelViewSet):
    serializer_class = ClientSerializer
    permission_classes = (permissions.IsAuthenticated, HasClientAccess)
    lookup_field = "slug"
    lookup_value_regex = r"[^/]+"

    def get_queryset(self):
        return Client.objects.filter(owner=self.request.user).order_by("-created_at")

    @action(detail=False, methods=["post"], url_path="import")
    def import_clients(self, request):
        owner = request.user
        rows = request.data.get("rows")

        if not isinstance(rows, list):
            return Response(
                {"detail": "'rows' must be a list of client rows."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        summary = {"created": 0, "updated": 0, "skipped": 0}
        results: list[dict] = []

        for index, payload in enumerate(rows):
            serializer = ClientImportRowSerializer(data=payload)
            if not serializer.is_valid():
                summary["skipped"] += 1
                results.append(
                    {
                        "index": index,
                        "status": "error",
                        "errors": serializer.errors,
                    }
                )
                continue

            normalized = self._normalize_import_data(serializer.validated_data)

            try:
                with transaction.atomic():
                    client, status_label = self._upsert_client(owner, normalized)
            except Exception as exc:  # pragma: no cover - defensive
                summary["skipped"] += 1
                results.append(
                    {
                        "index": index,
                        "status": "error",
                        "errors": [str(exc)],
                    }
                )
                continue

            summary[status_label] += 1
            results.append(
                {
                    "index": index,
                    "status": status_label,
                    "slug": client.slug,
                    "name": client.__str__(),
                }
            )

        return Response({"summary": summary, "results": results}, status=status.HTTP_200_OK)

    def _normalize_import_data(self, data: dict) -> dict:
        first_name, last_name = self._resolve_names(data)
        email = (data.get("email") or "").strip().lower()
        gender = self._normalize_gender(data.get("gender"))
        normalized_slug = self._normalize_slug(data.get("slug"))

        return {
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "dob": data.get("date_of_birth"),
            "gender": gender,
            "informant1_name": (data.get("informant1_name") or "").strip(),
            "informant1_email": (data.get("informant1_email") or "").strip(),
            "informant2_name": (data.get("informant2_name") or "").strip(),
            "informant2_email": (data.get("informant2_email") or "").strip(),
            "slug": normalized_slug,
        }

    def _resolve_names(self, data: dict) -> tuple[str, str]:
        first_name = (data.get("first_name") or "").strip()
        last_name = (data.get("last_name") or "").strip()
        if not first_name and last_name:
            first_name = last_name
        return first_name, last_name

    def _normalize_gender(self, raw_value: str | None) -> str:
        if not raw_value:
            return ""
        gender_raw = raw_value.strip().lower()
        gender_map = {
            "diverse": Client.Gender.DIVERSE,
            "gender_diverse": Client.Gender.DIVERSE,
            "gender diverse": Client.Gender.DIVERSE,
            "non_binary": Client.Gender.DIVERSE,
            "non-binary": Client.Gender.DIVERSE,
            "non binary": Client.Gender.DIVERSE,
        }
        valid_choices = {choice[0] for choice in Client.Gender.choices}
        if gender_raw in valid_choices:
            return gender_raw
        return gender_map.get(gender_raw, "")

    def _normalize_slug(self, slug_value: str | None) -> str:
        cleaned = (slug_value or "").strip()
        return slugify(cleaned) if cleaned else ""

    def _upsert_client(self, owner, data: dict) -> tuple[Client, str]:
        slug = data.get("slug") or ""
        client = self._find_existing_client(owner, slug, data.get("email"))
        payload = {key: value for key, value in data.items() if key != "slug"}

        if client:
            self._update_existing_client(client, payload)
            return client, "updated"

        return self._create_client(owner, slug, payload, data.get("email"))

    def _find_existing_client(self, owner, slug: str, email: str | None):
        if slug:
            client = Client.objects.filter(owner=owner, slug=slug).first()
            if client:
                return client
        if email:
            return Client.objects.filter(owner=owner, email=email).first()
        return None

    def _update_existing_client(self, client: Client, payload: dict) -> None:
        fields_to_update: list[str] = []
        for field, value in payload.items():
            if getattr(client, field) != value:
                setattr(client, field, value)
                fields_to_update.append(field)

        if fields_to_update:
            client.save(update_fields=fields_to_update + ["updated_at"])
        update_client_group_cache(client)

    def _create_client(self, owner, slug: str, payload: dict, fallback_name: str | None) -> tuple[Client, str]:
        base_name = f"{payload.get('first_name', '')} {payload.get('last_name', '')}".strip() or fallback_name
        slug_candidate = slug or generate_unique_client_slug(owner.pk, base_name)
        if Client.objects.filter(owner=owner, slug=slug_candidate).exists():
            slug_candidate = generate_unique_client_slug(owner.pk, slug_candidate)

        client = Client.objects.create(owner=owner, slug=slug_candidate, is_active=True, **payload)
        update_client_group_cache(client)
        return client, "created"


class ClientGroupViewSet(viewsets.ModelViewSet):
    serializer_class = ClientGroupSerializer
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = "slug"
    lookup_value_regex = r"[^/]+"

    def get_queryset(self):
        return ClientGroup.objects.filter(owner=self.request.user).order_by("-created_at")

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    def perform_update(self, serializer):
        if serializer.instance.owner_id != self.request.user.id:
            raise exceptions.PermissionDenied("You do not have permission to modify this client group.")
        serializer.save()

    def perform_destroy(self, instance):
        if instance.owner_id != self.request.user.id:
            raise exceptions.PermissionDenied("You do not have permission to delete this client group.")

        clients = [membership.client for membership in instance.memberships.select_related("client")]
        instance.delete()
        for client in clients:
            update_client_group_cache(client)

