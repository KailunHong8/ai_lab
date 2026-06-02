"""
Gmail ingestion service.
Polls a Gmail label (default: Research/ARK), converts emails to markdown,
stores them in the Document table, and triggers LLM thesis extraction.

Setup requirements:
1. Create a Google Cloud project and enable the Gmail API.
2. Download OAuth2 credentials as backend/credentials.json (Desktop App type).
3. On first run, the browser will open for OAuth2 consent; token saved to backend/token.json.
"""
import asyncio
import base64
import hashlib
import os
from pathlib import Path
from typing import Optional

import html2text
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Document

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
_BACKEND_DIR = Path(__file__).parent.parent
TOKEN_PATH = _BACKEND_DIR / "token.json"
CREDS_PATH = _BACKEND_DIR / "credentials.json"
DOCS_DIR = _BACKEND_DIR.parent / "knowledge_base" / "documents"

_h2t = html2text.HTML2Text()
_h2t.ignore_links = False
_h2t.ignore_images = True


def _get_gmail_service():
    """Load or refresh OAuth2 credentials and return a Gmail API service object."""
    creds: Optional[Credentials] = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDS_PATH.exists():
                raise FileNotFoundError(
                    f"Gmail credentials not found at {CREDS_PATH}. "
                    "Download OAuth2 credentials (Desktop App) from Google Cloud Console "
                    "and save as backend/credentials.json."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_PATH), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_PATH.write_text(creds.to_json())
    return build("gmail", "v1", credentials=creds)


def _decode_body(payload: dict) -> str:
    """Recursively extract plain text or HTML body from a Gmail message payload."""
    mime = payload.get("mimeType", "")
    body_data = payload.get("body", {}).get("data", "")

    if mime == "text/plain" and body_data:
        return base64.urlsafe_b64decode(body_data).decode("utf-8", errors="replace")
    if mime == "text/html" and body_data:
        html = base64.urlsafe_b64decode(body_data).decode("utf-8", errors="replace")
        return _h2t.handle(html)

    for part in payload.get("parts", []):
        text = _decode_body(part)
        if text:
            return text
    return ""


def _fetch_label_id(service, label_name: str) -> Optional[str]:
    """Resolve a Gmail label name to its internal ID."""
    result = service.users().labels().list(userId="me").execute()
    for lbl in result.get("labels", []):
        if lbl["name"] == label_name:
            return lbl["id"]
    return None


def _fetch_messages(service, label_id: str, max_results: int = 50) -> list[dict]:
    result = service.users().messages().list(
        userId="me", labelIds=[label_id], maxResults=max_results
    ).execute()
    return result.get("messages", [])


def _fetch_full_message(service, msg_id: str) -> dict:
    return service.users().messages().get(
        userId="me", id=msg_id, format="full"
    ).execute()


async def sync_gmail(label_name: str, db: AsyncSession) -> int:
    """
    Fetch emails from `label_name`, save new ones to DB + documents/ folder,
    and trigger LLM extraction. Returns count of newly ingested documents.
    """
    from backend.services import thesis_extractor  # avoid circular import at module level

    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    def _fetch():
        service = _get_gmail_service()
        label_id = _fetch_label_id(service, label_name)
        if not label_id:
            raise ValueError(
                f"Gmail label '{label_name}' not found. "
                "Create it in Gmail and apply it to your research emails."
            )
        return _fetch_messages(service, label_id), service

    messages, service = await asyncio.to_thread(_fetch)
    count = 0

    for msg_ref in messages:
        msg_id = msg_ref["id"]
        doc_id = hashlib.sha256(msg_id.encode()).hexdigest()[:32]

        # Skip if already ingested
        existing = await db.execute(select(Document).where(Document.id == doc_id))
        if existing.scalar_one_or_none():
            continue

        full_msg = await asyncio.to_thread(_fetch_full_message, service, msg_id)
        headers = {h["name"]: h["value"] for h in full_msg.get("payload", {}).get("headers", [])}
        subject = headers.get("Subject", "No Subject")
        date_str = headers.get("Date", "")[:10]  # rough YYYY-MM-DD extraction
        content = _decode_body(full_msg.get("payload", {}))

        if not content.strip():
            continue

        # Persist raw markdown file
        safe_date = date_str.replace("-", "") if date_str else "unknown"
        filename = DOCS_DIR / f"{safe_date}_{doc_id[:8]}.md"
        filename.write_text(content, encoding="utf-8")

        # Save Document record
        doc = Document(
            id=doc_id,
            source=label_name.split("/")[-1],  # e.g. "ARK" from "Research/ARK"
            title=subject,
            content=content,
            date=date_str or None,
            email_id=msg_id,
            processed=False,
        )
        db.add(doc)
        await db.commit()
        await db.refresh(doc)

        # Trigger LLM extraction
        await thesis_extractor.extract_and_save(doc_id, content, db)
        count += 1

    return count
