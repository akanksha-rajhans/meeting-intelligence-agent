# **Meeting Intelligence Agent (MVP)**

Automating post-meeting workflows with AI
*Turning raw conversations into structured, actionable knowledge.*

---

## Overview

Teams spend hours in meetings, yet critical tasks and decisions often get lost.
This **AI-powered Meeting Intelligence Agent** automates everything that happens *after* a meeting:

* Extracts **Minutes of Meeting (MoM)**
* Identifies **action items**, **owners**, and **deadlines**
* Sends **Slack notifications** to stakeholders
* Stores structured outputs in a **SQLite3 database** for retrieval and analytics

This MVP demonstrates **real-world AI workflow automation**, combining LLM reasoning, structured data generation, and seamless integrations.

---

## Key Features

### **1. Automated MoM Extraction**

* Parses raw transcripts
* Detects tasks, decisions, risks, clarifications
* Produces structured JSON (stored in DB)

### **2. Action Item Intelligence**

* Maps tasks to owners
* Infers deadlines (explicit or implied)
* Normalizes vague commitments:
  *“I’ll handle it” → inferred owner*

### **3. Slack Notifications**

Pushes concise, actionable updates to a Slack channel immediately after processing.

### **4. Local Persistence (SQLite3)**

Every meeting is saved for future retrieval, analytics, and dashboarding.

### **5. Extensible Architecture**

Clean component boundaries → easy future integrations with Jira, Notion, Confluence, etc.

---

## Architecture

```
                +----------------------+
                |   Meeting Transcript |
                +----------+-----------+
                           |
                           v
                +----------------------+
                |  AI Processing Layer |
                | - MoM extraction     |
                | - Action items       |
                | - Decisions          |
                +----------+-----------+
                           |
                           v
               +--------------------------+
               |  Structured JSON Output  |
               | (stored as TEXT in DB)   |
               +-------------+------------+
                             |
                             v
         +----------------------------+----------------------+
         |                                                    |
         v                                                    v
+---------------------+                      +----------------------------+
| Slack Notification  |                      | SQLite3 Local Database     |
+---------------------+                      | meeting_agent.db           |
                                             +----------------------------+
```

---

## 🗂 Persistence Layer — SQLite3

All processed meetings are stored in a local SQLite database.

### **Database File**

./meeting_agent.db

### **Table: meeting_records**

| Column             | Type    | Description               |
| ------------------ | ------- | ------------------------- |
| id                 | INTEGER | Primary key               |
| meeting_date       | TEXT    | Extracted meeting date    |
| raw_transcript     | TEXT    | Original transcript       |
| structured_payload | TEXT    | JSON output (as a string) |
| created_at         | TEXT    | Timestamp                 |

This DB enables:

* Persistent meeting history
* Auditability
* Analytics layer for future enterprise features
* Ability to build dashboards or feed into BI tools

---

## Repository Structure

meeting-intelligence-agent/
│
├── src/
│   ├── main.py                # Entry point
│   ├── parser.py              # AI extraction logic
│   ├── db.py                  # SQLite3 wrapper (CRUD)
│   ├── slack_client.py        # Slack integration
│   ├── config.py              # Environment + constants
│
├── demo/
│   ├── sample_transcript.txt
│   ├── sample_output.json     # Demonstration only
│   └── demo_video.gif
│
├── docs/
│   ├── architecture.md
│   ├── roadmap.md
│   └── sequence_diagram.png
│
├── meeting_agent.db           # Auto-created on first run
├── requirements.txt
└── README.md

---

## Sample Structured Output (stored in SQLite as TEXT)

{
  "meeting_date": "2025-11-29",
  "participants": ["Arun", "Bharathi", "Nagaraju"],
  "action_items": [
    {
      "task": "Provide next steps for TAC uptake",
      "owner": "Nagaraju",
      "due_date": "ASAP"
    }
  ],
  "decisions": [
    "Service Logistics team will proceed with Approval Rules UI"
  ]
}

---

## Setup & Installation

### **1. Clone the repo**

git clone https://github.com/<your-username>/meeting-intelligence-agent.git
cd meeting-intelligence-agent

### **2. Install dependencies**

pip install -r requirements.txt

### **3. Environment variables**

Create a `.env`:

SLACK_BOT_TOKEN=your-slack-token
SLACK_CHANNEL_ID=your-channel-id
OPENAI_API_KEY=your-api-key

### **4. Run the agent**

python src/main.py --input demo/sample_transcript.txt

### **5. Check stored records**

Use any SQLite viewer
or run:

sqlite3 meeting_agent.db
SELECT id, meeting_date, created_at FROM meeting_records;

---

## Slack Output Example

> **Action Items from Today’s Meeting**
> • *Nagaraju:* Provide next steps for TAC uptake
> • *Deadline:* ASAP

Automatically generated → posted to Slack.

---

## Roadmap

### ** Next version**

* Better speaker attribution
* Improved task/owner detection
* Deadline extraction using temporal models

### ** Medium-term**

* Jira ticket creation
* Email summaries
* Multi-format transcript ingestion (audio → transcript)

### ** Enterprise Vision**

A full **Meeting OS** that handles:

* Pre-meeting briefs
* Real-time meeting intelligence
* Post-meeting orchestration
* Knowledge graphs across teams
* Org-level insights dashboard

---

## Contributions

PRs and suggestions welcome.

---

## License

MIT License.

---

