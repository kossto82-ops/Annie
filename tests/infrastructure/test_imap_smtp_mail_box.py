"""Offline tests for the IMAP/SMTP mail adapter.

Exercises list/read/send through fake IMAP and SMTP connections so nothing ever
touches the wire, plus the `build_mail_source` factory's config opt-in.
"""

from __future__ import annotations

from email.message import EmailMessage as Mime

import pytest

from jarvis.domain.retrieval.mail_source import MailBox
from jarvis.infrastructure.mail_source import IMAPSMTPMailBox, build_mail_source


def _header_only() -> bytes:
    msg = Mime()
    msg["Subject"] = "Hello"
    msg["From"] = "alice@example.com"
    msg["To"] = "jarvis@example.com"
    msg.set_content("Read carefully.")
    return bytes(msg)


def _full_email() -> bytes:
    msg = Mime()
    msg["Subject"] = "Full message"
    msg["From"] = "alice@example.com"
    msg["To"] = "jarvis@example.com"
    msg.set_content("The body text.")
    return bytes(msg)


class _FakeIMAP:
    """A stub of the imaplib surface used by the adapter."""

    def __init__(self) -> None:
        self.logged_out = False
        self.limit = 10

    def login(self, email: str, password: str) -> None:
        pass

    def select(self, folder: str) -> tuple[str, list]:
        self.folder = folder
        return ("OK", [folder])

    def search(self, charset: str | None, criteria: str) -> tuple[str, list[bytes]]:
        return ("OK", [b"1 2 3"])

    def fetch(self, number: bytes, parts: str) -> tuple[str, list]:
        if "BODY.PEEK[]" in parts:
            return ("OK", [(number, _full_email())])
        if number in ("1", "2", "3"):
            return ("OK", [(number, _header_only())])
        return ("OK", [])

    def logout(self) -> None:
        self.logged_out = True


class _FakeSMTP:
    def __init__(self) -> None:
        self.sent: list[tuple[str, list[str], str]] = []
        self.closed = False

    def login(self, email: str, password: str) -> None:
        pass

    def sendmail(self, fro: str, to: list[str], message: str) -> None:
        self.sent.append((fro, to, message))

    def close(self) -> None:
        self.closed = True


def _build() -> tuple[IMAPSMTPMailBox, _FakeIMAP, _FakeSMTP]:
    imap = _FakeIMAP()
    smtp = _FakeSMTP()
    mailbox = IMAPSMTPMailBox(
        email="jarvis@example.com",
        password="secret",
        imap_host="imap.example.com",
        smtp_host="smtp.example.com",
        imap_connect=lambda: imap,  # type: ignore[arg-type]
        smtp_connect=lambda: smtp,  # type: ignore[arg-type]
    )
    return mailbox, imap, smtp


class TestSmoke:
    def test_adapter_satisfies_the_mailbox_protocol(self) -> None:
        mailbox, _, _ = _build()
        assert isinstance(mailbox, MailBox)


class TestListRead:
    def test_list_messages_returns_headers_of_latest_messages(self) -> None:
        mailbox, imap, _ = _build()
        messages = mailbox.list_messages(limit=2)
        assert len(messages) == 2
        assert {m.subject for m in messages} == {"Hello"}
        assert all(m.folder == "inbox" for m in messages)
        assert imap.logged_out

    def test_read_message_returns_body_and_content_type_parse(self) -> None:
        mailbox, imap, _ = _build()
        msg = mailbox.read_message("2")
        assert msg.subject == "Full message"
        assert "The body text." in msg.body
        assert msg.sender == "alice@example.com"
        assert msg.message_id == "2"

    def test_read_message_raises_when_missing(self) -> None:
        mailbox, _, _ = _build()

        class Empty:
            def login(self, e, p):
                pass

            def select(self, folder):
                return ("OK", [folder])

            def fetch(self, number, parts):
                return ("BAD", [])

            def logout(self):
                pass

        mailbox._imap_connect = lambda: Empty()  # type: ignore[assignment]
        with pytest.raises(RuntimeError):
            mailbox.read_message("99")


class TestSend:
    def test_send_message_routes_through_smtp_and_returns_a_record(self) -> None:
        mailbox, _, smtp = _build()
        record = mailbox.send_message(to=("carol@example.com",), subject="Re", body="Sure.")
        assert smtp.sent
        assert smtp.sent[0][1] == ["carol@example.com"]
        assert "Sure." in smtp.sent[0][2]
        assert smtp.closed
        assert record.folder == "sent"
        assert record.sender == "jarvis@example.com"


class TestBuild:
    def test_build_returns_none_without_configuration(self) -> None:
        assert build_mail_source({}) is None

    def test_build_returns_adapter_with_configuration(self) -> None:
        source = build_mail_source(
            {
                "MAIL_EMAIL": "jarvis@example.com",
                "MAIL_PASSWORD": "secret",
                "MAIL_IMAP_HOST": "imap.example.com",
            }
        )
        assert source is not None
        assert source._imap_host == "imap.example.com"
        assert source._smtp_host == "imap.example.com"  # defaults to imap host
