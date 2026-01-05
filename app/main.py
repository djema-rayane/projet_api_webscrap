from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.api.routes import scraping, tasks, health, analysis

# Créer l'application
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="API pour scraper les avis Amazon",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inclure les routes
app.include_router(health.router)
app.include_router(scraping.router)
app.include_router(tasks.router)
app.include_router(analysis.router)
