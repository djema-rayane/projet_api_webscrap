# app/models/schemas.py

from enum import Enum
from typing import Dict, Optional

from pydantic import BaseModel, Field, model_validator


# =========================================================
# Scraping
# =========================================================

class ScrapeMode(str, Enum):
    SEARCH = "search"
    URL = "url"
    URL_AUTH = "url_auth"


class ScrapeRequest(BaseModel):
    """
    Requête de scraping
    - search : recherche multi-produits
    - url : un produit via URL
    - url_auth : un produit via URL + login (username/password uniquement)
    """

    mode: ScrapeMode = Field(
        default=ScrapeMode.SEARCH,
        description="Mode: 'search', 'url', 'url_auth'"
    )

    # MODE SEARCH
    query: Optional[str] = Field(
        default=None,
        description="[MODE SEARCH] Terme de recherche (ex: 'écran pc')"
    )
    nb_products: Optional[int] = Field(
        default=10,
        ge=1,
        le=100,
        description="[MODE SEARCH] Nombre de produits à scraper"
    )

    # MODE URL / URL_AUTH
    product_url: Optional[str] = Field(
        default=None,
        description="[MODE URL/URL_AUTH] URL du produit Amazon"
    )

    # MODE URL_AUTH (login obligatoire)
    username: Optional[str] = Field(
        default=None,
        description="[MODE URL_AUTH] Identifiant de connexion"
    )
    password: Optional[str] = Field(
        default=None,
        description="[MODE URL_AUTH] Mot de passe"
    )
    cookies_only: bool = Field(
    default=False,
    description="[MODE URL_AUTH] Si True: utilise uniquement les cookies (pas de login manuel, même si username/password sont fournis)"
    )
    # Communs
    france_only: bool = Field(default=True, description="Filtrer uniquement les avis français")
    limit_per_product: Optional[int] = Field(default=None, ge=1, description="Limite d'avis par produit (None = tous)")
    headless: bool = Field(default=True, description="Mode headless")

    @model_validator(mode="after")
    def validate_by_mode(self):
        if self.mode == ScrapeMode.SEARCH:
            if not self.query:
                raise ValueError("Le paramètre 'query' est requis en mode SEARCH")

        if self.mode == ScrapeMode.URL:
            if not self.product_url:
                raise ValueError("Le paramètre 'product_url' est requis en mode URL")

        if self.mode == ScrapeMode.URL_AUTH:
            if not self.product_url:
                raise ValueError("Le paramètre 'product_url' est requis en mode URL_AUTH")

            # Si cookies_only=True, username/password deviennent optionnels
            if not self.cookies_only and not (self.username and self.password):
                raise ValueError("En mode URL_AUTH, fournissez 'username' et 'password' (ou activez cookies_only=True)")


        if self.product_url and not self.product_url.startswith("http"):
            raise ValueError("L'URL doit commencer par http:// ou https://")

        return self

    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "mode": "search",
                    "query": "écran pc",
                    "nb_products": 10,
                    "france_only": True,
                    "limit_per_product": 5,
                    "headless": True
                },
                {
                    "mode": "url",
                    "product_url": "https://www.amazon.fr/dp/B0F1FSGNLT",
                    "france_only": True,
                    "limit_per_product": 50,
                    "headless": True
                },
                {
                    "mode": "url_auth",
                    "product_url": "https://www.amazon.fr/dp/B0F1FSGNLT",
                    "username": "email@example.com",
                    "password": "motdepasse",
                    "france_only": True,
                    "limit_per_product": 50,
                    "headless": False
                }
            ]
        }


class ScrapeResponse(BaseModel):
    """Réponse lors du lancement d'un scraping"""
    task_id: str
    status: str
    message: str
    mode: str


# =========================================================
# Tasks
# =========================================================

class TaskStatus(BaseModel):
    task_id: str
    status: str
    progress: Optional[str] = None
    result_file: Optional[str] = None
    error: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class TasksList(BaseModel):
    total: int
    tasks: Dict[str, TaskStatus]


# =========================================================
# Health
# =========================================================

class HealthResponse(BaseModel):
    status: str
    timestamp: str
    active_tasks: int
    total_tasks: int


# =========================================================
# Analysis (sentiment + replies)
# =========================================================

class AnalysisRequest(BaseModel):
    scrape_task_id: str = Field(..., description="ID de la tâche de scraping terminée")
    use_gpu: bool = Field(default=True, description="Utiliser GPU si dispo")
    output_csv: bool = Field(default=True, description="Générer un CSV")
    output_json: bool = Field(default=False, description="Générer aussi un JSON enrichi")


class AnalysisResponse(BaseModel):
    analysis_task_id: str
    status: str
    message: str


class AnalysisTaskStatus(BaseModel):
    task_id: str
    source_scrape_task_id: str
    status: str
    progress: Optional[str] = None
    result_file: Optional[str] = None
    error: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


# =========================================================
# Reply one
# =========================================================

class ReplyOneRequest(BaseModel):
    scrape_task_id: str = Field(..., description="ID de la tâche de scraping terminée")
    product_index: int = Field(default=1, ge=1, description="Produit ciblé (1 si single_product)")
    review_numero: int = Field(..., ge=1, description="Numéro de l'avis dans le JSON (champ 'numero')")
    use_gpu: bool = True


class ReplyOneResponse(BaseModel):
    scrape_task_id: str
    product_index: int
    review_numero: int
    sentiment: str
    reply: str
