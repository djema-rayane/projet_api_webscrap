from pydantic_settings import BaseSettings
import os

class Settings(BaseSettings):
    app_name: str = "Amazon Review Scraper API"
    app_version: str = "2.0.0"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    
    results_dir: str = "results"
    selenium_profile_dir: str = "~/.selenium_profiles/amazon"
    default_wait_seconds: int = 15
    max_products_per_request: int = 100
    
    cors_origins: list = ["*"]
    log_level: str = "info"
    
    class Config:
        env_file = ".env"
        case_sensitive = False

settings = Settings()
os.makedirs(settings.results_dir, exist_ok=True)