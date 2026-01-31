from pydantic_settings import BaseSettings
from pathlib import Path

class Settings(BaseSettings):
    app_name: str = "Review Scraper API"
    app_version: str = "2.0.0"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    
    results_dir: str = "results"
    selenium_profile_dir: str = "results/selenium_profiles/amazon"
    default_wait_seconds: int = 15
    max_products_per_request: int = 100
    
    cors_origins: list = ["*"]
    log_level: str = "info"
    
    class Config:
        env_file = ".env"
        case_sensitive = False

settings = Settings()
Path(settings.results_dir).mkdir(parents=True, exist_ok=True)
Path(settings.selenium_profile_dir).mkdir(parents=True, exist_ok=True)