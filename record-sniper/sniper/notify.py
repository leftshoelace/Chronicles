"""Send deal alerts: console, phone push (ntfy), Discord, email."""
from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage

from .config import Config
from .http import HttpError, request
from .models import Deal


def format_deal(d: Deal) -> tuple[str, str]:
    """Return (title, body) for a deal."""
    l = d.listing
    icon = "🔥" if d.tier == "STEAL" else "💰"
    title = f"{icon} {d.tier}: {d.want.label}"
    ship = "ship est." if d.shipping_assumed else "ship"
    ship_amt = d.total - l.price
    lines = [f"${l.price:.2f} + ${ship_amt:.2f} {ship} = ${d.total:.2f}  ·  {l.source}"]
    if l.is_auction:
        hrs = f"{d.hours_left:.1f}h" if d.hours_left is not None else "?"
        lines.append(f"⏱ Auction — current bid, ends in {hrs} (will likely go higher)")
    if l.local:
        lines.append(f"📍 LOCAL — go check it out{': ' + l.location if l.location else ''}")
    elif l.location:
        lines.append(f"Ships from {l.location}")
    lines += [f"• {r}" for r in d.reasons]
    if d.want.min_condition:
        lines.append(f"Check grade (you want {d.want.min_condition}+)")
    lines.append(l.title)
    lines.append(l.url)
    return title, "\n".join(lines)


class Notifier:
    def __init__(self, cfg: Config, dry_run: bool = False):
        self.cfg = cfg
        self.dry_run = dry_run

    def send(self, deals: list[Deal]) -> None:
        if not deals:
            return
        for d in deals:
            title, body = format_deal(d)
            if self.cfg.notify_console or self.dry_run:
                print(f"\n{title}\n{body}")
            if self.dry_run:
                continue
            self._try(self._ntfy, d, title, body)
            self._try(self._discord, d, title, body)
        if not self.dry_run:
            self._try(self._email, deals)

    def _try(self, fn, *args) -> None:
        try:
            fn(*args)
        except (HttpError, OSError, smtplib.SMTPException) as e:
            print(f"  ! notification via {fn.__name__.strip('_')} failed: {e}")

    def _ntfy(self, d: Deal, title: str, body: str) -> None:
        if not self.cfg.ntfy_topic:
            return
        ascii_title = title.encode("ascii", "ignore").decode().strip()  # HTTP headers must be latin-1
        tags = ["fire" if d.tier == "STEAL" else "moneybag"] + (["round_pushpin"] if d.listing.local else [])
        request(
            f"{self.cfg.ntfy_server}/{self.cfg.ntfy_topic}", method="POST", data=body,
            headers={
                "Title": ascii_title,
                "Click": d.listing.url,
                "Tags": ",".join(tags),
                "Priority": "5" if d.tier == "STEAL" or d.listing.local else "4",
                "Content-Type": "text/plain; charset=utf-8",
            },
        )

    def _discord(self, d: Deal, title: str, body: str) -> None:
        if not self.cfg.discord_webhook:
            return
        request(self.cfg.discord_webhook, method="POST", data={"content": f"**{title}**\n{body}"[:1990]})

    def _email(self, deals: list[Deal]) -> None:
        e = self.cfg.email
        if not e or not e.get("to") or not e.get("smtp_host"):
            return
        msg = EmailMessage()
        steals = sum(d.tier == "STEAL" for d in deals)
        msg["Subject"] = f"Record Sniper: {len(deals)} deal(s)" + (f", {steals} steal(s)" if steals else "")
        msg["From"] = e.get("from") or e.get("username") or e["to"]
        msg["To"] = e["to"]
        msg.set_content("\n\n".join("\n".join(format_deal(d)) for d in deals))
        port = int(e.get("smtp_port", 587))
        ctx = ssl.create_default_context()
        if port == 465:
            server = smtplib.SMTP_SSL(e["smtp_host"], port, context=ctx, timeout=30)
        else:
            server = smtplib.SMTP(e["smtp_host"], port, timeout=30)
            server.starttls(context=ctx)
        with server:
            if e.get("username"):
                server.login(e["username"], e.get("password", ""))
            server.send_message(msg)
