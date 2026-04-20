"""Pulls new listing-alert emails from the shared Gmail inbox via IMAP.

We use IMAP instead of scraping because every aggregator supports saved-search
email alerts and sending mail is within their ToS. This gives us fresh listings
within minutes, no bot detection, no brittle HTML selectors to maintain across
the whole site.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Iterable

from imap_tools import AND, MailBox, MailMessage

from .config import EMAIL_SENDERS

log = logging.getLogger(__name__)


@dataclass
class RawEmail:
    uid: str
    sender: str
    subject: str
    html: str
    text: str
    date: str


def fetch_new_emails(since_uid: str | None = None) -> Iterable[RawEmail]:
    """Yield emails from allowlisted senders newer than since_uid.

    We fetch UNSEEN messages so the GitHub Actions run only sees new arrivals,
    then mark them SEEN. The dedupe DB is authoritative for what we've already
    processed, so re-runs are safe even if we mis-flag.
    """
    address = os.environ["GMAIL_ADDRESS"]
    password = os.environ["GMAIL_APP_PASSWORD"]

    with MailBox("imap.gmail.com").login(address, password, initial_folder="INBOX") as mb:
        for msg in mb.fetch(AND(seen=False), mark_seen=True, bulk=True):
            sender = (msg.from_ or "").lower()
            if not _sender_allowed(sender):
                continue
            yield RawEmail(
                uid=msg.uid or "",
                sender=sender,
                subject=msg.subject or "",
                html=msg.html or "",
                text=msg.text or "",
                date=str(msg.date) if msg.date else "",
            )


def _sender_allowed(sender: str) -> bool:
    return any(domain in sender for domain in EMAIL_SENDERS)
