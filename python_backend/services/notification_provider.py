"""Pluggable notification provider contract with a safe offline default."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol

from models.contract import Notification, User


@dataclass(frozen=True)
class DeliveryResult:
    provider_message_id: str
    channel: str


class NotificationProvider(Protocol):
    name: str
    channel: str

    def send(
        self,
        notification: Notification,
        recipient: User,
        *,
        idempotency_key: str,
    ) -> DeliveryResult: ...


class FakeNotificationProvider:
    """Deterministic provider used by default; it never performs network I/O."""

    name = "fake"
    channel = "fake"

    def send(
        self,
        notification: Notification,
        recipient: User,
        *,
        idempotency_key: str,
    ) -> DeliveryResult:
        digest = hashlib.sha256(
            f"{notification.id}|{recipient.id}|{idempotency_key}".encode("utf-8")
        ).hexdigest()[:24]
        return DeliveryResult(provider_message_id=f"fake-{digest}", channel=self.channel)


def default_provider_registry() -> dict[str, NotificationProvider]:
    provider = FakeNotificationProvider()
    return {provider.name: provider}
