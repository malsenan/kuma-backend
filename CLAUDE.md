# Claude instructions for this project

## What this project is now

Lumora is a credit-access platform for informal Brazilian micro-entrepreneurs (mostly women). The project has pivoted from a rules-based scorecard to a three-deliverable pipeline:

1. **WhatsApp chatbot** — intake tool that contacts leads, guides them through a conversation flow, and collects documents, photos, and text
2. **Business portfolio builder** — AI pipeline that turns raw WhatsApp uploads into a structured business profile per applicant
3. **Scoring integration** — parses the portfolio into features and calls external scoring APIs (Serasa, Belvo)

The Phase 0 rules-based scorecard and its spec docs were removed in the pivot. They are preserved in git under the tag `phase0-archive` (`git checkout phase0-archive`) if anything is ever needed back — do not resurrect them into the new codebase.

## Environment

Always use the `.venv` at the project root. Never install packages on system Python.
On this machine the interpreter is `.venv/Scripts/python.exe` (Windows); on POSIX it's `.venv/bin/python`.

```bash
# Install
.venv/Scripts/python.exe -m pip install -e ".[api,dev]"

# Test
.venv/Scripts/python.exe -m pytest tests/ -v

# Run API (serves the WhatsApp webhook)
.venv/Scripts/python.exe -m uvicorn api.main:app --reload
```

## Project structure (current state)

```
whatsapp/    — WhatsApp Cloud API: config, webhook, client, store (SQLite), conversation engine, flows/
leads/       — load + normalize the Meta lead-ad CSV exports (Brazilian phone normalization)
portfolio/   — build a structured BusinessPortfolio from a contact's intake (Claude enrichment stubbed)
api/         — FastAPI app hosting the webhook (GET/POST /webhook, GET /health)
tests/       — pytest suite for the above (conftest has a FakeClient + message factories)
data/        — runtime SQLite DB + downloaded media (gitignored)
```

## Lead data

Two CSV files in the repo root are the source of real leads:
- `Negativados_Leads_2026-06-17_2026-06-20.csv` — leads with negative credit history
- `Taxa_Leads_2026-06-17_2026-06-20.csv` — leads concerned about high interest rates

Key fields: `full_name`, `whatsapp_number`, `email`, `date_of_birth`, `qual_negócio_você_tem` (business type), plus survey answers about credit needs.

The pilot targets ~20 of the ~200 leads.

## Hard constraints (LGPD)

Demographics — gender, location, residential moves — are collected only for bias monitoring and display. They must never be passed to a scoring function as features. This applies to the portfolio builder and the scoring integration.

## Pending external inputs

Before certain features can be built, these are needed:
- **Sandra's conversation flow** — the WhatsApp chatbot script/prompt
- **Business portfolio field template** — Sandra's definition of what fields a portfolio contains
- **WhatsApp Business API credentials** — phone number verified with Meta or Twilio
- **Serasa API access** — registration required; reference doc is `Serasa Experian developer API's.docx`
