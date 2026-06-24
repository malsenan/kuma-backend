"""Tests for lead loading and Brazilian phone normalization."""

from pathlib import Path

import pytest

from leads.extract import default_csv_paths, load_leads, load_many, normalize_br_phone, select_pilot


@pytest.mark.parametrize(
    "raw, expected_e164, valid, review",
    [
        ("+5588992444155", "+5588992444155", True, False),   # already E.164
        ("19993745240", "+5519993745240", True, False),       # missing +55
        ("+55 (62) 98228-9422", "+5562982289422", True, False),  # punctuation
        ("+558197974282", "+5581997974282", True, True),      # 8-digit local → infer 9th
        ("(82) 99821310", "+5582999821310", True, True),      # no country code, 8-digit local
        ("", "", False, False),                               # empty
        ("123", "", False, False),                            # too short
        ("5511999999999999", "", False, False),               # too many digits
    ],
)
def test_normalize_br_phone(raw, expected_e164, valid, review):
    e164, is_valid, needs_review = normalize_br_phone(raw)
    assert is_valid == valid
    if valid:
        assert e164 == expected_e164
        assert needs_review == review
    else:
        assert e164 == ""


def test_normalize_rejects_unknown_ddd():
    # DDD 00 is not a valid Brazilian area code.
    e164, valid, _ = normalize_br_phone("0099821310")
    assert not valid and e164 == ""


def test_load_real_csvs_if_present():
    paths = default_csv_paths(".")
    if not paths:
        pytest.skip("lead CSVs not present in repo root")
    leads = load_many(paths)
    assert len(leads) > 0
    # Every lead should at least have a name or a phone parsed.
    assert any(l.phone_valid for l in leads)
    # Segment is derived from the filename.
    assert {l.segment for l in leads} & {"negativados", "taxa"}


def test_select_pilot_excludes_review_by_default():
    paths = default_csv_paths(".")
    if not paths:
        pytest.skip("lead CSVs not present in repo root")
    leads = load_many(paths)
    pilot = select_pilot(leads, n=20)
    assert len(pilot) <= 20
    assert all(l.phone_valid and not l.phone_needs_review for l in pilot)
