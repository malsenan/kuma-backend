"""Lead ingestion: read Meta lead-ad CSV exports into normalized Lead objects."""

from leads.extract import (
    load_leads,
    load_many,
    normalize_br_phone,
    select_pilot,
)
from leads.models import Lead

__all__ = ["Lead", "load_leads", "load_many", "normalize_br_phone", "select_pilot"]
