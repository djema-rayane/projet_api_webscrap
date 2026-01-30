"""
Configuration de la base de données SQLite avec SQLAlchemy.
Gestion des modèles pour le stockage des avis multi-sources (Amazon, Trustpilot, Yelp).
"""

from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    Index,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, relationship, sessionmaker

# Configuration du chemin de la base de données
DB_PATH = Path(__file__).parent.parent / "data" / "avis_scraping.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# Création de l'engine SQLite
DATABASE_URL = f"sqlite:///{DB_PATH}"
engine = create_engine(DATABASE_URL, echo=False, connect_args={"check_same_thread": False})

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base déclarative
Base = declarative_base()


# ============================================================================
# MODÈLES DE DONNÉES
# ============================================================================


class SessionScraping(Base):
    """
    Table de traçabilité des sessions de scraping.
    Permet de grouper les avis par extraction et de suivre les performances.
    """

    __tablename__ = "sessions_scraping"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(255), unique=True, nullable=False, index=True)
    type_scraping = Column(String(50), nullable=False)  # 'single_product', 'multiple_products', etc.
    source = Column(String(50), nullable=False)  # 'amazon', 'trustpilot', 'yelp'
    query = Column(String(500), nullable=True)  # Requête de recherche (si applicable)
    filtre_france = Column(Boolean, default=False)
    nb_avis_demandes = Column(Integer, nullable=True)
    nb_avis_extraits = Column(Integer, nullable=False, default=0)
    nb_produits_scrapes = Column(Integer, nullable=True)
    date_extraction = Column(DateTime, nullable=False, default=datetime.now)
    duree_secondes = Column(Float, nullable=True)  # Durée du scraping
    statut = Column(String(20), default="completed")  # 'running', 'completed', 'failed', 'interrupted'
    erreur = Column(Text, nullable=True)  # Message d'erreur si échec

    # Relations
    produits = relationship("Produit", back_populates="session", cascade="all, delete-orphan")
    avis = relationship("Avis", back_populates="session", cascade="all, delete-orphan")

    # Index pour performances
    __table_args__ = (
        Index("idx_session_source", "source"),
        Index("idx_session_date", "date_extraction"),
        Index("idx_session_statut", "statut"),
    )


class Produit(Base):
    """
    Table des produits/entités scrapés.
    Gère les informations des produits Amazon ou entités Trustpilot/Yelp.
    """

    __tablename__ = "produits"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("sessions_scraping.id"), nullable=False)
    
    # Identifiants
    produit_numero = Column(Integer, nullable=True)  # Numéro dans la liste (multi-produits)
    source = Column(String(50), nullable=False)  # 'amazon', 'trustpilot', 'yelp'
    
    # Informations produit
    titre = Column(Text, nullable=False)
    marque = Column(String(200), nullable=True)
    url = Column(Text, nullable=False)
    
    # Métadonnées
    date_ajout = Column(DateTime, nullable=False, default=datetime.now)

    # Relations
    session = relationship("SessionScraping", back_populates="produits")
    avis = relationship("Avis", back_populates="produit", cascade="all, delete-orphan")

    # Index pour performances
    __table_args__ = (
        Index("idx_produit_source", "source"),
        Index("idx_produit_marque", "marque"),
        Index("idx_produit_url", "url", unique=True),  # Éviter doublons
    )


class Avis(Base):
    """
    Table centralisée des avis multi-sources.
    Stocke les avis Amazon, Trustpilot, Yelp avec analyse de sentiment.
    """

    __tablename__ = "avis"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("sessions_scraping.id"), nullable=False)
    produit_id = Column(Integer, ForeignKey("produits.id"), nullable=False)
    
    # Identifiants avis
    numero = Column(Integer, nullable=False)  # Numéro séquentiel dans le produit
    source = Column(String(50), nullable=False)  # 'amazon', 'trustpilot', 'yelp'
    
    # Informations avis
    profil = Column(String(200), nullable=True)  # Nom de l'auteur
    titre_review = Column(Text, nullable=True)
    contenu = Column(Text, nullable=False)
    
    # Notation
    etoiles = Column(String(50), nullable=True)  # Format brut (ex: "5,0 sur 5 étoiles")
    etoiles_valeur = Column(Float, nullable=True)  # Valeur numérique (0-5)
    
    # Date
    date_avis = Column(String(200), nullable=True)  # Date brute du scraping
    date_scraping = Column(DateTime, nullable=False, default=datetime.now)
    
    # ========================================================================
    # ANALYSE DE SENTIMENT (colonnes à remplir après scraping)
    # ========================================================================
    sentiment = Column(String(20), nullable=True)  # 'positif', 'neutre', 'negatif'
    score_sentiment = Column(Float, nullable=True)  # Score de confiance (0-1)
    date_analyse = Column(DateTime, nullable=True)
    
    # ========================================================================
    # GÉNÉRATION DE RÉPONSE (colonne à remplir après analyse)
    # ========================================================================
    reponse_generee = Column(Text, nullable=True)
    date_reponse = Column(DateTime, nullable=True)
    
    # Statut du traitement
    statut = Column(String(20), default="scraped")  # 'scraped', 'analyzed', 'responded'

    # Relations
    session = relationship("SessionScraping", back_populates="avis")
    produit = relationship("Produit", back_populates="avis")

    # Index pour performances
    __table_args__ = (
        Index("idx_avis_source", "source"),
        Index("idx_avis_statut", "statut"),
        Index("idx_avis_produit", "produit_id"),
        Index("idx_avis_sentiment", "sentiment"),
        Index("idx_avis_etoiles", "etoiles_valeur"),
        # Index composite pour filtrage avancé
        Index("idx_avis_produit_statut", "produit_id", "statut"),
    )


# ============================================================================
# FONCTIONS UTILITAIRES
# ============================================================================


def init_database():
    """
    Initialise la base de données en créant toutes les tables.
    À appeler au démarrage de l'application.
    """
    Base.metadata.create_all(bind=engine)
    print(f"Base de données initialisée : {DB_PATH}")


def get_db() -> Session:
    """
    Générateur de session de base de données pour les dépendances FastAPI.
    
    Usage dans FastAPI:
        @app.get("/avis")
        def get_avis(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def drop_all_tables():
    """
    DANGER : Supprime toutes les tables de la base de données.
    À utiliser uniquement en développement pour reset complet.
    """
    Base.metadata.drop_all(bind=engine)
    print("Toutes les tables ont été supprimées")


# ============================================================================
# INITIALISATION AU DÉMARRAGE
# ============================================================================

if __name__ == "__main__":
    # Pour tester le module directement
    init_database()
    print("\nStructure de la base de données :")
    print(f"  - SessionScraping : {SessionScraping.__tablename__}")
    print(f"  - Produit : {Produit.__tablename__}")
    print(f"  - Avis : {Avis.__tablename__}")
    print(f"\nFichier : {DB_PATH}")
