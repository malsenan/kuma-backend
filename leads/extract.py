"""Load and normalize leads from the Meta lead-ad CSV exports.

The CSVs are UTF-16 LE, tab-separated, with Portuguese column headers. This
module reads them, maps the columns to the `Lead` model, and normalizes the
WhatsApp numbers to E.164 (+55DDXXXXXXXXX).

CLI:
    python -m leads.extract                 # summarize both CSVs in the repo root
    python -m leads.extract --pilot 20 --out data/pilot.json
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Iterable, Optional

from leads.models import Lead

# Map the (snake_cased) Portuguese headers Meta exports to Lead fields.
# Matching is done on a normalized key (lowercase, spaces/punctuation stripped)
# so small header variations between exports still line up.
COLUMN_MAP = {
    "id": "lead_id",
    "createdtime": "created_time",
    "platform": "platform",
    "email": "email",
    "fullname": "full_name",
    "whatsappnumber": "whatsapp_raw",
    "dateofbirth": "date_of_birth",
    "qualnegóciovocêtem": "business_type",
    "quandovocêprecisadedinheiroparaoseunegócioondevocêbusca": "where_seek_money",
    "quantovocêcostumaprecisarquandobuscacrédito": "amount_needed",
    "paraoquevocêmaisusaessedinheiro": "money_use",
    "qualéamaiordificuldadequandovocêtentapegarumempréstimo": "biggest_difficulty",
    "seexistisseumappqueanalisasseseuhistóricodopixparaliberarcréditosemburocraciaqualachancedevocêusar": "app_likelihood",
}


def _force_utf8_stdout() -> None:
    """Make stdout tolerate non-ASCII (lead names) on a Windows console."""
    try:
        import sys
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass


def _norm_key(header: str) -> str:
    """Normalize a CSV header for tolerant matching."""
    return re.sub(r"[^0-9a-zàáâãéêíóôõúüç]", "", header.strip().lower())


def normalize_br_phone(raw: str) -> tuple[str, bool, bool]:
    """Normalize a Brazilian phone number to E.164.

    Returns (e164, valid, needs_review).
      * e164         "+55DDXXXXXXXXX" or "" when unparseable
      * valid        True if we produced a plausible 13-digit BR mobile
      * needs_review True when we had to infer the 9th (mobile) digit

    Brazilian mobiles are +55 + 2-digit area code (DDD) + 9 digits (the local
    part starts with 9). Some exports drop the country code and/or the leading
    9; we repair those but flag the inferred ones for review.
    """
    if not raw:
        return "", False, False

    digits = re.sub(r"\D", "", raw)
    if digits.startswith("00"):          # international dialing prefix
        digits = digits[2:]

    # Strip country code if present.
    if digits.startswith("55") and len(digits) >= 12:
        rest = digits[2:]
    else:
        rest = digits

    if len(rest) < 10 or len(rest) > 11:
        return "", False, False          # cannot place a DDD + local number

    ddd, local = rest[:2], rest[2:]
    if not _valid_ddd(ddd):
        return "", False, False

    needs_review = False
    if len(local) == 8:
        # Missing the leading mobile 9 — infer it, but flag for review.
        local = "9" + local
        needs_review = True
    elif len(local) == 9 and local[0] != "9":
        # 9-digit local that doesn't start with 9 is unusual; keep but flag.
        needs_review = True

    return f"+55{ddd}{local}", True, needs_review


# Valid Brazilian area codes (DDDs). Numbers outside this set are rejected.
_VALID_DDDS = {
    11, 12, 13, 14, 15, 16, 17, 18, 19, 21, 22, 24, 27, 28, 31, 32, 33, 34, 35,
    37, 38, 41, 42, 43, 44, 45, 46, 47, 48, 49, 51, 53, 54, 55, 61, 62, 63, 64,
    65, 66, 67, 68, 69, 71, 73, 74, 75, 77, 79, 81, 82, 83, 84, 85, 86, 87, 88,
    89, 91, 92, 93, 94, 95, 96, 97, 98, 99,
}


def _valid_ddd(ddd: str) -> bool:
    try:
        return int(ddd) in _VALID_DDDS
    except ValueError:
        return False


def _segment_from_path(path: Path) -> str:
    stem = path.stem.lower()
    if "negativ" in stem:
        return "negativados"
    if "taxa" in stem:
        return "taxa"
    return ""


def load_leads(path: Path | str) -> list[Lead]:
    """Read one CSV export into a list of normalized Lead objects."""
    path = Path(path)
    segment = _segment_from_path(path)

    # Meta exports UTF-16 LE with a BOM; utf-16 lets Python detect endianness.
    with path.open(encoding="utf-16", newline="") as f:
        reader = csv.reader(f, delimiter="\t")
        rows = list(reader)

    if not rows:
        return []

    header = rows[0]
    field_by_index: dict[int, str] = {}
    for i, col in enumerate(header):
        field = COLUMN_MAP.get(_norm_key(col))
        if field:
            field_by_index[i] = field

    leads: list[Lead] = []
    for raw_row in rows[1:]:
        if not any(cell.strip() for cell in raw_row):
            continue
        values: dict[str, str] = {"segment": segment}
        for i, field in field_by_index.items():
            if i < len(raw_row):
                values[field] = raw_row[i].strip().strip('"')

        lead = Lead(**values)
        lead.first_name = lead.full_name.split(" ")[0] if lead.full_name else ""
        e164, valid, review = normalize_br_phone(lead.whatsapp_raw)
        lead.phone_e164, lead.phone_valid, lead.phone_needs_review = e164, valid, review
        if not valid:
            lead.notes.append(f"unparseable phone: {lead.whatsapp_raw!r}")
        elif review:
            lead.notes.append("phone 9th digit inferred — verify before sending")
        leads.append(lead)

    return leads


def load_many(paths: Iterable[Path | str]) -> list[Lead]:
    """Load and de-duplicate leads across multiple CSVs (dedupe by phone)."""
    seen: set[str] = set()
    out: list[Lead] = []
    for p in paths:
        for lead in load_leads(p):
            key = lead.phone_e164 or f"{lead.email}:{lead.full_name}"
            if key in seen:
                continue
            seen.add(key)
            out.append(lead)
    return out


def select_pilot(leads: list[Lead], n: int = 20, include_review: bool = False) -> list[Lead]:
    """Pick the first N contactable leads (valid phone) for the pilot."""
    pool = [
        lead for lead in leads
        if lead.phone_valid and (include_review or not lead.phone_needs_review)
    ]
    return pool[:n]


def default_csv_paths(root: Path | str = ".") -> list[Path]:
    return sorted(Path(root).glob("*Leads_*.csv"))


def _summarize(leads: list[Lead]) -> dict:
    return {
        "total": len(leads),
        "valid_phone": sum(1 for l in leads if l.phone_valid),
        "needs_review": sum(1 for l in leads if l.phone_needs_review),
        "unparseable": sum(1 for l in leads if not l.phone_valid),
        "by_segment": _count_by(leads, lambda l: l.segment or "?"),
    }


def _count_by(leads: list[Lead], key) -> dict[str, int]:
    out: dict[str, int] = {}
    for lead in leads:
        k = key(lead)
        out[k] = out.get(k, 0) + 1
    return out


def main(argv: Optional[list[str]] = None) -> None:
    _force_utf8_stdout()
    parser = argparse.ArgumentParser(description="Load and normalize Lumora leads.")
    parser.add_argument("paths", nargs="*", help="CSV files (default: *Leads_*.csv in cwd)")
    parser.add_argument("--pilot", type=int, default=0, help="Select first N contactable leads")
    parser.add_argument("--include-review", action="store_true", help="Include inferred-phone leads in pilot")
    parser.add_argument("--out", type=str, default="", help="Write selected leads as JSON to this path")
    args = parser.parse_args(argv)

    paths = [Path(p) for p in args.paths] or default_csv_paths()
    if not paths:
        parser.error("No CSV files found. Pass paths explicitly.")

    leads = load_many(paths)
    summary = _summarize(leads)
    print(json.dumps(summary, indent=2, ensure_ascii=False))

    selected = select_pilot(leads, args.pilot, args.include_review) if args.pilot else leads
    if args.pilot:
        print(f"\nPilot selection ({len(selected)} contactable):")
        for lead in selected:
            print(f"  {lead.phone_e164}  {lead.full_name}  - {lead.business_type}")

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps([l.model_dump() for l in selected], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"\nWrote {len(selected)} leads → {out_path}")


if __name__ == "__main__":
    main()
