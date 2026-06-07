"""
Parse .mbox files (Gmail exports) into a list of clean text documents.

Each email is returned as a dict with:
  - subject: str   (decoded email Subject header)
  - date:    str   (ISO date YYYY-MM-DD, or None if unparseable)
  - content: str   (clean plain text, HTML → text via BeautifulSoup)

Usage:
    from backend.services.mbox_parser import parse_mbox
    emails = parse_mbox(raw_bytes)
"""
from __future__ import annotations

import logging
import re
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime
from typing import Optional

logger = logging.getLogger(__name__)


def _decode_header_str(value: Optional[str]) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def _parse_iso_date(date_str: Optional[str]) -> Optional[str]:
    if not date_str:
        return None
    try:
        dt = parsedate_to_datetime(date_str)
        return dt.date().isoformat()
    except Exception:
        return None


def _html_to_text(html: str) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")

    # Remove non-content elements
    for tag in soup(["script", "style", "img", "head"]):
        tag.decompose()

    # Replace links with their text only
    for a in soup.find_all("a"):
        a.replace_with(a.get_text())

    text = soup.get_text(separator="\n", strip=True)

    # Strip invisible email preheader spacers (zero-width/soft-hyphen chars)
    text = re.sub(r"[\u00ad\u034f\u200b-\u200f\u2060\ufeff\u180e\u0600-\u0605͏]+", "", text)

    # Drop lines that became blank after spacer removal
    lines = [ln for ln in text.splitlines() if ln.strip()]
    text = "\n".join(lines)

    # Collapse excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def _extract_body(message) -> str:
    """Extract the best available body from an email message."""
    html_body = ""
    text_body = ""

    for part in message.walk():
        ct = part.get_content_type()
        if part.get_content_maintype() == "multipart":
            continue
        charset = part.get_param("charset") or "utf-8"
        payload = part.get_payload(decode=True)
        if not payload:
            continue
        decoded = payload.decode(charset, errors="replace")
        if ct == "text/html" and not html_body:
            html_body = decoded
        elif ct == "text/plain" and not text_body:
            text_body = decoded

    if html_body:
        return _html_to_text(html_body)

    # Fall back to plain text — strip quoted-printable artifacts
    return re.sub(r"\n{3,}", "\n\n", text_body).strip()


def parse_mbox(raw: bytes) -> list[dict]:
    """
    Parse raw .mbox bytes into a list of email dicts.
    Skips messages with empty bodies.
    Returns [{"subject": ..., "date": ..., "content": ...}, ...]
    """
    import email as email_mod

    # Normalize line endings — mbox message separator is \nFrom (LF-based)
    normalized = raw.replace(b"\r\n", b"\n")

    logger.warning(
        "parse_mbox called: raw=%d bytes, crlf_count=%d, from_lines=%d, first_80=%r",
        len(raw),
        raw.count(b"\r\n"),
        normalized.count(b"\nFrom "),
        raw[:80],
    )

    # Split into individual message chunks on the "From " envelope line.
    # The separator is a line that starts with "From " (mbox standard).
    # We split on \nFrom<space> to handle both the first message (starts
    # at byte 0) and subsequent ones.
    parts: list[bytes] = re.split(rb"\nFrom [^\n]*\n", normalized)

    # The very first chunk is everything before the first "From " line.
    # If the file starts with "From " (standard), the first chunk is empty
    # or just the first envelope line. Re-attach it with the actual content.
    #
    # Simpler alternative: find all "From " lines and slice between them.
    if not parts or (len(parts) == 1 and not parts[0].strip()):
        # Try an alternative: the whole file is one email with no separator
        parts = [normalized]

    results = []
    for chunk in parts:
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            msg = email_mod.message_from_bytes(chunk)
        except Exception:
            continue

        subject = _decode_header_str(msg.get("Subject"))
        date = _parse_iso_date(msg.get("Date"))
        content = _extract_body(msg)
        if not content:
            continue
        results.append({"subject": subject, "date": date, "content": content})

    return results
