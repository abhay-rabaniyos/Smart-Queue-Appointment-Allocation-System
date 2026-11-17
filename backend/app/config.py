from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="config.properties", extra="ignore")
    database_url: str = "sqlite:///./queuepilot.db"
    cors_origins: list[str] = ["http://localhost:5173"]
    public_url: str = "http://localhost:5173"
    cookie_secure: bool = False
    organization_id: str = "main"
    organization_name: str = "QueuePilot Central"
    timezone: str = "Asia/Kolkata"
    admin_email: str = "admin@example.com"
    admin_password: str = ""
    notification_mode: str = "console"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "queuepilot@example.com"
    notification_webhook_url: str = ""
    notification_webhook_token: str = ""
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_sms_from: str = ""
    twilio_whatsapp_from: str = ""
    twilio_whatsapp_content_sid: str = ""


settings = Settings()
