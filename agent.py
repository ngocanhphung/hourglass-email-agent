"""
Hourglass Comms Agent
Autonomous email triage, drafting, routing and digest — built for the Hourglass AI challenge.
Author: Rachel Phung
"""

import os
import json
import base64
import sqlite3
import logging
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

import anthropic
from googleapiclient.discovery import build

load_dotenv()

# ── Paths ────────────────────────────────────────────────────────────────────
ROOT        = Path(__file__).parent
DB_PATH     = ROOT / "logs" / "emails.db"
LOG_PATH    = ROOT / "logs" / "agent.log"
DIGEST_PATH = ROOT / "logs" / "digest.md"

# Ensure logs directory exists before logging is configured
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    handlers=[logging.FileHandler(LOG_PATH), logging.StreamHandler()],
)
log = logging.getLogger("comms-agent")

# ── DB ───────────────────────────────────────────────────────────────────────
def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS processed (
            message_id   TEXT PRIMARY KEY,
            subject      TEXT,
            sender       TEXT,
            category     TEXT,
            urgency      TEXT,
            confidence   REAL,
            draft        TEXT,
            action_items TEXT,
            processed_at TEXT
        )
    """)
    conn.commit()
    return conn

def already_processed(conn, message_id: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM processed WHERE message_id=?", (message_id,)
    ).fetchone() is not None

def save_result(conn, result: dict):
    conn.execute("""
        INSERT OR REPLACE INTO processed
        VALUES (:message_id,:subject,:sender,:category,:urgency,
                :confidence,:draft,:action_items,:processed_at)
    """, result)
    conn.commit()

# ── Gmail helpers ─────────────────────────────────────────────────────────────
def get_gmail_service():
    """Build Gmail service from stored credentials."""
    from google.oauth2.credentials import Credentials
    cred_file = ROOT / "credentials" / "token.json"
    if not cred_file.exists():
        raise FileNotFoundError(
            "credentials/token.json not found. Run setup_gmail.py first."
        )
    creds = Credentials.from_authorized_user_file(str(cred_file))
    return build("gmail", "v1", credentials=creds)

def fetch_unread_emails(service, max_results: int = 20) -> list[dict]:
    """Return list of unread emails from inbox."""
    results = service.users().messages().list(
        userId="me",
        q="is:unread in:inbox",
        maxResults=max_results,
    ).execute()

    messages = results.get("messages", [])
    emails = []
    for msg in messages:
        full = service.users().messages().get(
            userId="me", id=msg["id"], format="full"
        ).execute()
        emails.append(parse_email(full))
    return emails

def parse_email(msg: dict) -> dict:
    headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}

    # Extract body text
    body = ""
    def extract_parts(parts):
        nonlocal body
        for part in parts:
            if part.get("mimeType") == "text/plain" and "data" in part.get("body", {}):
                body += base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="ignore")
            if "parts" in part:
                extract_parts(part["parts"])

    payload = msg["payload"]
    if "parts" in payload:
        extract_parts(payload["parts"])
    elif "data" in payload.get("body", {}):
        body = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="ignore")

    return {
        "id":      msg["id"],
        "subject": headers.get("Subject", "(no subject)"),
        "sender":  headers.get("From", "unknown"),
        "snippet": msg.get("snippet", ""),
        "body":    body[:3000],  # cap to avoid excessive tokens
    }

def apply_gmail_label(service, message_id: str, label_name: str):
    """Create label if needed and apply it."""
    try:
        labels = service.users().labels().list(userId="me").execute().get("labels", [])
        label_id = next((l["id"] for l in labels if l["name"] == label_name), None)
        if not label_id:
            new_label = service.users().labels().create(
                userId="me", body={"name": label_name}
            ).execute()
            label_id = new_label["id"]
        service.users().messages().modify(
            userId="me", id=message_id,
            body={"addLabelIds": [label_id]},
        ).execute()
    except Exception as e:
        log.warning(f"Label apply failed for {message_id}: {e}")

def mark_as_read(service, message_id: str):
    try:
        service.users().messages().modify(
            userId="me", id=message_id,
            body={"removeLabelIds": ["UNREAD"]},
        ).execute()
    except Exception as e:
        log.warning(f"Mark-read failed for {message_id}: {e}")

# ── Claude brain ──────────────────────────────────────────────────────────────
CLAUDE = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

TRIAGE_PROMPT = """You are an autonomous email triage agent. Analyse the email and return ONLY valid JSON.

Categories:
- urgent_action   → needs reply or action today
- follow_up       → waiting on someone / needs reply within a few days
- fyi             → informational, no action needed
- newsletter      → marketing / newsletter
- spam            → junk

Return exactly this JSON structure:
{{
  "category":     "<one of the above>",
  "urgency":      "high|medium|low",
  "confidence":   <0.0-1.0>,
  "summary":      "<one sentence summary>",
  "action_items": ["<item1>", "<item2>"],
  "reply_needed": true|false,
  "tone":         "formal|casual|neutral"
}}

Email:
FROM: {sender}
SUBJECT: {subject}
BODY:
{body}
"""

DRAFT_PROMPT = """You are a professional email assistant. Write a concise, helpful reply to the email below.
Match the tone: {tone}. The reply should be ready to send — no placeholders.

FROM: {sender}
SUBJECT: {subject}
BODY:
{body}

Summary of what's needed: {summary}
Action items to address: {action_items}

Write only the email body (no subject line, no "Here is a draft:" preamble).
"""

def triage_email(email: dict) -> dict:
    prompt = TRIAGE_PROMPT.format(
        sender=email["sender"],
        subject=email["subject"],
        body=email["body"] or email["snippet"],
    )
    response = CLAUDE.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text.strip()
    # Strip markdown fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw)

def draft_reply(email: dict, triage: dict) -> str:
    prompt = DRAFT_PROMPT.format(
        sender=email["sender"],
        subject=email["subject"],
        body=email["body"] or email["snippet"],
        tone=triage.get("tone", "neutral"),
        summary=triage.get("summary", ""),
        action_items=", ".join(triage.get("action_items", [])),
    )
    response = CLAUDE.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()

# ── Routing rules ─────────────────────────────────────────────────────────────
LABEL_MAP = {
    "urgent_action": "Agent/Urgent",
    "follow_up":     "Agent/FollowUp",
    "fyi":           "Agent/FYI",
    "newsletter":    "Agent/Newsletter",
    "spam":          "Agent/Spam",
}

def route_email(service, email: dict, triage: dict):
    category = triage.get("category", "fyi")
    label    = LABEL_MAP.get(category, "Agent/FYI")
    apply_gmail_label(service, email["id"], label)
    log.info(f"  → Routed to [{label}]")

# ── Daily digest ──────────────────────────────────────────────────────────────
def write_digest(results: list[dict]):
    now   = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    counts = {}
    for r in results:
        counts[r["category"]] = counts.get(r["category"], 0) + 1

    urgent = [r for r in results if r["category"] == "urgent_action"]

    lines = [
        f"# 📬 Comms Agent Digest — {now}",
        f"\n**Processed:** {len(results)} emails\n",
        "## Summary",
    ]
    for cat, n in sorted(counts.items()):
        lines.append(f"- `{cat}`: {n}")

    if urgent:
        lines.append("\n## 🔴 Urgent — Action Required")
        for r in urgent:
            lines.append(f"\n### {r['subject']}")
            lines.append(f"**From:** {r['sender']}")
            if r.get("action_items"):
                items = json.loads(r["action_items"]) if isinstance(r["action_items"], str) else r["action_items"]
                for item in items:
                    lines.append(f"- {item}")
            if r.get("draft"):
                lines.append(f"\n**Draft reply:**\n> {r['draft'][:300]}...")

    DIGEST_PATH.write_text("\n".join(lines))
    log.info(f"Digest written → {DIGEST_PATH}")
    return DIGEST_PATH

# ── Main agent loop ───────────────────────────────────────────────────────────
def run(dry_run: bool = False, max_emails: int = 20):
    log.info("=" * 60)
    log.info("Hourglass Comms Agent — starting run")
    log.info(f"dry_run={dry_run}  max_emails={max_emails}")

    conn    = init_db()
    service = get_gmail_service()

    log.info("Fetching unread emails...")
    emails = fetch_unread_emails(service, max_results=max_emails)
    log.info(f"Found {len(emails)} unread emails")

    session_results = []

    for email in emails:
        mid = email["id"]
        if already_processed(conn, mid):
            log.info(f"  skip (already processed): {email['subject'][:50]}")
            continue

        log.info(f"\nProcessing: {email['subject'][:60]}")
        log.info(f"  From: {email['sender']}")

        try:
            # Step 1: Triage
            triage = triage_email(email)
            log.info(f"  Category={triage['category']}  Urgency={triage['urgency']}  Confidence={triage['confidence']:.2f}")

            # Step 2: Draft reply if needed
            draft = ""
            if triage.get("reply_needed") and triage["category"] in ("urgent_action", "follow_up"):
                draft = draft_reply(email, triage)
                log.info(f"  Draft generated ({len(draft)} chars)")

            # Step 3: Route (apply Gmail labels)
            if not dry_run:
                route_email(service, email, triage)
                mark_as_read(service, mid)

            result = {
                "message_id":   mid,
                "subject":      email["subject"],
                "sender":       email["sender"],
                "category":     triage["category"],
                "urgency":      triage["urgency"],
                "confidence":   triage["confidence"],
                "draft":        draft,
                "action_items": json.dumps(triage.get("action_items", [])),
                "processed_at": datetime.now(timezone.utc).isoformat(),
            }
            save_result(conn, result)
            session_results.append(result)

        except Exception as e:
            log.error(f"  ERROR processing {mid}: {e}")
            continue

    # Step 4: Write digest
    if session_results:
        write_digest(session_results)

    log.info(f"\nDone. Processed {len(session_results)} new emails.")
    conn.close()
    return session_results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Hourglass Comms Agent")
    parser.add_argument("--dry-run", action="store_true", help="Skip Gmail label writes")
    parser.add_argument("--max",     type=int, default=20, help="Max emails to fetch")
    args = parser.parse_args()
run(dry_run=args.dry_run)