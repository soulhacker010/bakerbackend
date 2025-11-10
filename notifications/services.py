from __future__ import annotations

from typing import Any, Iterable

from django.utils import timezone

from .models import Notification


def create_notification(
    *,
    recipient,
    event_type: str,
    title: str,
    body: str | None = None,
    payload: dict[str, Any] | None = None,
    read: bool = False,
) -> Notification:
    notification = Notification.objects.create(
        recipient=recipient,
        event_type=event_type,
        title=title,
        body=body or "",
        payload=payload or {},
        read_at=timezone.now() if read else None,
    )
    return notification


def create_notifications(
    *,
    recipients: Iterable,
    event_type: str,
    title: str,
    body: str | None = None,
    payload: dict[str, Any] | None = None,
) -> list[Notification]:
    created: list[Notification] = []
    for recipient in recipients:
        created.append(
            create_notification(
                recipient=recipient,
                event_type=event_type,
                title=title,
                body=body,
                payload=payload,
            )
        )
    return created
