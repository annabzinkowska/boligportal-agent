"""Deterministic matching of an extracted listing against config.yaml.

Missing fields never reject a listing; they pass with a warning so the user
can judge from the card.
"""
from dataclasses import dataclass, field
from datetime import date


@dataclass
class Match:
    profile: str | None                 # key in config["profiles"], None = rejected
    warnings: list[str] = field(default_factory=list)
    reason: str | None = None           # why it was rejected


def _check_area(listing: dict, area: dict, warnings: list[str]) -> str | None:
    postcode = listing.get("postal_code")
    if postcode is not None:
        if any(lo <= postcode <= hi for lo, hi in area["postcodes"]):
            return None
        return f"postcode {postcode} outside search area"
    district = (listing.get("district") or "").strip().lower()
    if district:
        if district in area["districts"]:
            return None
        return f"district '{district}' outside search area"
    warnings.append("area unknown")
    return None


def _check_lease(listing: dict, lease: dict, warnings: list[str]) -> str | None:
    months = listing.get("rental_period_months")
    if months is None:
        warnings.append("lease length unknown")
        return None
    if months == 0 or months >= lease["min_months"]:
        return None
    return f"lease {months} months < {lease['min_months']}"


def _check_move_in(listing: dict, move_in: dict, warnings: list[str]) -> str | None:
    raw = listing.get("available_from")
    if not raw:
        warnings.append("move-in date unknown")
        return None
    try:
        available = date.fromisoformat(raw)
    except ValueError:
        warnings.append(f"move-in date unreadable: {raw}")
        return None
    if move_in["earliest"] <= available <= move_in["latest"]:
        return None
    return f"move-in {available} outside {move_in['earliest']}–{move_in['latest']}"


def _check_profile(listing: dict, profile: dict, warnings: list[str]) -> str | None:
    rooms = listing.get("rooms")
    if rooms is not None:
        if rooms < profile["rooms_min"]:
            return f"{rooms} rooms < {profile['rooms_min']}"
        if profile["rooms_max"] is not None and rooms > profile["rooms_max"]:
            return f"{rooms} rooms > {profile['rooms_max']}"
    rent = listing.get("monthly_rent")
    if rent is None:
        warnings.append("rent unknown")
        return None
    aconto = listing.get("aconto")
    if aconto is None:
        warnings.append("aconto unknown, compared rent only")
        aconto = 0
    total = rent + aconto
    if total > profile["max_total_rent"]:
        return f"{total:,.0f} kr incl. aconto > {profile['max_total_rent']:,}"
    if listing.get("rooms") is None:
        warnings.append("room count unknown")
    return None


def match(listing: dict, config: dict) -> Match:
    warnings: list[str] = []
    for check, key in ((_check_area, "area"), (_check_lease, "lease"), (_check_move_in, "move_in")):
        reason = check(listing, config[key], warnings)
        if reason:
            return Match(None, reason=reason)

    reasons = []
    for name, profile in config["profiles"].items():
        profile_warnings: list[str] = []
        reason = _check_profile(listing, profile, profile_warnings)
        if reason is None:
            return Match(name, warnings + profile_warnings)
        reasons.append(f"{name}: {reason}")
    return Match(None, reason="; ".join(reasons))
