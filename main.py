"""Turn BoligPortal SearchAgent alert emails into tailored application drafts on Telegram.

Usage:
  python main.py                       # process unread alerts via IMAP, send to Telegram
  python main.py --dry-run             # same, but print cards and leave emails unread
  python main.py --eml alert.eml       # process a saved email (implies --dry-run unless --send)
"""
import argparse
import email
import html
import imaplib
import logging
import os
import re
from email.message import Message
from html.parser import HTMLParser
from pathlib import Path

import requests
import yaml

import llm
from filters import match

ROOT = Path(__file__).parent
log = logging.getLogger("bolig")


class _TextExtractor(HTMLParser):
    """HTML email -> plain text, keeping link targets next to their anchor text."""

    BLOCK = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "table"}

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.hrefs: list[str | None] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("style", "script"):
            self.skip += 1
        elif tag == "a":
            self.hrefs.append(dict(attrs).get("href"))
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("style", "script"):
            self.skip -= 1
        elif tag == "a" and self.hrefs:
            href = self.hrefs.pop()
            if href and href.startswith("http"):
                self.parts.append(f" [{href}]")
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)

    def text(self) -> str:
        text = "".join(self.parts)
        text = re.sub(r"[ \t\xa0]+", " ", text)
        return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def email_to_text(msg: Message) -> str:
    bodies: dict[str, str] = {}
    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        payload = part.get_payload(decode=True)
        if payload is not None:
            charset = part.get_content_charset() or "utf-8"
            bodies.setdefault(part.get_content_type(), payload.decode(charset, errors="replace"))
    if "text/html" in bodies:
        parser = _TextExtractor()
        parser.feed(bodies["text/html"])
        return parser.text()
    return bodies.get("text/plain", "")


def listing_id(url: str) -> str:
    found = re.findall(r"\d{5,}", url)
    return found[-1] if found else url


def _kr(value) -> str:
    return "?" if value is None else f"{value:,.0f}".replace(",", ".")


def format_card(listing: dict, profile_label: str, warnings: list[str], draft: dict) -> str:
    e = html.escape
    rent, aconto = listing.get("monthly_rent"), listing.get("aconto")
    total = None if rent is None else rent + (aconto or 0)
    months = listing.get("rental_period_months")
    lease = "?" if months is None else "unlimited" if months == 0 else f"{months} mo"
    fit_icon = {"ok": "✅", "warn": "⚠️", "reject": "⛔"}[draft["fit"]]
    lines = [
        f"🏠 <b>{e(listing['title'])}</b>",
        e(" · ".join(filter(None, [listing.get("address"), listing.get("district")]))),
        f"{_kr(listing.get('rooms'))} rooms · {_kr(listing.get('size_m2'))} m² · "
        f"{_kr(rent)} + {_kr(aconto)} aconto = <b>{_kr(total)} kr</b>",
        f"Lease: {lease} · Move-in: {e(listing.get('available_from') or '?')}",
        f"Profile: <b>{e(profile_label)}</b> · Fit: {fit_icon}",
    ]
    if warnings:
        lines.append("❔ " + e(", ".join(warnings)))
    if draft["blockers"]:
        lines.append("❗ " + e("; ".join(draft["blockers"])))
    lines += [f'<a href="{e(listing["url"], quote=True)}">Open listing</a>', "",
              f"<pre>{e(draft['message'])}</pre>"]
    return "\n".join(lines)


def send_telegram(text: str) -> None:
    response = requests.post(
        f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/sendMessage",
        json={
            "chat_id": os.environ["TELEGRAM_CHAT_ID"],
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
        timeout=20,
    )
    response.raise_for_status()


def process_email(msg: Message, config: dict, applicant: str) -> list[str]:
    """Returns the Telegram cards to send for one alert email."""
    cards = []
    for listing in llm.extract_listings(email_to_text(msg)):
        ad_id = listing_id(listing["url"])
        result = match(listing, config)
        if result.profile is None:
            log.info("listing %s skipped: %s", ad_id, result.reason)
            continue
        profile = config["profiles"][result.profile]
        draft = llm.draft_application(listing, profile["label"], result.warnings, applicant)
        log.info("listing %s matched %s, fit=%s", ad_id, result.profile, draft["fit"])
        cards.append(format_card(listing, profile["label"], result.warnings, draft))
    return cards


def unread_alerts(imap: imaplib.IMAP4_SSL):
    _, data = imap.uid("search", None, "UNSEEN")
    for uid in data[0].split():
        _, fetched = imap.uid("fetch", uid, "(BODY.PEEK[])")
        yield uid, email.message_from_bytes(fetched[0][1])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="print cards, don't send or mark read")
    parser.add_argument("--eml", type=Path, help="process a saved .eml instead of the mailbox")
    parser.add_argument("--send", action="store_true", help="with --eml: send cards to Telegram")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    config = yaml.safe_load((ROOT / "config.yaml").read_text())
    applicant = os.environ.get("APPLICANT_PROFILE") or (ROOT / "applicant_profile.md").read_text()

    def deliver(cards: list[str], dry_run: bool) -> None:
        for card in cards:
            print(card, end="\n\n" + "-" * 60 + "\n\n") if dry_run else send_telegram(card)

    if args.eml:
        msg = email.message_from_bytes(args.eml.read_bytes())
        deliver(process_email(msg, config, applicant), dry_run=not args.send)
        return

    imap = imaplib.IMAP4_SSL(os.environ.get("IMAP_HOST") or "imap.gmail.com")
    imap.login(os.environ["IMAP_USER"], os.environ["IMAP_PASSWORD"])
    imap.select(f'"{os.environ.get("IMAP_FOLDER") or "BoligPortal"}"')
    try:
        for uid, msg in unread_alerts(imap):
            try:
                deliver(process_email(msg, config, applicant), args.dry_run)
            except Exception:
                # Mark it read anyway so a broken email isn't retried (and billed) every run.
                log.exception("failed to process email uid %s", uid.decode())
                if not args.dry_run:
                    send_telegram(f"⚠️ Couldn't process a BoligPortal alert: "
                                  f"{html.escape(msg.get('Subject', '(no subject)'))}. Check the email manually.")
            if not args.dry_run:
                imap.uid("store", uid, "+FLAGS", "(\\Seen)")
    finally:
        imap.logout()


if __name__ == "__main__":
    main()
