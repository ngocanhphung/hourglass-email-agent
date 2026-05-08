"""
demo.py — Run the agent on mock emails (no Gmail setup needed).
Perfect for testing the AI brain before connecting your inbox.
"""

import os, json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Add src to path
import sys
sys.path.insert(0, str(Path(__file__).parent / "src"))

from agent import triage_email, draft_reply, write_digest, init_db, save_result
from datetime import datetime, timezone

MOCK_EMAILS = [
    {
        "id": "mock_001",
        "subject": "URGENT: Server down — prod deployment failing",
        "sender": "ops-team@company.com",
        "snippet": "Our production server has been down for 20 minutes...",
        "body": """Hi team,

Our production server has been down for 20 minutes and clients are being affected.
The deployment pipeline is throwing a 500 error on the final step.
We need someone to review the logs immediately and roll back if needed.

Error: ConnectionRefusedError on port 5432 (PostgreSQL)

Can you respond ASAP?

— DevOps""",
    },
    {
        "id": "mock_002",
        "subject": "Following up on our meeting last week",
        "sender": "sarah.chen@client.com",
        "snippet": "Just checking in on the proposal we discussed...",
        "body": """Hey,

Hope you're well! Just wanted to follow up on the AI workflow proposal 
we discussed last Tuesday. Did you get a chance to review the scope document?

We're hoping to move forward before end of month.

Let me know when you're free for a quick call.

Best,
Sarah""",
    },
    {
        "id": "mock_003",
        "subject": "Your weekly AI newsletter — 7 tools you need to know",
        "sender": "newsletter@aiweekly.io",
        "snippet": "This week in AI: GPT-5 rumours, Claude updates, and more...",
        "body": """Welcome to AI Weekly!

This week's top stories:
1. GPT-5 rumours intensify as OpenAI files new trademarks
2. Anthropic releases Claude Sonnet with 1M context
3. 7 new AI tools for productivity
4. Startup funding roundup: $2B raised across 40 deals

Click here to read more...

Unsubscribe | View in browser""",
    },
    {
        "id": "mock_004",
        "subject": "Invoice #INV-2847 — Due in 3 days",
        "sender": "billing@vendor.com",
        "snippet": "Your invoice for cloud services is due on Friday...",
        "body": """Dear Customer,

This is a reminder that Invoice #INV-2847 for $342.00 (cloud services - April)
is due in 3 days on Friday 10 May 2026.

Please ensure payment is made to avoid service interruption.

Payment link: https://pay.vendor.com/inv-2847

Thank you,
Billing Team""",
    },
    {
        "id": "mock_005",
        "subject": "Congrats on the CaseIT top 10 finish!",
        "sender": "professor.nguyen@deakin.edu.au",
        "snippet": "Just saw the results — incredible achievement...",
        "body": """Hi Rachel,

I just saw the CaseIT results — top 10 globally is a fantastic achievement, 
especially for a Year 2 student. You should be very proud.

I'd love to feature your work in our faculty newsletter if you're happy to 
share a brief reflection (2–3 sentences) on what you learned.

No rush — next week is fine.

Best,
Prof. Nguyen""",
    },
]


def run_demo():
    print("=" * 60)
    print("🤖  Hourglass Comms Agent — DEMO MODE")
    print("=" * 60)
    print(f"Processing {len(MOCK_EMAILS)} mock emails...\n")

    conn = init_db()
    results = []

    for email in MOCK_EMAILS:
        print(f"📧  {email['subject'][:55]}")
        print(f"    From: {email['sender']}")

        triage = triage_email(email)
        print(f"    → Category: {triage['category']}")
        print(f"    → Urgency:  {triage['urgency']}")
        print(f"    → Confidence: {triage['confidence']:.0%}")
        print(f"    → Summary: {triage.get('summary', '')[:80]}")

        draft = ""
        if triage.get("reply_needed") and triage["category"] in ("urgent_action", "follow_up"):
            draft = draft_reply(email, triage)
            print(f"    → Draft generated ({len(draft)} chars)")

        if triage.get("action_items"):
            print(f"    → Actions: {', '.join(triage['action_items'])}")

        result = {
            "message_id":   email["id"],
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
        results.append(result)
        print()

    digest_path = write_digest(results)
    print("=" * 60)
    print(f"✅  Done! Processed {len(results)} emails")
    print(f"📄  Digest written to: {digest_path}")
    print("\n--- DIGEST PREVIEW ---")
    print(digest_path.read_text())

    conn.close()


if __name__ == "__main__":
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("❌  Set ANTHROPIC_API_KEY in your .env file first")
        print("    Get free credits at: https://console.anthropic.com/")
    else:
        run_demo()
