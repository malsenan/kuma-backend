"""Tests for the business portfolio builder."""

from __future__ import annotations

from portfolio.builder import _parse_brl, build_portfolio

from tests.conftest import button_msg, image_msg, text_msg


def _run_full_flow(engine, wa):
    engine.handle(text_msg(wa, "oi", "p1"))
    engine.handle(button_msg(wa, "consent_yes", "Sim", "p2"))
    engine.handle(text_msg(wa, "Vendo marmitas e bolos caseiros", "p3"))
    engine.handle(button_msg(wa, "time_1to3", "1 a 3 anos", "p4"))
    engine.handle(image_msg(wa, "doc1", "p5"))
    engine.handle(button_msg(wa, "docs_done", "Já enviei", "p6"))
    engine.handle(image_msg(wa, "photo1", "p7"))
    engine.handle(button_msg(wa, "photos_done", "Já enviei", "p8"))
    engine.handle(button_msg(wa, "rev_2to5k", "R$2 a 5 mil", "p9"))
    engine.handle(text_msg(wa, "Preciso de R$1.500 para comprar estoque", "p10"))


def test_build_portfolio_from_conversation(engine, store):
    wa = "5511999992222"
    _run_full_flow(engine, wa)

    pf = build_portfolio(wa, store)

    assert pf.portfolio_id == f"pf_{wa}"
    assert pf.owner.full_name == "Maria Silva"
    assert pf.business.description == "Vendo marmitas e bolos caseiros"
    assert pf.business.months_active == 24                  # inferred from time_1to3
    assert pf.financials.monthly_revenue_band == "rev_2to5k"
    assert pf.financials.monthly_revenue_brl == 3500.0      # band midpoint
    assert pf.credit_need.amount_requested_brl == 1500.0
    assert "estoque" in pf.credit_need.purpose

    assert len(pf.documents) == 1                           # one doc-step upload
    assert len(pf.photos) == 1                              # one photo-step upload
    assert pf.documents[0].file_path                        # has a saved path

    assert pf.completeness.has_business_description
    assert pf.completeness.has_documents
    assert pf.completeness.has_photos
    assert pf.completeness.fraction >= 0.6
    assert pf.status == "complete"


def test_build_portfolio_sparse(engine, store):
    wa = "5511999993333"
    engine.handle(text_msg(wa, "oi", "q1"))
    engine.handle(button_msg(wa, "consent_yes", "Sim", "q2"))
    engine.handle(text_msg(wa, "Costura", "q3"))
    # user stops here

    pf = build_portfolio(wa, store)
    assert pf.business.description == "Costura"
    assert pf.documents == []
    assert pf.photos == []
    assert "no documents received" in pf.review_flags
    assert pf.status == "draft"


def test_claude_stub_flags_review(engine, store):
    wa = "5511999994444"
    _run_full_flow(engine, wa)
    pf = build_portfolio(wa, store, use_claude=True)
    assert any("stub" in f for f in pf.review_flags)


def test_parse_brl():
    assert _parse_brl("R$1.500 para estoque") == 1500.0
    assert _parse_brl("preciso de 800") == 800.0
    assert _parse_brl("R$ 2.000,50") == 2000.50
    assert _parse_brl("sem valor") is None
