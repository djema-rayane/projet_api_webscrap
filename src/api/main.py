from fastapi import FastAPI
from src.api.routes import router

app = FastAPI(
    title="Avis API",
    description="API pour analyser les avis clients et générer des réponses.",
    version="1.0.0"
)

app.include_router(router)
