from .base import SMSProvider, SMSResult


class FakeSMSProvider(SMSProvider):
    """Test double: records messages; can be told to fail."""

    code = "fake"
    sent: list[tuple[str, str]] = []
    fail_with: SMSResult | None = None

    @classmethod
    def reset(cls):
        cls.sent = []
        cls.fail_with = None

    @classmethod
    def last_code(cls, phone):
        return next((c for p, c in reversed(cls.sent) if p == phone), None)

    def send_otp(self, phone, code, *, ttl_seconds):
        if type(self).fail_with is not None:
            return type(self).fail_with
        type(self).sent.append((phone, code))
        return SMSResult(ok=True, provider_message_id=f"fake-{len(type(self).sent)}")
