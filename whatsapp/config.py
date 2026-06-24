"""Configuration for the WhatsApp Cloud API integration.

All secrets are read from environment variables (or a local `.env` file).
See `.env.example` for the full list and `docs/SETUP_WHATSAPP.md` for how to
obtain each value from the Meta Developer console.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class WhatsAppSettings(BaseSettings):
    """Meta WhatsApp Cloud API credentials and local storage paths.

    Importing this module never raises even when the env is empty — fields
    default to empty strings so the extractor and tests can run without
    credentials. Call `is_configured()` before attempting to send/receive.
    """

    model_config = SettingsConfigDict(
        env_prefix="WHATSAPP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Credentials (Meta Developer console → WhatsApp → API Setup) ---
    token: str = Field(default="", description="Permanent system-user access token")
    phone_number_id: str = Field(default="", description="Sending phone number ID")
    business_account_id: str = Field(default="", description="WhatsApp Business Account (WABA) ID")

    # --- Webhook ---
    verify_token: str = Field(default="", description="Arbitrary string we choose; echoed back during webhook verification")
    app_secret: str = Field(default="", description="Meta App secret, used to validate X-Hub-Signature-256")

    # --- API version ---
    graph_api_version: str = Field(default="v21.0")

    # --- Local storage ---
    data_dir: Path = Field(default=Path("data"))

    @property
    def base_url(self) -> str:
        return f"https://graph.facebook.com/{self.graph_api_version}"

    @property
    def messages_url(self) -> str:
        return f"{self.base_url}/{self.phone_number_id}/messages"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "messages.db"

    @property
    def media_dir(self) -> Path:
        return self.data_dir / "media"

    def is_configured(self) -> bool:
        """True only when the minimum required to send/receive is present."""
        return bool(self.token and self.phone_number_id and self.verify_token)


_settings: WhatsAppSettings | None = None


def get_settings() -> WhatsAppSettings:
    """Cached settings singleton."""
    global _settings
    if _settings is None:
        _settings = WhatsAppSettings()
    return _settings
