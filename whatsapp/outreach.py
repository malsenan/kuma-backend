"""Send the first-contact message to pilot leads.

WhatsApp requires a pre-approved *template* to open a conversation (you can only
send free-form text within 24h of the user's last message). So first contact =
a template send; the rest of the conversation is handled by the webhook + engine.

Usage:
    # Preview who would be contacted (no messages sent):
    python -m whatsapp.outreach --pilot 20 --dry-run

    # Actually send, using an approved template named 'lumora_intro':
    python -m whatsapp.outreach --pilot 20 --template lumora_intro

Always dry-runs unless --template is given AND --dry-run is absent.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from leads.extract import default_csv_paths, load_many, select_pilot
from whatsapp.client import WhatsAppClient, WhatsAppError
from whatsapp.config import get_settings
from whatsapp.store import get_store

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> None:
    try:
        import sys
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Send first-contact messages to pilot leads.")
    parser.add_argument("--pilot", type=int, default=20, help="How many leads to contact")
    parser.add_argument("--template", type=str, default="", help="Approved template name (required to actually send)")
    parser.add_argument("--language", type=str, default="pt_BR")
    parser.add_argument("--include-review", action="store_true", help="Include inferred-phone leads")
    parser.add_argument("--dry-run", action="store_true", help="Print only; send nothing")
    parser.add_argument("paths", nargs="*", help="Lead CSVs (default: *Leads_*.csv in cwd)")
    args = parser.parse_args(argv)

    paths = [Path(p) for p in args.paths] or default_csv_paths()
    leads = load_many(paths)
    pilot = select_pilot(leads, args.pilot, include_review=args.include_review)

    print(f"Selected {len(pilot)} leads to contact:")
    for lead in pilot:
        flag = " (review phone)" if lead.phone_needs_review else ""
        print(f"  {lead.phone_e164}  {lead.full_name}{flag}")

    really_send = bool(args.template) and not args.dry_run
    if not really_send:
        reason = "no --template given" if not args.template else "--dry-run set"
        print(f"\nDRY RUN ({reason}). No messages sent.")
        return

    settings = get_settings()
    if not settings.is_configured():
        parser.error("WhatsApp not configured. Fill in .env (see .env.example).")

    client = WhatsAppClient(settings)
    store = get_store()
    sent, failed = 0, 0
    for lead in pilot:
        to = lead.phone_e164.lstrip("+")
        store.upsert_contact(to, lead.full_name, lead.lead_id)
        try:
            mid = client.send_template(to, args.template, args.language)
            store.save_outbound(to, "template", args.template, mid)
            sent += 1
            logger.info("Sent to %s (%s)", to, lead.full_name)
        except WhatsAppError as e:
            failed += 1
            logger.error("Failed for %s: %s", to, e)

    print(f"\nDone. Sent {sent}, failed {failed}.")


if __name__ == "__main__":
    main()
