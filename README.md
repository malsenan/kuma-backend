# Lumora — Credit Access for Informal Entrepreneurs

A credit-access platform for informal Brazilian micro-entrepreneurs (mostly women). Lumora uses WhatsApp to reach leads, collects documents and business information through a guided chat, builds a structured business portfolio from the raw uploads, and feeds that data into a probability scoring pipeline to assess creditworthiness.

---

## Three deliverables

### 1. WhatsApp chatbot (`whatsapp/`)

An intake tool that contacts leads from the lead CSV files and guides them through a structured conversation.

- Sends dynamic multiple-choice messages using the WhatsApp Business API
- Accepts text, images, documents, and voice messages from users
- Includes an escalation path to a human representative
- Stores all incoming data as raw + lightly structured responses for the portfolio builder

**Status:** Built — webhook, signature check, SQLite store, media download, and a declarative
flow engine are working and tested. Running on a **placeholder** flow (`whatsapp/flows/intake_pt_BR.json`)
until Sandra's approved script lands; needs Meta credentials in `.env` to go live.

### 2. Business portfolio builder (`portfolio/`)

An AI pipeline that turns raw WhatsApp uploads into a structured business profile per applicant.

- Input: text messages, photos (receipts, storefronts, ID), documents (bank statements, MEI certificate)
- OCR for text in images
- Claude processes all collected material and populates a business portfolio JSON schema
- Output: one structured JSON object per applicant

**Status:** Schema + deterministic builder are working and tested (assembles answers and media
from the store into a `BusinessPortfolio`). The Claude enrichment pass (OCR + soft-field extraction)
is stubbed, pending Sandra's field template.

### 3. Scoring integration (`api/`)

Parses the business portfolio into scoring features and calls external credit APIs.

- Serasa Experian API — credit bureau data
- Belvo API — Open Finance / PIX transaction history
- Outputs a probability score + recommended loan amount

**Status:** Serasa API reference doc in repo; access requires registration.

---

## Lead data

Two CSV files from Meta ad campaigns are the source of real leads (~200 total, ~20 targeted for pilot):

| File | Segment |
|------|---------|
| `Negativados_Leads_2026-06-17_2026-06-20.csv` | Leads with negative credit history |
| `Taxa_Leads_2026-06-17_2026-06-20.csv` | Leads concerned about high interest rates |

Key fields per lead: `full_name`, `whatsapp_number`, `email`, `date_of_birth`, business type (free text), and survey answers about credit needs and usage.

---

## Pipeline

```
Lead CSV (whatsapp_number)
    │
    ▼
WhatsApp chatbot  ←→  User sends text, photos, docs
    │
    ▼
Raw message store (per-user)
    │
    ▼
Business portfolio builder (Claude AI)
    │
    ▼
BusinessPortfolio JSON
    │
    ▼
Scoring integration  →  Serasa API / Belvo API
    │
    ▼
Probability score + recommended loan amount
```

---

## Repository layout

```
whatsapp/    — WhatsApp Cloud API: webhook, client, SQLite store, conversation engine, flows/
leads/       — load + normalize the Meta lead-ad CSV exports (Brazilian phone normalization)
portfolio/   — build a structured BusinessPortfolio from a contact's intake (AI enrichment stubbed)
api/         — FastAPI app hosting the webhook (GET/POST /webhook, GET /health)
tests/       — pytest suite for the above
data/        — runtime SQLite DB + downloaded media (gitignored)
```

> The Phase 0 rules-based scorecard was removed in the pivot; it lives in git under the
> tag `phase0-archive` if ever needed.

---

## Compliance

Demographics (gender, location) are collected for bias monitoring only. They are never passed as features to any scoring function (LGPD, Brazil).

---

## Getting started

```bash
# 1. Create and activate venv
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 2. Install
pip install -e ".[api,dev]"

# 3. Run tests
pytest tests/ -v

# 4. Run the API (serves the WhatsApp webhook)
uvicorn api.main:app --reload
# Swagger UI → http://localhost:8000/docs

# 5. Preview the pilot leads (sends nothing)
python -m leads.extract --pilot 20
```

---

## What's needed before building

| Item | Who | Unblocks |
|------|-----|---------|
| WhatsApp conversation flow / script | Sandra | Chatbot D1 |
| Business portfolio field template | Sandra | Portfolio builder D2 |
| WhatsApp Business API credentials | Muhannad | Chatbot D1 |
| Serasa API access | Muhannad | Scoring D3 |
