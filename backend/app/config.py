try:
    from pydantic_settings import BaseSettings
except ImportError:  # pragma: no cover
    from pydantic import BaseSettings


class Settings(BaseSettings):
    database_url: str = 'postgresql://postgres:postgres@localhost:5432/secret_game'
    resend_api_key: str = ''
    resend_from_email: str = 'game@refixion.nl'
    admin_password: str = 'change-me'
    backend_url: str = 'http://localhost:8000'
    frontend_url: str = 'http://localhost:5173'
    app_name: str = 'Secret Game'

    class Config:
        env_file = '.env'
        case_sensitive = False


settings = Settings()
