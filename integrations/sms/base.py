"""SMS provider interface. Business code only talks to this, never to a vendor API."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class SMSResult:
    ok: bool
    provider_message_id: str | None = None
    error_code: str | None = None
    retryable: bool = False


class SMSProvider(ABC):
    code: str = ""

    @abstractmethod
    def send_otp(self, phone: str, code: str, *, ttl_seconds: int) -> SMSResult: ...

    def send_text(self, phone: str, text: str, *, template: str | None = None) -> SMSResult:
        return SMSResult(ok=False, error_code="not_supported")
