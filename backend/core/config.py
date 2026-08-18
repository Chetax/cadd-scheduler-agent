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
    test_slack_user_id: str
    test_slack_team_id: str

    # Redis
    redis_url: str

    environment: str = "development" 
    app_port: int = 8000
    log_level: str = "INFO"

    # AWS
    aws_region: str = "us-east-1"
    bedrock_model_id:str 
    use_agent: bool = False
    
    

    # AgentCore
    callback_url: str  
    agentcore_oauth_provider_arn: str

    table_name:str
    table_endpoint_url:str



settings = Settings()