from pydantic import BaseSettings

class Settings(BaseSettings):
    database_url: str
    resend_api_key: str
    admin_password: str
    backend_url: str = 'http://localhost:8000'

    class Config:
        env_file = '.env'

settings = Settings()
