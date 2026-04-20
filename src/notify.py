"""Telegram notification sink.

Uses the HTTP Bot API directly (no async runtime needed for a one-shot cron).
"""
from __future__ import annotations

import logging
import os
import time

import requests

from .model import Listing

log = logging.getLogger(__name__)

_API = "https://api.telegram.org/bot{token}/{method}"


def send_listings(listings: list[Listing]) -> None:
    if not listings:
        return
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    for listing in listings:
        try:
            _send_one(token, chat_id, listing)
        except requests.HTTPError as e:
            log.warning("telegram send failed for %s: %s", listing.url, e)
        # Telegram rate limit is ~30 msg/sec globally, 1 msg/sec per chat.
        time.sleep(1.1)


def _send_one(token: str, chat_id: str, listing: Listing) -> None:
    caption = _format_caption(listing)
    if listing.image_url:
        url = _API.format(token=token, method="sendPhoto")
        data = {
            "chat_id": chat_id,
            "photo": listing.image_url,
            "caption": caption,
            "parse_mode": "HTML",
        }
    else:
        url = _API.format(token=token, method="sendMessage")
        data = {
            "chat_id": chat_id,
            "text": caption,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        }
    r = requests.post(url, data=data, timeout=20)
    r.raise_for_status()


def _format_caption(listing: Listing) -> str:
    price = f"${listing.price:,}" if listing.price else "price ?"
    beds = f"{listing.bedrooms:g}BR" if listing.bedrooms else "BR ?"
    hood = listing.neighborhood or listing.address or "location ?"
    source = listing.source.upper()
    fee = ""
    if listing.broker_fee is True:
        fee = f"  broker fee ({listing.fee_text})"
    elif listing.broker_fee is False:
        fee = "  no-fee"
    title = _escape(listing.title)[:120]
    return (
        f"<b>{price}</b>  {beds}  {_escape(hood)}{_escape(fee)}\n"
        f"{title}\n"
        f"<a href=\"{_escape(listing.url)}\">{source}</a>"
    )


def _escape(s: str) -> str:
    return (
        (s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
