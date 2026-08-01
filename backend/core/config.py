from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):

    model_config=SettingsConfigDict(
         env_file=".env",
         env_file_encoding="utf-8",
         case_sensitive=False,
    )

    # Slack
    slack_bot_token:str
    slack_signing_secret:str 
    slack_app_token:str 

    # Google Calendar
    google_client_id: str
    google_client_secret: str
    google_redirect_uri: str

    # Redis
    redis_url: str

    environment: str = "development" 
    app_port: int = 8000
    log_level: str = "INFO"

    # AWS
    aws_region: str = "us-east-1"

    # AgentCore
    callback_url: str  # ← add this


settings = Settings()