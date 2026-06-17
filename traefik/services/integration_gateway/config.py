from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    host: str = "0.0.0.0"
    port: int = 8001
    log_level: str = "info"

    # Odoo JSON-RPC target
    odoo_url: str = "http://odoo:8069"
    odoo_db: str = "odoo"
    odoo_admin_user: str = "admin"
    odoo_admin_password: str = "admin"

    # WhatsApp / Meta
    whatsapp_app_secret: str = ""         # used to verify X-Hub-Signature-256

    # Twilio
    twilio_auth_token: str = ""           # used to verify Twilio request signatures

    # Bank import shared secret (POST from bank adapter scripts)
    bank_import_secret: str = ""


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
