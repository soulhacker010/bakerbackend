"""Utilities for issuing and validating respondent assessment links."""
from __future__ import annotations

import secrets
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Iterable, List, Optional

from django.conf import settings
from django.core import signing
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from clients.models import Client

from .models import Assessment, RespondentInvite

RESPONDENT_LINK_SALT = "assessments.respondent-link.v1"
RESPONDENT_LINK_MAX_AGE_SECONDS = getattr(settings, "RESPONDENT_LINK_MAX_AGE_SECONDS", 60 * 60 * 24 * 14)
RESPONDENT_LINK_DEFAULT_TTL_HOURS = getattr(settings, "RESPONDENT_LINK_TTL_HOURS", 48)
RESPONDENT_LINK_DEFAULT_MAX_USES = getattr(settings, "RESPONDENT_LINK_MAX_USES", 1)


@dataclass(frozen=True)
class RespondentLinkPayload:
    owner_id: int
    assessments: List[str]
    mode: str
    client_slug: Optional[str]
    share_results: bool
    pending_client: bool
    nonce: str
    invite_id: Optional[int] = None
    max_uses: int = 1
    uses: int = 0
    expires_at: Optional[datetime] = None


class RespondentLinkError(Exception):
    """Raised when a respondent link token cannot be processed."""


def _serialise_payload(payload: RespondentLinkPayload) -> str:
    data = {
        "owner": payload.owner_id,
        "assessments": payload.assessments,
        "mode": payload.mode,
        "client": payload.client_slug,
        "share": payload.share_results,
        "pending": payload.pending_client,
        "nonce": payload.nonce,
    }
    return signing.dumps(data, salt=RESPONDENT_LINK_SALT)


def _deserialise_payload(token: str, *, max_age: int | None = RESPONDENT_LINK_MAX_AGE_SECONDS) -> RespondentLinkPayload:
    try:
        data = signing.loads(token, salt=RESPONDENT_LINK_SALT, max_age=max_age)
    except signing.SignatureExpired as exc:  # pragma: no cover - defensive logging branch
        raise RespondentLinkError("This respondent link has expired. Please request a new invitation.") from exc
    except signing.BadSignature as exc:
        raise RespondentLinkError("The respondent link is invalid or has been tampered with.") from exc

    try:
        owner_id = int(data["owner"])
        assessments = list(data["assessments"])
        mode = str(data["mode"])
        client_slug = data.get("client") or None
        share_results = bool(data.get("share"))
        pending_client = bool(data.get("pending"))
        nonce = str(data.get("nonce"))
    except (KeyError, TypeError, ValueError) as exc:
        raise RespondentLinkError("The respondent link payload is malformed.") from exc

    return RespondentLinkPayload(
        owner_id=owner_id,
        assessments=assessments,
        mode=mode,
        client_slug=client_slug,
        share_results=share_results,
        pending_client=pending_client,
        nonce=nonce,
    )


def _validate_assessments(owner_id: int, assessment_slugs: Iterable[str]) -> List[Assessment]:
    slugs = list(dict.fromkeys(slug for slug in assessment_slugs if slug))
    if not slugs:
        raise RespondentLinkError("At least one assessment must be selected.")

    assessments = list(
        Assessment.objects.filter(slug__in=slugs).filter(
            Q(status=Assessment.Status.PUBLISHED) | Q(created_by_id=owner_id)
        )
    )
    found_slugs = {assessment.slug for assessment in assessments}
    missing = [slug for slug in slugs if slug not in found_slugs]
    if missing:
        raise RespondentLinkError(_(f"Unknown assessments: {', '.join(missing)}."))

    return assessments


def _normalise_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if timezone.is_naive(value):
        return timezone.make_aware(value, timezone.get_current_timezone())
    return value


def _create_invite_record(
    token: str,
    payload: RespondentLinkPayload,
    *,
    owner_id: int,
    client: Client | None,
    valid_from: datetime | None = None,
    expires_at: datetime | None = None,
    max_uses: int | None = None,
) -> RespondentInvite:
    base_time = _normalise_datetime(valid_from) or timezone.now()
    expiry = _normalise_datetime(expires_at)
    if expiry is None:
        expiry = base_time + timedelta(hours=RESPONDENT_LINK_DEFAULT_TTL_HOURS)

    max_uses_value = max_uses if max_uses is not None else RESPONDENT_LINK_DEFAULT_MAX_USES
    try:
        max_uses_value = max(1, int(max_uses_value))
    except (TypeError, ValueError):
        max_uses_value = RESPONDENT_LINK_DEFAULT_MAX_USES

    return RespondentInvite.objects.create(
        token=token,
        owner_id=owner_id,
        assessments=payload.assessments,
        mode=payload.mode,
        client=client,
        share_results=payload.share_results,
        pending_client=payload.pending_client,
        expires_at=expiry,
        max_uses=max_uses_value,
    )


def issue_link_token(
    *,
    owner_id: int,
    assessments: Iterable[str],
    mode: str,
    client_slug: str | None,
    share_results: bool,
    valid_from: datetime | None = None,
    expires_at: datetime | None = None,
    max_uses: int | None = None,
) -> str:
    assessments = _validate_assessments(owner_id, assessments)

    if mode not in {"self-entry", "linked"}:
        raise RespondentLinkError("Unsupported respondent mode.")

    pending_client = False
    resolved_client_slug: str | None = None
    client: Client | None = None

    if mode == "linked":
        if not client_slug:
            raise RespondentLinkError("Linked respondent links require an existing client.")
        try:
            client = Client.objects.get(owner_id=owner_id, slug=client_slug)
        except ObjectDoesNotExist as exc:
            raise RespondentLinkError("Client could not be found for this clinician.") from exc
        resolved_client_slug = client.slug
    else:
        pending_client = True
        resolved_client_slug = client_slug or None

    payload = RespondentLinkPayload(
        owner_id=owner_id,
        assessments=[assessment.slug for assessment in assessments],
        mode=mode,
        client_slug=resolved_client_slug,
        share_results=share_results,
        pending_client=pending_client,
        nonce=secrets.token_urlsafe(8),
    )

    token = _serialise_payload(payload)
    _create_invite_record(
        token,
        payload,
        owner_id=owner_id,
        client=client,
        valid_from=valid_from,
        expires_at=expires_at,
        max_uses=max_uses,
    )

    return token


def refresh_token_for_client(payload: RespondentLinkPayload, *, client_slug: str) -> str:
    client = Client.objects.filter(owner_id=payload.owner_id, slug=client_slug).first()
    if client is None:
        raise RespondentLinkError("Client could not be found for this clinician.")

    refreshed_payload = RespondentLinkPayload(
        owner_id=payload.owner_id,
        assessments=payload.assessments,
        mode="linked",
        client_slug=client_slug,
        share_results=payload.share_results,
        pending_client=False,
        nonce=secrets.token_urlsafe(8),
    )

    token = _serialise_payload(refreshed_payload)

    with transaction.atomic():
        if payload.invite_id:
            existing_invite = (
                RespondentInvite.objects.select_for_update()
                .filter(id=payload.invite_id)
                .first()
            )
        else:
            existing_invite = None

        if existing_invite and (
            existing_invite.client_id in {None, client.id}
        ):
            existing_invite.token = token
            existing_invite.client = client
            existing_invite.pending_client = False
            existing_invite.uses = 0
            existing_invite.save(update_fields=["token", "client", "pending_client", "uses"])
            return token

        _create_invite_record(token, refreshed_payload, owner_id=payload.owner_id, client=client)

    return token


def resolve_link_token(token: str) -> RespondentLinkPayload:
    payload = _deserialise_payload(token)

    invite = RespondentInvite.objects.select_related("client").filter(token=token).first()
    if invite is None:
        raise RespondentLinkError("The respondent link is invalid or has expired. Please request a new invitation.")

    if invite.owner_id != payload.owner_id:
        raise RespondentLinkError("The respondent link is invalid or has been tampered with.")

    if invite.client and invite.client.slug != payload.client_slug:
        raise RespondentLinkError("The respondent link is no longer valid for this client.")

    if invite.pending_client != payload.pending_client:
        raise RespondentLinkError("The respondent invitation state is inconsistent. Please request a new link.")

    if invite.is_expired():
        raise RespondentLinkError("This respondent link has expired. Please request a new invitation.")

    if invite.uses >= invite.max_uses:
        raise RespondentLinkError("This respondent link has already been used.")

    return replace(
        payload,
        invite_id=invite.id,
        max_uses=invite.max_uses,
        uses=invite.uses,
        expires_at=invite.expires_at,
    )


def mark_invite_used(token: str) -> None:
    with transaction.atomic():
        invite = RespondentInvite.objects.select_for_update().filter(token=token).first()
        if invite is None:
            return
        if invite.uses >= invite.max_uses:
            return
        invite.uses += 1
        invite.used_at = timezone.now()
        invite.save(update_fields=["uses", "used_at"])
