# ⏳ Hourglass Email Agent

Agent that autonomously reads and triage emails by urgent/newsletter/spam/etc and suggest replies.
By Rachel Phung :)

---

## What It Does

The agent goes through your Gmail inbox and handles unread email end-to-end:

| Step | What happens |
|------|-------------|
| **1. Fetch** | Pulls unread emails from Gmail inbox |
| **2. Triage** | Claude classifies each email: `urgent_action`, `follow_up`, `fyi`, `newsletter`, or `spam` — with urgency level and confidence score |
| **3. Draft** | For emails needing a reply, Claude generates a context-aware draft matched to the email's tone |
| **4. Route** | Applies Gmail labels automatically (`Agent/Urgent`, `Agent/FollowUp`, etc.) |
| **5. Digest** | Writes a Markdown daily digest summarising everything processed, with drafts surfaced for urgent items |

All results are persisted to a local SQLite database so emails are never double-processed.

---

## Architecture

```
hourglass-agent/
├── src/
│   └── agent.py          # Core agent: triage → draft → route → digest
├── demo.py               # Run on mock emails (no Gmail needed)
├── setup_gmail.py        # One-time Gmail OAuth authorisation
├── credentials/          # Gmail OAuth token (gitignored)
├── logs/
│   ├── emails.db         # SQLite — all processed emails + drafts
│   ├── agent.log         # Full run logs
│   └── digest.md         # Latest daily digest
├── .env.example          # Environment variables template
└── requirements.txt
```

**LLM:** Claude Sonnet 4.6 via Anthropic API  
**Email:** Gmail API (OAuth 2.0)  
**Storage:** SQLite (persistent, no double-processing)  
**Stack:** Python 3.11+, no heavy frameworks

---

## Categories

| Category | Description | Auto-label |
|----------|-------------|------------|
| `urgent_action` | Needs reply or action today | `Agent/Urgent` |
| `follow_up` | Waiting on someone / reply within days | `Agent/FollowUp` |
| `fyi` | Informational, no action needed | `Agent/FYI` |
| `newsletter` | Marketing / newsletters | `Agent/Newsletter` |
| `spam` | Junk | `Agent/Spam` |

---

## Test my agent! You can either -

### Demo mode (no Gmail)

```bash
git clone <repo-url>
cd hourglass-agent

pip install -r requirements.txt

cp .env.example .env
# Edit .env — add your ANTHROPIC_API_KEY
# Get free credits at: https://console.anthropic.com/

python demo.py
```

### Live Gmail mode

**Step 1: Set up Google Cloud credentials**
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project → Enable Gmail API
3. Create OAuth 2.0 Client ID (Desktop app)
4. Download JSON → save as `credentials/client_secret.json`

**Step 2: Authorise**
```bash
python setup_gmail.py
# Opens browser, sign in with your Google account
```

**Step 3: Run**
```bash
# Live run (reads + labels your inbox)
python src/agent.py

# Dry run (reads only, no Gmail writes)
python src/agent.py --dry-run

# Limit emails processed
python src/agent.py --max 10
```

---

## Output Example

```
2026-05-08 10:14:22  INFO     Hourglass Comms Agent — starting run
2026-05-08 10:14:22  INFO     Fetching unread emails...
2026-05-08 10:14:23  INFO     Found 5 unread emails

Processing: URGENT: Server down — prod deployment failing
  From: ops-team@company.com
  Category=urgent_action  Urgency=high  Confidence=0.97
  → Routed to [Agent/Urgent]
  Draft generated (312 chars)

Processing: Following up on our meeting last week
  From: sarah.chen@client.com
  Category=follow_up  Urgency=medium  Confidence=0.91
  → Routed to [Agent/FollowUp]
  Draft generated (241 chars)

Processing: Your weekly AI newsletter
  From: newsletter@aiweekly.io
  Category=newsletter  Urgency=low  Confidence=0.99
  → Routed to [Agent/Newsletter]

Digest written → logs/digest.md
Done. Processed 5 new emails.
```

---

## Requirements

```
anthropic
google-auth
google-auth-oauthlib
google-auth-httplib2
google-api-python-client
python-dotenv
```
