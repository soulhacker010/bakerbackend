"""Utilities for issuing and validating respondent assessment links."""
from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Iterable, List, Optional

from django.conf import settings
from django.core import signing
from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import gettext_lazy as _

from clients.models import Client

from .models import Assessment

RESPONDENT_LINK_SALT = "assessments.respondent-link.v1"
RESPONDENT_LINK_MAX_AGE_SECONDS = getattr(settings, "RESPONDENT_LINK_MAX_AGE_SECONDS", 60 * 60 * 24 * 14)


@dataclass(frozen=True)
class RespondentLinkPayload:
    owner_id: int
    assessments: List[str]
    mode: str
    client_slug: Optional[str]
    share_results: bool
    pending_client: bool
    nonce: str


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
        Assessment.objects.filter(slug__in=slugs, status=Assessment.Status.PUBLISHED, created_by_id=owner_id)
    )
    found_slugs = {assessment.slug for assessment in assessments}
    missing = [slug for slug in slugs if slug not in found_slugs]
    if missing:
        raise RespondentLinkError(_(f"Unknown assessments: {', '.join(missing)}."))

    return assessments


def issue_link_token(*, owner_id: int, assessments: Iterable[str], mode: str, client_slug: str | None, share_results: bool) -> str:
    assessments = _validate_assessments(owner_id, assessments)

    if mode not in {"self-entry", "linked"}:
        raise RespondentLinkError("Unsupported respondent mode.")

    pending_client = False
    resolved_client_slug: str | None = None

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

    return _serialise_payload(payload)


def refresh_token_for_client(payload: RespondentLinkPayload, *, client_slug: str) -> str:
    return _serialise_payload(
        RespondentLinkPayload(
            owner_id=payload.owner_id,
            assessments=payload.assessments,
            mode="linked",
            client_slug=client_slug,
            share_results=payload.share_results,
            pending_client=False,
            nonce=secrets.token_urlsafe(8),
        )
    )


def resolve_link_token(token: str) -> RespondentLinkPayload:
    return _deserialise_payload(token)
