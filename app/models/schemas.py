from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict, Literal
from enum import Enum


class ScrapeMode(str, Enum):
    """Mode de scraping"""
    SEARCH = "search"  # Recherche multi-produits
    URL = "url"        # Produit unique par URL


class ScrapeRequest(BaseModel):
    """Requête de scraping (supporte 2 modes)"""
    
    # Mode de scraping
    mode: ScrapeMode = Field(
        default=ScrapeMode.SEARCH,
        description="Mode: 'search' pour recherche multi-produits, 'url' pour produit unique"
    )
    
    # Paramètres MODE SEARCH
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
    
    # Paramètres MODE URL
    product_url: Optional[str] = Field(
        default=None,
        description="[MODE URL] URL du produit Amazon (ex: https://www.amazon.fr/dp/B0F1FSGNLT)"
    )
    
    # Paramètres communs
    france_only: bool = Field(
        default=True,
        description="Filtrer uniquement les avis français"
    )
    limit_per_product: Optional[int] = Field(
        default=None,
        ge=1,
        description="Limite d'avis par produit (None = tous)"
    )
    headless: bool = Field(
        default=True,
        description="Mode headless (sans interface graphique)"
    )
    
    @field_validator('query')
    def validate_query_for_search_mode(cls, v, info):
        """Valider que query est présent en mode SEARCH"""
        if info.data.get('mode') == ScrapeMode.SEARCH and not v:
            raise ValueError("Le paramètre 'query' est requis en mode SEARCH")
        return v
    
    @field_validator('product_url')
    def validate_url_for_url_mode(cls, v, info):
        """Valider que product_url est présent en mode URL"""
        if info.data.get('mode') == ScrapeMode.URL and not v:
            raise ValueError("Le paramètre 'product_url' est requis en mode URL")
        if v and not v.startswith('http'):
            raise ValueError("L'URL doit commencer par http:// ou https://")
        return v
    
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
                }
            ]
        }


class ScrapeResponse(BaseModel):
    """Réponse lors du lancement d'un scraping"""
    task_id: str
    status: str
    message: str
    mode: str


class TaskStatus(BaseModel):
    """Statut d'une tâche de scraping"""
    task_id: str
    status: str
    progress: Optional[str] = None
    result_file: Optional[str] = None
    error: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class TasksList(BaseModel):
    """Liste de toutes les tâches"""
    total: int
    tasks: Dict[str, TaskStatus]


class HealthResponse(BaseModel):
    """Réponse health check"""
    status: str
    timestamp: str
    active_tasks: int
    total_tasks: int