"""MailBox: the seam between Jarvis and a mailbox (Odysseus email domain).

Email is a *material* capability Jarvis may gain (Vision §34, and the revised
D1: delegating actions is allowed, delegating cognition is not). Like
``ExternalSource``/``ResearchSource`` (Vision §38), this is a domain Protocol
behind which a concrete IMAP/SMTP adapter lives in ``infrastructure`` (D7): the
network and mailbox credentials stay at the edge, the transport is injectable,
and tests stay deterministic and offline (D8).

A ``MailBox`` *acts* on messages on request and *returns* message content with
provenance. It never reasons about them (D6) and never writes to Jarvis's
beliefs or memory. Reading is retrieval; sending is a deliberate material
action that the caller must have gated through the controlled-autonomy policy
(ask-first, per `09_CONTROLLED_AUTONOMY` and the Tool Registry's permission
levels for outbound/external actions).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from jarvis.domain.value_objects.email_message import EmailMessage


@runtime_checkable
class MailBox(Protocol):
    """Gives Jarvis read and outbound access to a mailbox on request."""

    def list_messages(self, *, folder: str = "inbox", limit: int = 10) -> tuple[EmailMessage, ...]:
        """Return the latest ``limit`` messages in ``folder``, as retrieval artifacts.

        An empty tuple is an honest "no messages here", not an error. Each message
        carries provenance; Jarvis weighs them as candidate evidence (D6).
        """
        ...

    def read_message(self, message_id: str, *, folder: str = "inbox") -> EmailMessage:
        """Read one message by its id, or raise when it cannot be retrieved.

        Raises only on a real failure of the underlying mailbox; absence of a
        message is a clear error, never a fabricated reply.
        """
        ...

    def send_message(self, *, to: tuple[str, ...], subject: str, body: str) -> EmailMessage:
        """Send an outbound message and return a record of it.

        This is a material action; the caller is responsible for having it
        approved through the controlled-autonomy gate before calling.
        """
        ...
