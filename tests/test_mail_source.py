"""Tests for the email capability seam (D1-revised, Vision §34).

Covers the `EmailMessage` value object, the `MailBox` Protocol surface, the
`MailCapability` provider, and Jarvis's integration: `can_do` reflects a wired
mailbox, list/read/send delegate to the mail edge, and an unwired Jarvis stays
offline with clear errors.
"""

from __future__ import annotations

import pytest

from jarvis.domain.retrieval.mail_source import MailBox
from jarvis.domain.value_objects.capability import Capability
from jarvis.domain.value_objects.email_message import EmailMessage
from jarvis.infrastructure.capability_registry import (
    MailCapability,
    build_default_registry,
)
from jarvis.jarvis import Jarvis


class _FakeMailBox:
    """A mailbox that returns canned messages and records sends."""

    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []

    def list_messages(self, *, folder: str = "inbox", limit: int = 10) -> tuple[EmailMessage, ...]:
        return (
            EmailMessage(
                subject="Hello",
                body="Read carefully.",
                sender="alice@example.com",
                recipients=("jarvis@example.com",),
                message_id="msg-1",
                folder=folder,
            ),
        )

    def read_message(self, message_id: str, *, folder: str = "inbox") -> EmailMessage:
        if message_id != "msg-1":
            raise RuntimeError("message not found")
        return EmailMessage(
            subject="Hello",
            body="Read carefully.",
            sender="alice@example.com",
            message_id=message_id,
            folder=folder,
        )

    def send_message(self, *, to: tuple[str, ...], subject: str, body: str) -> EmailMessage:
        msg = EmailMessage(subject=subject, body=body, sender="jarvis@example.com", recipients=to)
        self.sent.append(msg)
        return msg


class TestEmailMessage:
    def test_message_requires_subject_or_body(self) -> None:
        with pytest.raises(ValueError):
            EmailMessage(subject="", body="")

    def test_message_records_provenance(self) -> None:
        msg = EmailMessage(
            subject="Hi", body="Bye", sender="bob@example.com", folder="inbox"
        )
        assert msg.provenance == "email in inbox from bob@example.com"
        assert msg.recipients == ()


class TestMailBoxProtocol:
    def test_fake_mailbox_satisfies_the_protocol(self) -> None:
        assert isinstance(_FakeMailBox(), MailBox)


class TestMailCapability:
    def test_mail_capability_backs_the_email_capability_name(self) -> None:
        provider = MailCapability(_FakeMailBox())  # type: ignore[arg-type]
        assert provider.capability == "send and read email"
        assert provider.is_available()

    def test_default_registry_backs_email_when_a_mailbox_is_wired(self) -> None:
        mailbox = _FakeMailBox()
        registry = build_default_registry(None, mail_source=mailbox)  # type: ignore[arg-type]
        assert registry.provider_for("send and read email") is not None

    def test_default_registry_without_a_mailbox_has_no_email(self) -> None:
        registry = build_default_registry(None)
        assert registry.provider_for("send and read email") is None


class TestJarvisEmail:
    @staticmethod
    def _acquire(jarvis: Jarvis) -> None:
        capability = Capability(
            name="send and read email",
            description="list, read, and send messages via a mailbox",
            requirement="a wired mailbox at the edge (MailBox)",
            provenance="test",
        )
        jarvis.remember_capability(capability)
        jarvis.acquire_capability("send and read email")

    def test_can_do_reflects_a_wired_mailbox(self) -> None:
        jarvis = Jarvis(mail_source=_FakeMailBox())  # type: ignore[arg-type]
        self._acquire(jarvis)
        assert jarvis.can_do("send and read email")

    def test_unwired_jarvis_is_offline_to_email(self) -> None:
        jarvis = Jarvis()
        self._acquire(jarvis)
        assert not jarvis.can_do("send and read email")

    def test_list_emails_delegates_to_the_mailbox(self) -> None:
        jarvis = Jarvis(mail_source=_FakeMailBox())  # type: ignore[arg-type]
        msgs = jarvis.list_emails()
        assert len(msgs) == 1
        assert msgs[0].subject == "Hello"

    def test_read_email_delegates_to_the_mailbox(self) -> None:
        jarvis = Jarvis(mail_source=_FakeMailBox())  # type: ignore[arg-type]
        msg = jarvis.read_email("msg-1")
        assert msg.sender == "alice@example.com"

    def test_send_email_delegates_and_records(self) -> None:
        mailbox = _FakeMailBox()
        jarvis = Jarvis(mail_source=mailbox)  # type: ignore[arg-type]
        msg = jarvis.send_email(to=("carol@example.com",), subject="Re", body="Sure.")
        assert msg.recipients == ("carol@example.com",)
        assert mailbox.sent == [msg]

    def test_wiring_a_mailbox_at_runtime_updates_can_do(self) -> None:
        jarvis = Jarvis()
        self._acquire(jarvis)
        assert not jarvis.can_do("send and read email")
        jarvis.set_mail_source(_FakeMailBox())  # type: ignore[arg-type]
        assert jarvis.can_do("send and read email")
        jarvis.set_mail_source(None)
        assert not jarvis.can_do("send and read email")

    def test_email_methods_raise_clearly_when_offline(self) -> None:
        jarvis = Jarvis()
        for call in (
            lambda: jarvis.list_emails(),
            lambda: jarvis.read_email("msg-1"),
            lambda: jarvis.send_email(to=("a@b.c",), subject="s", body="b"),
        ):
            with pytest.raises(RuntimeError, match="email capability"):
                call()
