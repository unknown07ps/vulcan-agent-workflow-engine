from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    anthropic_api_key: str = ""
    llm_model: str = "claude-sonnet-4-6"
    llm_provider: str = "anthropic"

    redis_url: str = "redis://localhost:6379/0"

    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"

    max_critic_revisions: int = 2

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
