"""IMAPSMTPMailBox: a MailBox adapter backed by IMAP + SMTP (Odysseus email).

This is the real transport for the mail capability (D1-revised, Vision §34): it
*lists* and *reads* messages over IMAP and *sends* over SMTP, mirroring
Odysseus's ``services/email`` module as a self-contained adapter -- it does not
import Odysseus's app, so it brings no coupling and stays offline-testable
(D7, D8).

The edge never decides anything (D6): this adapter only acts on a mailbox on
request and returns messages with provenance. Reading an inbox produces candidate
text the core weighs; sending is a deliberate material action the caller must
already have gated through the controlled-autonomy policy.

Network is injectable through ``imap_connect``/``smtp_connect`` connection
*factories* (mirroring the `transport` seam in :class:`AgentReachSource` /
:class:`SearXNGResearchSource`), so offline tests swap in fakes and never touch
the wire.
"""

from __future__ import annotations

import contextlib
import imaplib
import smtplib
import ssl
from collections.abc import Callable
from email import policy
from email.message import Message as EmailParsed
from email.parser import BytesParser
from typing import Any

from jarvis.domain.value_objects.email_message import EmailMessage

# -- Connection factories (injectable transports) -----------------------------

IMAPConnect = Callable[[], "imaplib.IMAP4"]
SMTPConnect = Callable[[], "smtplib.SMTP"]

_DEFAULT_IMAP_PORT = 993
_DEFAULT_SMTP_PORT = 465

_ACTUAL_MESSAGE = "_actual"


def _make_imap_connect(
    host: str, email: str, password: str, *, port: int, timeout: float
) -> IMAPConnect:
    """Build a factory that opens, secures, and logs into an IMAP connection."""

    def connect() -> imaplib.IMAP4:
        connection = imaplib.IMAP4_SSL(host, port, timeout=timeout)
        try:
            connection.login(email, password)
        except Exception:
            connection.logout()
            raise
        return connection

    return connect


def _make_smtp_connect(
    host: str, email: str, password: str, *, port: int, timeout: float
) -> SMTPConnect:
    """Build a factory that opens, secures, and logs into an SMTP connection."""

    def connect() -> smtplib.SMTP:
        context = ssl.create_default_context()
        connection = smtplib.SMTP_SSL(host, port, timeout=timeout, context=context)
        try:
            connection.login(email, password)
        except Exception:
            connection.close()
            raise
        return connection

    return connect


class IMAPSMTPMailBox:
    """List/read messages over IMAP and send them over SMTP, with provenance.

    ``imap_connect`` and ``smtp_connect`` are connection *factories*; by default
    they open and log into the configured servers. Injecting fakes lets tests run
    entirely offline and deterministically.
    """

    def __init__(
        self,
        *,
        email: str,
        password: str,
        imap_host: str,
        smtp_host: str,
        imap_port: int = _DEFAULT_IMAP_PORT,
        smtp_port: int = _DEFAULT_SMTP_PORT,
        timeout: float = 15.0,
        imap_connect: IMAPConnect | None = None,
        smtp_connect: SMTPConnect | None = None,
    ) -> None:
        self._email = email
        self._password = password
        self._imap_host = imap_host
        self._smtp_host = smtp_host
        self._imap_port = imap_port
        self._smtp_port = smtp_port
        self._timeout = timeout
        self._imap_connect: IMAPConnect = imap_connect or _make_imap_connect(
            imap_host, email, password, port=imap_port, timeout=timeout
        )
        self._smtp_connect: SMTPConnect = smtp_connect or _make_smtp_connect(
            smtp_host, email, password, port=smtp_port, timeout=timeout
        )

    # -- MailBox --------------------------------------------------------------

    def list_messages(self, *, folder: str = "inbox", limit: int = 10) -> tuple[EmailMessage, ...]:
        """Return the header-level view of the latest ``limit`` messages in ``folder``."""
        connection = self._imap_connect()
        try:
            self._select(connection, folder)
            typ, data = connection.search(None, "ALL")
            if typ != "OK" or not data or not data[0]:
                return ()
            sequence = data[0].split()
            chosen = sequence[-limit:]
            messages: list[EmailMessage] = []
            for number in chosen:
                message = self._list_one(connection, number, folder)
                if message is not None:
                    messages.append(message)
            return tuple(messages)
        finally:
            with contextlib.suppress(Exception):
                connection.logout()

    def read_message(self, message_id: str, *, folder: str = "inbox") -> EmailMessage:
        """Read one message by its IMAP message sequence, including the body."""
        connection = self._imap_connect()
        try:
            self._select(connection, folder)
            typ, data = connection.fetch(message_id, "(BODY.PEEK[])")
            if typ != "OK" or not data:
                raise RuntimeError(f"message {message_id!r} not found in {folder}")
            raw = data[0][1] if isinstance(data[0], tuple) else None
            if raw is None:
                raise RuntimeError(f"message {message_id!r} could not be fetched")
            parsed = BytesParser(policy=policy.default).parsebytes(raw)
            return self._from_parsed(
                parsed, message_id=message_id, folder=folder, include_body=True
            )
        finally:
            with contextlib.suppress(Exception):
                connection.logout()

    def send_message(self, *, to: tuple[str, ...], subject: str, body: str) -> EmailMessage:
        """Send an outbound message and return a record of it.

        The caller is responsible for having this material action approved through
        the controlled-autonomy gate before calling.
        """
        connection = self._smtp_connect()
        try:
            message = self._build_mime(to, subject, body)
            connection.sendmail(self._email, list(to), message.as_string())
        finally:
            with contextlib.suppress(Exception):
                connection.close()
        return EmailMessage(
            subject=subject,
            body=body,
            sender=self._email,
            recipients=tuple(to),
            folder="sent",
        )

    # -- IMAP plumbing --------------------------------------------------------

    def _select(self, connection: imaplib.IMAP4, folder: str) -> None:
        typ, _ = connection.select(folder)
        if typ != "OK":
            raise RuntimeError(f"cannot open folder {folder!r}")

    def _list_one(
        self, connection: imaplib.IMAP4, number: bytes, folder: str
    ) -> EmailMessage | None:
        message_set = number.decode("ascii", "replace")
        typ, data = connection.fetch(message_set, "(BODY.PEEK[HEADER])")
        if typ != "OK" or not data:
            return None
        raw = data[0][1] if isinstance(data[0], tuple) else None
        if raw is None:
            return None
        parsed = BytesParser(policy=policy.default).parsebytes(raw)
        identifier = number.decode("ascii", "replace")
        return self._from_parsed(parsed, message_id=identifier, folder=folder)

    def _from_parsed(
        self, parsed: EmailParsed, *, message_id: str, folder: str, include_body: bool = False
    ) -> EmailMessage:
        recipients = tuple(
            part.strip()
            for part in (parsed.get("To") or "").split(",")
            if part.strip()
        )
        body = self._extract_body(parsed) if include_body else ""
        return EmailMessage(
            subject=parsed.get("Subject") or "",
            body=body,
            sender=parsed.get("From") or "",
            recipients=recipients,
            message_id=message_id,
            folder=folder,
        )

    @staticmethod
    def _extract_body(parsed: EmailParsed) -> str:
        if parsed.is_multipart():
            for part in parsed.walk():
                if part.get_content_type() == "text/plain":
                    payload = part.get_payload()
                    return str(payload).strip() if isinstance(payload, str) else ""
            return ""
        payload = parsed.get_payload()
        return str(payload).strip() if isinstance(payload, str) else ""

    @staticmethod
    def _build_mime(to: tuple[str, ...], subject: str, body: str) -> Any:
        from email.message import EmailMessage as Mime

        message = Mime()
        message["Subject"] = subject
        message["From"] = ""
        message["To"] = ", ".join(to)
        message.set_content(body)
        return message


def build_mail_source(environ: dict[str, str] | None = None) -> IMAPSMTPMailBox | None:
    """Build an :class:`IMAPSMTPMailBox` when mailbox configuration is present.

    ``None`` means "no mail capability configured" (missing required env vars), so
    a Jarvis built from this keeps working offline. Requires ``MAIL_IMAP_HOST``,
    ``MAIL_EMAIL``, and ``MAIL_PASSWORD``; ``MAIL_SMTP_HOST`` defaults to the IMAP
    host when absent.
    """
    import os

    env = environ or os.environ
    email = env.get("MAIL_EMAIL")
    password = env.get("MAIL_PASSWORD")
    imap_host = env.get("MAIL_IMAP_HOST")
    if not email or not password or not imap_host:
        return None
    smtp_host = env.get("MAIL_SMTP_HOST") or imap_host
    return IMAPSMTPMailBox(
        email=email,
        password=password,
        imap_host=imap_host,
        smtp_host=smtp_host,
        imap_port=int(env.get("MAIL_IMAP_PORT", _DEFAULT_IMAP_PORT)),
        smtp_port=int(env.get("MAIL_SMTP_PORT", _DEFAULT_SMTP_PORT)),
    )
