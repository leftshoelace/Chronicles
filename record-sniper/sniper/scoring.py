"""Turn (want, listing, reference price) into a Deal — or nothing."""
from __future__ import annotations

from datetime import datetime, timezone

from .config import Config
from .models import Deal, Listing, Reference, WantItem


def hours_until(iso: str | None, now: datetime | None = None) -> float | None:
    if not iso:
        return None
    try:
        end = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    return (end - now).total_seconds() / 3600


def buy_under(want: WantItem, ref: Reference | None, cfg: Config) -> float | None:
    """The price at which this record becomes worth grabbing."""
    caps = []
    if want.max_price is not None:
        caps.append(want.max_price)
    if ref is not None:
        caps.append(ref.value * cfg.deal_ratio)
    return max(caps) if caps else None


def flip_profit(total: float, ref: Reference | None, cfg: Config) -> float | None:
    """Rough profit if you resold at fair value after marketplace fees (buyer pays shipping)."""
    if ref is None:
        return None
    return round(ref.value * (1 - cfg.resale_fee_pct) - total, 2)


def evaluate(want: WantItem, listing: Listing, ref: Reference | None, cfg: Config,
             now: datetime | None = None) -> Deal | None:
    if listing.currency and listing.currency.upper() != cfg.currency.upper():
        return None
    if listing.price <= 0:
        return None

    shipping_assumed = listing.shipping is None
    ship = (0.0 if listing.local else cfg.default_shipping) if shipping_assumed else listing.shipping
    total = round(listing.price + ship, 2)

    hrs = hours_until(listing.ends_at, now) if listing.is_auction else None
    if listing.is_auction:
        if hrs is not None and hrs < 0:
            return None
        # A $3 bid with 6 days left means nothing. Only snipe auctions near the end.
        if hrs is None or hrs > cfg.auction_alert_hours:
            return None

    reasons: list[str] = []
    scores: list[float] = []
    steal = False

    if want.max_price is not None and total <= want.max_price:
        reasons.append(f"${total:.2f} is under your max of ${want.max_price:.2f}")
        frac = total / want.max_price if want.max_price else 0
        scores.append(0.5 + 0.5 * (1 - frac))
        steal |= frac <= 0.6

    if ref is not None and ref.value > 0:
        ratio = total / ref.value
        if ratio <= cfg.deal_ratio:
            reasons.append(f"{(1 - ratio) * 100:.0f}% below fair value ${ref.value:.2f} ({ref.basis})")
            scores.append(min(1.0, 1 - ratio))
            steal |= ratio <= cfg.steal_ratio

    profit = flip_profit(total, ref, cfg)
    if profit is not None and profit >= cfg.min_flip_profit:
        reasons.append(f"est. flip profit +${profit:.2f} after {cfg.resale_fee_pct * 100:.0f}% fees")
        scores.append(min(1.0, 0.4 + profit / 100))

    if not reasons:
        return None

    score = max(scores)
    if listing.local:
        score = min(1.0, score + 0.1)  # local = no shipping risk, can inspect, no competition from bots
    return Deal(
        want=want,
        listing=listing,
        total=total,
        shipping_assumed=shipping_assumed,
        reference=ref,
        tier="STEAL" if steal else "DEAL",
        score=round(score, 3),
        reasons=reasons,
        flip_profit=profit,
        hours_left=hrs,
    )
