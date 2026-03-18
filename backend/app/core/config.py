from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    PROJECT_NAME: str = "Plan Code Resolver"
    SERVICE_NAME: str = "plan-code-resolver"
    VERSION: str = "1.0.0"
    DATA_FILE: str = "/app/data/plancode_mappings.xlsx"
    CORS_ORIGINS: list[str] = ["*"]

    class Config:
        env_file = ".env"


settings = Settings()
