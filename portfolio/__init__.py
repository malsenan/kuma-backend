"""Business portfolio builder: WhatsApp intake → structured BusinessPortfolio."""

from portfolio.builder import build_portfolio
from portfolio.models import BusinessPortfolio

__all__ = ["BusinessPortfolio", "build_portfolio"]
