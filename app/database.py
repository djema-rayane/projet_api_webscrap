"""
Configuration de la base de données SQLite avec SQLAlchemy.
Gestion des modèles pour le stockage des avis multi-sources (Amazon, Trustpilot, Yelp).
"""

from datetime import datetime
from pathlib import Path
from typing import Generator

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
from sqlalchemy.orm import (
    DeclarativeBase,
    Session,
    relationship,
    sessionmaker,
)

# ============================================================================
# CONFIGURATION BASE DE DONNÉES
# ============================================================================

DB_PATH = Path(__file__).parent.parent / "data" / "avis_scraping.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

DATABASE_URL = f"sqlite:///{DB_PATH}"
engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

# ============================================================================
# BASE DÉCLARATIVE (SQLAlchemy 2.0 friendly + mypy compliant)
# ============================================================================

class Base(DeclarativeBase):
    pass


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
    type_scraping = Column(String(50), nullable=False)
    source = Column(String(50), nullable=False)
    query = Column(String(500), nullable=True)
    filtre_france = Column(Boolean, default=False)
    nb_avis_demandes = Column(Integer, nullable=True)
    nb_avis_extraits = Column(Integer, nullable=False, default=0)
    nb_produits_scrapes = Column(Integer, nullable=True)
    date_extraction = Column(DateTime, nullable=False, default=datetime.now)
    duree_secondes = Column(Float, nullable=True)
    statut = Column(String(20), default="completed")
    erreur = Column(Text, nullable=True)

    produits = relationship(
        "Produit",
        back_populates="session",
        cascade="all, delete-orphan",
    )
    avis = relationship(
        "Avis",
        back_populates="session",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_session_source", "source"),
        Index("idx_session_date", "date_extraction"),
        Index("idx_session_statut", "statut"),
    )


class Produit(Base):
    """
    Table des produits/entités scrapés.
    """

    __tablename__ = "produits"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("sessions_scraping.id"), nullable=False)

    produit_numero = Column(Integer, nullable=True)
    source = Column(String(50), nullable=False)

    titre = Column(Text, nullable=False)
    marque = Column(String(200), nullable=True)
    url = Column(Text, nullable=False)

    date_ajout = Column(DateTime, nullable=False, default=datetime.now)

    session = relationship("SessionScraping", back_populates="produits")
    avis = relationship(
        "Avis",
        back_populates="produit",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_produit_source", "source"),
        Index("idx_produit_marque", "marque"),
        Index("idx_produit_url", "url", unique=True),
    )


class Avis(Base):
    """
    Table centralisée des avis multi-sources.
    """

    __tablename__ = "avis"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("sessions_scraping.id"), nullable=False)
    produit_id = Column(Integer, ForeignKey("produits.id"), nullable=False)

    numero = Column(Integer, nullable=False)
    source = Column(String(50), nullable=False)

    profil = Column(String(200), nullable=True)
    titre_review = Column(Text, nullable=True)
    contenu = Column(Text, nullable=False)

    etoiles = Column(String(50), nullable=True)
    etoiles_valeur = Column(Float, nullable=True)

    date_avis = Column(String(200), nullable=True)
    date_scraping = Column(DateTime, nullable=False, default=datetime.now)

    sentiment = Column(String(20), nullable=True)
    score_sentiment = Column(Float, nullable=True)
    date_analyse = Column(DateTime, nullable=True)

    reponse_generee = Column(Text, nullable=True)
    date_reponse = Column(DateTime, nullable=True)

    statut = Column(String(20), default="scraped")

    session = relationship("SessionScraping", back_populates="avis")
    produit = relationship("Produit", back_populates="avis")

    __table_args__ = (
        Index("idx_avis_source", "source"),
        Index("idx_avis_statut", "statut"),
        Index("idx_avis_produit", "produit_id"),
        Index("idx_avis_sentiment", "sentiment"),
        Index("idx_avis_etoiles", "etoiles_valeur"),
        Index("idx_avis_produit_statut", "produit_id", "statut"),
    )


# ============================================================================
# FONCTIONS UTILITAIRES
# ============================================================================

def init_database() -> None:
    """
    Initialise la base de données en créant toutes les tables.
    """
    Base.metadata.create_all(bind=engine)
    print(f"Base de données initialisée : {DB_PATH}")


def get_db() -> Generator[Session, None, None]:
    """
    Générateur de session de base de données pour FastAPI.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def drop_all_tables() -> None:
    """
    Supprime toutes les tables (DÉVELOPPEMENT UNIQUEMENT).
    """
    Base.metadata.drop_all(bind=engine)
    print("Toutes les tables ont été supprimées")


# ============================================================================
# TEST LOCAL
# ============================================================================

if __name__ == "__main__":
    init_database()
    print("\nStructure de la base de données :")
    print(f"  - SessionScraping : {SessionScraping.__tablename__}")
    print(f"  - Produit : {Produit.__tablename__}")
    print(f"  - Avis : {Avis.__tablename__}")
    print(f"\nFichier : {DB_PATH}")
