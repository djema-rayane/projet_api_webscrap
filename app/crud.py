"""
Module CRUD pour les opérations sur la base de données.
Gestion complète du cycle de vie des avis : insertion, lecture, mise à jour, analyse.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.database import SessionScraping, Produit, Avis


# ============================================================================
# SESSIONS DE SCRAPING
# ============================================================================


def creer_session_scraping(
    db: Session,
    task_id: str,
    type_scraping: str,
    source: str,
    query: Optional[str] = None,
    filtre_france: bool = False,
    nb_avis_demandes: Optional[int] = None,
) -> SessionScraping:
    """
    Crée une nouvelle session de scraping.
    
    Args:
        db: Session SQLAlchemy
        task_id: ID unique de la tâche (identifiant métier)
        type_scraping: Type de scraping ('single_product', 'multiple_products', 'authenticated', etc.)
        source: Source des données ('amazon', 'trustpilot', 'yelp')
        query: Requête de recherche (optionnel)
        filtre_france: Si le filtre France est activé
        nb_avis_demandes: Nombre d'avis demandés (optionnel)
    
    Returns:
        Instance SessionScraping créée
    """
    session = SessionScraping(
        task_id=task_id,  
        type_scraping=type_scraping,
        source=source,
        query=query,
        filtre_france=filtre_france,
        nb_avis_demandes=nb_avis_demandes,
        date_extraction=datetime.now(),
        statut="running",
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def get_session_by_task_id(db: Session, task_id: str) -> Optional[SessionScraping]:
    """
    Récupère une session de scraping par son task_id.
    
    Args:
        db: Session SQLAlchemy
        task_id: ID de la tâche à rechercher
    
    Returns:
        Instance SessionScraping ou None si introuvable
    """
    return db.query(SessionScraping).filter(SessionScraping.task_id == task_id).first()


def finaliser_session_scraping(
    db: Session,
    session_id: int,
    nb_avis_extraits: int,
    nb_produits_scrapes: Optional[int] = None,
    duree_secondes: Optional[float] = None,
    statut: str = "completed",
    erreur: Optional[str] = None,
) -> Optional[SessionScraping]:
    """
    Finalise une session de scraping avec les statistiques finales.

    Returns:
        Instance SessionScraping mise à jour, ou None si introuvable
    """
    session = db.query(SessionScraping).filter(SessionScraping.id == session_id).first()
    if session is None:
        return None

    session.nb_avis_extraits = nb_avis_extraits  # type: ignore[assignment]
    session.nb_produits_scrapes = nb_produits_scrapes  # type: ignore[assignment]
    session.duree_secondes = duree_secondes  # type: ignore[assignment]
    session.statut = statut  # type: ignore[assignment]
    session.erreur = erreur  # type: ignore[assignment]

    db.commit()
    db.refresh(session)
    return session


def recuperer_sessions(
    db: Session,
    source: Optional[str] = None,
    statut: Optional[str] = None,
    limite: int = 50,
) -> List[SessionScraping]:
    """
    Récupère les sessions de scraping avec filtres optionnels.
    
    Args:
        db: Session SQLAlchemy
        source: Filtrer par source ('amazon', 'trustpilot', 'yelp')
        statut: Filtrer par statut ('completed', 'failed', 'running')
        limite: Nombre maximum de résultats
    
    Returns:
        Liste des sessions correspondant aux critères
    """
    query = db.query(SessionScraping)
    
    if source:
        query = query.filter(SessionScraping.source == source)
    if statut:
        query = query.filter(SessionScraping.statut == statut)
    
    return query.order_by(SessionScraping.date_extraction.desc()).limit(limite).all()


# ============================================================================
# PRODUITS
# ============================================================================


def creer_produit(
    db: Session,
    session_id: int,
    source: str,
    titre: str,
    url: str,
    marque: Optional[str] = None,
    produit_numero: Optional[int] = None,
) -> Produit:
    """
    Crée un nouveau produit dans la base de données.
    
    Args:
        db: Session SQLAlchemy
        session_id: ID de la session de scraping parent
        source: Source ('amazon', 'trustpilot', 'yelp')
        titre: Titre du produit/entité
        url: URL du produit
        marque: Marque du produit (optionnel)
        produit_numero: Numéro séquentiel (pour multi-produits)
    
    Returns:
        Instance Produit créée
    """
    # Vérifier si le produit existe déjà (par URL)
    produit_existant = db.query(Produit).filter(Produit.url == url).first()
    if produit_existant:
        return produit_existant
    
    produit = Produit(
        session_id=session_id,
        source=source,
        titre=titre,
        url=url,
        marque=marque,
        produit_numero=produit_numero,
        date_ajout=datetime.now(),
    )
    db.add(produit)
    db.commit()
    db.refresh(produit)
    return produit


def recuperer_produits(
    db: Session,
    source: Optional[str] = None,
    marque: Optional[str] = None,
    limite: int = 100,
) -> List[Produit]:
    """
    Récupère les produits avec filtres optionnels.
    
    Args:
        db: Session SQLAlchemy
        source: Filtrer par source
        marque: Filtrer par marque
        limite: Nombre maximum de résultats
    
    Returns:
        Liste des produits correspondant aux critères
    """
    query = db.query(Produit)
    
    if source:
        query = query.filter(Produit.source == source)
    if marque:
        query = query.filter(Produit.marque.ilike(f"%{marque}%"))
    
    return query.order_by(Produit.date_ajout.desc()).limit(limite).all()


# ============================================================================
# AVIS - INSERTION EN TEMPS RÉEL PENDANT SCRAPING
# ============================================================================


def inserer_avis(
    db: Session,
    session_id: int,
    produit_id: int,
    source: str,
    numero: int,
    contenu: str,
    profil: Optional[str] = None,
    titre_review: Optional[str] = None,
    etoiles: Optional[str] = None,
    etoiles_valeur: Optional[float] = None,
    date_avis: Optional[str] = None,
) -> Avis:
    """
    Insère un avis dans la base de données en temps réel pendant le scraping.
    
    ⚡ USAGE EN BOUCLE DE SCRAPING :
    --------------------------------
    for avis_data in avis_scrapes:
        inserer_avis(db, session_id, produit_id, source, ...)
        # L'avis est immédiatement sauvegardé, pas besoin d'attendre la fin
    
    Args:
        db: Session SQLAlchemy
        session_id: ID de la session de scraping
        produit_id: ID du produit associé
        source: Source de l'avis ('amazon', 'trustpilot', 'yelp')
        numero: Numéro séquentiel de l'avis
        contenu: Texte de l'avis
        profil: Nom de l'auteur
        titre_review: Titre de l'avis
        etoiles: Format brut des étoiles
        etoiles_valeur: Valeur numérique (0-5)
        date_avis: Date brute de l'avis
    
    Returns:
        Instance Avis créée
    """
    avis = Avis(
        session_id=session_id,
        produit_id=produit_id,
        source=source,
        numero=numero,
        profil=profil,
        titre_review=titre_review,
        contenu=contenu,
        etoiles=etoiles,
        etoiles_valeur=etoiles_valeur,
        date_avis=date_avis,
        date_scraping=datetime.now(),
        statut="scraped",
    )
    db.add(avis)
    db.commit()
    db.refresh(avis)
    return avis


def inserer_avis_batch(
    db: Session,
    session_id: int,
    produit_id: int,
    source: str,
    avis_liste: List[Dict[str, Any]],
) -> int:
    """
    Insère plusieurs avis en une seule transaction (optimisation performance).
    
    Args:
        db: Session SQLAlchemy
        session_id: ID de la session de scraping
        produit_id: ID du produit associé
        source: Source des avis
        avis_liste: Liste de dictionnaires contenant les données des avis
    
    Returns:
        Nombre d'avis insérés
    
    Exemple d'utilisation:
        avis_liste = [
            {"numero": 1, "contenu": "Super produit", "etoiles_valeur": 5.0, ...},
            {"numero": 2, "contenu": "Moyen", "etoiles_valeur": 3.0, ...},
        ]
        inserer_avis_batch(db, session_id, produit_id, "amazon", avis_liste)
    """
    avis_objets = [
        Avis(
            session_id=session_id,
            produit_id=produit_id,
            source=source,
            numero=avis_data.get("numero"),
            profil=avis_data.get("profil"),
            titre_review=avis_data.get("titre_review"),
            contenu=avis_data.get("contenu"),
            etoiles=avis_data.get("etoiles"),
            etoiles_valeur=avis_data.get("etoiles_valeur"),
            date_avis=avis_data.get("date_avis"),
            date_scraping=datetime.now(),
            statut="scraped",
        )
        for avis_data in avis_liste
    ]
    
    db.bulk_save_objects(avis_objets)
    db.commit()
    return len(avis_objets)


# ============================================================================
# AVIS - RÉCUPÉRATION ET FILTRAGE
# ============================================================================


def recuperer_avis(
    db: Session,
    source: Optional[str] = None,
    statut: Optional[str] = None,
    sentiment: Optional[str] = None,
    produit_id: Optional[int] = None,
    etoiles_min: Optional[float] = None,
    etoiles_max: Optional[float] = None,
    limite: int = 100,
) -> List[Avis]:
    """
    Récupère les avis avec filtres optionnels avancés.
    
    Args:
        db: Session SQLAlchemy
        source: Filtrer par source ('amazon', 'trustpilot', 'yelp')
        statut: Filtrer par statut ('scraped', 'analyzed', 'responded')
        sentiment: Filtrer par sentiment ('positif', 'neutre', 'negatif')
        produit_id: Filtrer par ID produit
        etoiles_min: Note minimale (0-5)
        etoiles_max: Note maximale (0-5)
        limite: Nombre maximum de résultats
    
    Returns:
        Liste des avis correspondant aux critères
    """
    query = db.query(Avis)
    
    if source:
        query = query.filter(Avis.source == source)
    if statut:
        query = query.filter(Avis.statut == statut)
    if sentiment:
        query = query.filter(Avis.sentiment == sentiment)
    if produit_id:
        query = query.filter(Avis.produit_id == produit_id)
    if etoiles_min is not None:
        query = query.filter(Avis.etoiles_valeur >= etoiles_min)
    if etoiles_max is not None:
        query = query.filter(Avis.etoiles_valeur <= etoiles_max)
    
    return query.order_by(Avis.date_scraping.desc()).limit(limite).all()


def recuperer_avis_non_analyses(db: Session, limite: int = 100) -> List[Avis]:
    """
    Récupère TOUS les avis qui n'ont pas encore été analysés (sentiment NULL).
    
    Utile pour traiter les avis en batch après scraping.
    
    Args:
        db: Session SQLAlchemy
        limite: Nombre maximum d'avis à traiter
    
    Returns:
        Liste des avis à analyser
    """
    return (
        db.query(Avis)
        .filter(Avis.sentiment.is_(None))
        .order_by(Avis.date_scraping.asc())
        .limit(limite)
        .all()
    )


def get_avis_non_analyses_by_task_id(db: Session, task_id: str) -> List[Avis]:
    """
    Récupère les avis non analysés d'une session spécifique (via task_id).
    
    Args:
        db: Session SQLAlchemy
        task_id: ID de la tâche de scraping
    
    Returns:
        Liste des avis à analyser pour cette session
    """
    return (
        db.query(Avis)
        .join(SessionScraping, Avis.session_id == SessionScraping.id)
        .filter(SessionScraping.task_id == task_id)
        .filter(Avis.sentiment.is_(None))
        .order_by(Avis.date_scraping.asc())
        .all()
    )


def recuperer_avis_sans_reponse(db: Session, limite: int = 100) -> List[Avis]:
    """
    Récupère TOUS les avis analysés mais sans réponse générée.
    
    Args:
        db: Session SQLAlchemy
        limite: Nombre maximum d'avis à traiter
    
    Returns:
        Liste des avis nécessitant une réponse
    """
    return (
        db.query(Avis)
        .filter(and_(Avis.sentiment.isnot(None), Avis.reponse_generee.is_(None)))
        .order_by(Avis.date_analyse.asc())
        .limit(limite)
        .all()
    )


def get_avis_sans_reponse_by_task_id(db: Session, task_id: str) -> List[Avis]:
    """
    Récupère les avis sans réponse d'une session spécifique (via task_id).
    
    Args:
        db: Session SQLAlchemy
        task_id: ID de la tâche de scraping
    
    Returns:
        Liste des avis nécessitant une réponse pour cette session
    """
    return (
        db.query(Avis)
        .join(SessionScraping, Avis.session_id == SessionScraping.id)
        .filter(SessionScraping.task_id == task_id)
        .filter(Avis.sentiment.isnot(None))
        .filter(Avis.reponse_generee.is_(None))
        .order_by(Avis.date_analyse.asc())
        .all()
    )


# ============================================================================
# AVIS - MISE À JOUR APRÈS ANALYSE
# ============================================================================


def mettre_a_jour_sentiment(
    db: Session,
    avis_id: int,
    sentiment: str,
    score_sentiment: float,
) -> Optional[Avis]:  # Changé de Avis à Optional[Avis]
    """
    Met à jour l'analyse de sentiment d'un avis.
    
    Args:
        db: Session SQLAlchemy
        avis_id: ID de l'avis
        sentiment: Sentiment détecté ('positif', 'neutre', 'negatif')
        score_sentiment: Score de confiance (0-1)
    
    Returns:
        Instance Avis mise à jour ou None si introuvable
    """
    avis = db.query(Avis).filter(Avis.id == avis_id).first()
    if avis:
        avis.sentiment = sentiment  # type: ignore[assignment]
        avis.score_sentiment = score_sentiment  # type: ignore[assignment]
        avis.date_analyse = datetime.now()  # type: ignore[assignment]
        avis.statut = "analyzed"  # type: ignore[assignment]
        db.commit()
        db.refresh(avis)
    return avis


def mettre_a_jour_reponse(
    db: Session,
    avis_id: int,
    reponse_generee: str,
) -> Optional[Avis]:  # Changé de Avis à Optional[Avis]
    """
    Met à jour la réponse générée pour un avis.
    
    Args:
        db: Session SQLAlchemy
        avis_id: ID de l'avis
        reponse_generee: Texte de la réponse générée
    
    Returns:
        Instance Avis mise à jour ou None si introuvable
    """
    avis = db.query(Avis).filter(Avis.id == avis_id).first()
    if avis:
        avis.reponse_generee = reponse_generee  # type: ignore[assignment]
        avis.date_reponse = datetime.now()  # type: ignore[assignment]
        avis.statut = "responded"  # type: ignore[assignment]
        db.commit()
        db.refresh(avis)
    return avis