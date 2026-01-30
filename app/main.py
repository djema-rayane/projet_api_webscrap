from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.api.routes import scraping, tasks, health, analysis

from app.database import init_database

# Créer l'application
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="BOT - Réponse automatique aux avis clients",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup_event():
    """Initialiser la base de données au démarrage de l'application."""
    init_database()
    print("Base de données SQLite initialisée")

# Inclure les routes
app.include_router(health.router)
app.include_router(scraping.router)
app.include_router(tasks.router)
app.include_router(analysis.router)
