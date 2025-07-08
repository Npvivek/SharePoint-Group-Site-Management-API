from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    tenant_id:     str
    client_id:     str
    client_secret: str
    class Config:
        env_prefix = ""
        env_file   = ".env"

settings = Settings()
